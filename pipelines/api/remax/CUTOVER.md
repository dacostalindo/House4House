# RE/MAX bronze cutover — legacy → dlt SCD2

> **Status: CUTOVER COMPLETE (2026-04-28)**
>
> Day-0 of new bronze: 2026-04-28. First successful load:
> - 609 developments, 8,630 listings (current SCD2 state)
> - 3,806 listings enriched via parallel Pass 2 (~37 min — 8× faster than legacy ~5h)
> - 77 Pass 2 timeouts (2%) yielded NULL enrichment per the documented design
>
> Legacy DAG files (`remax_ingestion_dag.py`, `remax_bronze_developments_dag.py`,
> `remax_bronze_listings_dag.py`) and helpers (`remax_scraper.py`, `remax_config.py`)
> were deleted on 2026-04-28 in the same PR as the dlt code. Legacy bronze tables
> (`raw_remax_developments`, `raw_remax_listings`) dropped before first load.
>
> Soak gates (informational — decommission already done):
> - [ ] ≥3 successful weekly runs (1/3 so far; need 2 more Tuesday runs)
> - [ ] ≥1 SCD2 transition (none yet — will appear once a unit's price/status changes)
> - [ ] ≥1 sidecar delisting (none yet — first run, baseline)
>
> This document is kept as the migration runbook reference.

---

Day-0 of new bronze: **today** (no historical scrapes preserved — clean slate).

This cutover follows the same pattern as the Zome migration (see
`pipelines/api/zome/CUTOVER.md`). Differences:

- Day-1 deletion of legacy DAG files in the same PR — no soak alongside.
- Pass 2 detail enrichment is parallelized via `ThreadPoolExecutor` inside
  `source._prefetch_pass2()`. Expected runtime drops from ~5h (sequential)
  to ~15-20 min (4 workers × 1s per-worker delay).

## Pre-flight (before touching anything)

1. **Verify `dlt[postgres]~=1.25.0` is installed** in the Airflow image:
   ```bash
   docker compose exec airflow-webserver python -c "import dlt; print(dlt.__version__)"
   # → 1.25.0 (already installed for Zome cutover)
   ```
2. **Verify `dlt_state` volume mounted** and writable:
   ```bash
   docker compose exec airflow-scheduler ls -la /opt/airflow/dlt_state
   # → `airflow` user can write; will create `remax/` subdir on first load
   ```
3. **Verify the new DAG parses** in Airflow:
   - Airflow UI → DAGs → search `remax_dlt`
   - If it doesn't appear, check the scheduler log for an `ImportError`. Most
     likely cause: `pipelines.api.remax.source` failed to import; fix and re-run.

## Cutover sequence (clean slate — no backup, no soak)

### 1. Verify no dbt/scripts dependency on legacy tables
```bash
grep -rn "raw_remax\|REMAX_BRONZE\|remax_ingestion\|remax_bronze_load" \
  dbt/ scripts/ \
  | grep -v __pycache__
# Expect: no hits (legacy DAGs only referenced by their own files)
```

### 2. Drop legacy bronze tables
```sql
DROP TABLE IF EXISTS bronze_listings.raw_remax_developments CASCADE;
DROP TABLE IF EXISTS bronze_listings.raw_remax_listings     CASCADE;
```

### 3. Delete legacy DAG files (same PR as the new code)
```bash
rm pipelines/api/remax/remax_scraper.py
rm pipelines/api/remax/remax_config.py
rm pipelines/api/remax/remax_ingestion_dag.py
rm pipelines/api/remax/remax_bronze_developments_dag.py
rm pipelines/api/remax/remax_bronze_listings_dag.py
```

Force Airflow to reparse so the legacy DAGs disappear:
```bash
docker compose exec airflow-webserver airflow dags reserialize
docker compose exec airflow-webserver airflow dags list | grep remax
# → only `remax_dlt` should remain (plus dbt_remax_build)
```

### 4. Trigger the new DAG once manually
- Airflow UI → `remax_dlt` → Trigger DAG (no config args needed)
- Watch tasks in order: `audit_to_minio` → `load_facts` → `validate_facts`
- `load_facts` is the long-running one. Expected: ~15-20 min total.
  - First ~30s: Pass 1 (14 paginated POSTs at 1s delay)
  - ~15-20 min: Pass 2 parallel prefetch (3,900 details / 4 workers @ 1s = ~15 min)
  - Final ~30s: dlt SCD2 merge into Postgres

### 5. Verify expected tables exist
```sql
\dt bronze_listings.*
-- expect to see (in addition to existing zome_* tables):
--   remax_developments
--   remax_listings
--   remax_developments_state
--   remax_listings_state
```

### 6. Verify counts
```sql
SELECT
  (SELECT count(*) FROM bronze_listings.remax_developments  WHERE _dlt_valid_to IS NULL) AS dev_current,
  (SELECT count(*) FROM bronze_listings.remax_listings      WHERE _dlt_valid_to IS NULL) AS list_current,
  (SELECT count(*) FROM bronze_listings.remax_developments_state) AS dev_state,
  (SELECT count(*) FROM bronze_listings.remax_listings_state)     AS list_state,
  (SELECT count(*) FROM bronze_listings.remax_listings
   WHERE _dlt_valid_to IS NULL AND market_days IS NOT NULL) AS pass2_enriched;
-- expect: dev_current ~614, list_current ~8745, state == current, pass2 ~3900
```

If counts are off, do NOT enable the schedule yet — investigate first. The
`validate_facts` task will also have flagged this, so check its log.

### 7. Enable Tuesday weekly schedule
- Airflow UI → `remax_dlt` → toggle ON
- Confirm next scheduled run is the upcoming Tuesday at 06:00 UTC
  (Tuesday avoids the Monday clash with `zome_dlt`)

## Soak (informational — decommission already done in step 3)

Same gates as Zome, observed retroactively:

1. **≥1 SCD2 transition** in the new pipeline (validates `row_hash` design):
   ```sql
   SELECT count(*) FROM bronze_listings.remax_listings WHERE _dlt_valid_to IS NOT NULL;
   -- expect > 0 within 1-2 weeks
   ```
2. **≥1 sidecar delisting** (validates heartbeat):
   ```sql
   SELECT count(*) FROM bronze_listings.remax_listings_state
   WHERE last_seen_date < (SELECT max(last_seen_date) FROM bronze_listings.remax_listings_state);
   -- expect > 0 within 1-2 weeks
   ```
3. **≥3 successful weekly runs** (validates Pass 2 parallel stability):
   ```sql
   SELECT count(DISTINCT load_id)
   FROM bronze_listings._dlt_loads
   WHERE schema_name = 'remax_facts' AND status = 0;
   -- expect ≥ 3 within 4 weeks
   ```

If either (1) or (2) hasn't fired naturally within 4 weeks, force one with a
synthetic edit on a test row (DO NOT mark validation complete on row counts
alone — that would validate insertion only, not the SCD2 transition path).

## Rollback (only viable BEFORE step 7 — schedule enabled)

If something fundamental breaks after step 4 but before the schedule is on,
restore the legacy code from git:

```bash
git checkout HEAD~1 -- pipelines/api/remax/
# Then drop the new tables:
psql -c "DROP TABLE bronze_listings.remax_developments CASCADE;
         DROP TABLE bronze_listings.remax_listings CASCADE;
         DROP TABLE bronze_listings.remax_developments_state CASCADE;
         DROP TABLE bronze_listings.remax_listings_state CASCADE;"
# Recreate empty legacy tables:
psql -f pipelines/api/remax/rollback_remax.sql
# Re-enable the legacy DAGs and trigger remax_ingestion to repopulate.
```

The `rollback_remax.sql` companion file recreates the legacy bronze table
DDL. There is no data backup taken (clean-slate cutover); a rollback would
mean re-scraping from RE/MAX (~5h sequential).

## Known caveats

- **Day-1 deletion is irreversible without re-scraping.** Unlike the Zome
  cutover (which kept legacy DAGs paused alongside), the RE/MAX cutover
  deletes legacy code and tables in the same PR. If `remax_dlt` fails on
  first run, Pass 1 needs ~5 min to re-fetch — easy to recover from.
  Production data wipeout is the bigger risk; tables can be recreated
  from `rollback_remax.sql` but contain no rows until next scrape.
- **`PASS2_MAX_WORKERS = 4` is conservative.** RE/MAX has not rate-limited us
  in testing, but parallelism could trigger an IP block. Start at 4. If 3
  consecutive runs succeed, raise to 8 for ~7 min runtime. If 429s appear,
  drop back to 4 or sequential.
- **Pass 2 detail failures yield empty enrichment**, never block the load.
  Watch the `validate_facts` `pass2_enriched` count over time — if it drops
  significantly, the Next.js endpoint format changed or buildId extraction
  broke.
- **MinIO files are an audit copy of Pass 1 only.** Pass 2 details are not
  mirrored (~3,900 tiny files would be too granular). If we ever need Pass 2
  audit, dump to a single concatenated JSONL.
- **Sidecar staleness threshold for silver.** Use `last_seen_date >=
  current_date - 21` (weekly cadence + 1 missed run + slack). Same as Zome.
