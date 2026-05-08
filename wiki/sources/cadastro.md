---
title: Cadastro Predial — OGC API
type: source
last_verified: 2026-05-08
tags: [gis, regulatory, government, cadastre, ogc-api]
---

## For future Claude

This is a source page about Cadastro Predial, the legacy formal cadastre served via OGC API Features. It documents the paginated GeoJSON ingest, the deliberate API-only strategy (no bulk GeoPackage exists), and the partial coverage limitation (only municipalities surveyed 2000-2007). Read this page before editing [pipelines/gis/cadastro/cadastro_config.py](../../pipelines/gis/cadastro/cadastro_config.py) or its DAG.

## Source

- **Official name**: Cadastro Predial — formal property cadastre
- **Owner**: government agency (DGTERRITÓRIO — Direção-Geral do Território)
- **Protocol**: OGC API Features REST (paginated GeoJSON)
- **Base endpoint**: `https://ogcapi.dgterritorio.gov.pt/collections/cadastro/items`
- **License**: CC-BY 4.0
- **Schedule**: manual trigger (low-frequency upstream changes; old surveys, no new ingest cadence)

## Schema

Bronze table: `bronze_regulatory.raw_cadastro`.

- **nationalcadastralreference** — unique cadastral ID (e.g., `AAA000338225`)
- **areavalue** — parcel area in m²
- **administrativeunit** — 6-digit DTCC code (links to [[caop]])
- **inspireid** — INSPIRE-compliant identifier (EU directive)
- **beginlifespanversion** — temporal validity start (parcel could have been re-surveyed since)
- **geometry** — MultiPolygon, EPSG:3763 (PT-TM06)

## Quirks

- **Partial coverage — IMPORTANT**: only municipalities surveyed between 2000 and 2007. Most of PT was NEVER surveyed under this regime; [[bupi]] is the modern (post-2017, simplified) replacement covering 152 concelhos. Reporting that says "find me the parcel for this listing" must check both sources and merge.
- **OGC API only** (no bulk GeoPackage): unlike [[cos]] and [[caop]] which offer bulk downloads, Cadastro is API-only. Pagination at `PAGE_SIZE=1000`, `rate_limit=2.0s`, full-fetch takes ~time.
- **No incremental fetch**: the OGC API doesn't expose a `since` filter. Each run re-fetches from scratch. dlt write-disposition is full-replace.
- **INSPIRE compliance**: schema follows the EU INSPIRE Cadastral Parcels theme (https://inspire.ec.europa.eu/Themes/Data-Specifications/2892). Field names are standardized across EU countries — useful for cross-border tooling that targets multiple cadastres. Notable INSPIRE fields: `nationalcadastralreference`, `inspireid`, `beginlifespanversion`.
- **Cross-source role**: see [[bupi]] for the comparison. Cadastro is older, more rigorous, smaller coverage. BUPI is newer, simplified, broader coverage. Silver-layer logic prefers BUPI when both have a parcel for the same address; falls back to Cadastro when BUPI doesn't cover the concelho.
- **OGC API pagination quirk**: per the recent commit on `cadastro_ingestion_dag.py` (May 8), pagination state is preserved across retries; if the DAG resumes mid-fetch, it continues from the last completed page rather than restarting.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read; recent DAG modifications reflected).
