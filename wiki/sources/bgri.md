---
title: BGRI Census 2021 — INE Statistical Geography
type: source
last_verified: 2026-05-08
tags: [gis, statistics, government, census, geopackage]
---

## For future Claude

This is a source page about BGRI 2021 (Base Geográfica de Referenciação de Informação), [[ine]]'s statistical geography grid for Census 2021. It documents the GeoPackage bulk-download ingest, the two-level grid (subsections ~120-200k polygons / sections ~20-40k), and the 32 census variables across 4 thematic groups. Read this page before editing [pipelines/gis/bgri/bgri_config.py](../../pipelines/gis/bgri/bgri_config.py).

## Source

- **Official name**: BGRI 2021 — Base Geográfica de Referenciação de Informação (Census 2021 statistical geography)
- **Owner**: government agency ([[ine]] — INE, the same agency behind the statistical-API source)
- **Protocol**: GeoPackage bulk download (.zip → .gpkg)
- **Base endpoint**: `https://mapas.ine.pt/download/filesGPG/2021/BGRI21_CONT.zip`
- **License**: open data (CC-BY)
- **Schedule**: manual trigger — Census 2021 is static (next refresh is 2031)
- **Coverage**: continental Portugal only (Madeira and Açores out of scope for MVP per the configured download URL)

## Schema

Bronze tables:
- `bronze_statistics.raw_bgri_subsections` — finest-grain (statistical subsection, ~120k-200k polygons)
- `bronze_statistics.raw_bgri_sections` — coarser (statistical section, ~20k-40k polygons)

**32 variables across 4 thematic groups**:
- **Buildings** (12 vars): stock count, typology, floor count, construction period, repair needs, etc.
- **Dwellings** (8 vars): occupancy status, dwelling-type breakdown
- **Households** (5 vars): composition, size
- **Population** (7 vars): age groups, sex breakdown

Geometry: Polygon, EPSG:3763 (PT-TM06).

## Quirks

- **Layer names unknown until first inspection**: the config uses `expected_layers=None` so the validator logs all available layers without hard-failing on missing names. After the first run, read the Airflow task logs to update `expected_layers`. Defensive default — INE has shipped GeoPackages with subtle layer-name drift across releases.
- **Validation bands**: file size ≥ 50 MB, feature count ∈ [1, 500k]. Outside → fail.
- **Census 2021 is static**: re-running the DAG yields no new data. The "manual trigger" schedule reflects this. Set up a Census-2031 reminder (TODO) to re-run when INE publishes the next round.
- **What's NOT in BGRI** (intentionally; available via [[ine]] API as P1 supplements):
  - Education attainment
  - Employment status
  - Foreign-born percentage
  - Income distribution
- **Cross-source role**: BGRI is the spatial backbone for joining listing-level data ([[idealista]], [[remax]], etc.) to demographic context. Each listing's geocoordinate maps to a subsection; subsection joins to the 32 vars; downstream features like "% young families in walking distance" become possible per [[medallion-layering]] silver/gold layers.
- **PT-TM06 (EPSG:3763)**: native CRS of all PT regulatory GIS sources. Listing geocoords from portals are typically WGS84 (EPSG:4326) and need reprojection in dbt staging for spatial joins.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read).
