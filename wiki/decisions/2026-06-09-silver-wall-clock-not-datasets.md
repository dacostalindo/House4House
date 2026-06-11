---
title: Silver orchestration — wall-clock cron, not Airflow Datasets
type: decision
last_verified: 2026-06-09
tags: [orchestration, silver, airflow, datasets, scheduling, dev-uid, portals]
confidence: medium
---

## For future Claude

This is a decision record locking the trigger model for `silver_unified_developments` + `silver_unified_listings`: **wall-clock daily cron at `0 11 * * *`, not event-driven Airflow Datasets**. The decision was reached through an interview that started by adopting Datasets, then walked back to wall-clock after a senior-data-eng review showed Datasets were over-engineering for a system whose upstreams (portal scrapers) are themselves cron-driven, not event-driven. Read this before adding any cross-DAG triggering to the silver layer, or before reopening "should silver fire when a portal lands?" — the answer is "no, silver runs at 11:00 daily and sees whatever bronze has."

## Decision

Daily silver build runs on **wall-clock cron `0 11 * * *`** via Cosmos `DbtDag`. All five portal scrapers continue to run on their existing per-portal cron schedules ([[idealista]] daily 06:00, [[remax]] Tuesday, [[jll]] Thursday, [[zome]] Monday, [[imovirtual]] TBD). No Airflow Datasets are emitted by the portal DAGs for the silver chain. Silver builds whatever bronze + heartbeat-alive rows it finds at 11:00, regardless of which portal scrapers ran today.

Specifically rejected: per-portal `Dataset("portal://X/v1")` emission with silver subscribing via `schedule=[ds1, ds2, ds3, ds4, ds5]` and an any-of trigger.

## Why

The interview initially adopted Datasets because Dataset-driven triggering seemed semantically correct ("fire silver when portals refresh"). On review, three problems collapsed the choice:

1. **The upstreams are already cron, not event-driven.** Portal scrapers fire on fixed wall-clock schedules. The "event" they emit (Dataset on success) is deterministic-by-time anyway. A wall-clock silver run at 11:00 catches everything that landed in the 05:00–10:00 scraper window. Datasets buy zero freshness vs. the simpler cron.

2. **Any-of-5 firing rebuilds silver up to 5× per week with no semantic gain.** UC-3 (the only v1 consumer per [[2026-05-12-uc3-expanded-scope]]) cares about latest state, not refresh timeliness within the day. Five rebuilds Mon–Fri = 5× the recursive-CTE cost, 5× dbt test runs, 5× downstream matview churn. Wall-clock collapses to one rebuild per day.

3. **The "stability machinery" the Datasets choice forced was the actual over-engineering.** Dataset-driven any-of-5 firing meant silver rebuilt on every portal landing → daily `dev_key` churn → required a persistent registry + alias table + Python pre-step DAG + manual full-reeval DAG to keep enrichment FKs stable. Wall-clock + the append-only `silver_dev_uid_map` (see [[dev-uid-stability]]) achieves the same stability with one dbt incremental model and zero extra DAGs.

The senior-data-eng review framed it: "Datasets here are over-engineering — your scrapers run on fixed daily/weekly crons, not event-driven." Adopted.

Wall-clock also aligns with the project-wide pattern documented in [[orchestration]] §"Dependency conventions": **"Cross-DAG dependencies are deliberately wall-clock based rather than `ExternalTaskSensor`-driven. Sensors create tight coupling that breaks on retry-storms; wall-clock tolerates a single-DAG miss without cascading."** Datasets are a softer form of the same coupling; the same argument applies.

## Consequences

**What this enables:**

- One silver rebuild per day at `0 11 * * *`. ~3min wall-clock today, ~15min projected at 5M listings (see [[cross-portal-dev-dedup]] revisit gate).
- No Dataset URI namespace to maintain. No `Dataset(...)` outlets in portal DAGs.
- The chain `portal scrapers → silver → gold → enrichment DAGs` stays purely wall-clock-coordinated. Failure of one portal does not block silver via process state; it just means that portal's bronze rows aren't refreshed today (heartbeat 21-day floor smooths the gap per [[heartbeat-sidecar]]).
- `silver_dev_uid_map` (the append-only stability map per [[dev-uid-stability]]) is the only state-carrying element across runs. Removed: `silver_matching.dev_uid_aliases`, `dag_dev_uid_resolver` Python pre-step DAG, `dag_dev_uid_full_reeval` manual DAG. Macro flushes are operator-driven: delete affected map rows + rerun silver.

**What this costs:**

- Silver runs even on quiet days where no portal refreshed. Cost: ~3min of compute for no semantic change. Acceptable (single server, off-hours).
- If a portal scraper fails its 06:00 run + uses all retries through ~07:45 (per the locked uniform `retries=2, exponential backoff to 1h` policy), silver at 11:00 may build without that portal's fresh data. Heartbeat 21d floor smooths this — old rows stay alive in silver until 21d of consecutive misses.

**What stays open:**

- Gold gate (silver → gold trigger): deferred to gold-design session. Current placeholder is wall-clock `0 12 * * *` as in [[orchestration]] §"Schedule map".
- Enrichment DAGs (CV, LLM dev-actor, LLM plot extraction) run on their own schedules; they consume silver tables at read-time, no trigger coupling. CV/LLM enrichment FKs use stable keys per [[dev-uid-stability]] so they survive silver rebuilds.

## Status

`accepted` (2026-06-09). Re-open if a future enrichment pipeline emerges that genuinely needs sub-daily latency from a portal landing to a downstream artifact — at which point per-portal Datasets become reasonable for that specific consumer (not for silver itself).

## See also

- [[dev-uid-stability]] — the append-only map that makes wall-clock stability work without registry machinery.
- [[cross-portal-dev-dedup]] — how `silver_unified_developments` consumes bronze + heartbeat-alive rows on each rebuild.
- [[heartbeat-sidecar]] — the 21-day floor that smooths individual portal-miss days.
- [[orchestration]] — DAG taxonomy + schedule map; wall-clock-vs-sensor rationale.
- [[2026-05-10-airflow-2-not-3]] — the orchestrator pin under which this design runs.
- [[2026-05-12-uc3-expanded-scope]] — the use case constraint that justified the simplification (only UC-3 matters for v1).
