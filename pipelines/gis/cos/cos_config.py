"""
COS 2023 — Land Use / Cover Map (DGT)

Carta de Uso e Ocupação do Solo, Series 2, published by DGT
(Direção-Geral do Território). Satellite-derived land use/cover
classification for all of continental Portugal.

Source:  https://dados.gov.pt/en/datasets/carta-de-uso-e-ocupacao-do-solo-cos-serie-2-nova/
Format:  GeoPackage (.gpkg) inside a .zip archive
CRS:     ETRS89 / PT-TM06 (EPSG:3763)
Refresh: Periodic (~5 years: 2018, 2023)

--- WHAT IT CONTAINS ---

~784K polygons, each classified with a 4-level hierarchical land-use code:
  Level 1: Broad category (1=Artificial, 2=Agriculture, 3=Pasture, 4=Forest, ...)
  Level 4: Detailed type (e.g. 1.1.1.1 = continuous vertical residential)

GPKG layer: COS2023v1 (main data layer). Also contains 'layer_styles' (QGIS styling, ignored).

Fields per feature:
  ID           — integer feature ID
  COS23_n4_C   — 4-level land-use code (e.g. "1.1.1.1")
  COS23_n4_L   — human-readable label
  AREA_ha      — polygon area in hectares

--- HOW TO TRIGGER ---

Trigger this DAG manually from the Airflow UI with:
    {"version": "2023"}

The download URL is hardcoded (static release from DGT).
"""

from pipelines.gis.template.gis_ingestion_template import GISIngestionConfig


COS_CONFIG = GISIngestionConfig(
    # --- DAG identity ---
    dag_id="cos2023_ingestion",
    source_name="cos",
    description=(
        "COS 2023 — Land Use/Cover Map (DGT). "
        "Downloads the official Portuguese land use classification GeoPackage "
        "and stores the raw file in MinIO. "
        "842K polygons with 4-level hierarchical classification for continental Portugal."
    ),

    # --- Source ---
    download_url="https://geo2.dgterritorio.gov.pt/cos/S2/COS2023/COS2023v1-S2-gpkg.zip",
    expected_format="gpkg",

    # --- Validation ---
    expected_layers=["COS2023v1"],  # skip 'layer_styles' (QGIS styling table)
    expected_crs_epsg=3763,

    # COS 2023 has ~784K polygons in the COS2023v1 layer.
    min_feature_count=500_000,
    max_feature_count=1_500_000,

    # Extracted GPKG is typically several hundred MB.
    min_file_size_bytes=50 * 1024 * 1024,  # 50 MB

    # --- MinIO storage ---
    minio_bucket="raw",
    minio_prefix="cos",

    # --- Schedule ---
    schedule=None,
    start_date=None,

    # --- Version ---
    source_version=None,
    version_param_key="version",

    dag_params={
        "version": {
            "default": "2023",
            "description": (
                "COS release year, e.g. '2023'. "
                "Determines the MinIO storage path: raw/cos/{version}/"
            ),
        },
    },

    # --- Tags ---
    tags=["cos", "land-use", "dgt", "p1"],
)
