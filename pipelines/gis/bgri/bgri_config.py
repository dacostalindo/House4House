"""
BGRI Census 2021 (S12) — GIS Ingestion Configuration

Base Geográfica de Referenciação de Informação — the INE statistical
geography grid bundled with Census 2021 variables. Published by INE
(Instituto Nacional de Estatística).

Source:  https://mapas.ine.pt/download/index2021.phtml
Format:  GeoPackage (.gpkg) inside a .zip archive
CRS:     ETRS89 / PT-TM06 (EPSG:3763)
Refresh: Static — Census 2021 data. Next census ~2031.

--- WHAT IT CONTAINS ---

32 census variables (synthesis file) at two geographic levels:
  - Statistical subsection  — city-block level (~120K–200K polygons)
  - Statistical section     — aggregated level (~20K–40K polygons)

Variable groups:
  Buildings (12):    stock, typology, floor count, construction period, repair needs
  Dwellings  (8):   total, vacant/secondary, owner-occupied, rented, parking
  Households (5):   size, family nuclei, children
  Population (7):   total, sex, age bands (0-14 / 15-24 / 25-64 / 65+)

Missing from synthesis file (available via INE API as P1 supplements):
  education level, employment/unemployment, foreign-born %, income

--- LAYER NAMES ---

Layer names inside the GeoPackage are confirmed on first run via the
validation report (same workflow as CAOP). expected_layers is left empty
here; update after inspecting the Airflow task logs.

--- HOW TO TRIGGER ---

This is a one-time load (Census 2021 is static). Trigger manually:

    Airflow UI → s12_bgri_ingestion → Trigger DAG

No config parameters needed — URL and version are hardcoded.
"""

from pipelines.gis.template.gis_ingestion_template import GISIngestionConfig


BGRI_CONFIG = GISIngestionConfig(
    # --- DAG identity ---
    dag_id="s12_bgri_ingestion",
    source_name="bgri",
    description=(
        "S12 — BGRI Census 2021 (INE). "
        "Downloads the continental Portugal Census 2021 GeoPackage (BGRI synthesis file) "
        "and stores the raw file in MinIO for exploration. "
        "Contains 32 census variables at statistical subsection and section level "
        "for continental Portugal. Islands (Azores, Madeira) are out of scope for MVP."
    ),

    # --- Source ---
    # Continental Portugal only — islands are out of scope for MVP.
    # National file (portugal2021.zip) is inaccessible; BGRI21_CONT.zip is confirmed working.
    # The zip wraps a .gpkg; download_file handles zip extraction automatically.
    download_url="https://mapas.ine.pt/download/filesGPG/2021/BGRI21_CONT.zip",
    expected_format="gpkg",

    # --- Validation ---
    # Layer names unknown until first inspection — leave empty so the validation
    # report logs all available layers without hard-failing on missing names.
    # Update this list after reading the Airflow task logs.
    expected_layers=[],

    # ETRS89 / PT-TM06 (projected, metres) — same CRS as CAOP.
    expected_crs_epsg=3763,

    # Loose bounds that accommodate both layers (subsection ~120K–200K,
    # section ~20K–40K) plus any auxiliary tables (layer_styles, etc.).
    # Tighten after layer names are confirmed.
    min_feature_count=1,
    max_feature_count=500_000,

    # National GeoPackage with ~200K polygons and 32 attributes.
    # Reject anything under 50 MB as a truncated or empty download.
    min_file_size_bytes=50 * 1024 * 1024,   # 50 MB

    # --- MinIO storage ---
    # Lands at: s3://raw/bgri/2021/BGRI21_CONT.gpkg (or similar, confirmed after first run)
    minio_bucket="raw",
    minio_prefix="bgri",

    # --- Schedule ---
    # One-time load — Census 2021 is static until the next census (~2031).
    schedule=None,

    # --- Version ---
    # Fixed: Census 2021. Not a trigger param.
    source_version="2021",

    # --- Tags ---
    tags=["bgri", "census", "geography", "ine", "p0", "static"],
)
