"""
BUPI — Simplified Cadastral Property Parcels (eBUPi / dados.gov.pt)

Representação Gráfica Georreferenciada (RGG) — georeferenced property
boundary polygons from the BUPi simplified cadastral registration system.
3.25M parcels covering 152 municipalities in continental Portugal.

Source:  https://dados.gov.pt/en/datasets/representacao-grafica-georreferenciada/
Format:  GeoPackage (.gpkg) inside a .zip archive
CRS:     ETRS89 / PT-TM06 (EPSG:3763)
Refresh: Monthly

--- WHAT IT CONTAINS ---

~3.25M MultiPolygon property parcels, each with:
  ProcessoId    — BUPi process identifier (unique integer)
  NumeroMatriz  — property tax matrix number (string, may contain commas)
  Dicofre       — 6-digit parish code (distrito + concelho + freguesia)
  Concelho      — municipality name
  Freguesia     — parish name
  Area_m2       — parcel area in square metres

GPKG layer name varies by download date (e.g. rgg_20260316_opendata).
Auto-detect is used since the layer name is not stable.

--- SCHEDULE ---

Runs on the 5th of every month at 06:00 UTC (dados.gov.pt publishes on the 1st).
Can also be triggered manually with: {"version": "2026-04"}
Version defaults to the current month (YYYY-MM) if not provided.
"""

from datetime import datetime

from pipelines.gis.template.gis_ingestion_template import GISIngestionConfig


BUPI_CONFIG = GISIngestionConfig(
    # --- DAG identity ---
    dag_id="bupi_ingestion",
    source_name="bupi",
    description=(
        "BUPI — Simplified Cadastral Property Parcels (RGG). "
        "Downloads georeferenced property boundary polygons from dados.gov.pt. "
        "3.25M parcels covering 152 municipalities in continental Portugal."
    ),

    # --- Source ---
    # Stable redirect URL — always resolves to the latest monthly GPKG.
    # dados.gov.pt maintains this permalink; no hardcoded dates to update.
    download_url="https://dados.gov.pt/pt/datasets/r/8dedcd3e-ba46-4f0f-a75f-36e0b327fc56",
    expected_format="gpkg",

    # --- Validation ---
    expected_layers=None,  # layer name includes date, auto-detect
    expected_crs_epsg=3763,

    # Continental BUPI has ~3.25M parcels (March 2026).
    # Bounds give slack for monthly growth while catching bad downloads.
    min_feature_count=2_500_000,
    max_feature_count=5_000_000,

    # Extracted GPKG is ~1.4 GB.
    min_file_size_bytes=500 * 1024 * 1024,  # 500 MB

    # --- MinIO storage ---
    minio_bucket="raw",
    minio_prefix="bupi",

    # --- Schedule ---
    # 5th of every month at 06:00 UTC (dados.gov.pt publishes on the 1st)
    schedule="0 6 5 * *",
    start_date=datetime(2026, 4, 1),

    # --- Version ---
    source_version=None,
    version_param_key="version",

    dag_params={
        "version": {
            "default": datetime.now().strftime("%Y-%m"),
            "description": (
                "BUPI release month, e.g. '2026-04'. "
                "Defaults to current month. "
                "Determines the MinIO storage path: raw/bupi/{version}/"
            ),
        },
    },

    # --- Tags ---
    tags=["bupi", "cadastro", "property", "p1"],
)
