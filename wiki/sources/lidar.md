---
title: DGT LiDAR Aveiro (2m DTM & DSM)
type: source
last_verified: 2026-06-03
tags: [gis, regulatory, government, terrain, raster, stac]
priority: P1
---

## For future Claude

This is a source page about DGT's LiDAR-derived 2m elevation rasters (DTM bare-earth + DSM first-return) for the Aveiro region. It documents the STAC-Collections ingest with Keycloak cookie auth, the deliberate 2m-only resolution choice (vs. 50cm at 14× cost), and the manifest-table layout (one row per tile). Read this page before editing [pipelines/gis/lidar/lidar_config.py](../../pipelines/gis/lidar/lidar_config.py).

## Source

- **Official name**: DGT CDD LiDAR (Centro de Dados Digitais)
- **Owner**: government agency (DGT — via CDD STAC catalog)
- **Protocol**: STAC Collections (HTTP cookie-authenticated downloads behind Keycloak)
- **Base endpoint**: `https://cdd.dgterritorio.gov.pt/dgt-be` (STAC root)
- **License**: open data (cookie-gated)
- **Schedule**: manual trigger
- **Coverage**: currently Aveiro município / centro / lagoon only (489 tiles per collection × 2 collections = 978 tiles total). The 489-tile figure is the CANONICAL count for the configured bbox (`-8.764, 40.528, -8.521, 40.728` ≈ 462 km²), verified 2026-05-13 by direct DGT STAC query (`limit=500` → `returned=489, has_next=False`). To expand to Aveiro distrito (~2,800 km², ≥600 tiles available per STAC), widen `AVEIRO_BBOX_4326` in [pipelines/gis/lidar/lidar_config.py](../../pipelines/gis/lidar/lidar_config.py) and confirm pagination works (current `page_size=500` + the recovered `DgtStacAdapter.fetch_to` loop handles `next` links).

## Schema

**Two manifest tables** (pointers to MinIO-mirrored TIFFs, NOT the raster bytes):

- `bronze_terrain.raw_lidar_mdt_2m_manifest` — MDT-2m (bare-earth DTM). 489 rows.
- `bronze_terrain.raw_lidar_mds_2m_manifest` — MDS-2m (first-return DSM, includes buildings + vegetation). 489 rows.

Per-tile manifest row:
- **tile_id** — STAC item identifier
- **geom** — Polygon, EPSG:3763 PT-TM06 (tile bounding box)
- **minio_object** — `lidar/<collection>/<date>/tiles/<tile_id>.tif` path
- **version, acquisition_date** — STAC item metadata
- **file_size_bytes** — for sanity checks

The raw GeoTIFF tiles (~1 MB each, ~490 MB per collection) live in MinIO. Downstream pipelines stream them on demand.

**One in-DB raster table** (sprint-09 WS4 PR A, 2026-06-03):

- `bronze_terrain.raster_lidar_slope_2m` — slope COGs derived from MDT-2m via `gdaldem slope -alg Horn` and loaded into postgis_raster as 489 rows × ~1 MB each (~500 MB total). Queried directly by `gold.fn_assess_polygon` via `ST_Clip` + `ST_SummaryStatsAgg` — see [[silver-dq-baseline]].

## Silver layer

`silver_geo.terrain_slope_raster` (shipped sprint-09 WS4 PR A, 2026-06-03) — thin dbt view over `bronze_terrain.raster_lidar_slope_2m` that adds two materialized convex-hull footprint columns (`footprint_pt` in EPSG:3763, GIST-indexed; `footprint` in EPSG:4326 for display). This lets `fn_assess_polygon` pre-filter the 489 tiles to the 1-4 overlapping a drawn polygon via an index-only `ST_Intersects` before the expensive `ST_Clip`.

**Architectural pivot**: the original sprint-09 plan called for `parcel_zonal_stats_dag` to pre-compute per-BUPI-parcel slope/elevation stats into `bronze_terrain.parcel_terrain_stats` (10,339 rows). That approach was rejected because (a) BUPI coverage has gaps (anywhere outside BUPI = no slope info), and (b) parcel-proxied stats are imprecise for arbitrary drawn polygons that don't align with parcel boundaries. Option C — on-the-fly raster computation via postgis_raster — gives exact stats per drawn polygon. The pre-aggregated `parcel_terrain_stats` table and its DAG were dropped after a one-time spot-check confirmed agreement within tolerance.

### Operational notes

- **`postgis.gdal_enabled_drivers`** must be set (PostGIS 3.x defaults to empty whitelist for security). Production sets `GTiff PNG JPEG` at the database level via `ALTER DATABASE ... SET postgis.gdal_enabled_drivers TO ...`; the DAG also issues `SET LOCAL` as belt-and-braces.
- **`raster2pgsql` not used**: the Airflow image lacks the binary. Instead the DAG reads raster bytes via Python and passes them to `ST_FromGDALRaster(bytea, 3763)` from PostGIS 3.4. Same end result, no Dockerfile rebuild.
- **No MinIO archive of slope COGs**: they're regenerable from MDT in ~25-40 min via DAG re-run. Saves ~490 MB in MinIO. If postgres dies + we need to rebuild, derive_terrain_dag is the recovery path.

### Pre-drop QA result (2026-06-03)

Before dropping `bronze_terrain.parcel_terrain_stats`, verified the new raster path agreed with the old parcel-proxy on 20 random Aveiro BUPI parcels:

| Metric | Result |
|---|---|
| Max absolute slope-mean diff | 0.069° |
| Median absolute diff | ~0.003° |
| Tolerance threshold | 0.5° |
| Verdict | PASS — raster path matches parcel proxy within numerical noise |

The small residual differences are attributable to nodata-handling differences between rasterio.zonal_stats (used in the old DAG) and PostGIS ST_Clip + ST_SummaryStatsAgg. The raster path is more correct for arbitrary drawn polygons (no parcel-snapping); the agreement on parcel queries confirms there's no upstream-data drift between the two methods.

## Quirks

- **Keycloak session cookie required**: `Airflow Variable DGT_CDD_COOKIE` must be set. **Manual refresh weekly** until v2 hardening (Phase 7+ candidate: programmatic cookie refresh via the Keycloak SSO flow). When the cookie expires, the DAG fails on the first 302; refresh the variable and re-run.
- **Server 302-redirects to MinIO presigned URL**: the STAC item endpoint redirects to a `stor-002.acnca.pt:9000` presigned URL. Our ingest follows the redirect, downloads the TIFF, and re-mirrors to our own MinIO. Belt-and-suspenders against the upstream MinIO going away.
- **2m resolution chosen deliberately** (per project decisions): 50cm rasters give sub-meter terrain detail at 14× the storage cost. 2m comfortably resolves typical Aveiro parcels (parcel widths ~10-30m). 50cm only matters for sub-parcel features (driveway slope, individual tree heights) — not Phase 1-5 use cases.
- **Float32 GeoTIFF, noDataValue=-999, native EPSG:3763**: standard for PT terrain rasters. No reprojection needed for spatial joins against [[bgri]], [[bupi]], [[caop]] — all native-PT-TM06.
- **DTM vs DSM in features**: DTM = bare-earth (terrain only); DSM = first-return (includes buildings + vegetation canopy). DSM-DTM = canopy/building height. Useful for "is this listing on a slope?" (DTM gradient) and "is the listing in a high-canopy area?" (DSM-DTM ≥ 5m).
- **Coverage extension is a future step**: 489 tiles ≈ Aveiro distrito. Expanding to the rest of PT means re-running with different STAC collections. Storage cost scales linearly.

## Last verified

2026-06-03 — sprint-09 WS4 PR A. Re-verified via live warehouse: 489 MDT manifests + 489 MDS manifests + 489 postgis_raster rows in `bronze_terrain.raster_lidar_slope_2m`. Confirmed `derive_terrain_dag` end-to-end on Aveiro município bbox. The previous sprint-09 claim "bronze never populated" was wrong — bronze had been populated (10,339 BUPI-keyed parcel stats + 489×3 manifests) but the wiki hadn't been refreshed. Resolved by silver-dq-baseline Rule 0 (schema discovery precedes derivation).
