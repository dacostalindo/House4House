---
title: CRUS National OGC API
type: source
last_verified: 2026-05-08
tags: [gis, regulatory, government, landuse, ogc-api]
priority: P1
---

## For future Claude

This is a source page about CRUS via OGC API Features — the national-coverage successor to the legacy per-município [[crus]] WFS path. It documents the paginated GeoJSON ingest (~236,920 features), the dual-run validation strategy with the WFS legacy, and the richer typed schema vs. WFS's diacritic-laden columns. Read this page before editing [pipelines/gis/crus_ogc/crus_ogc_config.py](../../pipelines/gis/crus_ogc/crus_ogc_config.py).

## Source

- **Official name**: CRUS National (Carta do Regime de Uso do Solo, OGC API Features)
- **Owner**: government agency (DGTERRITÓRIO)
- **Protocol**: OGC API Features REST (paginated GeoJSON)
- **Base endpoint**: `https://ogcapi.dgterritorio.gov.pt/collections/crus/items`
- **License**: open data (CC-BY)
- **Schedule**: manual trigger
- **Status**: replaces the per-município [[crus]] WFS path; dual-run during validation, after parity holds the WFS pipeline is decommissioned

## Schema

Bronze table: `bronze_regulatory.raw_crus_national_ogc`.

- **classe_2021, categoria_2021** — typed land-use classification columns (no JSONB unpacking needed; CRUS WFS returned these inside a generic attributes blob)
- **escala_origine** — source scale of the underlying PDM (1:10000, 1:25000, etc.)
- **designacao** — full regulatory designation
- **area_ha** — hectares
- **geometry** — Polygon, EPSG:3763 (PT-TM06)
- Plus 10+ additional typed fields the WFS path didn't expose

## Quirks

- **~236,920 national features**: PAGE_SIZE=200 (~1185 pages); rate_limit 0.5s, request_timeout 300s. Full fetch takes ~10-15 minutes.
- **National coverage** vs. [[crus]]'s 5-municipality scope: this is the strategic upgrade — once parity validates, listing-feature engineering can join CRUS for any concelho instead of just Aveiro/Lisboa/Porto/Coimbra/Leiria.
- **Dual-run parity validation**: a dbt macro at `dbt/macros/gis_dual_run_count_parity.sql` compares the 5-municipality OGC subset against the legacy WFS bronze. Equality on feature counts + bounding-box centroids = parity confirmed.
- **Richer schema than WFS**: typed columns directly on features. No `dbt-postgres unpack JSONB → cast → rename` toil per [[medallion-layering]] silver layer.
- **No incremental fetch**: full re-fetch each run. dlt write-disposition is full-replace.
- **Cross-source role**: see [[crus]] for the regulatory-classification narrative. OGC version is strictly better than WFS version (national coverage, richer schema, fewer normalization quirks).

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read; new pipeline post-PR 1 work).
