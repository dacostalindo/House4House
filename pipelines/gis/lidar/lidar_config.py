"""
DGT LiDAR Aveiro ingestion configuration — 2m resolution only.

Two STAC collections at the DGT CDD catalogue:
  1. MDT-2m  →  Modelo Digital de Terreno (bare-earth DTM at 2m)
  2. MDS-2m  →  Modelo Digital de Superfície (first-return DSM at 2m)

Both collections cover the same Aveiro tile grid (489 tiles), acquired
2025-07-12 → 2025-08-04, native EPSG:3763 (PT-TM06). Each tile is a Float32
GeoTIFF with noDataValue=-999, ~1 MB per tile → ~490 MB per collection,
~1 GB total for both.

Per the locked plan (D26 follow-up 2026-05-05): 2m only, NOT 50cm. 50cm
gives sub-meter terrain detail at 14× the storage cost; 2m comfortably
resolves typical Aveiro parcels (100-500 m² lots = dozens of pixels) and
keeps WS3b derived-product processing under 5 minutes total.

Auth flow (proven in pre-flight gate 1):
  1. POST /v1/search → STAC FeatureCollection with tokenized download URLs.
     Catalog access is PUBLIC.
  2. GET /v1/download/{token} with the Keycloak session cookie.
     Cookie stored in Airflow Variable DGT_CDD_COOKIE.
  3. Server validates cookie, 302-redirects to a fresh MinIO presigned URL
     on stor-002.a.acnca.pt:9000. requests follows the redirect transparently
     and returns the GeoTIFF bytes.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# DGT CDD STAC catalogue
# ---------------------------------------------------------------------------

DGT_CDD_STAC_ROOT = "https://cdd.dgterritorio.gov.pt/dgt-be"

# Aveiro município bounding box (WGS84 / EPSG:4326), used as the STAC bbox
# filter parameter for /v1/search. Generous envelope covering the full
# Aveiro distrito (not just the município centroid) so the 489 tiles per
# collection all return.
AVEIRO_BBOX_4326: tuple[float, float, float, float] = (-8.764, 40.528, -8.521, 40.728)

# ---------------------------------------------------------------------------
# Request tuning
# ---------------------------------------------------------------------------

PAGE_SIZE = 500
REQUEST_DELAY_SECONDS: float = 0.5
REQUEST_TIMEOUT_SECONDS: int = 300

# ---------------------------------------------------------------------------
# Auth — Keycloak session cookie stored in an Airflow Variable
# ---------------------------------------------------------------------------

DGT_CDD_COOKIE_VARIABLE = "DGT_CDD_COOKIE"

# ---------------------------------------------------------------------------
# MinIO landing
# ---------------------------------------------------------------------------

MINIO_BUCKET = "raw"
# Paths: raw/lidar/{COLLECTION}/{YYYYMMDD}/{tile_id}.tif


class LiDARLayerConfig(BaseModel):
    """One STAC collection in the DGT LiDAR catalogue."""

    name: str
    collection_id: str
    bronze_table: str
    label: str
    expected_min_features: int


LIDAR_LAYERS: list[LiDARLayerConfig] = [
    LiDARLayerConfig(
        name="lidar_mdt_2m",
        collection_id="MDT-2m",
        bronze_table="bronze_terrain.raw_lidar_mdt_2m_manifest",
        label="DGT LiDAR MDT-2m (Aveiro, bare-earth DTM at 2m)",
        expected_min_features=400,
    ),
    LiDARLayerConfig(
        name="lidar_mds_2m",
        collection_id="MDS-2m",
        bronze_table="bronze_terrain.raw_lidar_mds_2m_manifest",
        label="DGT LiDAR MDS-2m (Aveiro, first-return DSM at 2m)",
        expected_min_features=400,
    ),
]


def minio_prefix_for(layer: LiDARLayerConfig) -> str:
    return f"lidar/{layer.collection_id}"


class LiDARIngestionConfig(BaseModel):
    """Top-level config for the LiDAR omnibus ingestion + bronze DAGs."""

    ingestion_dag_id: str = "lidar_aveiro_ingestion"
    bronze_dag_id: str = "lidar_aveiro_bronze_load"

    description_ingestion: str = (
        "DGT LiDAR Aveiro ingestion (2m DTM + DSM). Fetches ~489 GeoTIFF tiles "
        "per collection from the DGT CDD STAC catalogue, cookie-gated downloads, "
        "~1 GB total to MinIO."
    )
    description_bronze: str = (
        "DGT LiDAR bronze loader — populates bronze_terrain.raw_lidar_*_manifest "
        "tables with one row per tile (tile_id, EPSG:3763 footprint geom, "
        "minio_object, version, datetime, file_size_bytes)."
    )

    stac_root: str = DGT_CDD_STAC_ROOT
    aveiro_bbox_4326: tuple[float, float, float, float] = AVEIRO_BBOX_4326
    auth_cookie_variable: str = DGT_CDD_COOKIE_VARIABLE

    page_size: int = PAGE_SIZE
    request_delay_seconds: float = REQUEST_DELAY_SECONDS
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS

    minio_bucket: str = MINIO_BUCKET

    schedule: str | None = None
    start_date: datetime = Field(default_factory=lambda: datetime(2026, 5, 1))
    max_active_runs: int = 1
    max_active_tasks: int = 2

    trigger_dbt_dag_id: str | None = None

    tags: list[str] = Field(default_factory=lambda: ["lidar", "dgt_stac", "raster", "aveiro"])
    retries: int = 1
    retry_delay_minutes: int = 5


LIDAR_CONFIG = LiDARIngestionConfig()
