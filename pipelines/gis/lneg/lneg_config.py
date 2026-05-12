# v2 scope — preserved from .pyc decompile, not wired into v1 wedge DAGs.
# See wiki/sources/lneg.md for the canonical source spec.

"""
LNEG (Laboratório Nacional de Energia e Geologia) ingestion configuration.

Two ArcGIS REST polygon layers serve Layer 2 (physical) of the parcel
assessment:

  1. CGP500k / MapServer / 2  →  Geologia do Continente (NATIONAL 1:500k)
     282 polygons covering all of Continental PT and surfaces Aveiro-
     specific lithology classes (e.g. C3 = "Arenitos e argilas de Aveiro,
     Vagos, Taveiro e Viso"). Used because the higher-resolution CGP200k
     vector series has Folha 5 (Beira Litoral, includes Aveiro)
     UNPUBLISHED, AND the 1:50k INSPIRE harmonised series — although
     larger (31,285 polys) — only has 30 of ~175 folhas published, ALL
     in northern PT. Verified live 2026-05-05: ZERO CGP50k INSPIRE polys
     overlap Aveiro município PT-TM06 bbox, despite source returning a
     loose WGS84 bbox count of 9 (those were fringe polys at lat 40.76°N,
     just north of Aveiro município's ymax=117750 PT-TM06).

     POST-DEMO PATH: as LNEG publishes more 1:50k INSPIRE folhas, swap
     this layer for the higher-resolution one once Folha 13-D (Aveiro
     centro) lands.

  2. RecursosHidro / MapServer / 2  →  Sistemas Aquíferos (NATIONAL)
     63 polygons covering Continental PT. Used because CHP200k_vetor (the
     1:200k hidrogeo vector) only publishes Folha 1 (NW) and Folha 6
     (Lisboa-Setúbal) — same Folha-5 gap as geology. Sistemas Aquíferos is
     the canonical Portuguese aquifer-system inventory (e.g. O1 Quaternário
     de Aveiro, O2 Cretácico de Aveiro), maintained by APA/INAG. Schema:
     CodigoInag, NomeCompleto, SistemaAquifero, Idade, IDUnidadeHidrogeologica.

Native CRS is Web Mercator (102100). The ArcgisRestAdapter requests
`outSR=3763` so the server reprojects to PT-TM06 before serialisation —
no client-side transform needed (matches the APA pre-flight pattern).

Per pre-flight gate 7, sig.lneg.pt has a self-signed/legacy SSL cert that
trips Python's default verifier. Adapter calls go through with
`verify=False` for now; tracked as v2 hardening (pin the LNEG cert into
the airflow image and drop the `verify=False` workaround).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

LNEG_GEOLOGY_500K_URL = "https://sig.lneg.pt/server/rest/services/CGP500k/MapServer/2"
LNEG_AQUIFEROS_URL = "https://sig.lneg.pt/server/rest/services/RecursosHidro/MapServer/2"

PAGE_SIZE = 1000
REQUEST_DELAY_SECONDS: float = 0.5
REQUEST_TIMEOUT_SECONDS: int = 180

MINIO_BUCKET = "raw"


class LNEGLayerConfig(BaseModel):
    name: str
    endpoint_url: str
    bronze_table: str
    label: str
    expected_min_features: int


LNEG_LAYERS: list[LNEGLayerConfig] = [
    LNEGLayerConfig(
        name="lneg_geology_500k",
        endpoint_url=LNEG_GEOLOGY_500K_URL,
        bronze_table="bronze_geology.raw_lneg_geology_500k",
        label="LNEG CGP 1:500k Geologia do Continente (national)",
        expected_min_features=200,
    ),
    LNEGLayerConfig(
        name="lneg_aquiferos",
        endpoint_url=LNEG_AQUIFEROS_URL,
        bronze_table="bronze_hydrology.raw_lneg_aquiferos",
        label="LNEG RecursosHidro Sistemas Aquíferos (national)",
        expected_min_features=50,
    ),
]


def minio_prefix_for(layer: LNEGLayerConfig) -> str:
    return layer.name


class LNEGIngestionConfig(BaseModel):
    """Top-level config for the LNEG omnibus ingestion + bronze DAGs."""

    ingestion_dag_id: str = "lneg_ingestion"
    bronze_dag_id: str = "lneg_bronze_load"

    description_ingestion: str = (
        "LNEG ArcGIS REST ingestion — geology (Folha 1, NW) + hidrogeo "
        "classificação (national) for Layer 2 (physical) of parcel assessment."
    )
    description_bronze: str = (
        "LNEG bronze loader — typed-column DDL per layer, CRS-correct insert "
        "(server already reprojected to EPSG:3763) into bronze_geology / "
        "bronze_hydrology."
    )

    page_size: int = PAGE_SIZE
    request_delay_seconds: float = REQUEST_DELAY_SECONDS
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS

    minio_bucket: str = MINIO_BUCKET

    schedule: str | None = None
    start_date: datetime = Field(default_factory=lambda: datetime(2026, 5, 1))
    max_active_runs: int = 1
    max_active_tasks: int = 2
    trigger_dbt_dag_id: str | None = None

    tags: list[str] = Field(default_factory=lambda: ["lneg", "arcgis_rest", "geology", "hidrogeo"])
    retries: int = 1
    retry_delay_minutes: int = 5


LNEG_CONFIG = LNEGIngestionConfig()
