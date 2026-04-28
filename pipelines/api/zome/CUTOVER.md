# Zome bronze cutover — legacy → dlt SCD2

> **Status: COMPLETE (2026-04-28)**
>
> Day-0 of new bronze was 2026-04-26. Decommission gates passed on 2026-04-28:
> - ✅ 3 successful weekly loads in `_dlt_loads`
> - ✅ 13 SCD2 transitions observed in `zome_listings`
> - ✅ 13 sidecar delistings observed in `zome_listings_state`
>
> Legacy DAG files (`zome_ingestion_dag.py`, `zome_bronze_developments_dag.py`,
> `zome_bronze_listings_dag.py`) and `zome_config.py` were deleted on 2026-04-28.
> The single `zome_dlt` DAG is now the sole ingestion path.
>
> This document is kept for historical reference and as a template for the
> RE/MAX cutover.

---

Day-0 of new bronze: **today** (no historical scrapes preserved).

## Pre-flight (before touching anything)

1. **Rebuild the Airflow image** so `dlt[postgres]~=1.25.0` is installed:
   ```bash
   docker compose build airflow-webserver airflow-scheduler airflow-init
   ```
2. **Recreate the Airflow services** so the new `dlt_state` named volume is mounted:
   ```bash
   docker compose up -d airflow-webserver airflow-scheduler
   docker compose exec airflow-scheduler ls -la /opt/airflow/dlt_state
   # → should be writable by `airflow` user
   ```
3. **Verify the new DAG parses** in Airflow:
   - Airflow UI → DAGs → search `zome_dlt`
   - If it doesn't appear, check the scheduler log for an `ImportError`. Most likely cause: `pipelines.api.zome.source` failed to import; fix and re-run.

## Cutover sequence

### 1. Capture rollback insurance
```bash
docker compose exec warehouse pg_dump \
  -U warehouse -d house4house --data-only \
  -t bronze_listings.raw_zome_developments \
  -t bronze_listings.raw_zome_listings \
  > /tmp/zome_pre_cutover.sql

# Move the dump out of the container (or run pg_dump from the host with -p 5433).
```

The DDL companion to this dump is committed at `rollback_zome.sql`.

### 2. Pause legacy DAGs (do NOT delete the files yet)
- Airflow UI → toggle off:
  - `zome_api_ingestion`
  - `zome_bronze_load_developments`
  - `zome_bronze_load_listings`

### 3. Drop legacy bronze tables
```sql
DROP TABLE IF EXISTS bronze_listings.raw_zome_developments CASCADE;
DROP TABLE IF EXISTS bronze_listings.raw_zome_listings     CASCADE;
```
Confirmed safe via `grep -r raw_zome dbt/` — no dbt sources or models reference these tables.

### 4. Trigger the new DAG once manually
- Airflow UI → `zome_dlt` → Trigger DAG (no config args needed)
- Watch tasks in order: `audit_to_minio` → `load_facts` → (`load_refs`, `validate_facts`)

### 5. Verify expected tables exist
```sql
\dt bronze_listings.*
-- expect to see:
--   developments
--   listings
--   zome_developments_state
--   zome_developments
--   zome_listings
--   zome_developments_state
--   zome_listings_state
--   ref_zome_condition          (if refs task succeeded)
--   ref_zome_property_type      (")
--   ref_zome_business_type      (")
--   _dlt_loads
--   _dlt_pipeline_state
--   _dlt_version
```

If `ref_zome_*` tables are missing, the refs task failed (almost certainly because the
endpoint paths in `source.REF_PATHS` don't match Supabase's actual lookup tables). This
does NOT block the migration — verify paths against
`https://luvskhnljpxllkxpeasu.supabase.co/rest/v1/` and update in a follow-up PR.

### 6. Verify counts
```sql
SELECT
  (SELECT count(*) FROM bronze_listings.zome_developments WHERE _dlt_valid_to IS NULL) AS dev_current,
  (SELECT count(*) FROM bronze_listings.zome_listings     WHERE _dlt_valid_to IS NULL) AS list_current,
  (SELECT count(*) FROM bronze_listings.zome_developments_state) AS dev_state,
  (SELECT count(*) FROM bronze_listings.zome_listings_state)     AS list_state;
-- expect: dev_current ~297, list_current ~9000, dev_state == dev_current, list_state == list_current
```

If counts are off, do NOT proceed to step 7 — investigate first. The validate_facts
task will also have flagged this, so check its log.

### 7. Re-enable on weekly schedule
- Airflow UI → `zome_dlt` → toggle ON
- Confirm next scheduled run is the upcoming Monday at 06:00 UTC

## Decommission (semantic gate, not "after N days")

The legacy code can be deleted only after:

1. **≥1 SCD2 transition observed** in the new pipeline:
   ```sql
   SELECT count(*) FROM bronze_listings.zome_listings WHERE _dlt_valid_to IS NOT NULL;
   -- must be > 0
   ```
2. **≥1 sidecar delisting observed**:
   ```sql
   SELECT count(*) FROM bronze_listings.zome_listings_state
   WHERE last_seen_date < (SELECT max(last_seen_date) FROM bronze_listings.zome_listings_state);
   -- must be > 0
   ```
3. **≥3 successful weekly runs** (status=0 means success in dlt's bigint encoding):
   ```sql
   SELECT count(DISTINCT load_id) FROM bronze_listings._dlt_loads WHERE status=0;
   -- must be >= 3
   ```

If either (1) or (2) hasn't fired naturally within 4 weeks (Zome's catalog happens to
be perfectly stable, or the source paused), force one with a synthetic edit on a test
row in postgres — DO NOT mark decommission complete on row counts alone, because that
would validate insertion only, not the SCD2 transition path.

Once gated, delete:
- `pipelines/api/zome/zome_ingestion_dag.py`
- `pipelines/api/zome/zome_bronze_developments_dag.py`
- `pipelines/api/zome/zome_bronze_listings_dag.py`
- the bronze-DDL/INSERT/flatten sections of `zome_config.py` (keep `SUPABASE_URL` and
  `_supabase_headers` — `source.py` re-implements them but other tooling may import them)

Update the README to remove references to `raw_zome_*` and document the new tables.

## Rollback (if cutover fails before step 7)

1. Toggle off the new `zome_dlt` DAG.
2. `psql -f rollback_zome.sql` (recreates the empty legacy tables with their indexes).
3. Restore data: `psql -f /tmp/zome_pre_cutover.sql`.
4. Re-enable the three legacy DAGs.

## Known caveats

- **`boundary_timestamp` / backfill is NOT wired up.** Day 0 is today. To replay
  historical data later, use `source.resources["<name>"].apply_hints(...)` in the
  DAG before `pipeline.run(...)`. See the docstring in `zome_dlt_dag.py`.
- **MinIO files are an audit copy, NOT a load source.** `audit_to_minio` makes its own
  HTTP requests; `load_facts` makes separate ones. They may see slightly different data
  if Zome refreshes mid-run (rare given weekly cadence). If you ever change MinIO to be
  the load source, change the source in `source.py` to read from the local path instead
  of Supabase.
- **Refs endpoint paths are best-guess.** `source.REF_PATHS` was inferred from the
  `tab_*` naming convention; verify against the Supabase OpenAPI spec on first run. If
  a 404, the refs task fails non-fatally — facts load is unaffected.
- **Sidecar staleness threshold for silver.** Silver-layer `is_active` should query
  `last_seen_date >= current_date - 21` (weekly cadence + 1 missed run + slack). Do
  not lower below 14 days. Document this in any silver model that reads the sidecars.
