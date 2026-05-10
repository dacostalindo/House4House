---
title: BUPI RGG — Simplified Cadastral Property Parcels
type: source
last_verified: 2026-05-08
tags: [gis, regulatory, government, cadastre, geopackage]
priority: P1
---

## For future Claude

This is a source page about BUPI RGG (Representação Gráfica Georreferenciada), the simplified cadastral property-parcel layer covering 152 PT municipalities. It documents the dados.gov.pt bulk-download ingest, the ~3.25M MultiPolygon parcel volume, and the auto-detect layer-name strategy that handles BUPI's date-stamped layer names. Read this page before editing [pipelines/gis/bupi/bupi_config.py](../../pipelines/gis/bupi/bupi_config.py).

## Source

- **Official name**: BUPI RGG — Balcão Único do Prédio, Representação Gráfica Georreferenciada
- **Owner**: government agency (cadastral authority, via dados.gov.pt portal)
- **Protocol**: GeoPackage bulk download (.zip → .gpkg) from dados.gov.pt permalink
- **Base endpoint**: `https://dados.gov.pt/pt/datasets/r/8dedcd3e-ba46-4f0f-a75f-36e0b327fc56` — STABLE permalink, redirects to current release
- **License**: open data (CC-BY)
- **Schedule**: monthly 5th 06:00 UTC (`0 6 5 * *`) — dados.gov.pt typically publishes 1st of month; 5-day buffer

## Schema

Bronze table: `bronze_regulatory.raw_bupi_parcels`.

- **ProcessoId** — BUPI internal property identifier (PK)
- **NumeroMatriz** — tax matrix number (links to Finanças tax records, useful for owner lookups in P2)
- **Dicofre** — 6-digit parish code (DT-CC-FF: distrito-concelho-freguesia); links to [[caop]]
- **Concelho, Freguesia** — denormalized administrative names
- **Area_m2** — parcel area
- **geometry** — MultiPolygon (parcels can be discontiguous), EPSG:3763 (PT-TM06)

## Quirks

- **~3.25M parcels covering 152 municipalities** in continental Portugal. NOT national coverage — 152 of 308 concelhos surveyed under BUPI. The remaining 156 are covered partially (or not at all) by [[cadastro]] (the older OGC-API cadastre, restricted to 2000-2007 surveys).
- **Auto-detect layer name**: BUPI's GeoPackage layer names embed the release date (e.g., `rgg_20260316_opendata`). Config uses `expected_layers=None` to auto-detect. No code change needed when dados.gov.pt publishes a new release — the permalink resolves to the latest, and the auto-detect adapts.
- **Validation**: file size ≥ 500 MB, feature count ∈ [2.5M, 5M]. Outside → fail.
- **Streaming download in 4 MB chunks** (RAM hygiene; the GeoPackage zip is ~600-900 MB and a naïve full-buffer read inflates Airflow worker memory significantly).
- **Batch INSERT at 5,000 rows**: the 3.25M parcel load takes ~30-45 minutes; smaller batch sizes inflated total time, larger batches risked tx-log pressure on PostGIS. 5k is the empirical sweet spot.
- **Cascade strategy when BUPI doesn't cover a concelho**: silver-layer logic falls back to [[cadastro]] for those concelhos. Listings in a concelho with neither BUPI nor Cadastro (rare) skip parcel-features and use only [[caop]]-level administrative geography.
- **Coverage gap vs [[cadastro]]**: BUPI is the modern simplified cadastre (post-2017 program); [[cadastro]] is the legacy formal cadastre (2000-2007 only). The two overlap in some concelhos; downstream silver-layer logic prefers BUPI (newer, broader) when both exist.
- **No detailed boundaries between adjacent parcels**: BUPI is "simplified" — parcel polygons may be approximate rather than survey-grade. For high-precision applications (e.g., dispute resolution), the formal [[cadastro]] survey takes precedence where available.
- **Cross-source role**: BUPI is THE spatial primitive for "what listing maps to what parcel." Listings ([[idealista]], etc.) have addresses; parcels have polygons. Spatial join via geocoded address → ProcessoId enables P2 features like neighbor-listing density, parcel-area normalization, etc.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read).
