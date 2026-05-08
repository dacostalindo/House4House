# Wiki Index

## For future Claude

This is the **catalog** of every wiki page — read it FIRST when answering any factual question or before any ingest. It has every page grouped by type (Overview / Sources / Concepts / Decisions / Plan) with a 1-line summary so Claude can grep + select the relevant pages without reading the whole wiki on every query. The `Last lint run:` line is the freshness indicator (updated by `/wiki-lint`); a stale date means lint hasn't fired recently and contradiction-detection coverage is degrading.

Last lint run: 2026-05-08

This is the catalog of every wiki page. Each entry has a 1-line summary. Updated on every ingest and on every weekly lint run.

## Overview

- [[overview]] — 1-page synthesis of the project from the root README's 16 sections; entry-point for orientation queries.

## Sources (23 pages)

### Real-estate portals (4)

- [[idealista]] — largest PT real-estate portal; ZenRows RE API + Universal Scraper mix; three coexisting streams (resale, developments+units, plots); SCD2 + heartbeat sidecars.
- [[jll]] — JLL Residential PT; dlt-driven SCD2 from imoguia.com proxy; plots deliberately excluded.
- [[remax]] — RE/MAX Portugal; unified dlt SCD2 (replaces legacy 3-DAG); Pass 2 enrichment pre-fetched in source.py; plots via sitemap walk.
- [[zome]] — Zome PT; dlt SCD2 from Supabase REST; soft-fail refs / hard-fail facts; curated row_hash to fix JSONB-array reorder.

### Statistical & financial APIs (4)

- [[ine]] — INE Statistics Portugal; 47 indicators (33 active) via JSON-stat 1.0; monthly cron.
- [[bpstat]] — Banco de Portugal stats; ~311 series, JSON-stat 2.0; housing credit + interest rates + housing prices.
- [[ecb]] — ECB Euribor 3M/6M/12M; SDMX REST; the simplest source in the stack.
- [[eurostat]] — Eurostat PRC_HPI_Q only; SDMX 2.1; quarterly cross-EU benchmark.

### Scraping (1)

- [[sce]] — SCE energy-certificate registry; only nodriver scraper; Cloudflare Turnstile; current scope Aveiro distrito.

### Regulatory + spatial GIS (14)

- [[caop]] — official administrative boundaries (distritos / municípios / freguesias); P0 foundation source.
- [[bupi]] — modern simplified cadastre; 152 concelhos, ~3.25M parcels.
- [[cadastro]] — legacy formal cadastre via OGC API; partial coverage (2000-2007 surveys only).
- [[cos]] — national land-use/cover map (COS 2023); ~784k polygons; 4-level hierarchical code.
- [[crus]] — legacy WFS land-use classification; 5 municipalities only; being replaced by [[crus-ogc]].
- [[crus-ogc]] — national CRUS via OGC API; ~236k features; dual-runs with [[crus]] for parity.
- [[srup]] — legacy WFS property constraints; Phase 1 categories (IC / RAN / DPH); being replaced by [[srup-ogc]].
- [[srup-ogc]] — modern OGC API for SRUP + SGIFR; 22 layers; per-layer page_size/timeout overrides.
- [[apa]] — APA ARPSI floodplain; EU Floods Directive scope (NOT all flood zones); ~188 polygons national.
- [[bgri]] — INE Census 2021 statistical geography; 32 variables across 4 themes; subsections + sections.
- [[lidar]] — DGT 2m DTM + DSM rasters; STAC Collections; Aveiro region; manifest tables in bronze.
- [[lneg]] — LNEG geology 1:500k + national aquifers; ArcGIS REST.
- [[osm]] — OpenStreetMap PT via Geofabrik; 18 layers, ~4.5M features; companion OSRM + Nominatim services.
- [[aveiro-pmot]] — Aveiro municipal WebGIS bulk WMS-GFI extractor; one-off, not a recurring DAG; ~1,669 feature types.

## Concepts (8 pages)

- [[bronze-permissive]] — bronze accepts whatever the source returns; validation lives in dbt staging; never-delete invariant.
- [[pydantic-not-in-dlt]] — Pydantic in configs YES, in dlt resources NO; the strict guardrail protecting [[bronze-permissive]].
- [[scd2-row-hash]] — curated `*_VERSION_COLUMNS` policy for SCD2 row versioning; include real business events, exclude noisy proxies.
- [[heartbeat-sidecar]] — UPSERT-only companion table answering "is this entity still in the source?"; the 21-day silver-layer floor.
- [[zenrows-universal-vs-re-api]] — [[idealista]]'s mixed-API scrape strategy; ~5× cheaper RE API + Universal Scraper for HTML pages.
- [[payload-cache-lifecycle]] — module-level `_payload_cache` shared across [[idealista]]'s four resources; saves ~85% of ZenRows spend per run.
- [[medallion-layering]] — bronze/silver/gold + per-source-bronze-schema architecture; transformation-placement rules.
- [[airflow-home-isolation]] — the `~/airflow/airflow.cfg` bleed gotcha + `make verify`'s `AIRFLOW_HOME=$(PWD)/.airflow-home` fix.

## Decisions (5 ADRs)

- [[2026-05-05-uv-workspace-shape]] — single root pyproject + apps/pipelines workspace members; one lockfile.
- [[2026-05-05-cosmos-pin]] — `astronomer-cosmos>=1.6,<1.7` because 1.7+ imports `airflow.sdk` (Airflow-3-only).
- [[2026-05-08-sqla-1.4-concession]] — apps/ accepts workspace-wide SQLA 1.4 (Airflow 2.10 forces <2.0; apps had zero SQLA code).
- [[2026-05-08-phase-2-5-closure]] — Phase 2.5 absorbed into Phase 2 (zero Pydantic-eligible sites surfaced by audit).
- [[2026-05-08-idealista-enrichment-architecture]] — three coexisting streams; Phase 5 enrichment writes to silver, not bronze.

## Plan

Plan content arrives iteratively across PR 3+ alongside README-derived ADRs (PostGIS-as-warehouse, MinIO-not-S3, etc.). Recommended sequencing:

| PR | Content | Pages |
|---|---|---|
| 3 | `plan/sprints/*` | ~11 |
| 4 | `plan/use-cases/*` | 3 |
| 5 | `plan/sources-by-priority/*` | 3 |
| 6 | `plan/data-flows/*` | 6 |
| 7 | `plan/conceptual-models/*` | 3 |
| 8 | Single-page topics: tech-stack, infra, data-quality, risks, resources, roadmap-p3-p4 | 6 |

- [[plan/README|Plan section overview]] — orientation for the strategic-roadmap decomposition; sub-section content arrives iteratively in PR 3+.
