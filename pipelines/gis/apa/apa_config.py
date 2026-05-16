# v2 scope — preserved from .pyc decompile, not wired into v1 wedge DAGs.
# See wiki/sources/apa.md for the canonical source spec.

"""
APA (Agência Portuguesa do Ambiente) Floodplain ingestion configuration.

Source: ARPSI (Áreas de Risco Potencial Significativo de Inundação) — APA's
official EU Floods Directive 2007/60/CE polygon dataset, hosted at the
Aqualogus AGOL org (NOT the apambiente AGOL, which returns empty per
pre-flight gate 8).

  https://services9.arcgis.com/heNM9t1Uq1GNOWAW/arcgis/rest/services/ARPSI/FeatureServer/0

188 polygons nationally, ~18 intersect Aveiro município (1× T1000 + 17× T100,
all in PTRH4A Vouga sub-basin — Aveiro centro + Cova Mira). Schema:
  OBJECTID, RHidro, Local, Designa, Fonte, Data,
  TRetorno (return period — KEY for flood_class), GEOCOD

Native CRS is Web Mercator (102100) but the ArcgisRestAdapter requests
`outSR=3763` so the server reprojects server-side — no client transform.

Coverage caveat: ARPSI is the EU Floods Directive scope (188 highest-priority
polygons); NOT every floodable area in Portugal. Aveiro centro + Cova Mira are
covered; other parts may have undocumented flood risk. This caveat is surfaced
in the dbt staging model description.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

ARPSI_URL = (
    "https://services9.arcgis.com/heNM9t1Uq1GNOWAW/arcgis/rest/services/ARPSI/FeatureServer/0"
)

PAGE_SIZE = 2000
REQUEST_DELAY_SECONDS: float = 0.0
REQUEST_TIMEOUT_SECONDS: int = 120

BRONZE_SCHEMA_TABLE = "bronze_hydrology.raw_apa_arpsi_floodplain"
MINIO_BUCKET = "raw"
MINIO_PREFIX = "apa_arpsi"


class APAIngestionConfig(BaseModel):
    """Top-level config for the APA ARPSI ingestion + bronze DAGs."""

    ingestion_dag_id: str = "apa_arpsi_ingestion"
    bronze_dag_id: str = "apa_arpsi_bronze_load"

    description_ingestion: str = (
        "APA ARPSI floodplain ingestion — fetches 188 EU Floods Directive polygons "
        "from Aqualogus AGOL FeatureServer and writes GeoJSON to MinIO."
    )
    description_bronze: str = (
        "APA ARPSI bronze loader — typed-column DDL "
        "(rhidro/local/designa/fonte/data/return_period/geocod), geometry already "
        "in PT-TM06 (server-side reprojection)."
    )

    arpsi_url: str = ARPSI_URL

    page_size: int = PAGE_SIZE
    request_delay_seconds: float = REQUEST_DELAY_SECONDS
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS

    minio_bucket: str = MINIO_BUCKET
    minio_prefix: str = MINIO_PREFIX

    bronze_schema_table: str = BRONZE_SCHEMA_TABLE

    schedule: str | None = None
    start_date: datetime = Field(default_factory=lambda: datetime(2026, 5, 1))
    max_active_runs: int = 1
    trigger_dbt_dag_id: str | None = None

    tags: list[str] = Field(
        default_factory=lambda: ["apa", "arcgis_rest", "floodplain", "hydrology"]
    )
    retries: int = 1
    retry_delay_minutes: int = 5


APA_CONFIG = APAIngestionConfig()
