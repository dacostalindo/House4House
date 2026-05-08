---
title: APA ARPSI — Floodplain (EU Floods Directive)
type: source
last_verified: 2026-05-08
tags: [gis, regulatory, government, hydrology, arcgis-rest]
---

## For future Claude

This is a source page about APA's ARPSI (Áreas de Risco Potencial Significativo de Inundação) floodplain layer. It documents the ArcGIS REST FeatureServer ingest with server-side reprojection to EPSG:3763, the small national footprint (~188 polygons), and the critical caveat that ARPSI is the EU Floods Directive scope — NOT a complete national floodable-areas map. Read this page before editing [pipelines/gis/apa/apa_config.py](../../pipelines/gis/apa/apa_config.py).

## Source

- **Official name**: APA ARPSI — Áreas de Risco Potencial Significativo de Inundação (Floodplain)
- **Owner**: government agency (Agência Portuguesa do Ambiente — environment agency)
- **Protocol**: ArcGIS REST FeatureServer (server-side reprojection to EPSG:3763 = PT-TM06)
- **Base endpoint**: `https://services9.arcgis.com/heNM9t1Uq1GNOWAW/arcgis/rest/services/ARPSI/FeatureServer/0`
- **License**: open data
- **Schedule**: manual trigger (low-frequency upstream changes; ARPSI is reviewed every 6 years per EU directive cycle)

## Schema

Bronze table: `bronze_hydrology.raw_apa_arpsi_floodplain`.

- **OBJECTID** — ArcGIS internal feature ID
- **RHidro** — hydrographic region (PTRH4A = Vouga sub-basin, etc.)
- **Local, Designa, Fonte, Data** — descriptive fields (location, designation, data source, date)
- **TRetorno** — RETURN PERIOD (T100 = 100-year flood, T1000 = 1000-year flood). KEY field for flood_class downstream classification per [[medallion-layering]].
- **GEOCOD** — geocode reference
- **geometry** — Polygon, EPSG:3763 (PT-TM06) — server returns reprojected, no client-side transform needed

## Quirks

- **188 polygons nationally** (~18 in Aveiro município, all T100/T1000 in PTRH4A Vouga sub-basin). Single request fetches the full set (PAGE_SIZE=2000 ≥ server's maxRecordCount); no pagination logic needed.
- **Coverage caveat — IMPORTANT**: ARPSI is the EU Floods Directive scope (the 188 highest-priority floodable polygons identified for risk-management planning). It is NOT a complete national floodable-areas map. Areas not in ARPSI may still flood. Downstream UI must label this layer as "EU-priority floodplains" not "all flood zones" to avoid misleading users.
- **TRetorno semantics**: T100 = ~1% annual exceedance probability, T1000 = ~0.1% annual exceedance probability. PT typical risk classification combines T100 (planning constraint) and T1000 (catastrophe scenario).
- **Cross-source role**: APA ARPSI overlaps thematically with [[srup-ogc]]'s REN areal layer (which includes ecological reserves AND some flood-prone areas). [[2026-05-08-idealista-enrichment-architecture]] discusses how the two layers compose for "is-this-listing-flood-exposed" feature engineering.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read).
