"""
CAOP Boundaries (S08) — GIS Ingestion Configuration

Carta Administrativa Oficial de Portugal, published annually by DGT
(Direção-Geral do Território).

Source:  https://www.dgterritorio.gov.pt/cartografia/caop
Format:  GeoPackage (.gpkg), multiple layers
CRS:     ETRS89 / PT-TM06 (EPSG:3763) or ETRS89 geographic (EPSG:4258)
Refresh: Annual — no predictable release date, manual trigger per release

--- HOW TO TRIGGER A NEW RELEASE ---

Trigger this DAG manually from the Airflow UI with:

    {
        "version": "2025",
        "download_url": "<direct .gpkg or .zip URL from the DGT CAOP page>"
    }

No code changes needed between annual releases.

--- LAYER NAME CONVENTION ---

DGT layer names inside the GeoPackage (current convention, as of CAOP 2025):
    cont_distritos    — Distritos           (~18 polygons)
    cont_municipios   — Concelhos/Municípios (~278 polygons)
    cont_freguesias   — Freguesias          (~3,049 polygons)

If DGT changes the naming convention, only _caop_layer_names() needs updating.
"""

from pipelines.gis.template.gis_ingestion_template import GISIngestionConfig


def _caop_layer_names(_version: str) -> list[str]:
    """
    Returns the expected GeoPackage layer names for a given CAOP release year.

    Current DGT naming convention (as of CAOP 2025):
        cont_distritos    → Distritos
        cont_municipios   → Concelhos/Municípios
        cont_freguesias   → Freguesias

    If DGT changes naming in a future release, update this list.
    """
    return ["cont_distritos", "cont_municipios", "cont_freguesias"]


CAOP_CONFIG = GISIngestionConfig(
    # --- DAG identity ---
    dag_id="s08_caop_ingestion",
    source_name="caop",
    description=(
        "S08 — CAOP Boundaries (DGT). "
        "Downloads the official Portuguese administrative boundary GeoPackage "
        "and stores the raw file in MinIO for exploration. "
        "Covers: distritos, concelhos, and freguesias for continental Portugal."
    ),

    # --- Source ---
    # URL is supplied at trigger time — it changes with each DGT release.
    download_url="param:download_url",
    expected_format="gpkg",

    # --- Validation ---
    # Layer names embed the version, so expected_layers is empty here and
    # layer_name_fn computes the correct names at runtime from the trigger param.
    expected_layers=[],
    layer_name_fn=_caop_layer_names,

    # The GeoPackage uses PT-TM06 / ETRS89 (EPSG:3763).
    # Mismatch triggers a warning, not a failure — the file still gets stored.
    expected_crs_epsg=3763,

    # Loose bounds covering all three layers:
    #   distritos:  18 features
    #   concelhos:  308 features
    #   freguesias: ~3,091 features
    # Catches clearly broken downloads without being brittle to minor
    # boundary revisions between releases.
    min_feature_count=10,
    max_feature_count=5_000,

    # A valid CAOP GeoPackage is typically 50–200 MB.
    # Reject anything under 10 MB as a truncated or empty download.
    min_file_size_bytes=10 * 1024 * 1024,   # 10 MB

    # --- MinIO storage ---
    # Lands at: s3://raw/caop/{version}/caop_{version}.gpkg
    minio_bucket="raw",
    minio_prefix="caop",

    # --- Schedule ---
    # Manual trigger only — DGT releases CAOP with no predictable date.
    # start_date omitted → template defaults to yesterday UTC.
    schedule=None,

    # --- Version ---
    # Always supplied at trigger time via dag_run.conf["version"].
    source_version=None,
    version_param_key="version",

    # --- Trigger params (shown in Airflow "Trigger DAG w/ config" dialog) ---
    dag_params={
        "version": {
            "default": "",
            "description": (
                "CAOP release year, e.g. '2024'. "
                "Determines the expected layer names and MinIO storage path."
            ),
        },
        "download_url": {
            "default": "",
            "description": (
                "Direct .gpkg download URL from the DGT CAOP page "
                "(https://www.dgterritorio.gov.pt/cartografia/caop). "
                "URL changes with each release."
            ),
        },
    },

    # --- Tags ---
    tags=["caop", "geography", "dgt", "p0", "annual"],
)
