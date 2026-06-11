"""
Rede Escolar — paginated ArcGIS REST FeatureServer config.

GesEdu (Gestão da Educação, AGSE I.P.) publishes the canonical school register
as a public ArcGIS FeatureServer with Query+Extract capabilities. ~8,670 active
schools across mainland + autonomous regions, point geometry in 4326. Updated
continuously as schools open / close / reorg.

Why a custom DAG (not the GIS ingestion template):
- The template downloads a single static URL; ArcGIS REST requires pagination
  via resultOffset + resultRecordCount (server caps maxRecordCount=2000).
- The template expects file formats (GeoPackage/Shapefile/GeoJSON-file); this
  source serves GeoJSON over HTTP query, one page at a time.
- Verified 2026-06-06: 5 pages (0,2000,4000,6000 → 2000 each; 8000 → 670) =
  8,670 features. exceededTransferLimit=True on full pages signals more.

Endpoint drift risk: AGSE I.P. (DL 99/2025) absorbed DGEstE/DGAE/IGeFE; the
arcgis.com org id (`pXkWEYl9JkoX4UHe`) and service path have held through the
reorg but are NOT under an SLA — add a liveness probe before each full ingest.

License: undocumented public API. Treat as internally-derived; do not
redistribute raw blobs.
"""

from __future__ import annotations

# ArcGIS REST FeatureServer query endpoint. Org `pXkWEYl9JkoX4UHe` is GesEdu's
# public AGOL tenant; layer 0 of `RedeEscolar_mapa` is the per-school point
# layer. Sibling layers (`RedeEscolar_tab`, `UnidadesOrganicas_mapa/_tab`) are
# explicitly NOT ingested here — we want per-school points only.
QUERY_URL = (
    "https://services-eu1.arcgis.com/pXkWEYl9JkoX4UHe/arcgis/rest/services/"
    "RedeEscolar_mapa/FeatureServer/0/query"
)

# Static query params shared by every page request. `f=geojson` returns a
# RFC-7946 FeatureCollection; `outSR=4326` ensures WGS84 (server default is
# already 4326 but we pin it). `where=1=1` is the ArcGIS idiom for "all rows".
QUERY_PARAMS_BASE: dict[str, str] = {
    "where": "1=1",
    "outFields": "*",
    "outSR": "4326",
    "f": "geojson",
    "returnGeometry": "true",
}

# Server-advertised cap. Verified 2026-06-06: full pages return exactly 2000
# features with exceededTransferLimit=True; the final page (offset 8000) returns
# the residual 670 with the flag absent. Do NOT raise this above the server cap;
# ArcGIS silently truncates.
PAGE_SIZE = 2000

# Expected feature count, ±20% sanity band. The probe (returnCountOnly=true) is
# the authoritative number at run time; this constant is only for "the API broke
# and is returning empty" alerts.
EXPECTED_TOTAL = 8670
MIN_TOTAL = 6500
MAX_TOTAL = 11000

# Liveness probe URL (returnCountOnly endpoint). Cheap call, used in fanout
# before mapping download tasks.
COUNT_URL = QUERY_URL  # same path; params differ
COUNT_PARAMS: dict[str, str] = {"where": "1=1", "returnCountOnly": "true", "f": "json"}

# Per-page sanity floor. A page that returns < this many features (other than
# the trailing residual) is suspicious. ArcGIS has been known to return 0
# features without an error when the service is reloading.
MIN_PAGE_FEATURES_NON_TAIL = 100

# Request headers — ArcGIS REST is permissive (no Referer required for query),
# but we send a UA for log forensics on AGSE side.
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
        "House4House/pipelines/rede_escolar"
    ),
    "Accept": "application/json,application/geo+json",
}

# MinIO storage layout: raw/rede_escolar/{run_date}/page_{offset:06d}.geojson
# run_date partitioning lets us keep historical snapshots — schools open and
# close, and time-series of the register is its own dataset.
MINIO_BUCKET = "raw"
MINIO_PREFIX = "rede_escolar"
