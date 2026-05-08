---
title: RE/MAX Portugal
type: source
last_verified: 2026-05-08
tags: [portal, real-estate, dlt, scd2, two-pass]
---

## For future Claude

This is a source page about RE/MAX Portugal. It documents the unified dlt-driven SCD2 pipeline (replaced the legacy three-DAG topology), the parallel Pass 2 enrichment pre-fetched in `source._prefetch_pass2()`, and the listings/developments/plots tri-fact bronze layout. Read this page before editing [pipelines/portals/remax/remax_dlt_dag.py](../../pipelines/portals/remax/remax_dlt_dag.py) or its source module.

## Source

- **Official name**: RE/MAX Portugal
- **Owner**: RE/MAX International (private franchise network; ~50% of real-estate transactions in PT through its agents)
- **Protocol**: dlt + REST JSON — proprietary Next.js API (PaginatedSearch + per-listing detail endpoints)
- **Base endpoint**: `https://www.remax.pt` (Next.js API surface)
- **License**: proprietary; public listing endpoints
- **Schedule**: weekly Tuesdays 06:00 UTC (`0 6 * * 2`)
- **Source pattern**: dlt with SCD2 write-disposition, per [[scd2-row-hash]]

## Schema

Three SCD2 fact tables (the most comprehensive portal coverage in our stack: listings + developments + plots):

- `bronze_listings.remax_listings` — listings SCD2; includes `market_days` (Pass 2 enrichment marker), `_dlt_valid_to` (NULL = current row)
- `bronze_listings.remax_developments` — new-build developments SCD2
- `bronze_listings.remax_plots` — land/plot inventory SCD2 (one of only ~3 portal sources for plots; [[zome]] and [[idealista]] also)

Plus per-listing heartbeat sidecars (per [[heartbeat-sidecar]]).

## Quirks

- **Two-pass enrichment** (per [[zenrows-universal-vs-re-api]]): Pass 1 = PaginatedSearch (bulk listings, ~3,900 results). Pass 2 = parallel Next.js detail fetch at ~4 req/s (~15-20 min total). Pass 2 details are pre-fetched inside `source._prefetch_pass2()` BEFORE the SCD2 merge runs, so SCD2 sees a single denormalized row per listing.
- **Validation bands**: `listings` ∈ [3k, 30k]; `developments` ∈ [200, 2k]; `pass2_enriched` ∈ [1k, 15k]; `plots` ∈ [5k, 25k]. Outside bands → DAG fails.
- **Legacy three-DAG decommissioned**: prior topology (separate listings DAG, separate developments DAG, separate plots DAG) was replaced by the unified `remax_dlt_dag.py`. References to `remax_listings_dag`, `remax_developments_dag`, `remax_plots_dag` in old commits are historical.
- **Audit copy on Pass 1 only**: raw JSON from PaginatedSearch is mirrored to MinIO under `audit/remax/<date>/`. Pass 2 details are NOT mirrored (too granular; ~3,900 small JSONs would inflate audit storage with no benefit).
- **Schema-contract hard-fail**: same pattern as [[jll]] — dlt's schema-contract enforcement blocks the load_facts task on shape drift.
- **Cookie auth**: Next.js endpoint occasionally requires a session cookie warm-up; `source.py` handles the bootstrap automatically.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — DAG re-read against the unified-pipeline state).
