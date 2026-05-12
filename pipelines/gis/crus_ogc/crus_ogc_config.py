# v2 scope — preserved from .pyc decompile, not wired into v1 wedge DAGs.
# See wiki/sources/crus-ogc.md for the canonical source spec.

"""
CRUS National OGC API Ingestion Configuration

Replaces the per-município WFS path (`pipelines/gis/crus/`) with a single
national fetch from `https://ogcapi.dgterritorio.gov.pt/collections/crus/items`
(numberMatched: 236,920 features as of 2026-05-05).

Coexists with the legacy 5-município WFS table `bronze_regulatory.raw_crus_ordenamento`
during dual-run validation. After parity holds (verified by the
`crus_national_ogc_parity` dbt singular test for ~1 month of nightly runs),
the legacy WFS pipeline is decommissioned per the same checklist used for
RAN OGC migration in WS2a.

The OGC schema is RICHER than legacy WFS — provides typed columns
(classe_2021, categoria_2021, escala_origem, etc.) directly on each feature,
no JSONB unpacking needed in the bronze loader. This is why CRUS gets its own
pipeline rather than going through the omnibus SRUP loader (which uses a
generic JSONB-properties layout).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

OGCAPI_URL = "https://ogcapi.dgterritorio.gov.pt/collections/crus/items"

PAGE_SIZE = 200
REQUEST_DELAY_SECONDS: float = 0.5
REQUEST_TIMEOUT_SECONDS: int = 300

BRONZE_SCHEMA_TABLE = "bronze_regulatory.raw_crus_national_ogc"
MINIO_BUCKET = "raw"
MINIO_PREFIX = "crus_ogc"


class CRUSOGCIngestionConfig(BaseModel):
    """Top-level config for the CRUS OGC ingestion + bronze DAGs."""

    ingestion_dag_id: str = "crus_ogc_ingestion"
    bronze_dag_id: str = "crus_ogc_bronze_load"

    description_ingestion: str = (
        "CRUS national OGC API ingestion — fetches ~236,920 features from "
        "ogcapi.dgterritorio.gov.pt and writes GeoJSON to MinIO."
    )
    description_bronze: str = (
        "CRUS national OGC bronze loader — typed-column DDL "
        "(classe/categoria/designacao/area_ha/...), CRS-correct insert into "
        "bronze_regulatory.raw_crus_national_ogc."
    )

    ogcapi_url: str = OGCAPI_URL

    page_size: int = PAGE_SIZE
    request_delay_seconds: float = REQUEST_DELAY_SECONDS
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS

    minio_bucket: str = MINIO_BUCKET
    minio_prefix: str = MINIO_PREFIX

    bronze_schema_table: str = BRONZE_SCHEMA_TABLE

    schedule: str | None = None
    start_date: datetime = Field(default_factory=lambda: datetime(2026, 5, 1))
    max_active_runs: int = 2
    trigger_dbt_dag_id: str | None = "dbt_srup_build"

    tags: list[str] = Field(default_factory=lambda: ["crus", "ogc_api", "zoning"])
    retries: int = 1
    retry_delay_minutes: int = 5


CRUS_OGC_CONFIG = CRUSOGCIngestionConfig()
