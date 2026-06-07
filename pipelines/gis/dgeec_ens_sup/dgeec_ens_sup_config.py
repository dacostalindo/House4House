"""
DGEEC Estabelecimentos do Ensino Superior — shapefile config.

DGEEC publishes the canonical PT higher-ed register as a shapefile bundle
served from DGTerritorio's ATOM-feed mirror. 321 unidades orgânicas
(faculdade-level grain), point geometry in EPSG:4326. Updated infrequently;
the current bundle is dated 2023-03-15.

Why a custom DAG (not the GIS ingestion template):
- The template auto-extracts ZIPs to a single inner file matching
  expected_format and DELETES the ZIP. Shapefiles are bundles of 5+
  sidecars (.shp/.shx/.dbf/.prj/.cpg) — extracting only .shp produces an
  unreadable file. We want to store the ZIP as-is and let the bronze loader
  unzip locally per-run.
- No other GIS source in this repo actually uses expected_format='shp';
  template support is aspirational. Templatising shapefile bundles is a
  separate refactor (deferred until N≥2 sibling shapefile sources).

Endpoint stability: DGTerritorio's ATOM mirror URL has been stable for
years; no version embedded in the path. The publishing cadence is irregular
(years between releases). Manual trigger only — no point in a cron.

License: CC BY 4.0 (DGEEC via DGTerritorio SNIG).
"""

from __future__ import annotations

# Stable ATOM-mirror URL. No version embedded; DGEEC overwrites in place.
DOWNLOAD_URL = (
    "http://geo2.dgterritorio.gov.pt/ATOM-download/DGEEC/Estab_Ens_Sup_Portugal.zip"
)

# Probed 2026-06-07: 40 788 bytes. Bounds catch obvious truncation /
# silent server returning a 200-with-empty-body.
MIN_ZIP_BYTES = 20_000
MAX_ZIP_BYTES = 500_000

# Probed 2026-06-07: 321 features, point geometry, EPSG:4326, UTF-8.
# Pillar decision: tight [200, 500] bands around the verified 321.
EXPECTED_FEATURES = 321
MIN_FEATURES = 200
MAX_FEATURES = 500
EXPECTED_CRS_EPSG = 4326
EXPECTED_GEOMETRY_TYPE = "Point"

# Shapefile sidecars we require inside the ZIP. .cpg is optional (declares
# encoding) but present in the current bundle. .qix/.qmd are QGIS metadata
# and may or may not be present — not required.
REQUIRED_SIDECAR_EXTS: tuple[str, ...] = (".shp", ".shx", ".dbf", ".prj")

# Inner layer name (basename of the .shp file). Verified 2026-06-07.
LAYER_NAME = "Estab_Ens_Sup_Portugal"

# UA for log forensics on DGTerritorio side.
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
        "House4House/pipelines/dgeec_ens_sup"
    ),
    "Accept": "application/zip,application/octet-stream",
}

# MinIO layout: raw/dgeec_ens_sup/{run_date}/Estab_Ens_Sup_Portugal.zip
# run_date partitioning mirrors rede_escolar so silver can pick max(run_date)
# uniformly across the pillar.
MINIO_BUCKET = "raw"
MINIO_PREFIX = "dgeec_ens_sup"
ZIP_FILENAME = "Estab_Ens_Sup_Portugal.zip"
