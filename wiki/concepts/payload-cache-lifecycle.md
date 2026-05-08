---
title: Payload cache lifecycle (`_payload_cache`)
type: concept
last_verified: 2026-05-08
tags: [idealista, scraping, cache, lifecycle, dlt]
---

## For future Claude

This is a concept page about the module-level `_payload_cache` mechanism in [[idealista]]'s dlt source — the shared cache that lets the four resources (developments, developments-state, units, units-state) reuse one Pass 2 + Pass 3 fetch instead of paying 4× the ZenRows cost. It explains the process-local lifecycle (fresh in every Airflow task, dirty in repeated `pipeline.run()` calls), the macOS host-sleep gotcha, and why the cache deliberately doesn't persist across runs. Read this before duplicating the pattern in another scraper, debugging "why are my Pass 3 calls re-firing?", or running [[idealista]] from a laptop.

## What it is

`_payload_cache` is a **module-level dict** in `pipelines/portals/idealista/source.py` that holds the result of Pass 2 (development detail pages) and Pass 3 (per-unit RE API JSON) fetches. The four dlt resources — developments, developments-state, development-units, development-units-state — all read from the same cache.

Lifecycle:

- **Populated once** at the start of each pipeline run, via a parallel `ThreadPoolExecutor` pre-fetch BEFORE the dlt resources start yielding rows
- **Read by all four resources** as they iterate
- **Process-local**: not persisted to disk, not shared across runs

## Why

Without the cache, each of the four resources would issue independent Pass 2 + Pass 3 fetches. Costs:

- ~3,000 developments × ~$0.007 (Universal Scraper Pass 2) × 4 resources = wasted ~$84 per run
- ~30,000 units × ~$0.0015 (RE API Pass 3) × 4 resources = wasted ~$135 per run

A run that should cost ~$26-38 would balloon to ~$300+ — economically infeasible at the configured cadence (daily 03:00 UTC).

The cache shaves the per-run cost by ~85% by ensuring each upstream call happens exactly once.

**Why not persist across runs?** Two reasons:

1. **Listings change** — caching across runs means a price drop or status change on day 2 isn't observed until the cache expires. SCD2 versioning ([[scd2-row-hash]]) depends on fresh fetches.
2. **Process boundaries are the right TTL** — Airflow tasks run in fresh Python processes; cache lifecycle naturally aligns with run boundaries. No additional invalidation logic needed.

## How

**The pattern**: pre-fetch in parallel, then yield from cache.

```python
# Module-level
_payload_cache: dict[str, dict] = {}

def _prefetch(developments: list[dict]) -> None:
    """Fan out Pass 2 + Pass 3 in parallel; populate _payload_cache."""
    with ThreadPoolExecutor(max_workers=...) as ex:
        for dev_id, payload in ex.map(_fetch_pass_2, developments):
            _payload_cache[dev_id] = payload
        # ... Pass 3 for unit_ids extracted from Pass 2 results

@dlt.resource(...)
def development_units():
    for unit_id in _all_unit_ids():
        detail = _payload_cache.get(unit_id, {})
        if detail.get("_re_api_stub"):
            continue  # stub handling per [[scd2-row-hash]]
        yield _row_from(unit_id, detail)
```

**Lifecycle constraints — IMPORTANT**:

- **Do NOT call `pipeline.run()` twice in the same Python process without clearing `_payload_cache`** between calls. Airflow tasks run in fresh processes, so this only matters in test harnesses or backfill scripts that loop `pipeline.run()`.
- **macOS host-sleep gotcha**: when triggering the DAG from a laptop, run under `caffeinate`. The cache is process-local — if macOS Idle Sleep kills the Python process mid-Pass-3, the heartbeat times out and the run fails to a full re-fetch from scratch on the retry. The dev-loop cost is real (~$30 wasted on the failed half-run).

**ThreadPoolExecutor concurrency**: tuned to balance ZenRows rate-limits (2.0s discovery, 1.5s detail per [[idealista]]) against parallelism. Roughly `max_workers ≈ 1 / rate_limit_per_endpoint × num_endpoints` — see config for current value.

**Why not `functools.lru_cache`?** Two issues: (1) per-function cache, can't share across the four resources without lifting it to module scope anyway; (2) no easy way to populate it in a single parallel sweep before iteration begins. Module-level dict is simpler and explicitly visible.

**Failure mode if violated**: if a future refactor moves cache-population into the resource generator, the four resources race to populate it, ZenRows rate-limits trigger, and the run fails opaquely. Keep the prefetch + read pattern explicit.

## See also

- [[idealista]] — the only consumer of this pattern today
- [[zenrows-universal-vs-re-api]] — the API-mix that makes the cache economically necessary
- [[scd2-row-hash]] — the stub-handling rule (stub-shaped payloads stay in the cache but skip the SCD2 row)
- [[heartbeat-sidecar]] — what the four resources still emit even for stub-shaped cache entries
