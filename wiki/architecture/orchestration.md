---
title: Orchestration & scheduling
type: plan
last_verified: 2026-05-10
tags: [architecture, orchestration, airflow, scheduling, plan]
---

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
│   ├── dag_dbt_silver.py            # Daily — all Silver models via Cosmos DbtDag
│   ├── dag_dbt_gold.py              # Daily — all Gold models
│   ├── dag_deduplication.py         # Daily — listing dedup across portals (Flow F)
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
- **Flow F** (development portal cross-reference for UC-2): handled by `dag_deduplication` + per-portal ingest DAGs

## Schedule map

Per README §11.2, the recurring schedule:

| DAG | Schedule | Sprint | Dependencies |
|---|---|---|---|
| [[idealista]] scraper | `0 6 * * *` (daily 6AM UTC) | 2+ | None |
| [[jll]] scraper | `0 6 * * 4` (Thursdays 6AM) | 4.5+ | None |
| [[remax]] scraper | `0 6 * * 2` (Tuesdays 6AM) | 4.5+ | None |
| [[zome]] scraper | `0 6 * * 1` (Mondays 6AM) | 4.5+ | None |
| Geocoding pipeline | `0 9 * * *` | 2+ | After scrapers |
| Listing dedup | `0 10 * * *` | 3+ | After geocoding |
| dbt Silver run | `0 11 * * *` | 2+ | After dedup |
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
- [[airflow-home-isolation]] — `~/airflow/airflow.cfg` bleed gotcha + `make verify`'s isolation
- README §11 — the original orchestration section
