"""
Cadastro Predial — OGC API Ingestion Configuration

Data source: DGTERRITÓRIO Cadastro Predial (Property Cadastre)
Official property parcel boundaries with cadastral references and areas.
Served via OGC API Features at ogcapi.dgterritorio.gov.pt.

Coverage: Partial — only municipalities surveyed between 2000-2007.
License: CC-BY 4.0

Unlike COS/CAOP (bulk GeoPackage download), Cadastro is only available via
API pagination — no bulk file download exists. This follows the PDM/CRUS
pattern (API → GeoJSON → MinIO → PostGIS).

OGC API endpoint:
  https://ogcapi.dgterritorio.gov.pt/collections/cadastro/items

--- WHAT IT CONTAINS ---

Property parcels with:
  geometry                    — legal property parcel boundary (MultiPolygon)
  nationalcadastralreference  — unique cadastral ID (e.g. AAA000338225)
  areavalue                   — official parcel area in m²
  administrativeunit          — 6-digit DTCC code (distrito+município+freguesia)
  inspireid                   — EU INSPIRE standard identifier
  beginlifespanversion        — record creation date

--- HOW TO TRIGGER ---

Trigger manually from Airflow UI — no parameters needed.
Downloads all available parcels via OGC API pagination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------------------
# OGC API endpoint configuration
# ---------------------------------------------------------------------------

OGCAPI_BASE_URL = "https://ogcapi.dgterritorio.gov.pt/collections/cadastro/items"
PAGE_SIZE = 1000
REQUEST_DELAY_SECONDS: float = 2.0
REQUEST_TIMEOUT_SECONDS: int = 120

# ---------------------------------------------------------------------------
# Bronze table
# ---------------------------------------------------------------------------

BRONZE_SCHEMA_TABLE = "bronze_regulatory.raw_cadastro"

# ---------------------------------------------------------------------------
# MinIO storage
# ---------------------------------------------------------------------------

MINIO_BUCKET = "raw"
MINIO_PREFIX = "cadastro"
# Paths: raw/cadastro/{YYYYMMDD}/cadastro.geojson

# ---------------------------------------------------------------------------
# DAG settings
# ---------------------------------------------------------------------------


@dataclass
class CadastroIngestionConfig:
    """All parameters for the Cadastro Predial ingestion pipeline.

    Follows the same dataclass-based config pattern as PDMIngestionConfig
    (pipelines/gis/pdm/pdm_config.py). Unlike COS/CAOP which use
    GISIngestionConfig for bulk file downloads, this config supports
    API-based pagination ingestion.
    """

    dag_id: str = "cadastro_ingestion"
    source_name: str = "cadastro"
    description: str = (
        "Cadastro Predial — OGC API ingestion. "
        "Fetches property parcel boundaries from DGTERRITÓRIO OGC API "
        "and stores GeoJSON in MinIO."
    )

    ogcapi_url: str = OGCAPI_BASE_URL
    page_size: int = PAGE_SIZE
    request_delay_seconds: float = REQUEST_DELAY_SECONDS
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS

    minio_bucket: str = MINIO_BUCKET
    minio_prefix: str = MINIO_PREFIX

    bronze_schema_table: str = BRONZE_SCHEMA_TABLE

    schedule: str | None = None  # manual trigger
    start_date: datetime = field(default_factory=lambda: datetime(2025, 1, 1))
    max_active_runs: int = 1

    trigger_dag_id: str = "cadastro_bronze_load"

    tags: list[str] = field(default_factory=lambda: ["cadastro", "parcels", "dgt"])
    retries: int = 2
    retry_delay_minutes: int = 5


CADASTRO_CONFIG = CadastroIngestionConfig()
