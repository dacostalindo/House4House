---
title: Sprint 4.6 — Silver orchestration + dev_uid stability + SCD2 heartbeat closure
type: plan
last_verified: 2026-06-09
tags: [sprint, plan, silver, orchestration, dev_uid, scd2, heartbeat, wall-clock]
status: planned
sprint_number: "4.6"
weeks: "TBD (post sprint-04, before sprint-05 hedonic)"
last_status_update: 2026-06-09
---

## For future Claude

This is the **Sprint 4.6** page — the implementation sprint for the 2026-06-09 orchestration interview output. Two interlocking workstreams: (WS-A) replace dlt's row-gated SCD2 closure with heartbeat-gated closure for all 5 portals (blocker — current behavior caused a real incident 2026-06-04); (WS-B) wire `silver_dev_uid_map` + the wall-clock daily silver chain per [[2026-06-09-silver-wall-clock-not-datasets]] + [[dev-uid-stability]]. Scope deliberately excludes anything not load-bearing for these two outcomes — gold gate, hedonic readiness, and listing-level cross-portal dedup all stay deferred. Read this when starting implementation, picking up after an interruption, or scoping a follow-up sprint.

## Goal

Land the orchestration design locked on 2026-06-09: a daily wall-clock silver build at `0 11 * * *` that consumes bronze + heartbeat-alive rows from all 5 portals and produces `silver_unified_developments` with a stable `dev_uids[]` surface (via the append-only `silver_dev_uid_map`) plus `silver_unified_listings` (pure UNION + full SCD2 history). Replace the broken row-gated SCD2 closure with heartbeat-gated closure so phantom gaps from validate failures stop reaching downstream. Deliver this scope without touching gold, hedonic, or the deferred gold gate.

## Why now (sprint priority)

- **Real incident already happened.** Wiki log shows a 2026-06-04 idealista one-shot SQL restore (`DELETE` 150 phantoms + `UPDATE` 444 rows back to `valid_to = NULL`) because dlt closed SCD2 on partial-payload-row-absence. Same failure mode is present in all 4 (now 5 with imovirtual) portals; ticking time bomb.
- **Blocks UC-4.** The [[use-cases/archive/UC-4|UC-4 (archived 2026-06-11)]] LLM dev-actor enrichment (planned post-sprint-04.5) FKs to `dev_uid`. Without the append-only map, every silver rebuild orphans the LLM outputs. Sprint 4.6 must land before UC-4 starts. (Historical context: UC-4 was archived 2026-06-11 after Sprint 4.6 shipped — the `dev_uid` work remains load-bearing for whichever consumer takes over per-dev LLM enrichment; the Project Actors track moved to the Knowledge-graph-PoC.)
- **Unblocks UC-3 v1 production runs.** UC-3 Atlas Inspector queries `silver_unified_developments` + `silver_unified_listings` directly. Today's daily rebuild already works; what's missing is the stable `dev_uids[]` surface and the SCD2 fix. Sprint 4.6 closes both gaps.

## Pre-implementation verification outcomes (2026-06-09)

| Check | Outcome | Action in scope |
|---|---|---|
| **C2: SCD2 closure path heartbeat-gated** | ❌ FAILS — dlt default closes on row absence; caused 2026-06-04 incident. All 5 portals affected. | Workstream A: implement portal-side heartbeat-driven closure (post-load custom task). BLOCKING. |
| **C3: recursive CTE scale projection** | ⚠️ BORDERLINE — concelho blocking enforced (good); 15-min projection at 5M defensible if name-collision density stays sparse, but pessimistic case is ~40 min. Token-Jaccard only is live; dual-Jaccard (char-trigram) claimed in concept doc NOT YET IMPLEMENTED. | Workstream B: run the empirical measurement query before merging the wall-clock cron change. Add the trigram edge generator if profile shows clean budget. Codify a runtime alert at >15min p95. |
| **C4: CAOP geo_concelho_name in all 5 portals** | ✅ PASSES — all 5 staging models expose `geo_concelho_name` via PIP on `dim_geography.freguesia_geom_pt`; COALESCE happens in silver. | None. Proceed. |

C2 promotes from "verification checklist item" to **mandatory blocking workstream**. C3 reframes one Sprint 4.6 deliverable as "measure + decide" rather than "ship as-designed."

## Deliverables

### Workstream A — Heartbeat-gated SCD2 closure (BLOCKER for wall-clock daily)

A.1 — **Per-portal `close_stale_scd2` post-load task** added to each portal DAG: [[idealista]], [[imovirtual]], [[remax]], [[jll]], [[zome]]. Runs after `load_facts` + heartbeat upsert, before `validate`. SQL closes `_dlt_valid_to` ONLY when heartbeat `last_seen_date < CURRENT_DATE - INTERVAL '21 days'` (matches [[heartbeat-sidecar]] floor). Replaces the implicit row-absence closure dlt does today.

A.2 — **Strip dlt's row-gated SCD2 closure** by switching all SCD2 resources to `disposition: merge, strategy: scd2` with EXPLICIT row-version-column AND emitting all live heartbeat'd PKs in each run (so dlt doesn't close anything itself). Alternative under consideration: keep dlt's default and run a corrective post-task that opens phantom-closed rows.

A.3 — **Migration backfill**: one-shot SQL on existing bronze to repair already-phantom-closed rows from prior incidents (the 2026-06-04 restore was idealista-only; verify same pattern hasn't quietly affected other portals). Audit query: `SELECT pipeline, COUNT(*) FROM bronze.*_listings WHERE _dlt_valid_to IS NOT NULL AND (portal_id, ..._dlt_valid_to) NOT IN (heartbeat_aged_out_pks) GROUP BY 1;`

A.4 — **Test fixture** (per portal) covering: row visible all 21 days → stays open; row missing for 1 day → stays open (heartbeat fresh); row missing for 22 days → closes on day 22. Run as dbt tests + integration test in the DAG.

### Workstream B — `silver_dev_uid_map` + wall-clock silver chain

B.1 — **New dbt model**: `silver/silver_dev_uid_map.sql` per [[dev-uid-stability]] §"How". Materialization: incremental, `unique_key=(portal, portal_dev_id)`, append-only (no `on_schema_change`). Build logic: bronze + heartbeat-alive → connected components → LEFT JOIN existing map → MIN(existing dev_uid) per component → mint UUID for new tuples. Postgres-native `gen_random_uuid()`.

B.2 — **Update `silver_unified_developments.sql`**: rename current volatile id to `component_id`, add `dev_uids UUID[]` column populated from the map via JOIN, document the per-portal staging compliance verified in C4. Keep token-Jaccard edge generator as-is for v1; add char-trigram edge generator behind a feature flag, measure cost (per C3), promote to default if budget permits.

B.3 — **Update `silver_unified_listings.sql`**: confirm pure UNION + dev_uid LEFT JOIN on `(geo_concelho_name, normalize_dev_name(canonical_name))`. Strip any residual listing-dedup logic from sprint-04.5 plans.

B.4 — **DAG changes**: lock `dag_dbt_silver` schedule to `0 11 * * *`. Confirm Cosmos task order: `silver_dev_uid_map` → `silver_unified_developments` → `silver_unified_listings`. Set `max_active_runs=1`. Remove `dag_deduplication` from `dags/transformation/` (already retired in docs per [[orchestration]] 2026-06-09 addendum).

B.5 — **Recursive CTE empirical measurement** (per C3): run the senior-eng's measurement query against today's data + a 10× synthetic dataset. Document p50/p95 runtime + edge count. If real worst-case concelho hits >10 min, raise a follow-up decision on incremental materialization. Add Airflow SLA on the silver task at 15min.

### Workstream C — Operational hardening (small but load-bearing)

C.1 — **Portal DAG defaults**: set `retries=2, retry_exponential_backoff=True, retry_delay=timedelta(minutes=15), max_retry_delay=timedelta(hours=1)` in each portal DAG's `default_args`. Per Q16 lock.

C.2 — **`zenrows_pool`** Airflow Pool created with `slots=2`. Idealista's ZenRows-using tasks use `pool='zenrows_pool'`. Per Q17 lock.

C.3 — **`ZENROWS_DAILY_BUDGET_USD=20`** soft cap implemented in idealista source (and any future ZenRows user). Refuses calls past budget, marks task `success` with `xcom` budget-exhausted signal. Per Q17 lock.

C.4 — **Schema-contract = freeze** verified on dlt resource configs for all 5 portals. Statistical drift checks in `validate` task → log to `metadata.pipeline_runs`, alert, never raise. Per Q15 lock.

### Workstream D — Wiki + runbook (closing the propagation loop)

D.1 — **Sprint-04.5 page**: strike Phase 2 + Phase 3 listing dedup from deliverables; mark `unified_listings v2` as "UNION + dev_uid via JOIN, no dedup" per the 2026-06-09 reframe. Update `last_status_update`.

D.2 — **Update [[scd2-row-hash]]** to document the heartbeat-gated closure path explicitly. Reference the 2026-06-04 incident as the why.

D.3 — **Update [[heartbeat-sidecar]]** to add a §"Closure semantics" section pointing at the new `close_stale_scd2` post-load task.

D.4 — **New runbook page** `wiki/runbooks/macro-flush-dev-uid.md` describing the operator-driven `normalize_dev_name` flush workflow per [[dev-uid-stability]] §"Macro-flush workflow."

## Exit criteria

1. All 5 portal DAGs use heartbeat-gated SCD2 closure; no SCD2 row closes on a single missed scrape day. Tested via integration fixtures (A.4).
2. `silver_dev_uid_map` table exists in silver schema; populated; passes `pk uniqueness on (portal, portal_dev_id)` + `dev_uid NOT NULL` dbt tests.
3. `silver_unified_developments.dev_uids` array exposed and joinable from a stub `silver_dev_actors` enrichment table (created by UC-4 sprint, but FK target exists now).
4. `dag_dbt_silver` runs daily at `0 11 * * *`; observed p95 runtime < 15min over 14-day window after deploy.
5. `dag_deduplication` removed from the codebase + Airflow UI.
6. Empirical measurement query (B.5) results documented in `wiki/log.md` with the decision: ship as-is OR escalate to incremental materialization.
7. ZenRows daily spend stays under $20/day for 14 consecutive days post-deploy.
8. Wiki updates (D.1–D.4) landed; `/wiki-reconcile` passes.

## Out of scope (explicitly deferred)

- **Gold gate** (silver → gold trigger semantics). Keep current wall-clock `0 12 * * *`; revisit during gold design.
- **Hedonic-readiness `fact_market_observations`** with its own dedup policy. Sprint-05 problem.
- **Listing-level cross-portal dedup** (the original Phase 2 + Phase 3 from sprint-04.5). Dropped 2026-06-09; document in sprint-04.5 amendment.
- **UC-4 LLM dev-actor pipeline**. Sprint 4.6 only needs to make the FK target exist; the LLM DAG itself ships later.
- **Promotion of imovirtual's geom priority** (per [[2026-06-05-imovirtual-portal-onboarding]] 2026-06-06 addendum). Independent unless 4.6's coverage spot-check happens to land it for free.

## Key decisions (cross-references)

- **Wall-clock, no Datasets**: [[2026-06-09-silver-wall-clock-not-datasets]].
- **Append-only map, no registry**: [[dev-uid-stability]].
- **Listings dropped as deduped**: this sprint, 2026-06-09 interview lock.
- **SCD2 heartbeat-gated closure**: this sprint, surfaced by C2 verification 2026-06-09.

## Risks

| Risk | Probability | Mitigation |
|---|---|---|
| C3 measurement shows recursive CTE >15 min at projected scale | Medium | Pre-merge measurement (B.5); if >10 min on current data, switch B.2 to incremental materialization before shipping. |
| Heartbeat-gated closure has portal-specific edge cases (e.g., zome's state-coverage quirks) | Medium | A.4 fixtures cover the canonical case per portal; runbook entry for unexpected behaviour. |
| dlt SCD2 strategy switch (A.2) breaks bronze row identity across versions | Low | Schema-frozen bronze; row_hash unchanged; only `_dlt_valid_to` semantics change. Test on jll first (lowest volume). |
| Imovirtual scale gap — full national crawl ~2,400 requests/run could blow ZenRows budget if we ever route it through ZenRows | Low | Direct `_next/data` works today (per [[2026-06-05-imovirtual-portal-onboarding]]); ZenRows only as fallback. C.3 budget cap catches accidental routing. |

## Status update history

- 2026-06-09: declared post-interview; status `planned`. Verification outcomes C2/C3/C4 logged. Scope locked to WS-A + WS-B + WS-C + WS-D.

## See also

- [[2026-06-09-silver-wall-clock-not-datasets]] — orchestration ADR this sprint implements.
- [[dev-uid-stability]] — concept this sprint operationalizes.
- [[cross-portal-dev-dedup]] — model this sprint extends with `dev_uids[]`.
- [[orchestration]] — DAG taxonomy + schedule map (2026-06-09 addendum).
- [[scd2-row-hash]], [[heartbeat-sidecar]] — to be updated as part of D.2/D.3.
- [[sprint-04.5]] — predecessor (scope reduced 2026-06-09; this sprint absorbs the silver-orchestration parts).
- [[sprint-05]] — successor (hedonic model; not blocked by 4.6 except for the `fact_market_observations` boundary call).
- [[use-cases/archive/UC-4|UC-4 (archived 2026-06-11)]] — primary consumer of the stable `dev_uid` exit criterion.
