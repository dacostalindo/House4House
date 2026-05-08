---
title: CAOP — Carta Administrativa Oficial de Portugal
type: source
last_verified: 2026-05-08
tags: [gis, regulatory, government, administrative, geopackage]
---

## For future Claude

This is a source page about CAOP, the canonical administrative-boundary layer for Portugal (distritos, municípios, freguesias). It documents the manual-trigger bulk GeoPackage ingest with per-release URL parameters, the runtime layer-name computation, and CAOP's role as the spatial dimension for nearly every other GIS source in the stack. Read this page before editing [pipelines/gis/caop/caop_config.py](../../pipelines/gis/caop/caop_config.py).

## Source

- **Official name**: CAOP — Carta Administrativa Oficial de Portugal (Official Administrative Map of Portugal)
- **Owner**: government agency (DGT — Direção-Geral do Território)
- **Protocol**: GeoPackage bulk download (.gpkg or .zip → .gpkg)
- **Base endpoint**: supplied at trigger time as `download_url` parameter (DGT release-specific URL; no permalink)
- **License**: open data
- **Schedule**: manual trigger only (annual release cadence, no fixed publication date)

## Schema

Three bronze tables (one per administrative level):

- `bronze_regulatory.raw_caop_distritos` — ~18 distritos (continental + Madeira + Açores)
- `bronze_regulatory.raw_caop_municipios` — ~308 municípios (concelhos)
- `bronze_regulatory.raw_caop_freguesias` — ~3,091 freguesias (parishes)

Each table: boundary polygons + names + Dicofre codes (DT, DT-CC, DT-CC-FF respectively) + administrative-hierarchy fields. Geometry: Polygon, EPSG:3763 (PT-TM06).

## Quirks

- **Manual trigger with params**: trigger from Airflow UI passing `version` (e.g., `2024.0`) and `download_url`. NO code change needed between annual releases — config reads params at runtime via `layer_name_fn`.
- **Layer names embed version**: e.g., `cont_distritos_2024_0`, `cont_municipios_2024_0`. `expected_layers` is empty; `layer_name_fn` computes the right names from the trigger param. Defensive against DGT's naming-convention drift across releases.
- **Validation**: file size ≥ 10 MB, feature count ∈ [10, 5000] per layer. Wide bands accommodate distrito (18) vs freguesia (3091).
- **Annual cadence is the upstream norm but not strict**: DGT sometimes skips a year, sometimes ships mid-year corrections. Each new release should trigger a manual run.
- **PT-TM06 native**: matches [[bgri]], [[apa]], [[srup-ogc]], etc. CAOP is the "ground truth" CRS for the regulatory-GIS stack.
- **Cross-source role — central**: CAOP is the spatial dimension that nearly every other source links to. [[idealista]] uses concelho IDs from CAOP; [[bgri]] census subsections nest within freguesias; [[cadastro]] / [[bupi]] administrative_unit fields reference CAOP municipios. Updating CAOP requires a downstream review of dim_geography in dbt staging.
- **Continental + islands**: CAOP includes Madeira and Açores. Most other sources are continental-only ([[bgri]], [[bupi]] notably). Be mindful when joining: a continental-only source against full-CAOP produces island concelhos with no listings/parcels.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read).
