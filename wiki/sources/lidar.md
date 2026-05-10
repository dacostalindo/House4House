---
title: DGT LiDAR Aveiro (2m DTM & DSM)
type: source
last_verified: 2026-05-08
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
- **Coverage**: currently Aveiro region only (489 tiles per collection, 2 collections = 978 tiles total)

## Schema

Two manifest tables (bronze stores manifests pointing to MinIO-mirrored TIFFs, NOT the raster bytes themselves):

- `bronze_terrain.raw_lidar_mdt_2m_manifest` — MDT-2m (bare-earth Digital Terrain Model)
- `bronze_terrain.raw_lidar_mds_2m_manifest` — MDS-2m (first-return Digital Surface Model — includes buildings + vegetation)

Per-tile manifest row:
- **tile_id** — STAC item identifier
- **footprint** — Polygon, EPSG:3763 PT-TM06 (tile bounding box)
- **minio_object** — `s3://lidar/<collection>/<tile_id>.tif` path
- **version, datetime** — STAC item version + timestamp
- **file_size_bytes** — for sanity checks

The actual raster files (~1 MB each, ~490 MB per collection) live in MinIO. Downstream pipelines stream them on demand.

## Quirks

- **Keycloak session cookie required**: `Airflow Variable DGT_CDD_COOKIE` must be set. **Manual refresh weekly** until v2 hardening (Phase 7+ candidate: programmatic cookie refresh via the Keycloak SSO flow). When the cookie expires, the DAG fails on the first 302; refresh the variable and re-run.
- **Server 302-redirects to MinIO presigned URL**: the STAC item endpoint redirects to a `stor-002.acnca.pt:9000` presigned URL. Our ingest follows the redirect, downloads the TIFF, and re-mirrors to our own MinIO. Belt-and-suspenders against the upstream MinIO going away.
- **2m resolution chosen deliberately** (per project decisions): 50cm rasters give sub-meter terrain detail at 14× the storage cost. 2m comfortably resolves typical Aveiro parcels (parcel widths ~10-30m). 50cm only matters for sub-parcel features (driveway slope, individual tree heights) — not Phase 1-5 use cases.
- **Float32 GeoTIFF, noDataValue=-999, native EPSG:3763**: standard for PT terrain rasters. No reprojection needed for spatial joins against [[bgri]], [[bupi]], [[caop]] — all native-PT-TM06.
- **DTM vs DSM in features**: DTM = bare-earth (terrain only); DSM = first-return (includes buildings + vegetation canopy). DSM-DTM = canopy/building height. Useful for "is this listing on a slope?" (DTM gradient) and "is the listing in a high-canopy area?" (DSM-DTM ≥ 5m).
- **Coverage extension is a future step**: 489 tiles ≈ Aveiro distrito. Expanding to the rest of PT means re-running with different STAC collections. Storage cost scales linearly.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read; new pipeline post-PR 1 work).
