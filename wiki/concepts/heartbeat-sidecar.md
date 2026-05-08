---
title: Heartbeat sidecar tables
type: concept
last_verified: 2026-05-08
tags: [scd2, heartbeat, dlt, bronze, lifecycle]
---

## For future Claude

This is a concept page about heartbeat sidecar tables — the UPSERT-only companion tables that every SCD2 pipeline emits alongside its versioned facts. They answer the question "is this entity still in the source?" which SCD2 alone cannot: a stable unchanged row and a delisted row both produce no new SCD2 version. Read this when adding a new SCD2 source, debugging "why is silver showing this listing as active when it's clearly delisted?", or considering changing the 21-day floor.

## What it is

Every dlt-based SCD2 pipeline in our stack emits a **heartbeat sidecar** table next to its main facts:

| Pipeline | Facts table (SCD2) | Heartbeat sidecar (UPSERT) |
|---|---|---|
| [[jll]] | `jll_listings` / `jll_developments` | `heartbeat_listings` / `heartbeat_developments` |
| [[remax]] | `remax_listings` / `remax_developments` / `remax_plots` | `*_state` per entity |
| [[zome]] | `zome_listings` / `zome_developments` / `zome_plots` | `zome_*_state` per entity |
| [[idealista]] | `idealista_developments` / `idealista_development_units` | `idealista_developments_state` / `idealista_development_units_state` |

Schema: minimal — primary_key + `last_seen_date` (and sometimes a small set of identifying fields for fast joins). Write disposition: **UPSERT** (not append, not SCD2). Every load updates `last_seen_date` to the run date for every entity present in the scrape.

## Why

[[scd2-row-hash]] versioning answers "what changed about this listing?" but cannot answer "is this listing still in the source?" because:

- A stable unchanged listing produces NO new SCD2 version (correct behavior)
- A delisted listing also produces NO new SCD2 version — it just stops appearing in scrapes

Both look identical to SCD2: an old row with `_dlt_valid_to = NULL` (still current). Without the heartbeat, silver-layer queries can't distinguish "this listing has been on the market unchanged for 3 weeks" from "this listing was sold 3 weeks ago, the SCD2 just hasn't noticed."

The heartbeat fills that gap: every entity's `last_seen_date` updates on every successful run that observes it. Silver checks the date.

## How

**The 21-day floor** — silver-layer queries should treat a row as currently-active when:

```sql
last_seen_date >= current_date - 21
```

Why 21 days: weekly cadence (7) + one missed run (7) + slack (7). **Do not lower below 14 days.** Lowering to 7 means a single missed cron run flips half the listings to "inactive" in silver. The 21-day floor is conservative — it tolerates one full miss-and-recovery cycle.

**Stub handling** (per [[scd2-row-hash]]): when a source returns a degraded payload that would write a NULL-filled SCD2 row, skip the SCD2 write but **still emit the heartbeat**. The last known full SCD2 row stays current; the heartbeat ages out as expected; silver detects "inactive" via the heartbeat floor — same mechanism as a true delisting.

**UPSERT semantics**: each load issues `INSERT ... ON CONFLICT (primary_key) DO UPDATE SET last_seen_date = EXCLUDED.last_seen_date`. Failed runs leave the heartbeat unchanged — partial scrapes don't corrupt the heartbeat (entities not seen this run keep their previous `last_seen_date`).

**Heartbeat for soft-fail refs ≠ heartbeat for facts**: [[zome]]'s ref tables soft-fail (load with `trigger_rule=all_done`); the heartbeat is only emitted for fact tables. Refs are dimensional lookups; their absence is observable directly via join misses.

## See also

- [[scd2-row-hash]] — the companion mechanism this complements
- [[bronze-permissive]] — bronze never deletes, only marks stale; heartbeat is the staleness signal
- [[idealista]], [[jll]], [[remax]], [[zome]] — the four current heartbeat producers
- [pipelines/common/SCD2_RULES.md](../../pipelines/common/SCD2_RULES.md) — the heartbeat section of the canonical rules
