---
title: Orchestration & scheduling
type: plan
last_verified: 2026-06-09
tags: [architecture, orchestration, airflow, scheduling, plan]
---

## Addendum 2026-06-09 — silver wall-clock trigger locked

Two changes from the 2026-06-09 orchestration interview ([[2026-06-09-silver-wall-clock-not-datasets]]):

1. **`dag_deduplication` removed** from the transformation taxonomy + schedule map. Cross-portal listing-level dedup was dropped from the silver design (only UC-3 matters for v1; UC-3 doesn't need it). Dev-grain dedup now lives inside `dag_dbt_silver` via the `silver_dev_uid_map` incremental model (see [[dev-uid-stability]]).
2. **Silver trigger explicitly locked to wall-clock cron `0 11 * * *`** (no Airflow Datasets). The wider rationale in [[2026-06-09-silver-wall-clock-not-datasets]]: portal scrapers are themselves cron-driven, so Dataset emission would buy zero freshness and introduce churn that forced rejected registry machinery downstream. This is consistent with the existing "wall-clock based, not sensor-based" posture documented below in §"Dependency conventions" — Datasets are a softer form of the same coupling and were rejected on the same grounds.

Default portal-DAG retry policy also locked (interview output): `retries=2`, exponential backoff, `max_retry_delay=1h`. Concurrency: `max_active_runs=1` per portal, `zenrows_pool slots=2`, `ZENROWS_DAILY_BUDGET_USD=20` soft cap in source.

## For future Claude

This is the **orchestration** page — the Airflow DAG taxonomy (ingestion / transformation / quality / maintenance), the schedule map for every recurring DAG, and the dependency conventions between them. Read this when adding a new DAG, debugging a missed schedule, planning a backfill, or asked "when does X run?". Companion to [[infra]] (where Airflow runs) and [[ingest-flows]] (the conceptual flow types each DAG implements).

## What it is

Airflow 2.10 with LocalExecutor + Cosmos 1.6 (per [[2026-05-05-cosmos-pin]]). DAGs live in `dags/` and `pipelines/<area>/<source>/<source>_ingestion_dag.py` (auto-discovered via the Airflow DAG processor). Four DAG categories: ingestion (pull data in), transformation (dbt staging + silver + gold), quality (dbt tests + Great Expectations), maintenance (vacuum, matview refresh, backups).

## DAG taxonomy

```
dags/
├── ingestion/         (one DAG per source — auto-discovered)
│   ├── (P0 sources): caop, bgri, osm, idealista, ine, bpstat, ecb
│   ├── (P1 sources): bupi, cadastro, cos, crus, crus-ogc, eurostat,
│   │                 jll, lidar, remax, sce, srup, srup-ogc, zome
│   └── (P2 sources): apa, aveiro-pmot, lneg
├── transformation/
│   ├── dag_dbt_silver.py            # Daily 11:00 — all Silver models via Cosmos DbtDag
│   │                                #   (includes silver_dev_uid_map → silver_unified_developments
│   │                                #    → silver_unified_listings; see [[dev-uid-stability]])
│   ├── dag_dbt_gold.py              # Daily 12:00 — all Gold models
│   ├── dag_geocoding.py             # Daily — geocode new records via Nominatim
│   └── dag_location_scores.py       # Weekly — recompute UC-1 location scores
├── quality/
│   ├── dag_data_quality.py          # Daily — dbt tests + Great Expectations checks
│   └── dag_freshness_monitor.py     # Hourly — check source freshness (heartbeat ages)
└── maintenance/
    ├── dag_matview_refresh.py       # Daily — refresh materialized views
    ├── dag_vacuum_analyze.py        # Weekly — PostgreSQL maintenance
    └── dag_backup.py                # Daily — pg_dump + MinIO backup
```

Per the [[ingest-flows]] taxonomy, ingestion DAGs map to flows:
- **Flow A** (REST API): [[ine]], [[bpstat]], [[eurostat]], [[ecb]], [[idealista]] (RE API leg)
- **Flow B** (web scraping): [[idealista]] (Universal Scraper leg), [[sce]]
- **Flow C** (GIS): all 14 GIS sources
- **Flow D** (derived): the `transformation/` DAGs above
- **Flow E** (spatial composition for UC-3): part of `dag_dbt_silver` + `dag_dbt_gold`
- **Flow F** (development portal cross-reference for UC-2): handled inside `dag_dbt_silver` via the [[dev-uid-stability|silver_dev_uid_map]] + [[cross-portal-dev-dedup]] models (the previous `dag_deduplication` was retired 2026-06-09; listing-grain dedup was dropped, dev-grain dedup is now an in-DAG dbt step)

## Schedule map

Per README §11.2, the recurring schedule:

| DAG | Schedule | Sprint | Dependencies |
|---|---|---|---|
| [[idealista]] scraper | `0 6 * * *` (daily 6AM UTC) | 2+ | None |
| [[jll]] scraper | `0 6 * * 4` (Thursdays 6AM) | 4.5+ | None |
| [[remax]] scraper | `0 6 * * 2` (Tuesdays 6AM) | 4.5+ | None |
| [[zome]] scraper | `0 6 * * 1` (Mondays 6AM) | 4.5+ | None |
| Geocoding pipeline | `0 9 * * *` | 2+ | After scrapers |
| dbt Silver run | `0 11 * * *` | 2+ | Wall-clock; includes `silver_dev_uid_map` + cross-portal dev dedup inline (see [[2026-06-09-silver-wall-clock-not-datasets]]) |
| dbt Gold run | `0 12 * * *` | 2+ | After Silver |
| MatView refresh | `0 13 * * *` | 6+ | After Gold |
| [[ecb]] Euribor | `0 6 1 * *` (monthly 1st) | 2+ | None |
| [[ine]] indicators | `0 6 1 * *` (monthly 1st) | 1+ | None |
| [[bpstat]] | `0 6 15 * *` (monthly 15th) | 2+ | None |
| [[eurostat]] HPI | `0 6 5 1,4,7,10 *` (quarterly) | 2+ | None |
| [[osm]] full import | `0 2 1 * *` (monthly 1st) | 1+ | None |
| Location scores | `0 3 * * 0` (weekly Sunday) | 4+ | After OSM |
| Data quality | `0 14 * * *` | 6+ | After Gold |
| Freshness monitor | `0 * * * *` (hourly) | 6+ | None |
| MatView refresh | `0 13 * * *` (daily) | 6+ | After Gold |
| Vacuum + analyze | `0 4 * * 0` (weekly Sunday 4AM) | 1+ | None |
| pg_dump backup | `0 2 * * *` (daily 2AM) | 1+ | None |
| `/wiki-lint` (host cron, NOT Airflow) | `0 6 * * 0` (weekly Sunday 6AM, host launchd) | 3+ | None |

**Manual-trigger DAGs** (no schedule; fired from Airflow UI as needed):
- All P2 GIS sources: [[apa]], [[aveiro-pmot]], [[lneg]]
- Slow / one-off P1 GIS: [[bupi]], [[cadastro]], [[cos]], [[crus]], [[crus-ogc]], [[lidar]], [[srup]], [[srup-ogc]]
- [[sce]] (only-Aveiro scope; expand-and-trigger when ready for full-country)
- [[caop]] (annual release; fired with version + download_url params)

## Dependency conventions

Two patterns:

1. **Time-based (wall-clock cron)**: most DAGs depend on the wall clock to coordinate (e.g., listing dedup runs at 10AM after scrapers complete by 9AM). Simple, no Airflow-level coupling.
2. **Task-graph dependency** (within a DAG): Cosmos's `DbtDag` auto-generates per-model task graphs from `dbt_project.yml` + `manifest.json`. dbt's `ref()` calls become Airflow task dependencies inside `dag_dbt_silver` and `dag_dbt_gold`. We don't manage this graph by hand.

**Cross-DAG dependencies are deliberately wall-clock based** rather than `ExternalTaskSensor`-driven. Reasons:
- Sensors create tight coupling that breaks on retry-storms or single-DAG failures
- Wall-clock scheduling tolerates a single-DAG miss without cascading
- Solo-dev operations doesn't have the bandwidth to debug sensor races

If a hard dependency emerges (e.g., "gold must NEVER run on stale silver"), encode it via the `dbt_test_*` task at the start of `dag_dbt_gold` — fail fast on the gate test rather than wait for a sensor.

## Operational conventions

- **All DAGs `catchup=False`** unless a backfill is explicitly running. Solo-dev operations doesn't have time to debug a backfill that started 6 months ago.
- **All DAGs use Pool=`default`** unless an explicit concurrency limit is needed (e.g., scrapers limited to 1 concurrent run via `max_active_runs=1`).
- **Audit copy + heartbeat sidecar** for every portal scraper (per [[scd2-row-hash]] + [[heartbeat-sidecar]]).
- **`on_failure_callback`** wired on portal scrapers to fire a dlt schema-contract alert (see [[bronze-permissive]]).
- **Schedule changes** require updating BOTH the DAG default + the schedule map above. The README → wiki migration's PR 7 will lift this table to a "living" `wiki/architecture/orchestration.md` section that `/wiki-lint` cross-checks against the actual DAG `schedule_interval=` declarations.

## See also

- [[tech-stack]] — Airflow + Cosmos versions + LocalExecutor rationale
- [[infra]] — where Airflow runs (Docker Compose service map)
- [[data-quality]] — `dag_data_quality.py` taxonomy
- [[ingest-flows]] — the conceptual flow types each DAG implements
- [[2026-05-05-cosmos-pin]] — Cosmos pinned `>=1.6,<1.7`
- [[2026-05-10-airflow-2-not-3]] — Airflow 2 stay-the-course decision
- [[2026-06-09-silver-wall-clock-not-datasets]] — silver wall-clock lock + Datasets rejection
- [[dev-uid-stability]] — append-only `silver_dev_uid_map` driving in-DAG dev-grain dedup
- [[cross-portal-dev-dedup]] — dev-dedup model `silver_unified_developments`
- [[airflow-home-isolation]] — `~/airflow/airflow.cfg` bleed gotcha + `make verify`'s isolation
- README §11 — the original orchestration section
