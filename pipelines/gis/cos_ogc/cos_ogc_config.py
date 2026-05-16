"""
COS 2023 — Land Use / Cover Map (DGT) via OGC API.

Replaces the legacy bulk-GeoPackage path (`pipelines/gis/cos/`) with a
paginated OGC API Features ingestion. The OGC API serves the same COS
2023 dataset at `ogcapi.dgterritorio.gov.pt/collections/cos2023v1`.

Scope:
  - **National** (~784k polygons, matching the legacy GPKG count)
  - Streaming-friendly (no large local disk requirement vs the ~700 MB bulk download)
  - Single shared adapter (OgcApiAdapter) with cadastro/crus_ogc/srup_ogc
  - Downstream silver consumers filter via `WHERE concelho_code = ...` at query time

The earlier Aveiro-bbox configuration (Activity 2.4 initial) was a v1-wedge
optimization (~30s ingestion); lifted 2026-05-13 to match parcel_universe's
national scope. Bbox can be reinstated by setting `bbox_4326` to a non-None
tuple in `COSOgcIngestionConfig` — the `OgcApiAdapter` honors it when set.

Schema notes:
  - OGC API serves geometries in EPSG:4326; transformed to EPSG:3763
    on insert (same convention as crus_ogc / srup_ogc bronze loaders).
  - OGC property fields differ from the legacy GeoPackage:
      OGC `objectid`     ← legacy `id`
      OGC `Municipio`    ← (legacy had no per-feature municipality)
      OGC `NUTSII`       ← (legacy had no NUTS attribution)
      OGC `NUTSIII`      ← (legacy had no NUTS attribution)
      OGC `COS23_n4_C`   = legacy `COS23_n4_C` (4-level land-use code)
      OGC `COS23_n4_L`   = legacy `COS23_n4_L` (land-use label)
    `AREA_ha` is NOT exposed by the OGC API — bronze computes it from
    `ST_Area(geom) / 10000.0` post-transform.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# OGC API endpoint
# ---------------------------------------------------------------------------

OGCAPI_BASE = "https://ogcapi.dgterritorio.gov.pt/collections"
COLLECTION_ID = "cos2023v1"
OGCAPI_URL = f"{OGCAPI_BASE}/{COLLECTION_ID}/items"

# Aveiro distrito bbox (kept for reference / quick-scope ingestion runs).
# Default ingestion is national (`bbox_4326=None` in the config below);
# to re-scope to Aveiro for a smoke test, set the config's `bbox_4326`
# field to this tuple.
AVEIRO_BBOX_4326: tuple[float, float, float, float] = (-8.764, 40.528, -8.521, 40.728)

# ---------------------------------------------------------------------------
# Request tuning
# ---------------------------------------------------------------------------

PAGE_SIZE = 500
REQUEST_DELAY_SECONDS: float = 0.5
REQUEST_TIMEOUT_SECONDS: int = 120

# ---------------------------------------------------------------------------
# Bronze table
# ---------------------------------------------------------------------------

BRONZE_SCHEMA_TABLE = "bronze_geo.raw_cos_national_ogc"

# ---------------------------------------------------------------------------
# MinIO storage
# ---------------------------------------------------------------------------

MINIO_BUCKET = "raw"
MINIO_PREFIX = "cos_ogc"
# Paths: raw/cos_ogc/{YYYYMMDD}/cos_ogc.geojson


# ---------------------------------------------------------------------------
# DAG settings
# ---------------------------------------------------------------------------


class COSOgcIngestionConfig(BaseModel):
    """All parameters for the COS OGC API ingestion pipeline.

    Pydantic config pattern shared with the other OGC API ingestion configs
    (cadastro, apa, crus_ogc, lneg, srup_ogc). Bbox-filtered to Aveiro by
    default; remove `bbox_4326` to ingest nationally.
    """

    ingestion_dag_id: str = "cos_ogc_ingestion"
    bronze_dag_id: str = "cos_ogc_bronze_load"

    description_ingestion: str = (
        "COS 2023 OGC API ingestion — fetches national land-use/cover polygons "
        "(~784k features) via ogcapi.dgterritorio.gov.pt/collections/cos2023v1. "
        "Replaces the legacy bulk-GeoPackage path. Set `bbox_4326` to "
        "AVEIRO_BBOX_4326 to scope to Aveiro for a fast smoke test."
    )
    description_bronze: str = (
        "COS 2023 OGC bronze loader — loads GeoJSON from MinIO into "
        "bronze_geo.raw_cos_national_ogc with `municipio`/`nutsii`/`nutsiii` "
        "columns (new in OGC) + `cos23_n4_c`/`cos23_n4_l` (matching legacy)."
    )

    ogcapi_url: str = OGCAPI_URL
    # Default scope: national. Set to AVEIRO_BBOX_4326 (or any tuple) for
    # bbox-scoped ingestion runs.
    bbox_4326: tuple[float, float, float, float] | None = None

    page_size: int = PAGE_SIZE
    request_delay_seconds: float = REQUEST_DELAY_SECONDS
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS

    minio_bucket: str = MINIO_BUCKET
    minio_prefix: str = MINIO_PREFIX

    bronze_schema_table: str = BRONZE_SCHEMA_TABLE

    schedule: str | None = None  # manual trigger
    start_date: datetime = Field(default_factory=lambda: datetime(2026, 5, 13))
    max_active_runs: int = 1

    trigger_dbt_dag_id: str | None = "dbt_cos_build"

    tags: list[str] = Field(default_factory=lambda: ["cos", "ogc_api", "land-use", "dgt"])
    retries: int = 2
    retry_delay_minutes: int = 5


COS_OGC_CONFIG = COSOgcIngestionConfig()
