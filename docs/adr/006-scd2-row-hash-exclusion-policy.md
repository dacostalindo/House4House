# ADR 006 — SCD2 `row_hash` exclusion policy

**Status:** Stub — body TBD (Sprint 9 backfill)
**Decision-makers:** TBD
**Date:** TBD

## Context (TBD)

Each portal's SCD2 fact table computes `row_hash` over a curated subset of columns (`*_VERSION_COLUMNS`). Many columns are deliberately excluded. Why?

A naive "hash everything" approach causes spurious SCD2 versions: the API reorders an array, the timestamp ticks, a Pass 2 snapshot field updates → new row version with no real lifecycle change.

## Decision (TBD)

We curate `*_VERSION_COLUMNS` per fact table to capture only fields that represent **real lifecycle events**.

Categories systematically excluded:
1. **JSONB arrays** (galleries, room lists, attribute arrays) — order non-deterministic across API calls.
2. **Snapshot-derived fields** (`market_days`, `previous_price`, modified-at timestamps) — change every load regardless.
3. **Immutable physical attributes** (GPS, address, construction year, name) — changes here are data corrections, not real events.
4. **Display-only metadata** (`raw_json`, `raw_meta`) — included for debugging; not signal.

## Rejected alternatives (TBD)

- Hash everything (default dlt behavior). Versions every load.
- Hash only the PK + price (too aggressive — misses status flips, count changes).
- Use dbt snapshots instead of dlt SCD2 (different tradeoffs — Postgres-side, less control).

## Consequences (TBD)

- Adding a new column to a portal's bronze table requires deciding: in `*_VERSION_COLUMNS` or not?
- Sprint 4.5 silver work can rely on SCD2 versions to detect real changes (price drops, status flips, sold transitions).
- Engineering convention: any column added to bronze must come with an explicit row_hash decision documented in source.py comments.

## References to dig into when filling

- `wiki/concepts/scd2-row-hash.md` — current policy doc.
- `pipelines/portals/{remax,idealista,zome}/source.py` — `*_VERSION_COLUMNS` and `*_JSON_COLUMNS` lists per fact table.
- `dbt/models/staging/listings/_staging_listings__sources.yml` — column descriptions note "IN row_hash" / "EXCLUDED from row_hash" inline.
- `_stable_hash` implementation in source.py.
