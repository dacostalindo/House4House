---
title: Zome PT
type: source
last_verified: 2026-05-08
tags: [portal, real-estate, dlt, scd2]
priority: P1
---

## For future Claude

This is a source page about Zome Portugal. It documents the dlt-driven SCD2 ingest from Zome's Supabase REST API, the soft-fail strategy for ref tables (vs. hard-fail for facts), and the deliberate non-wiring of dlt's SCD2 boundary_timestamp (backfill not yet supported). Read this page before editing [pipelines/portals/zome/zome_dlt_dag.py](../../pipelines/portals/zome/zome_dlt_dag.py).

## Source

- **Official name**: Zome PT
- **Owner**: Zome (private real-estate portal; mid-sized PT player)
- **Protocol**: dlt + Supabase REST API
- **Base endpoint**: `https://supabase.zome.pt/rest/v1/{tab_ventures,tab_listing_list,...}`
- **License**: proprietary; public API surface
- **Schedule**: weekly Mondays 06:00 UTC (`0 6 * * 1`) — matches Zome's upstream refresh
- **Source pattern**: dlt with SCD2 write-disposition, per [[scd2-row-hash]]

## Schema

Three SCD2 fact tables + soft-fail ref tables:

- `bronze_listings.zome_listings` — SCD2 with `_dlt_valid_from`/`_dlt_valid_to`
- `bronze_listings.zome_developments` — SCD2 (new-build developments)
- `bronze_listings.zome_plots` — SCD2 (land/plot inventory; one of three portal sources for plots)
- 3 small ref tables (lookup dimensions) — load via `trigger_rule=all_done`, soft-fail (logs but does NOT block facts load)

Per-entity heartbeat sidecars (per [[heartbeat-sidecar]]).

## Quirks

- **Soft-fail refs, hard-fail facts**: ref tables (small lookups) load with `trigger_rule=all_done` — schema drift on a ref is logged but doesn't fail the run. Facts (listings/developments/plots) hard-fail on schema-contract violation. Asymmetry is intentional: a missing ref entry produces a join miss in dbt staging (visible), whereas a missing fact row pollutes downstream silently.
- **Curated `row_hash` instead of dlt's auto-hash** (per [[scd2-row-hash]]): Zome's Supabase reorders JSONB arrays (gallery, video, etc.) between calls. Auto-hashing on the full row creates spurious SCD2 versions every week even when nothing changed semantically. Curated hash only includes stable fields → fixes the false-version problem.
- **Plot-specific version columns**: a separate `PLOTS_VERSION_COLUMNS` set excludes `areautilhab` and `areabrutaconst` (housing-only fields) from the row-hash for the plots SCD2 — those fields are NULL on plots and including them would produce no useful version signal.
- **Validation bands**: `listings` ∈ [1k, 50k]; `developments` ∈ [50, 1k]; `plots` ∈ [500, 5k]. Outside bands → fail.
- **No backfill yet**: dlt's SCD2 `boundary_timestamp` parameter (which would let `_dlt_valid_from` be set to a past date for historical replays) is intentionally NOT wired. Day 0 = today; previous scrapes are discarded. To be added later via `dag_run.conf["as_of"]` per [[2026-05-08-idealista-enrichment-architecture]] roadmap. Until then, treat the SCD2 history as "starts when the DAG started running, not when Zome started publishing."
- **Audit copy**: best-effort to MinIO; tab_ventures + tab_listing_list paginated. dlt fetches independently from Supabase (audit + dlt are decoupled, so an audit failure doesn't poison the dlt run).
- **Smaller scale than [[remax]] / [[idealista]]**: Zome's listing volume sits around 1k-3k typically; useful for cross-portal price-comparison signal, NOT for blanket coverage.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — DAG re-read).
