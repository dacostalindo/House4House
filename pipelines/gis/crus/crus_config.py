"""
CRUS WFS Ingestion Configuration

Data source: DGTERRITÓRIO CRUS (Carta do Regime de Uso do Solo)
Nationally standardized land-use classification extracted from each
municipality's active PDM, served via OGC WFS endpoints.

WFS URL pattern:
  https://servicos.dgterritorio.pt/SDISNITWFSCRUS_{code}_1/WFService.aspx

Confirmed municipalities: Aveiro, Lisboa, Porto, Coimbra, Leiria
(plus many others in the Aveiro distrito — Águeda, Estarreja, Ílhavo, etc.)
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote

# ---------------------------------------------------------------------------
# CRUS WFS endpoint configuration
# ---------------------------------------------------------------------------

CRUS_WFS_URL_TEMPLATE = (
    "https://servicos.dgterritorio.pt/SDISNITWFSCRUS_{code}_1/WFService.aspx"
)

WFS_VERSION = "2.0.0"
WFS_OUTPUT_FORMAT = "application/vnd.geo+json"

# DGTERRITÓRIO's WFS does not support STARTINDEX pagination (always returns
# the same features). All municipalities have <2,000 features so we fetch
# everything in a single request by omitting COUNT.


@dataclass(frozen=True)
class CRUSMunicipalityConfig:
    """Configuration for a single municipality's CRUS WFS endpoint."""

    code: str  # 4-digit DTCC code, e.g. "0105"
    name: str  # e.g. "Aveiro"
    feature_type: str  # e.g. "gmgml:CRUS_Aveiro_V"

    @property
    def wfs_url(self) -> str:
        return CRUS_WFS_URL_TEMPLATE.format(code=self.code)

    def get_capabilities_url(self) -> str:
        return (
            f"{self.wfs_url}?SERVICE=WFS&VERSION={WFS_VERSION}"
            f"&REQUEST=GetCapabilities"
        )

    def get_feature_url(self) -> str:
        """Build WFS GetFeature URL that returns ALL features as GeoJSON."""
        fmt = quote(WFS_OUTPUT_FORMAT, safe="")
        return (
            f"{self.wfs_url}?SERVICE=WFS&VERSION={WFS_VERSION}"
            f"&REQUEST=GetFeature"
            f"&TYPENAMES={self.feature_type}"
            f"&OUTPUTFORMAT={fmt}"
        )

    @property
    def name_lower(self) -> str:
        nfkd = unicodedata.normalize("NFKD", self.name)
        return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# ---------------------------------------------------------------------------
# Municipality registry
# ---------------------------------------------------------------------------

MUNICIPALITIES: list[CRUSMunicipalityConfig] = [
    CRUSMunicipalityConfig("0105", "Aveiro", "gmgml:CRUS_Aveiro_V"),
    CRUSMunicipalityConfig("1106", "Lisboa", "gmgml:CRUS_Lisboa_V"),
    CRUSMunicipalityConfig("1312", "Porto", "gmgml:CRUS_Porto_V"),
    CRUSMunicipalityConfig("0603", "Coimbra", "gmgml:CRUS_Coimbra_V"),
    CRUSMunicipalityConfig("1009", "Leiria", "gmgml:CRUS_Leiria_V"),
]

MUNICIPALITY_BY_CODE: dict[str, CRUSMunicipalityConfig] = {
    m.code: m for m in MUNICIPALITIES
}

# ---------------------------------------------------------------------------
# Field normalization
# ---------------------------------------------------------------------------
# WFS responses use accented field names (Designação, Data_PublicçãoPDM) that
# vary across municipalities. We strip diacritics from ALL field names and
# apply explicit renames (Porto's ID1 → ID) to guarantee a consistent schema.


def normalize_field_name(name: str) -> str:
    """Strip diacritics and apply explicit renames to a WFS field name.

    >>> normalize_field_name("Designação_PlantaOrdenamento")
    'Designacao_PlantaOrdenamento'
    >>> normalize_field_name("Data_PublicçãoPDM")
    'Data_PublicacaoPDM'
    >>> normalize_field_name("ID1")
    'ID'
    """
    # Strip diacritics (ç→c, ã→a, etc.)
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Explicit renames
    return _EXPLICIT_RENAMES.get(ascii_name, ascii_name)


_EXPLICIT_RENAMES: dict[str, str] = {
    "ID1": "ID",  # Porto uses ID1 instead of ID
    # Aveiro's "Data_PublicçãoPDM" accent-strips to "Data_PubliccaoPDM" (double-c
    # because ç→c leaves the preceding c intact). Canonical form is single-c.
    "Data_PubliccaoPDM": "Data_PublicacaoPDM",
}

NORMALIZED_FIELDS: set[str] = {
    "ID",
    "DTCC",
    "Municipio",
    "Classe",
    "Categoria",
    "Area_Ha",
    "Designacao_PlantaOrdenamento",
    "Escala_PlantaOrdenamento",
    "Data_PublicacaoPDM",
    "Fonte",
    "Autor",
}

# ---------------------------------------------------------------------------
# MinIO storage
# ---------------------------------------------------------------------------

MINIO_BUCKET = "raw"
MINIO_PREFIX = "crus"
# Paths: raw/crus/{municipality_name_lower}/{YYYYMMDD}/crus.geojson

# ---------------------------------------------------------------------------
# Bronze table
# ---------------------------------------------------------------------------

BRONZE_SCHEMA_TABLE = "bronze_regulatory.raw_crus_ordenamento"

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

WFS_REQUEST_DELAY_SECONDS: float = 2.0
WFS_REQUEST_TIMEOUT_SECONDS: int = 120

# ---------------------------------------------------------------------------
# DAG settings
# ---------------------------------------------------------------------------


@dataclass
class CRUSIngestionConfig:
    """All parameters for the CRUS ingestion pipeline."""

    dag_id: str = "crus_ingestion"
    source_name: str = "crus"
    description: str = (
        "CRUS WFS ingestion — queries DGTERRITÓRIO for standardized "
        "land-use data per municipality, stores GeoJSON in MinIO."
    )

    municipalities: list[CRUSMunicipalityConfig] = field(
        default_factory=lambda: MUNICIPALITIES
    )

    minio_bucket: str = MINIO_BUCKET
    minio_prefix: str = MINIO_PREFIX

    bronze_schema_table: str = BRONZE_SCHEMA_TABLE

    request_delay_seconds: float = WFS_REQUEST_DELAY_SECONDS
    request_timeout_seconds: int = WFS_REQUEST_TIMEOUT_SECONDS

    schedule: str | None = None  # manual trigger
    start_date: datetime = field(default_factory=lambda: datetime(2025, 1, 1))
    max_active_runs: int = 1
    max_active_tasks: int = 2

    trigger_dag_id: str = "crus_bronze_load"

    tags: list[str] = field(default_factory=lambda: ["crus", "zoning"])
    retries: int = 2
    retry_delay_minutes: int = 5


CRUS_CONFIG = CRUSIngestionConfig()
