---
title: COS 2023 — Carta de Uso e Ocupação do Solo
type: source
last_verified: 2026-05-08
tags: [gis, regulatory, government, landuse, geopackage]
---

## For future Claude

This is a source page about COS 2023 (Carta de Uso e Ocupação do Solo), DGT's national land-use/cover map. It documents the bulk GeoPackage ingest, the ~784k polygons with hierarchical 4-level land-use codes, and the role as the canonical "what is this land used for" layer. Read this page before editing [pipelines/gis/cos/cos_config.py](../../pipelines/gis/cos/cos_config.py).

## Source

- **Official name**: COS 2023 v1 — Carta de Uso e Ocupação do Solo (Land Use/Cover Map)
- **Owner**: government agency (DGT — Direção-Geral do Território)
- **Protocol**: GeoPackage bulk download (.zip → .gpkg)
- **Base endpoint**: `https://geo2.dgterritorio.gov.pt/cos/S2/COS2023/COS2023v1-S2-gpkg.zip`
- **License**: open data
- **Schedule**: manual trigger (low-frequency upstream changes; major COS releases every 2-5 years)

## Schema

Bronze table: `bronze_landuse.raw_cos_2023`.

- **ID** — feature ID
- **COS23_n4_C** — 4-level hierarchical land-use code (e.g., `1.1.1.1` = continuous vertical residential)
- **COS23_n4_L** — human-readable label for the n4 code
- **AREA_ha** — polygon area in hectares
- **geometry** — Polygon, EPSG:3763 (PT-TM06)

## Quirks

- **~784k polygons** (continental Portugal). Single GeoPackage download, no pagination.
- **4-level hierarchical code**: Level 1 = broad (e.g., 1=Artificial, 2=Agricultural, 3=Forest), Level 2-3 = progressive specialization, Level 4 = detailed (e.g., 1.1.1.1 = continuous vertical residential, 3.1.2.0 = mixed-leaf forest). Listing-feature engineering uses Level 1-2 typically (granularity matters less than presence-of-class within a buffer).
- **Layers in the GeoPackage**: `COS2023v1` (the data layer we ingest); `layer_styles` (QGIS styling metadata, ignored — we don't carry visual styles into the data warehouse).
- **Validation**: file size ≥ 50 MB, feature count ∈ [500k, 1.5M].
- **Versioning**: COS revisions release every ~5 years (COS 2018, COS 2023, next expected ~2028). Each is its own bronze table; downstream gold layer joins on the most recent. Old versions retained for trend analysis (land-use change between releases is a useful signal — converting agricultural to residential, etc.).
- **Level-1-vs-Level-2 granularity guidance**: feature engineering for listings typically uses Level 1 (Artificial / Agricultural / Forest / Water) or Level 2 (within Artificial: Residential / Industrial / Mining / etc.). Level 4 has 200+ classes and produces sparse features. Use deeper levels only when a specific use case demands it (e.g., "is this listing in a vineyard region?").
- **Cross-source role**: COS overlaps thematically with [[crus]] / [[crus-ogc]] (PDM land-use classification per municipality). The difference: COS is a national observation of actual land use ("what's there now, satellite-derived"); CRUS is a regulatory classification ("what's allowed by the municipal master plan"). They diverge — listing on COS-residential land that's CRUS-zoned-protected is a regulatory red flag.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read).
