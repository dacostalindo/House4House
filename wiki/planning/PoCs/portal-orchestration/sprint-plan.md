---
title: Portal Orchestration PoC — Sprint Plan
type: plan
last_verified: 2026-06-11
tags: [plan, poc, portals, scd2, sprint, pr-slicing, migration]
status: planned
last_status_update: 2026-06-11
---

# Portal Orchestration PoC — Sprint Plan

## For future Claude

This page is the per-PR breakdown of the Portal Orchestration PoC, paired with [[design|design.md]]. 6 PRs to v1; each PR has explicit scope, acceptance criteria, and the wiki updates it must ship in the same commit (per the project's CLAUDE.md rule). The sequencing is intentional: PR1 is purely additive (no bronze-shape changes, low risk, foundation only), PR2 is the canary on the smallest cleanest table (`idealista_developments` — 21 rows, 0 collisions, 0 phantoms — validates the full mechanics under low-blast-radius conditions), then portals roll out in volume-ascending order so each step's blast radius is bounded by what came before. PR5 lands the silver-side lock; PR6 closes the wiki + schedules the 30-day archive drop. Read this page when picking up the PoC mid-build, deciding whether a PR can ship without its wiki updates (no — they're same-commit), or sizing the PoC for a real sprint slot.

Read this when:
- Picking up portal-orchestration work mid-build — the PR table tells you what shipped and what's next.
- Deciding whether a PR can ship without its wiki updates (no — they're same-commit, per project rule).
- Sizing the PoC for a real sprint slot (rough estimate per PR below).

## Status snapshot

| PR | Scope | Acceptance | Wiki updates (same commit) | Est. effort |
|---|---|---|---|---|
| **PR1** | Foundation: snapshot resource + `first_seen_date` heartbeat extension, all 5 portals | ✅ Pending | 2 concept pages + index + log | ~1 day |
| **PR2** | Canary: migrate all 3 idealista fact tables (UPSERT + archive + staging) | ✅ Pending | Update 2 concepts + 1 source + index + log | ~2 days |
| **PR3** | Remax migration (3 fact tables — worst collision recovery) | ✅ Pending | Update source + log | ~1.5 days |
| **PR4** | Zome + Imovirtual migration (6 fact tables) | ✅ Pending | Update 2 sources + log | ~1.5 days |
| **PR5** | JLL migration + silver 21d lock + validation-band resize | ✅ Pending | Update source + silver concept + log | ~2 days |
| **PR6** | Wiki propagation + runbook + archive-drop schedule + integration tests | ✅ Pending | New runbook + supersede scd2-row-hash + amend bronze-permissive + index + log | ~1 day |

**Total: ~9 working days of focused effort for v1.** Slot into the next available sprint after PR #69 ([[sprint-04.6]] Shape A) is formally retired and after the in-flight news-pipeline PoC's PR1 ships (no resource contention but avoid running two foundational migrations in parallel).

## Overall sequencing principle

Front-load the *additive* parts (snapshots + `first_seen_date` are pure additions, low risk, deliver day-1 trajectory accrual) and back-load the *cleanup* parts (silver-side 21d lock, validation-band resize, wiki + runbook). The middle PRs are portal-by-portal migrations sequenced so each step's blast radius is bounded:

- **PR1 is risk-free** — pure additions; no bronze-shape changes; if anything breaks, revert is one config flip.
- **PR2 proves the mechanics** on the smallest, cleanest table (`idealista_developments` — 21 rows, 0 collisions, 0 phantoms). If the full A.3 → A.7 chain works here, the same pattern slots into every other portal.
- **PR3 proves the bug-fix** — remax has the worst phantom-close + second-worst hash collision rate. After PR3 ships, ~27% of `remax_developments` and ~21% of `remax_listings` collisions become observable as a row-count bump (previously-dropped collisions now land in bronze).
- **PR4 derisks scale** — zome + imovirtual ship together because their migration shape is identical to PR3; rolling them as one PR halves the calendar cost.
- **PR5 closes the bronze migration** — JLL is last because its 34.2% listings collision rate is the most dramatic recovery; landing it after PR2-4 means the silver-side 21d lock (which expects the new bronze contract) is applied once, not five times.
- **PR6 is the cleanup** — no code changes to runtime systems; just wiki + tests + the operator runbook for the 30-day archive drop.

## PR1 — Foundation: snapshot resource + heartbeat `first_seen_date`

**Scope:**

- New shared module `pipelines/portals/common/scd2_heartbeat_closure.py` is NOT what this PoC needs — instead build `pipelines/portals/common/snapshot_resource.py`: one callable parameterized by `(facts_table, schema='bronze_listings')` that runs `INSERT INTO bronze_listings.<facts_table>_snapshots SELECT *, CURRENT_DATE AS snapshot_date FROM bronze_listings.<facts_table>`.
- Wire `snapshot_facts` task into all 5 portal DAGs after `validate_facts`:
  - `pipelines/portals/idealista/idealista_dlt.py`
  - `pipelines/portals/imovirtual/imovirtual_dlt_dag.py`
  - `pipelines/portals/jll/jll_dlt_dag.py`
  - `pipelines/portals/remax/remax_dlt_dag.py`
  - `pipelines/portals/zome/zome_dlt_dag.py`
- DDL pass: create the 14 snapshot tables (`bronze_listings.<entity>_snapshots`) with full schema + `snapshot_date DATE`; PK = `(<natural_pk>, snapshot_date)`. Index on `snapshot_date DESC` for recent-query patterns.
- DDL pass: `ALTER TABLE bronze_listings.<entity>_state ADD COLUMN first_seen_date DATE` on all 14 sidecars.
- Heartbeat resource update per portal: yield `first_seen_date = CURRENT_DATE` on the row's first emission; on subsequent emissions, do not set the column (UPSERT semantics: existing rows keep their value). Implementation choice — evaluate (a) dlt `merge_key` + `incremental` strategy that preserves existing values vs (b) post-load SQL `UPDATE state SET first_seen_date = COALESCE(first_seen_date, CURRENT_DATE)`. Pick (a) if it works cleanly; (b) as fallback.
- Best-effort backfill: `UPDATE bronze_listings.<entity>_state s SET first_seen_date = (SELECT MIN(_dlt_valid_from::date) FROM bronze_listings.<entity> f WHERE f.<pk> = s.<pk>) WHERE s.first_seen_date IS NULL`. Acknowledged as imperfect (pre-migration SCD2 history is partially untrustworthy per the collision audit).

**Acceptance:**

- All 5 portals complete their next-scheduled DAG cycle successfully with the new `snapshot_facts` task.
- 14 snapshot tables exist and each has at least one row (one per active entity after the first post-PR1 run).
- All 14 heartbeat sidecars have populated `first_seen_date` (either from backfill or from new inserts).
- No SCD2-shape changes yet — bronze fact tables behave identically to pre-PR1 (verified via row-count comparison).
- Snapshot storage growth measured and logged in `wiki/log.md` (sanity check against [[design#storage-projection-full-row-snapshots|design.md storage projection]]).

**Wiki updates (must ship in this commit, per project CLAUDE.md):**

- New: `wiki/concepts/bronze-snapshots.md` — documents the snapshot contract (mandatory, full-row, every successful run, append-only, `(pk, snapshot_date)` PK). Cross-links to [[bronze-permissive]] and [[heartbeat-sidecar]].
- Update: [[heartbeat-sidecar]] — document `first_seen_date` column; note UPSERT-only-on-insert semantics; note this is the path toward becoming the sole liveness truth (full transition lands in PR2-5).
- Update: [[index]] — add `bronze-snapshots` to Concepts section.
- Append: `wiki/log.md` — one-line entry.

## PR2 — Canary: migrate idealista (all 3 fact tables)

**Scope:**

- For each of `idealista_developments`, `idealista_development_units`, `idealista_plots`:
  - In `pipelines/portals/idealista/idealista_dlt.py`, switch the resource: `disposition: merge, strategy: scd2, row_version_column_name: row_hash` → `disposition: merge` (PK is the merge key by default). Remove the `*_VERSION_COLUMNS` reference + `_stable_hash` call for this resource.
  - SQL: `ALTER TABLE bronze_listings.<entity> RENAME TO <entity>_scd2_archive`.
  - SQL: `CREATE TABLE bronze_listings.<entity> AS SELECT <columns minus _dlt_valid_from/_dlt_valid_to/row_hash> FROM bronze_listings.<entity>_scd2_archive WHERE _dlt_valid_to IS NULL`. Add primary key constraint + indexes per the original schema.
  - Update `dbt/models/staging/portals/stg_portal_<entity>_idealista.sql`: drop `WHERE _dlt_valid_to IS NULL` + `DISTINCT ON (pk) ORDER BY pk, _dlt_valid_from DESC`. Replace `_dlt_valid_from::DATE AS last_seen_date` alias with `LEFT JOIN bronze_listings.<entity>_state s USING (<pk>)` and expose `s.last_seen_date` + `s.first_seen_date`.
  - Update `dbt/models/staging/portals/_staging_listings__sources.yml` to drop `_dlt_valid_to` documentation references for these tables.

**Acceptance:**

- All 3 idealista fact tables on UPSERT; trigger one full idealista DAG run; rows update in place (verified via `SELECT _dlt_id` continuity for unchanged rows).
- `dbt run --select stg_portal_developments_idealista stg_portal_development_units_idealista stg_portal_listings_idealista` passes; output row counts match expectation (no DISTINCT ON dedup means same-or-very-close row counts to prior).
- Silver downstream (`silver_unified_developments`, `silver_unified_listings`) sees no row-count regression (small bump acceptable from `idealista_plots` collision recovery).
- Snapshot tables for all 3 idealista entities accrue one additional snapshot_date worth of rows after the run.
- `idealista_developments_scd2_archive` (and units, plots) tables exist and contain pre-migration SCD2 history.
- **Side finding handled**: log a `wiki/log.md` note that `idealista_plots_state` has 0 fresh heartbeats (per design's flagged backlog item). Migration proceeds; investigation deferred.

**Wiki updates:**

- Update: [[scd2-row-hash]] — add a deprecation banner at the top with link to the new design page. Body unchanged (it documents the historical pattern).
- Update: [[idealista]] source page — note the disposition change; cross-link to [[portal-orchestration/design|the PoC design]] for the why.
- Update: [[bronze-permissive]] — amend the "never-delete-from-bronze" invariant to point at snapshots rather than SCD2 versions. The bronze fact tables now UPSERT in place; snapshots own history.
- Update: [[index]] — flip the [[scd2-row-hash]] entry from "current pattern" to "historical pattern, superseded by [[portal-orchestration/design]]".
- Append: `wiki/log.md`.

## PR3 — Remax migration (3 fact tables, biggest phantom-close + second-worst hash collision)

**Scope:**

- Apply the PR2 pattern to `remax_developments`, `remax_listings`, `remax_plots`. Resource config change + RENAME + CREATE-from-archive + staging model updates per the same recipe.
- Update `dbt/models/staging/portals/stg_portal_developments_remax.sql`, `stg_portal_listings_remax.sql:22` (the canonical `DISTINCT ON (listing_id) WHERE _dlt_valid_to IS NULL` pattern), and the corresponding `_plots` staging if it exists (per existing surface map; if not, the remax_plots data lands via a different model).

**Acceptance:**

- All 3 remax fact tables on UPSERT.
- Step-change in active row count: `remax_developments` increases by roughly the 27% collision-recovery delta (~168 PKs); `remax_listings` increases by roughly the 21% collision-recovery delta (~1,789 PKs); `remax_plots` smaller increase (5.9%, ~733 PKs). Document exact deltas in `wiki/log.md`.
- Phantom-close re-audit on remax: post-migration query should show 0 phantoms (the bug is gone by construction since dlt no longer closes on absence).
- Silver `silver_unified_listings_residential` consumes the increased remax row count; UC-3 spot-check confirms the polygon-query results in remax coverage areas are sensible (higher counts, not garbage).

**Wiki updates:**

- Update: [[remax]] source page — note migration date, document the row-count bump as a one-time recovery (not a quality issue).
- Append: `wiki/log.md`.

## PR4 — Zome + Imovirtual migration (6 fact tables)

**Scope:**

- Apply the PR2 pattern to:
  - `zome_developments`, `zome_listings`, `zome_plots`
  - `imovirtual_developments`, `imovirtual_development_units`, `imovirtual_plots`
- Same recipe per table; ships as one PR because the migration shape is identical and the per-portal blast radius is bounded.

**Acceptance:**

- All 6 fact tables on UPSERT across both portals.
- Row-count deltas roughly match the collision-recovery percentages from [[design#hash-collision-audit-fraction-of-active-rows-whose-row-hash-is-shared-by-2-distinct-pks|design.md audit table]]: `zome_listings` ~+15.5%, `imovirtual_development_units` ~+19.4%, others smaller. Documented in `wiki/log.md`.
- Both portals' next scheduled DAG cycles complete cleanly.
- Silver build (`silver_unified_developments` + `silver_unified_listings`) lands at 11:00 daily without regression.

**Wiki updates:**

- Update: [[zome]] source page — note migration date.
- Update: [[imovirtual]] source page — note migration date.
- Append: `wiki/log.md`.

## PR5 — JLL migration + silver 21d lock + validation-band resize

**Scope:**

- Apply the PR2 pattern to `jll_developments` and `jll_listings`. JLL listings carries the worst collision rate (34.2%) — expect the biggest row-count bump of the migration (~2,586 PKs recovering).
- `dbt/models/silver/unified_listings_residential.sql`: replace `now() - interval '3 days'` with `current_date - interval '21 days'` for the `is_active` flag derivation. Aligns silver with [[heartbeat-sidecar]] floor.
- `pipelines/portals/idealista/idealista_dlt.py:340-350` — widen row-count validation bounds; document inline. Delisted entities now linger ≤21d in active set so steady-state counts grow modestly.
- `pipelines/portals/imovirtual/imovirtual_dlt_dag.py:62-64` — same.
- Run a full daily cycle end-to-end across all 5 portals after merge. Verify silver row counts stay within new bands.

**Acceptance:**

- JLL listings row count step-change: ~+34% recovery measured and logged.
- All 5 portals on UPSERT; bronze layer fully migrated.
- Silver `is_active = (last_seen_date >= current_date - 21)` applied consistently.
- Validation bands hold for 7 consecutive daily cycles post-merge (no false-positive alerts).
- UC-3 `fn_assess_polygon` spot-check on representative polygons returns sensible counts.

**Wiki updates:**

- Update: [[jll]] source page — note migration date + the dramatic collision-recovery delta as a one-time visible bug-fix.
- Update: `wiki/concepts/unified-listings-residential.md` (or whatever page documents the silver `is_active` semantics — discover via grep at PR time) — document the 21d threshold change.
- Append: `wiki/log.md`.

## PR6 — Wiki propagation + runbook + archive-drop schedule + integration tests

**Scope:**

- Integration tests:
  - `pipelines/portals/tests/test_snapshot_resource.py` — snapshot row count after a load equals active bronze row count for the table.
  - `pipelines/portals/tests/test_first_seen_date_upsert.py` — `first_seen_date` doesn't change across multiple UPSERTs for an existing PK; new PKs get `CURRENT_DATE`.
  - Optional dbt test: `first_seen_date <= last_seen_date` invariant on every staging row.
- New runbook: `wiki/runbooks/scd2-archive-drop.md` — describes the ~30-day archive drop. Includes:
  - Pre-drop validation queries (confirm 30-day stable operation, no rollback triggered).
  - The DROP TABLE commands (one per archive table; ~14 statements).
  - Rollback procedure (if needed within the 30-day window): rename current table to `<entity>_v2`, rename `<entity>_scd2_archive` back to `<entity>`, reset dlt state per portal, run the prior production DAG.
- Calendar reminder (operator-facing, not a cron): for ~30 days after PR5 merge, schedule the runbook execution.

**Acceptance:**

- Integration tests run as part of CI and pass.
- Runbook reviewed and approved by operator (in this project: the user).
- `/wiki-reconcile` lint pass — no broken cross-links, no orphan pages, no contradictions.
- Final `wiki/log.md` entry summarizing the migration outcome with exact row-count deltas per portal.

**Wiki updates:**

- New: `wiki/runbooks/scd2-archive-drop.md` (above).
- Update: [[scd2-row-hash]] — flip status banner from "deprecated" to "superseded". Body kept as historical archaeology.
- Update: [[bronze-permissive]] — finalize the never-delete invariant amendment ("snapshots own history; bronze facts UPSERT in place").
- Update: [[heartbeat-sidecar]] — finalize as sole liveness truth (`first_seen_date` populated everywhere; SCD2 path retired).
- Update: [[medallion-layering]] — note the project's bronze layer no longer carries SCD2; per-source history lives in `bronze_listings.<portal>_<entity>_snapshots`.
- Update: [[orchestration]] — add `snapshot_facts` to the per-portal DAG taxonomy.
- Update: [[index]] — finalize Concepts + Decisions cross-link updates.
- Append: `wiki/log.md`.

## What PR7+ looks like (post-v1)

Driven by what the snapshots actually surface and what UC-3 + sprint-05 hedonic actually need. Not in scope of this PoC; listing here so the trajectory is visible:

- **Days-on-market silver model** — derive from `first_seen_date` + `last_seen_date` on `silver_unified_listings`. One-shot dbt model. Trivial once heartbeat is the liveness truth.
- **Asking-price trajectory silver model** — read from `<entity>_snapshots` to derive `(listing_uid, snapshot_date, asking_price)` series. Feeds hedonic.
- **Snapshot retention policy enforcement** — only when storage growth crosses a threshold (projection says ~2 years before any concern). Runbook adds a "drop snapshots older than N years" pass.
- **Idealista plots heartbeat fix** — investigate the 0-fresh-heartbeats side finding from the audit; likely a missing heartbeat emission in the plots resource.
- **Validation-band tuning** — after 30 days of stable steady-state, reset the row-count bands to tight ±10% windows on observed values.
- **Archive table drop** — runbook execution, ~30 days post-PR5 merge.

## See also

- [[design|Design doc]] — what + why + architecture summary + empirical audit.
- [[sprint-04.6]] — the prior Shape A scope; this PoC supersedes it for the SCD2-related deliverables.
- [[bronze-permissive]], [[heartbeat-sidecar]], [[scd2-row-hash]], [[medallion-layering]] — load-bearing concepts referenced throughout.
- [[2026-06-09-silver-wall-clock-not-datasets]] — orchestration ADR this PoC builds on (silver wall-clock unchanged).

## Last verified

2026-06-11 — sprint plan drafted directly from 2026-06-11 empirical audit + Fable 5 grill agent verdict; effort estimates assume one engineer working from this branch; no PR has shipped yet.

## Status update history

- 2026-06-11 — plan drafted, design approved, awaiting sprint slot. Supersedes [[sprint-04.6]] for SCD2-related deliverables; silver_dev_uid_map and dev_uid stability work from prior 04.6 scope remain deferred per [[use-cases/archive/UC-4|UC-4 archive]].
