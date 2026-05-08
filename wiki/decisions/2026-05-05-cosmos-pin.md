---
title: Cosmos pinned to >=1.6,<1.7 (Airflow 2.10 compatibility)
type: decision
last_verified: 2026-05-08
tags: [cosmos, airflow, dbt, version-pin, infra]
confidence: high
---

## For future Claude

This is a decision record about pinning `astronomer-cosmos` to `>=1.6,<1.7`. It locks in the version range during Phase 1's spike that surfaced `airflow.sdk` import bleeds in Cosmos 1.7+. Read this before unpinning Cosmos, when upgrading to Airflow 3, or when debugging "ModuleNotFoundError: No module named 'airflow.sdk'" inside Cosmos's DbtDag entrypoint.

## Decision

House4House pins `astronomer-cosmos[dbt-postgres]>=1.6,<1.7` in the workspace pyproject. The pin holds until Airflow 3 lands as a deliberate migration (out of current scope) AND Cosmos 1.7+'s `airflow.sdk` dependencies become available in our Airflow image.

## Why

uv's auto-resolution selected Cosmos 1.14.1 on the first sync. That version (and every 1.7+) imports symbols from `airflow.sdk.execution_time` — an Airflow-3-only module. House4House runs Airflow 2.10. Result: every DAG-load attempt that touched Cosmos crashed with:

```
ModuleNotFoundError: No module named 'airflow.sdk'
```

Cosmos 1.6.x is the last release line that targets Airflow 2.x cleanly without the sdk imports. Pinning `>=1.6,<1.7` keeps the auto-resolution from drifting up.

This isn't a Cosmos bug — it's the right shape for Cosmos to track Airflow 3. The bug is on our side: we pulled the upper-bound resolver loose. The pin is a defensive constraint until Airflow 3 is itself in scope.

## Options considered

1. **Pin `astronomer-cosmos[dbt-postgres]>=1.6,<1.7`** (chosen) — explicit upper bound, blocks accidental drift.
2. **Pin to a single version (`==1.6.5`)** (rejected) — too rigid; misses bug fixes within 1.6.x.
3. **Migrate to Airflow 3** (rejected as out of scope) — large surface, would require replacing `airflow.providers.postgres.hooks.postgres` patterns + DAG-decorator changes + provider-version bumps. Worth doing eventually but not as a side-effect of a Cosmos issue.
4. **Replace Cosmos with manual dbt orchestration** (rejected) — Cosmos's `DbtDag` autogenerates per-model task graphs from dbt's manifest; doing that by hand would replicate ~150 lines per dbt project for a marginal gain.

## Consequences

- Cosmos's Airflow-3-targeted features (per the 1.7+ changelog: improved Iceberg support, async loaders, native dataset triggers) are unavailable until we migrate. Acceptable trade-off — none of those are P0 needs today.
- A future Airflow 3 migration must explicitly bump Cosmos's upper bound at the same time as the Airflow upgrade. Otherwise the pin becomes an invisible blocker.
- `uv lock` re-runs after dep changes will respect the bound; Renovate / Dependabot configurations should NOT auto-bump Cosmos past 1.7.
- The pin makes [[2026-05-05-uv-workspace-shape]]'s unified-resolution promise easier to honor — a single bound, propagated everywhere.

## Status

`accepted` — Phase 1 shipped; the pin has held through Phase 2 and Phase 3 PR 1 with zero Cosmos-related issues. High confidence; the failure mode it prevents is concrete and reproducible.

## See also

- [[2026-05-05-uv-workspace-shape]] — the workspace this pin lives inside
- [[airflow-home-isolation]] — separate Phase 1 gotcha (same spike surfaced both)
- [[2026-05-08-phase-2-5-closure]] — Phase 2.5 absorbed into 2; this pin survived the merge unchanged
- All [[idealista]], [[jll]], [[remax]], [[zome]] DAGs depend on Cosmos for dbt orchestration
