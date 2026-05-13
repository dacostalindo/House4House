---
title: COS 2023 — Carta de Uso e Ocupação do Solo (OGC API)
type: source
last_verified: 2026-05-13
tags: [gis, government, landuse, ogc_api]
priority: P1
---

## For future Claude

This source page documents COS 2023 (Carta de Uso e Ocupação do Solo), DGT's national land-use/cover map, now served via the OGC API (`ogcapi.dgterritorio.gov.pt/collections/cos2023v1`). The legacy bulk-GeoPackage pipeline (`pipelines/gis/cos/`) was retired on 2026-05-13 in favor of the OGC API path (`pipelines/gis/cos_ogc/`) with an Aveiro distrito bbox filter for the v1 wedge. Read this page before editing [pipelines/gis/cos_ogc/cos_ogc_config.py](../../pipelines/gis/cos_ogc/cos_ogc_config.py) or before consuming `silver_geo.land_use` for the v1 wedge demo.

## Source

- **Official name**: COS 2023 v1 — Carta de Uso e Ocupação do Solo (Land Use/Cover Map)
- **Owner**: DGT — Direção-Geral do Território
- **Protocol**: OGC API Features (`cos2023v1` collection)
- **Base endpoint**: `https://ogcapi.dgterritorio.gov.pt/collections/cos2023v1/items`
- **License**: open data
- **Schedule**: manual trigger (low-frequency upstream changes; major COS releases every 2-5 years)
- **v1 wedge scope**: bbox-filtered to Aveiro distrito (`-8.764,40.528,-8.521,40.728` in EPSG:4326) → ~5-15k polygons of the national ~784k

## Schema

Bronze table: `bronze_geo.raw_cos_national_ogc`.

- **feature_id** (= OGC `objectid`) — integer feature ID
- **municipio** — municipality name (OGC-only, not in legacy GeoPackage)
- **nutsii**, **nutsiii** — NUTS region codes (OGC-only)
- **cos23_n4_c** — 4-level hierarchical land-use code (e.g., `1.1.1.1` = continuous vertical residential)
- **cos23_n4_l** — human-readable label for the n4 code
- **area_ha** — polygon area in hectares — **computed `ST_Area(geom) / 10000.0`** post-transform (NOT exposed by the OGC API as a property, unlike the legacy GeoPackage)
- **geom** — Polygon / MultiPolygon, EPSG:3763 (PT-TM06) — transformed from the OGC API's native EPSG:4326 on insert

## Quirks

- **OGC API serves geometries in EPSG:4326** — the bronze loader transforms to PT-TM06 on insert (same convention as crus_ogc / srup_ogc loaders).
- **No `AREA_ha` field on the OGC API** — computed by the bronze loader from `ST_Area(geom)/10000` post-transform.
- **Bbox filter for v1 wedge**: Aveiro distrito only. To ingest nationally, set `cfg.bbox_4326 = None` in `cos_ogc_config.py` and trigger the DAG; expect ~10-15 min vs ~30s for Aveiro.
- **4-level hierarchical code**: Level 1 = broad (e.g., 1=Artificial, 2=Agricultural, 3=Forest), Level 2-3 = progressive specialization, Level 4 = detailed (e.g., 1.1.1.1 = continuous vertical residential, 3.1.2.0 = mixed-leaf forest). Feature engineering for listings typically uses Level 1-2.
- **Versioning**: COS revisions release every ~5 years. The OGC API offers `cos2018v3` + `cos2023v1` + per-year cosc2018..cosc2023 variants; we use `cos2023v1` as the canonical latest.
- **Cross-source role**: COS overlaps thematically with [[crus-ogc]] (PDM land-use classification per municipality). The difference: COS is a national observation of actual land use ("what's there now, satellite-derived"); CRUS is a regulatory classification ("what's allowed by the municipal master plan"). They diverge — listing on COS-residential land that's CRUS-zoned-protected is a regulatory red flag.

## Retired 2026-05-13: legacy bulk-GeoPackage path

Until 2026-05-13, COS was ingested from a single ~700 MB GeoPackage download (`https://geo2.dgterritorio.gov.pt/cos/S2/COS2023/COS2023v1-S2-gpkg.zip`) via `pipelines/gis/cos/cos_*`. That path was deleted on 2026-05-13 — the OGC API publishes the same dataset with richer fields (adds `Municipio`, `NUTSII`, `NUTSIII`), and bbox-filtering for the v1 wedge takes ~30s vs ~5 min for the bulk download.

The legacy bronze table `bronze_geo.raw_cos2023` is NOT dropped from PostgreSQL — leave for ad-hoc historical queries. To physically drop: `DROP TABLE bronze_geo.raw_cos2023`. The dbt staging model name `stg_cos2023` is preserved (no need to rename downstream consumers); only its underlying source was redirected to `raw_cos_national_ogc`.

## See also

- [[crus-ogc]] — sibling regulatory land-use layer (what's allowed)
- [[caop]] — administrative boundaries (for the freguesia join in `silver_geo.land_use`)
- [[sprint-08]] — Activity 2 cleanup pass that retired the legacy path

## Last verified

2026-05-13 (OGC API migration; legacy GPKG path retired).
