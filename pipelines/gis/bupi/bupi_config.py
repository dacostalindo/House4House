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

--- HOW TO TRIGGER ---

Trigger this DAG manually from the Airflow UI with:
    {"version": "2026-03"}

The download URL points to the continental Portugal GPKG on dados.gov.pt.
"""

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
    download_url=(
        "https://dados.gov.pt/s/resources/representacao-grafica-georreferenciada/"
        "20260316-082606/2026-03-16-opendata-rggs-continente.gpkg.zip"
    ),
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
    schedule=None,
    start_date=None,

    # --- Version ---
    source_version=None,
    version_param_key="version",

    dag_params={
        "version": {
            "default": "2026-03",
            "description": (
                "BUPI release month, e.g. '2026-03'. "
                "Determines the MinIO storage path: raw/bupi/{version}/"
            ),
        },
    },

    # --- Tags ---
    tags=["bupi", "cadastro", "property", "p1"],
)
