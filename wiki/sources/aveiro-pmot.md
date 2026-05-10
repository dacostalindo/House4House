---
title: Aveiro PMOT — Municipal WebGIS Bulk Extractor
type: source
last_verified: 2026-05-08
tags: [gis, regulatory, municipality, bulk-extractor, wms, gfi]
priority: P2
---

## For future Claude

This is a source page about Aveiro PMOT, a one-off bulk WMS-GetFeatureInfo extractor for the Aveiro municipality public WebGIS at `smiga.cm-aveiro.pt`. Different shape from the other GIS sources: NOT a recurring DAG, NOT registered with the medallion bronze-loader pattern. It's a disk-first extraction tool that pulls every WMS-published feature type to local GeoJSON, ready for a future PostGIS load. Read this page when extending Aveiro municipal-zoning coverage that DGT/SNIT doesn't publish authoritatively.

## Source

- **Official name**: Aveiro PMOT (Plano Municipal de Ordenamento do Território — Municipal Master Plan)
- **Owner**: municipality (Aveiro Câmara Municipal — local council; data published via the MunWebGIS ASP.NET viewer proxying a standard GeoServer)
- **Protocol**: WMS GetFeatureInfo (1×1 px click, large BUFFER, per-layer BBOX walk with quadrant recursion up to depth 6)
- **Base endpoint**: `http://smiga.cm-aveiro.pt/geomap/wms`
- **Discovery endpoint**: `http://smiga.cm-aveiro.pt/geomap/wfs?request=GetCapabilities` (open; ~1 MB XML; ~1,669 feature types)
- **License**: public PMOT cartography (publication mandated by RJIGT — Regime Jurídico dos Instrumentos de Gestão Territorial)
- **Schedule**: manual / on-demand (one-off extractor, not a recurring DAG)

## Schema

Output format: GeoJSON snapshot per layer, written to disk under `{workspace}/{feature_type}.geojson` + accompanying `{feature_type}.meta.json`.

Per layer, the GeoJSON contains the full attribute set + geometry returned by the GFI endpoint — schema varies per layer (Aveiro publishes plantas de ordenamento, plantas de condicionantes, infrastructure layers, environmental constraints, etc.).

**Phase 2 (planned, not yet implemented)**: PostGIS load via the [pipelines/gis/template](../../pipelines/gis/template/) `gpkg_bronze_template` pattern. Would land each layer as `bronze_aveiro.raw_pmot_<layer>` after `ogr2ogr` conversion.

## Quirks

- **Why GFI instead of WFS GetFeature**: WFS `GetFeature` is gated (HTTP 401 — auth required); WMS `GetFeatureInfo` is open. The viewer's identify tool calls GFI anonymously, so we replicate that pattern programmatically. NOT scraping in the adversarial sense — using the same public anonymous endpoint the viewer itself uses.
- **Two-stage workflow**:
  1. **Discover**: `python -m pipelines.gis.aveiro_pmot.discover` → fetches WFS GetCapabilities → builds `manifest.json` listing all available feature types.
  2. **Pull**: per-layer GFI walk with quadrant recursion (up to depth 6 = 4^6 = 4,096 click points per layer max). Each click returns features near that point; aggregation deduplicates.
- **Rate-limited to 1 req/s** by default. Identifies as `House4House/1.0 (manuelcostalindo@gmail.com)` in User-Agent — accountable scraping, not stealth.
- **Output persists across sessions**: each layer writes its GeoJSON + meta. A re-run skips layers already at `status=ok` in their meta — re-runs are safe and resumable. Useful for the long tail of 1,669 feature types where a network blip mid-walk doesn't restart the world.
- **Leaflet viewer** included (`pipelines/gis/aveiro_pmot/viewer.py`): renders the extracted layers locally for sanity-checking before promoting to PostGIS.
- **Ethics + ToS posture**: data is public (RJIGT-mandated publication); we respect robots.txt + Aveiro CM terms of use. If the server returns sustained 429/403, stop and email the SIG team. Prefer authoritative sources from SNIT/DGT where they exist; this scraper covers gaps where SNIT doesn't have the layer.
- **One-off, not registered**: this pipeline does NOT follow the auto-discovered `<source>_ingestion_dag.py` pattern that other GIS sources use. It lives in `pipelines/gis/aveiro_pmot/` as a callable module, not an Airflow DAG. Treat it as a tool, not a pipeline.
- **Cross-source role**: complements [[crus-ogc]] / [[srup-ogc]] / [[caop]] for the Aveiro município specifically. PMOT is the FULL set of municipal master-plan layers; the regulatory-GIS stack covers a subset (CRUS = land-use classification, SRUP = constraints, CAOP = administrative boundaries). For Aveiro-specific zoning analysis (where Phase 1 use cases live), PMOT layers fill the gap.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — README cross-checked; corrects earlier exclusion based on missing `*_config.py` / `*_dag.py`).
