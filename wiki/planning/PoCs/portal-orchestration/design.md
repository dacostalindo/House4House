---
title: Portal Orchestration PoC — Drop SCD2 from bronze, UPSERT + heartbeat + per-run snapshots
type: plan
last_verified: 2026-06-11
tags: [plan, poc, bronze, scd2, snapshots, heartbeat, dlt, portals, upsert]
status: design-approved
---

# Portal Orchestration PoC — Drop SCD2 from bronze, UPSERT + heartbeat + per-run snapshots

## For future Claude

This page is the wiki-shaped design for the portal-orchestration PoC: **drop SCD2 from the bronze layer across all 5 portals, replace it with PK-keyed UPSERT writes, and accrue history in append-only per-run snapshot tables**. It supersedes the Shape A plan locked 2026-06-09 in [[sprint-04.6]] (heartbeat-gated SCD2 closure), which the 2026-06-11 audit + Fable 5 grill agent + [[uc-3-economics|UC-3]]-only priority lock together reframed as overkill. The implementation plan with per-PR scope lives in [[sprint-plan]]. Read this when scoping the portal-orchestration PoC, deciding whether to bring SCD2 back, or wiring downstream consumers off the new bronze contract.

Read this when:
- Sizing or starting any PR on `pipelines/portals/*/source.py`, the heartbeat sidecar columns, the snapshot resource, or the 11 dbt staging models that filter `_dlt_valid_to`.
- Considering re-adding SCD2 to bronze — read §Why this collapses Shape A first, then read [[bronze-snapshots]] (to be created in PR6) for the snapshots-as-history replacement.
- Wiring a new downstream consumer that wants per-listing trajectory (asking-price path, days-on-market). Snapshots are the surface; not bronze versions.

## Goal

Replace SCD2-in-bronze with UPSERT-in-bronze + snapshots-as-history across all 5 portals ([[idealista]], [[remax]], [[jll]], [[zome]], [[imovirtual]]) and all 14 fact tables (devs/units/listings/plots variants). Two driving outcomes:

1. **Eliminate two live bugs**: hash-collision silent data loss (up to 34% of jll_listings, 27% of remax_developments — measured) and phantom-close on partial-payload days (caused the 2026-06-04 incident; latent in all 5 portals).
2. **Simplify the project's mental model** — drop `_dlt_valid_to IS NULL` filters from 11 staging models, drop the `row_hash` column + `_stable_hash` helper, drop the defensive `DISTINCT ON (pk)` dedup. The 21-day floor lives in one place: the [[heartbeat-sidecar]].

No new analytical capability. No backfill of trajectory before migration day (recorded trade-off — see §Recorded losses).

## Why this collapses Shape A

Shape A (the prior sprint-04.6 plan) was a 3-5 day fix to keep SCD2 working: switch dlt resources to `merge_key`, add a heartbeat-driven close-stale post-task, fix `_stable_hash` to include PK. Shape B (this PoC) is a 1-2 week migration to remove SCD2 entirely.

Three things forced the reframe:

1. **Empirical audit found the hash-collision rate is much worse than expected.** 34.2% of jll_listings, 27.3% of remax_developments, 21.1% of remax_listings, 19.4% of imovirtual_development_units, 15.5% of zome_listings have row_hash shared by ≥2 distinct PKs in the active set. The `_stable_hash` excludes PK by design — common identical-feature listings (same dev, same typology, same price band) silently lose their second-arriving row in dlt's insert clause. Existing SCD2 history is partially untrustworthy as a consequence.
2. **[[uc-3-economics|UC-3]] is the sole primary objective as of 2026-06-11.** UC-3 reads current-state bronze + a polygon-bounded subset via `fn_assess_polygon`. SCD2 in bronze doesn't help; UPSERT + snapshots do. The dev_uid persistence story originally argued for SCD2 stability (via [[dev-uid-stability]]) is preserved by snapshots equally well — the `silver_dev_uid_map` was tied to UC-4's LLM enrichment FK, and UC-4 is archived.
3. **Cognitive tax is real.** `_dlt_valid_to IS NULL` filters across 11 staging models + 2 source YAMLs + defensive DISTINCT ON dedup exist solely to manage SCD2 semantics. Dropping the semantics removes the code. Solo-dev maintenance cost drops.

Alternatives considered and rejected:

- **Shape A** (keep SCD2, fix closure + hash bugs). Rejected — permanent operational tax for a capability no current consumer needs, and the hash-collision blast radius is large enough that "fix" means a one-time re-version of ~57k active rows anyway.
- **Shape C** (UPSERT bronze + dbt-snapshots at silver). Rejected — dbt's `check_cols` strategy has the same close-on-absence bug we're escaping; `timestamp` strategy needs heartbeat plumbing anyway. Strictly more moving parts than per-run append-only snapshot tables.

## Empirical evidence (pre-flight audit, 2026-06-11)

### Hash collision audit — fraction of active rows whose row_hash is shared by ≥2 distinct PKs

| Facts table | Active rows | Collided | % at risk |
|---|---|---|---|
| jll_listings | 7,556 | 2,586 | **34.2 %** |
| remax_developments | 615 | 168 | **27.3 %** |
| remax_listings | 8,480 | 1,789 | **21.1 %** |
| imovirtual_development_units | 4,446 | 864 | 19.4 % |
| zome_listings | 9,349 | 1,452 | 15.5 % |
| idealista_development_units | 444 | 64 | 14.4 % |
| imovirtual_plots | 4,891 | 567 | 11.6 % |
| remax_plots | 12,414 | 733 | 5.9 % |
| imovirtual_developments | 798 | 29 | 3.6 % |
| idealista_plots | 6,997 | 227 | 3.2 % |
| zome_plots | 1,833 | 31 | 1.7 % |
| zome_developments | 318 | 2 | 0.6 % |
| idealista_developments | 21 | 0 | 0 % |
| jll_developments | 171 | 0 | 0 % |

### Phantom-close audit — PKs closed in bronze with no successor while heartbeat-fresh

| Facts table | Heartbeat fresh | Phantom-closed | % phantom |
|---|---|---|---|
| remax_listings | 8,827 | 357 | 4.0 % |
| remax_developments | 638 | 21 | 3.3 % |
| remax_plots | 12,817 | 395 | 3.1 % |
| zome_listings | 9,535 | 183 | 1.9 % |
| zome_plots | 1,855 | 21 | 1.1 % |
| imovirtual_development_units | 4,495 | 41 | 0.9 % |
| zome_developments | 321 | 3 | 0.9 % |
| imovirtual_plots | 4,784 | 26 | 0.5 % |
| imovirtual_developments | 801 | 3 | 0.4 % |
| jll_listings | 7,555 | 4 | 0.05 % |
| jll_developments | 171 | 0 | 0 % |
| idealista (all) | various | 0 | 0 % (post-2026-06-04 manual restore) |

**Side finding (out-of-scope, flagged)**: `idealista_plots_state` has 0 fresh heartbeats — the idealista plots heartbeat hasn't been emitted in 21+ days. Backlog item, not blocking this PoC.

### Storage projection — full-row snapshots, all 14 fact tables, every successful run

| Metric | Today | 5M-listings projection (10×) |
|---|---|---|
| Bronze active footprint | ~127 MB | ~1.3 GB |
| Snapshot writes/week | ~32 (idealista daily × 3 tables + 4 weekly portals × ~2-3 tables) | ~32 (unchanged — cadence not row-count-bound) |
| Annual snapshot accrual | ~8 GB | ~80 GB |
| 2-year cumulative | ~16 GB | ~160 GB |

Trivial on Hetzner AX102 (TB of NVMe). Full-row-every-run is safely the right call.

## Architecture summary

```
┌─────────────────────────────────────────────────────────────┐
│ Portal DAG (per portal, existing wall-clock cron)           │
│                                                             │
│  audit_to_minio  →  load_facts  →  snapshot_facts  →        │
│                     (UPSERT)       (append-only)            │
│                                                             │
│                  →  validate_facts                          │
└─────────────────────────────────────────────────────────────┘
        │                                       │
        ▼                                       ▼
┌──────────────────────────┐         ┌──────────────────────────┐
│ bronze_listings.         │         │ bronze_listings.         │
│   <portal>_<entity>      │         │   <portal>_<entity>      │
│   (UPSERT, 1 row/PK)     │         │   _snapshots             │
│                          │         │   (append-only,          │
│ bronze_listings.         │         │    snapshot_date PK)     │
│   <portal>_<entity>      │         │                          │
│   _state                 │         │                          │
│   (heartbeat sidecar,    │         │                          │
│    UPSERT, first_seen    │         │                          │
│    + last_seen)          │         │                          │
└──────────────────────────┘         └──────────────────────────┘
        │                                       │
        ▼                                       ▼
┌──────────────────────────────────────────────────────────┐
│ dbt staging: stg_portal_<entity>_<portal>.sql            │
│   LEFT JOIN state USING (pk) → real last_seen/first_seen │
│   WHERE state.last_seen_date >= CURRENT_DATE - 21        │
│   (no _dlt_valid_to filter, no DISTINCT ON)              │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│ Silver: unified_listings_residential, unified_devs       │
│   is_active = (last_seen_date >= CURRENT_DATE - 21)      │
│   (replaces existing 3-day window)                       │
└──────────────────────────────────────────────────────────┘
```

Headlines:

- **Bronze writes**: all 14 fact resources switch from `disposition: merge, strategy: scd2, row_version_column_name: row_hash` to `disposition: merge` (PK-keyed UPSERT only). `_dlt_valid_from` / `_dlt_valid_to` columns disappear from new writes. `row_hash` + `_stable_hash` helper retired.
- **Heartbeat sidecars**: `first_seen_date DATE` column added to all 14 `*_state` tables. UPSERT logic: write `first_seen_date = CURRENT_DATE` on insert only; existing rows keep their original value. `last_seen_date` continues to track per-run liveness as today.
- **Snapshot tables**: 14 new `bronze_listings.<portal>_<entity>_snapshots` tables. Append-only via `INSERT INTO snapshots SELECT *, CURRENT_DATE AS snapshot_date FROM bronze_listings.<entity>` at end of each portal DAG. PK = `(natural_pk, snapshot_date)`. Mandatory day-1, full-row, every successful run.
- **Existing SCD2 history**: preserved as `*_scd2_archive` tables for ~30 days via `ALTER TABLE ... RENAME`. NOT dropped during migration. Operator runbook schedules the post-30-day drop.
- **dbt staging**: 11 models + 2 YAMLs drop the `_dlt_valid_to IS NULL` filter + `DISTINCT ON (pk)` defensive dedup. Each model gains `LEFT JOIN bronze_listings.<entity>_state USING (pk)` to expose real `last_seen_date` and `first_seen_date`. The `_dlt_valid_from::DATE AS last_seen_date` proxy alias is removed.
- **Silver**: `unified_listings_residential.sql` 3-day `is_active` window replaced with 21-day heartbeat-based filter. Aligns with [[heartbeat-sidecar]] floor.
- **Validation bands**: row-count bounds in `pipelines/portals/idealista/idealista_dlt.py:340-350` and `pipelines/portals/imovirtual/imovirtual_dlt_dag.py:62-64` widen — delisted entities now linger ≤21d in the active set.
- **Orchestration**: unchanged. Wall-clock daily silver at `0 11 * * *` per [[2026-06-09-silver-wall-clock-not-datasets]]. Portal DAGs keep their existing per-portal cron schedules.

## Data model summary

Full SQL lands per-PR in [[sprint-plan]]. Headlines:

- **Bronze (`bronze_listings`)**:
  - 14 fact tables — drop `_dlt_valid_from`, `_dlt_valid_to`, `row_hash`. PK becomes the natural key.
  - 14 heartbeat sidecars — add `first_seen_date DATE`. UPSERT on insert only.
  - 14 new snapshot tables — full row schema + `snapshot_date DATE`; PK = `(natural_pk, snapshot_date)`.
  - 14 archive tables — `<name>_scd2_archive` from RENAME of pre-migration table; ~30-day retention then runbook drop.
- **Staging (`dbt/models/staging/portals/`)** — 11 models + 2 YAMLs updated. Drop `_dlt_valid_to IS NULL`, `DISTINCT ON (pk)`, `_dlt_valid_from::DATE` aliases. Add heartbeat JOIN.
- **Silver (`unified_listings_residential`)** — 3d → 21d threshold flip; no other shape changes.

## Recorded losses (not surprises)

- **Pre-migration days-on-market signal is unrecoverable.** Existing rows lack `first_seen_date` in heartbeat; the new column starts populating from migration day. Trajectory before 2026-06-11 is gone for existing entities. New entities accrue from day one. Mitigation: surface this in the UC-3 Atlas Inspector if/when the days-on-market feature ships — old listings show "first seen before tracking" rather than a wrong number.
- **Pre-migration SCD2 history** is preserved in `*_scd2_archive` for ~30 days, then dropped. Acceptable per the hash-collision finding (existing chain is partially untrustworthy anyway) and the snapshot table accruing from day one.

## NOT in scope (v1)

Gold gate (silver → gold trigger semantics). Hedonic `fact_market_observations` (sprint-05 problem). Listing-level cross-portal dedup (the original Phase 2 + Phase 3 from sprint-04.5; dropped 2026-06-09). UC-4 LLM dev-actor pipeline ([[use-cases/archive/UC-4|UC-4 archived 2026-06-11]] — Project Actors track moved to the Knowledge-graph-PoC). The idealista plots heartbeat brokenness (side finding; backlog item). Reintroducing SCD2 anywhere (snapshots are the history surface).

## Open items (not blockers)

- **Snapshot retention policy.** v1 ships unbounded retention. Revisit if snapshot accrual exceeds projection at 2-year mark (~160 GB) or if storage cost on Hetzner ever matters. Easy retrofit via runbook (drop snapshots older than N years).
- **`first_seen_date` backfill.** Best-effort backfill on Day 1: `UPDATE state SET first_seen_date = (SELECT MIN(_dlt_valid_from::date) FROM facts WHERE facts.pk = state.pk) WHERE first_seen_date IS NULL` — uses the pre-migration SCD2 history before it gets renamed to archive. Acknowledged as imperfect (the SCD2 history is partially untrustworthy per the collision audit).
- **dlt 1.25.0 `disposition: merge` validation against existing schemas.** A 3-load smoke fixture against a scratch schema is the safest pre-PR2 check; deferred to a runtime spike inside PR2 rather than a separate pre-flight.

## See also

- [[sprint-plan]] — per-PR scope, acceptance criteria, sequencing.
- [[bronze-permissive]] — never-delete invariant; amended in PR6 to point at snapshots rather than SCD2 versions.
- [[heartbeat-sidecar]] — extended with `first_seen_date` in PR1; now sole liveness truth.
- [[scd2-row-hash]] — superseded by this PoC; marked deprecated in PR6.
- [[medallion-layering]] — bronze layer history-tracking guidance updated in PR6.
- [[orchestration]] — DAG taxonomy; `snapshot_facts` task added in PR1.
- [[2026-06-09-silver-wall-clock-not-datasets]] — orchestration ADR this PoC builds on (silver wall-clock unchanged).
- [[sprint-04.6]] — the prior Shape A scope; this PoC supersedes it for the SCD2-related deliverables.
- [[uc-3-economics|UC-3]] — primary consumer whose needs justified the simplification.

## Last verified

2026-06-11 — design grounded in 2026-06-11 empirical audit (collision + phantom-close counts above) and Fable 5 grill agent review. Implementation not yet started.
