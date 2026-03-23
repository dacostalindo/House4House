"""
SRUP WFS Ingestion Configuration

Data source: DGTERRITÓRIO SRUP (Servidões e Restrições de Utilidade Pública)
Property constraint/restriction data from PDM Condicionantes — ecological reserves,
agricultural reserves, public water domain, and heritage protection zones.

WFS URL pattern:
  https://servicos.dgterritorio.pt/SDISNITWFS{suffix}/WFService.aspx

Phase 1 categories (national endpoints, full fetch):
  IC  — Imóveis Classificados (heritage sites)         ~3,676 features
  RAN — Reserva Agrícola Nacional (agricultural reserve)  ~268 features
  DPH — Domínio Público Hídrico (public water domain)       ~7 features

Phase 2 (not yet implemented):
  REN — Reserva Ecológica Nacional (regional endpoints, requires BBOX filtering)
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote

# ---------------------------------------------------------------------------
# WFS constants
# ---------------------------------------------------------------------------

WFS_BASE_URL = "https://servicos.dgterritorio.pt/SDISNITWFS"
WFS_VERSION = "2.0.0"
WFS_OUTPUT_FORMAT = "application/vnd.geo+json"

WFS_REQUEST_DELAY_SECONDS: float = 2.0
# RAN can take >120s for its 360 MB response (268 large polygons)
WFS_REQUEST_TIMEOUT_SECONDS: int = 300

# ---------------------------------------------------------------------------
# Endpoint configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SRUPEndpointConfig:
    """One WFS endpoint serving one or more feature types at a single URL."""

    category: str  # "ic", "ran", "dph"
    wfs_suffix: str  # e.g. "SRUP_IC_PT1"
    feature_types: tuple[str, ...]  # e.g. ("gmgml:RAN",)
    label: str  # Human-readable label for logging

    @property
    def wfs_url(self) -> str:
        return f"{WFS_BASE_URL}{self.wfs_suffix}/WFService.aspx"

    def get_capabilities_url(self) -> str:
        return (
            f"{self.wfs_url}?SERVICE=WFS&VERSION={WFS_VERSION}"
            f"&REQUEST=GetCapabilities"
        )

    def get_feature_url(self, feature_type: str) -> str:
        """Build WFS GetFeature URL for a specific feature type."""
        fmt = quote(WFS_OUTPUT_FORMAT, safe="")
        return (
            f"{self.wfs_url}?SERVICE=WFS&VERSION={WFS_VERSION}"
            f"&REQUEST=GetFeature"
            f"&TYPENAMES={feature_type}"
            f"&OUTPUTFORMAT={fmt}"
        )

    @property
    def safe_name(self) -> str:
        """Filename-safe version of the endpoint suffix."""
        return self.wfs_suffix.lower().replace("-", "_")


# ---------------------------------------------------------------------------
# Endpoint registry (single source of truth)
# ---------------------------------------------------------------------------

SRUP_ENDPOINTS: list[SRUPEndpointConfig] = [
    SRUPEndpointConfig(
        category="ic",
        wfs_suffix="SRUP_IC_PT1",
        feature_types=(
            "gmgml:Imóveis_Classificados_com_Zona_de_Proteção",
            "gmgml:Imóveis_Classificados_Localizados",
        ),
        label="IC Heritage Sites",
    ),
    SRUPEndpointConfig(
        category="ran",
        wfs_suffix="SRUP_RAN_PT1",
        feature_types=("gmgml:RAN",),
        label="RAN Agricultural Reserve",
    ),
    SRUPEndpointConfig(
        category="dph",
        wfs_suffix="SRUP_DPH_PT1",
        feature_types=(
            "gmgml:Zona_de_Ocupação_Condicionada",
            "gmgml:Zona_de_Ocupação_Proibida",
        ),
        label="DPH Public Water Domain",
    ),
]

# Derived lookups
SRUP_ENDPOINT_BY_SUFFIX: dict[str, SRUPEndpointConfig] = {
    e.wfs_suffix: e for e in SRUP_ENDPOINTS
}

SRUP_ENDPOINTS_BY_CATEGORY: dict[str, list[SRUPEndpointConfig]] = {}
for _e in SRUP_ENDPOINTS:
    SRUP_ENDPOINTS_BY_CATEGORY.setdefault(_e.category, []).append(_e)

ALL_CATEGORIES = list(SRUP_ENDPOINTS_BY_CATEGORY.keys())

# ---------------------------------------------------------------------------
# Field normalization
# ---------------------------------------------------------------------------
# WFS responses use accented Portuguese field names (DINÂMICA, SERVIDÃO).
# We strip diacritics for consistency. All fields are passed through to bronze
# (no filtering); field selection happens in dbt staging models.

_EXPLICIT_RENAMES: dict[str, str] = {
    # Add per-endpoint quirks here as they are discovered
}


def normalize_field_name(name: str) -> str:
    """Strip diacritics from a WFS field name and apply explicit renames.

    >>> normalize_field_name("DINÂMICA")
    'DINAMICA'
    >>> normalize_field_name("SERVIDÃO")
    'SERVIDAO'
    """
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    return _EXPLICIT_RENAMES.get(ascii_name, ascii_name)


# ---------------------------------------------------------------------------
# Known field schemas (from verify_srup_endpoints.py, 2026-03-19)
# All fields are passed through; this block is documentation only.
# ---------------------------------------------------------------------------
# IC — gmgml:Imóveis_Classificados_com_Zona_de_Proteção (GeometryCollection):
#   AREA_HA, CLASSIFICACAO, DESIGNACAO, ESTADO, FREGUESIAS, GEOMETRIA_AUTOR,
#   GEOMETRIA_DATA, GEOMETRIA_RIGOR, ID, LEI_TIPO, LOCAL, MUNICIPIOS,
#   NOTAS_GEOREF, REGIAO, SERVIDAO, SERV_DATA, SERV_DR, SERV_HIPERLINK,
#   SERV_LEI, SITUACAO, TUTELA
#
# IC — gmgml:Imóveis_Classificados_Localizados (Point):
#   (same 21 fields as above)
#
# RAN — gmgml:RAN (GeometryCollection):
#   AUTOR, CONCELHO, DATA, DINÂMICA, ID, RIGOR, SERVIDÃO
#
# DPH — gmgml:Zona_de_Ocupação_Condicionada (Polygon):
#   AREA_HA, DESIGNACAO, ESTADO, GEOMETRIA_AUTOR, GEOMETRIA_DATA,
#   GEOMETRIA_RIGOR, ID, LEI_TIPO, LOCAL, MUNICIPIOS, REGIAO, SERVIDAO,
#   SERV_DATA, SERV_DR, SERV_HIPERLINK, SERV_LEI, SITUACAO, TUTELA
#
# DPH — gmgml:Zona_de_Ocupação_Proibida (GeometryCollection):
#   (same 18 fields as Condicionada)

# ---------------------------------------------------------------------------
# MinIO storage
# ---------------------------------------------------------------------------

MINIO_BUCKET = "raw"
MINIO_PREFIX = "srup"
# Paths: raw/srup/{category}/{YYYYMMDD}/{safe_feature_type_name}.geojson

# ---------------------------------------------------------------------------
# Bronze tables
# ---------------------------------------------------------------------------

BRONZE_TABLES: dict[str, str] = {
    "ic": "bronze_regulatory.raw_srup_ic",
    "ran": "bronze_regulatory.raw_srup_ran",
    "dph": "bronze_regulatory.raw_srup_dph",
}

# ---------------------------------------------------------------------------
# DAG settings
# ---------------------------------------------------------------------------


@dataclass
class SRUPIngestionConfig:
    """All parameters for the SRUP ingestion pipeline."""

    dag_id: str = "srup_ingestion"
    source_name: str = "srup"
    description: str = (
        "SRUP WFS ingestion — queries DGTERRITÓRIO for property constraint data "
        "(IC, RAN, DPH), stores GeoJSON in MinIO."
    )

    minio_bucket: str = MINIO_BUCKET
    minio_prefix: str = MINIO_PREFIX

    request_delay_seconds: float = WFS_REQUEST_DELAY_SECONDS
    request_timeout_seconds: int = WFS_REQUEST_TIMEOUT_SECONDS

    schedule: str | None = None  # manual trigger
    start_date: datetime = field(default_factory=lambda: datetime(2025, 1, 1))
    max_active_runs: int = 1
    max_active_tasks: int = 2

    trigger_dag_id: str = "srup_bronze_load"

    tags: list[str] = field(default_factory=lambda: ["srup", "constraints"])
    retries: int = 2
    retry_delay_minutes: int = 5


SRUP_CONFIG = SRUPIngestionConfig()
