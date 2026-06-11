---
title: dev_uid stability — the append-only natural-key map
type: concept
last_verified: 2026-06-09
tags: [silver, cross_portal, dev_uid, stability, dbt, incremental, enrichment]
---

## For future Claude

This note is a concept about how `silver_unified_developments` keeps a **stable per-development identifier (`dev_uid`)** across wall-clock-triggered rebuilds, without the heavy registry/alias machinery first proposed and rejected during the 2026-06-09 orchestration interview. The mechanism is a single append-only dbt incremental table — `silver_dev_uid_map(portal, portal_dev_id) → dev_uid` — written once on first sight, never updated. Read this before extending enrichment pipelines that FK to `dev_uid` ([[UC-4]] LLM dev-actor search; future hedonic features that need per-dev identity), before tuning the `normalize_dev_name` macro, or before any change that would alter `silver_unified_developments` row identity.

## What it is

`silver_dev_uid_map` is the minimum viable persistence layer that makes `dev_uid` stable across rebuilds of the volatile connected-components graph in [[cross-portal-dev-dedup]].

Schema:

```sql
silver_dev_uid_map (
  portal           TEXT NOT NULL,
  portal_dev_id    TEXT NOT NULL,
  dev_uid          UUID NOT NULL,
  first_seen_at    TIMESTAMP NOT NULL,
  PRIMARY KEY (portal, portal_dev_id)
)
```

Materialization: dbt `incremental` model, `unique_key=(portal, portal_dev_id)`, **append strategy, no updates ever**. Once a row lands, it is immutable. The map grows monotonically — never shrinks even when a portal contributor disappears from bronze.

Scale: ~3k rows today (one per portal contributor across 5 portals); projected ~15k rows at 5-portal × 3k-dev steady state. Negligible.

## Why

The interview leading to this design rejected three alternatives in order:

1. **Live with `dev_key = MIN(member_id)` churn.** Rejected because [[UC-4]] LLM web-search for promoter+architect runs once per real-world dev, costs money per call, and writes back to a `silver_dev_actors` enrichment table. If the FK churns every rebuild, the LLM either re-runs daily (expensive) or its outputs orphan (worse).

2. **Persistent registry with oldest-wins + alias table + Python pre-step DAG.** Rejected as over-engineering: implied a `dag_dev_uid_resolver` DAG, a `silver_matching.dev_uid_aliases` table, and a `dag_dev_uid_full_reeval` manual DAG. The senior-data-eng review (consulted mid-interview) named the simpler form below.

3. **Content-hash `dev_uid` from `(concelho, normalized_name_from_highest_priority_portal)`.** Rejected because anchor portals can appear/disappear (e.g., JLL joins a dev that was previously idealista-only — content hash flips), and connected components are non-monotonic (merges AND splits can happen across runs), so no stateless content key is stable in general.

The append-only map adopted here is the minimal stateful element that survives all these failure modes. It is explicitly **not** the registry that was rejected: it has zero policy (no oldest-wins, no merge resolution, no alias redirection), zero extra DAGs (lives inside `dag_dbt_silver` as a vanilla dbt model), and zero non-dbt code.

## How

### Daily silver run (per [[2026-06-09-silver-wall-clock-not-datasets]])

`dag_dbt_silver` fires at `0 11 * * *`. The Cosmos task graph runs three models in order: `silver_dev_uid_map` (incremental append) → `silver_unified_developments` (full rebuild) → `silver_unified_listings` (full rebuild).

### `silver_dev_uid_map` build logic

```text
1. Read bronze + heartbeat-alive rows across all 5 portals
   (heartbeat.last_seen >= now() - 21d per [[heartbeat-sidecar]]).
2. Compute connected components via the dual-Jaccard recursive CTE
   from [[cross-portal-dev-dedup]] (same-concelho gated, token-Jaccard
   ≥ 0.6 OR char-trigram Jaccard ≥ 0.6).
3. LEFT JOIN each member (portal, portal_dev_id) against the existing
   silver_dev_uid_map.
4. For each component, the inherited dev_uid = MIN(existing dev_uid
   among members). If no member has an existing dev_uid, mint a fresh
   UUID via gen_random_uuid().
5. Emit only the NEW (portal, portal_dev_id) tuples (those absent from
   the existing map) with their assigned dev_uid. dbt's incremental
   append writes them; existing rows are untouched.
```

The append-only invariant is what guarantees stability: once a tuple is mapped, that mapping is permanent for the lifetime of the warehouse.

### Identity surface in `silver_unified_developments`

`silver_unified_developments` carries TWO identifiers:

| Column | Type | Stability | Use |
|---|---|---|---|
| `component_id` | INT | Volatile per run (just the recursive-CTE row number) | Runtime grouping label only; never persisted externally |
| `dev_uids` | UUID[] | Stable; each element is permanent | The FK target for enrichment |

Enrichment tables ([[UC-4]] `silver_dev_actors`, future hedonic features) FK on `dev_uid` (singular UUID, PK on those tables). They JOIN to `silver_unified_developments` via `WHERE silver_unified_developments.dev_uids @> ARRAY[silver_dev_actors.dev_uid]` or unnest equivalents.

For listings, see [[cross-portal-dev-dedup]] — `silver_unified_listings.dev_uid` is a single UUID populated via a LEFT JOIN on `(concelho, match_name)` against `silver_unified_developments` at silver build time. CV enrichment ([[silver_image_features]]) FKs on `(portal, portal_listing_id)` — naturally stable from bronze, independent of `dev_uid` mechanics.

### Merge case — when a new contributor bridges two existing components

Two previously-separate components each have their own `dev_uid` (`ABC` and `DEF`). On day N a new portal contributor (or a relisted record with a name that bridges both) joins → graph collapses to one component. The map LEFT JOIN finds two distinct existing `dev_uid`s in one component. The component inherits `MIN(ABC, DEF)` for any newly-inserted member tuples, but **both `ABC` and `DEF` survive in the map** (append-only — neither row gets deleted or rewritten).

`silver_unified_developments` for that real-world dev now has `dev_uids = [ABC, DEF]`. Existing enrichment rows for both `ABC` and `DEF` continue to surface side-by-side. The downstream signal "we thought these were two devs and ran LLM on both, but they are actually one" is **observable**, not silent. UC-3's Atlas Inspector can render both promoter answers and surface the conflict for operator review.

### Split case — when a bridge contributor disappears

A previously-bridged component loses the contributor that connected two halves (>21d heartbeat-stale → drops from bronze-alive). The graph splits into two sub-components. Every member of each sub-component still carries its original `dev_uid` (from the immutable map). Both sub-components emit `dev_uids = [ABC]`. Two rows in `silver_unified_developments` claim the same `dev_uid` — an observable signal that something split. Enrichment is correctly attached to `ABC` and surfaces in both rows; downstream UX decides how to render.

This is the rare case where having multiple silver rows share a `dev_uid` is correct behavior, not corruption. Document in UC-3 query patterns.

### Macro-flush workflow (when `normalize_dev_name` improves)

The map is sticky by design: a macro improvement does NOT auto-propagate to existing rows. To re-resolve affected devs, the operator:

1. Identifies the affected `(portal, portal_dev_id)` tuples by re-running the matching macros against bronze and diffing against the existing map (one-off SQL or notebook).
2. Issues a `DELETE FROM silver_dev_uid_map WHERE (portal, portal_dev_id) IN (...)`.
3. Re-runs `dag_dbt_silver`. The deleted rows are re-inserted with potentially different `dev_uid` assignments based on the new graph.
4. Affected enrichment rows now orphan or remap; an explicit ad-hoc cleanup of `silver_dev_actors` etc. is part of the runbook for each macro-flush event.

Deliberately not automated. Macro flushes are rare and high-stakes; each one is an operator-led event with a defined diff and rollback path.

## See also

- [[cross-portal-dev-dedup]] — the connected-components matching that produces the input to this map.
- [[2026-06-09-silver-wall-clock-not-datasets]] — the orchestration decision under which this design works.
- [[heartbeat-sidecar]] — the 21-day floor that defines "bronze + heartbeat-alive."
- [[UC-4]] — the LLM dev-actor enrichment that is the primary consumer of stable `dev_uid`.
- [[medallion-layering]] — silver layering principles this design respects.
- [[silver-dq-baseline]] — the universal silver invariants `silver_unified_developments` and the map satisfy.
