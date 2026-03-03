"""
OpenStreetMap Portugal (S09/S10/S11) — GIS Ingestion Configuration

Single GeoPackage from Geofabrik covering all three OSM sources:
  S09 — POIs (walkability & amenity scoring)
  S10 — Transport (accessibility scoring)
  S11 — Road Network (drive-time / OSRM routing)

Source:  https://download.geofabrik.de/europe/portugal.html
Format:  GeoPackage (.gpkg) inside a .zip archive
CRS:     WGS 84 (EPSG:4326) — geographic coordinates
Refresh: Monthly (Geofabrik updates daily, monthly is sufficient for our use case)

--- WHAT IT CONTAINS ---

18 layers, ~4.5M features total:

  POIs (S09):
    gis_osm_pois_free          174K points   — restaurants, supermarkets, pharmacies, banks, ...
    gis_osm_pois_a_free        130K polygons — schools, parks, hospitals, sports centres, ...
    gis_osm_pofw_free            2K points   — places of worship
    gis_osm_pofw_a_free         11K polygons — places of worship (areas)

  Transport (S10):
    gis_osm_transport_free      49K points   — bus stops, railway stations, tram stops, ...
    gis_osm_transport_a_free     1K polygons — bus/railway stations (areas)
    gis_osm_railways_free       11K lines    — rail, subway, tram, light rail tracks

  Roads (S11):
    gis_osm_roads_free        1.55M lines    — full road network with routing attributes
    gis_osm_traffic_free       172K points   — crossings, traffic signals, fuel, parking
    gis_osm_traffic_a_free      60K polygons — parking areas, fuel stations, marinas

  Other (useful for context):
    gis_osm_buildings_a_free  2.10M polygons — building footprints
    gis_osm_landuse_a_free     492K polygons — residential, commercial, industrial zones
    gis_osm_natural_free       227K points   — natural features
    gis_osm_natural_a_free       2K polygons — natural areas
    gis_osm_places_free         31K points   — cities, towns, villages, suburbs
    gis_osm_places_a_free        1K polygons — place boundaries
    gis_osm_water_a_free        56K polygons — water bodies
    gis_osm_waterways_free     119K lines    — rivers, streams

--- CRS NOTE ---

This file uses WGS 84 (EPSG:4326), not PT-TM06 (EPSG:3763) like CAOP/BGRI.
Spatial joins in the silver layer will need ST_Transform to align CRS.

--- HOW TO TRIGGER ---

Trigger manually from the Airflow UI:
    Airflow UI → s09_osm_ingestion → Trigger DAG

No config parameters needed — URL is hardcoded (Geofabrik's "latest" URL
always points to the most recent extract).
"""

from pipelines.gis.template.gis_ingestion_template import GISIngestionConfig


# All 18 layers in the Geofabrik Portugal GPKG.
# Grouped by source for clarity, but validated as a single file.
_OSM_EXPECTED_LAYERS = [
    # S09 — POIs
    "gis_osm_pois_free",
    "gis_osm_pois_a_free",
    "gis_osm_pofw_free",
    "gis_osm_pofw_a_free",
    # S10 — Transport
    "gis_osm_transport_free",
    "gis_osm_transport_a_free",
    "gis_osm_railways_free",
    # S11 — Roads & Traffic
    "gis_osm_roads_free",
    "gis_osm_traffic_free",
    "gis_osm_traffic_a_free",
    # Context layers (buildings, landuse, natural, places, water)
    "gis_osm_buildings_a_free",
    "gis_osm_landuse_a_free",
    "gis_osm_natural_free",
    "gis_osm_natural_a_free",
    "gis_osm_places_free",
    "gis_osm_places_a_free",
    "gis_osm_water_a_free",
    "gis_osm_waterways_free",
]


OSM_CONFIG = GISIngestionConfig(
    # --- DAG identity ---
    dag_id="s09_osm_ingestion",
    source_name="osm",
    description=(
        "S09/S10/S11 — OpenStreetMap Portugal (Geofabrik). "
        "Downloads the full Portugal GeoPackage covering POIs, transport network, "
        "and road network. Stores the raw file in MinIO for exploration. "
        "18 layers, ~4.5M features, ~1.5 GB extracted."
    ),

    # --- Source ---
    # Geofabrik's "latest" URL always points to the most recent daily extract.
    # The ZIP wraps a portugal.gpkg; download_file handles extraction.
    download_url="https://download.geofabrik.de/europe/portugal-latest-free.gpkg.zip",
    expected_format="gpkg",

    # --- Validation ---
    expected_layers=_OSM_EXPECTED_LAYERS,

    # WGS 84 — geographic coordinates (not projected like CAOP/BGRI).
    expected_crs_epsg=4326,

    # Loose bounds: smallest layer is ~700 features (places_a),
    # largest is ~2.1M (buildings_a). Allow the full range.
    min_feature_count=1,
    max_feature_count=3_000_000,

    # Extracted GPKG is ~1.5 GB. Reject anything under 500 MB.
    min_file_size_bytes=500 * 1024 * 1024,   # 500 MB

    # --- MinIO storage ---
    # Lands at: s3://raw/osm/{version}/portugal.gpkg
    minio_bucket="raw",
    minio_prefix="osm",

    # --- Schedule ---
    # Manual trigger only (matching BGRI/CAOP pattern).
    # Trigger with: {"version": "2026-03"}
    schedule=None,
    start_date=None,

    # --- Version ---
    # Use date-based versioning. The "latest" URL doesn't embed a version,
    # so we use a trigger param to tag each download.
    source_version=None,
    version_param_key="version",

    dag_params={
        "version": {
            "default": "",
            "description": (
                "Version tag for this OSM extract, e.g. '2026-03'. "
                "Used as the MinIO path segment: raw/osm/{version}/portugal.gpkg"
            ),
        },
    },

    # --- Tags ---
    tags=["osm", "pois", "transport", "roads", "geography", "geofabrik", "p0", "monthly"],
)
