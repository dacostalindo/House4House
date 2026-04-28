# Idealista developments (new construction) — dlt bronze pipeline

> **Status: NEW pipeline. No legacy to cut over from.**
>
> This is `idealista_developments_dlt` (file: `idealista_dlt.py`), distinct
> from the existing `idealista_ingestion` (resale catalog). The two pipelines
> coexist; the resale `bronze_listings.raw_idealista` table is slated for
> eventual decommissioning. This pipeline keeps RE API field names verbatim
> in `idealista_development_units` to enable a drop-in replacement when that
> happens.

## What it loads

Four tables in `bronze_listings`:

| Table | Disposition | PK | Source |
|---|---|---|---|
| `idealista_developments` | SCD2 | `development_id` | ZenRows Universal Scraper (Pass 1+2) |
| `idealista_developments_state` | UPSERT | `development_id` | heartbeat sidecar |
| `idealista_development_units` | SCD2 | `unit_id` | ZenRows Real Estate API (Pass 3) |
| `idealista_development_units_state` | UPSERT | `unit_id` | heartbeat sidecar |

`idealista_development_units.development_id` is the FK back to
`idealista_developments`. Silver/gold layers should treat dev↔units as a
1:N relationship.

## Coverage scope (initial)

Configured in `source.TARGET_AREAS` — 7 distrito-level slugs:

- `aveiro-distrito`, `braga-distrito`, `coimbra-distrito`, `leiria-distrito`,
  `lisboa-distrito`, `porto-distrito`, `setubal-distrito`

Lisboa + Setúbal distritos together cover the AML (Área Metropolitana de
Lisboa) plus surrounding rural concelhos — minor over-fetch vs enumerating
the 18 AML concelhos individually.

Expand by editing `TARGET_AREAS`. Slugs that 404 are logged and skipped —
the load does not abort.

## Cost

| Pass | API | Tier | Calls/run (est.) | $/run |
|---|---|---|---|---|
| Pass 1: discovery pages | Universal Scraper | 25× ($0.007) | ~30 | $0.21 |
| Pass 2: dev detail pages | Universal Scraper | 25× ($0.007) | ~700 | $4.90 |
| Pass 3: unit detail pages | **Real Estate API** | $0.0015 | ~14,000–21,000 | $21–32 |
| **Total** | | | ~15,000–22,000 | **~$26–38** |

Weekly cadence ⇒ **~$110–160/month** for the entire developments pipeline.
Numbers are estimates extrapolated from the Aveiro feasibility test
(80–100 devs, 10–30 units/dev) × 7 distritos. **The cost band will be
refined after the first Aveiro run** — see "First run" below.

## SCD2 rules

This pipeline follows the cross-pipeline SCD2 conventions documented in
[../../common/SCD2_RULES.md](../../common/SCD2_RULES.md). Field-naming policy
is documented in [../../common/NAMING_CONVENTIONS.md](../../common/NAMING_CONVENTIONS.md).

`UNITS_VERSION_COLUMNS` (12 cols including `last_deactivated_at` so a unit
going inactive opens an SCD2 version) and `DEVELOPMENTS_VERSION_COLUMNS`
(5 cols) are defined in `source.py`.

## Pass 3 RE API contract

Pass 3 calls `realestate.api.zenrows.com/v1/targets/idealista/properties/{id}`
with **`tld=.pt`** (REQUIRED). Without `tld=.pt` the endpoint resolves
against `idealista.es` and returns deactivated stub responses for PT IDs.

**Expected response**: 28–30 fields per active PT listing including
`property_price`, `bedroom_count`, `bathroom_count`, `lot_size`,
`property_features`, `property_images`, `property_condition`, `address`,
`latitude`, `longitude`, `agency_name`, `status`, `modified_at`,
`last_deactivated_at`, `operation`. New-construction units have
`property_condition='newdevelopment'`.

**Stub detection**: payloads with ≤6 fields, OR missing all of
`property_price` / `address` / `property_features`, are treated as inactive
stubs. Stubs are **skipped from the SCD2 table** (avoids phantom versions
on stub↔full oscillation) but the heartbeat sidecar still ticks. Silver
detects "currently inactive" via the 21-day heartbeat floor.

**Validation gates** (in `validate_facts`):
- Pass 2 enrichment floor: ≥80% of devs have `_has_detail = TRUE`
- Pass 3 enrichment floor: ≥95% of (Pass 3 attempts − stubs) land in
  `idealista_development_units`
- Pass 3 stub rate ceiling: <10%
- Pass 3 RE API error rate ceiling: <5% (catches 429 rate limiting)

## Pre-flight (before triggering the first run)

1. **Verify the Airflow image has `beautifulsoup4`** (it does, per
   `Dockerfile.airflow`). If you rebuilt the image recently, no action.

2. **Verify Airflow Variables are set:**
   - `ZENROWS_API_KEY` — must be a real key, not `change_me`. **Note: the
     RE-API tier credit balance is separate from the Universal Scraper
     quota; verify both are funded.** Pass 3 will burn through RE API
     credits at ~$30/run.
   - `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
   - `WAREHOUSE_HOST`, `WAREHOUSE_PORT`, `WAREHOUSE_DB`, `WAREHOUSE_USER`,
     `WAREHOUSE_PASSWORD`

3. **Verify the new DAG parses:**
   - Airflow UI → DAGs → search `idealista_developments_dlt`
   - If it doesn't appear, check the scheduler log for an `ImportError`.
     Most likely cause: `pipelines.api.idealista.source` failed to import
     (typo or missing dep); fix and re-run.

4. **Confirm `dlt_state/idealista_developments/` is writable** by the
   `airflow` user. The path is created on first load.

## First run — Aveiro test (RECOMMENDED before full scope)

1. **Trigger with the Aveiro override config:**
   - Airflow UI → `idealista_developments_dlt` → Trigger DAG w/ config:
     ```json
     {"target_areas_override": {"aveiro": ["aveiro-distrito"]}}
     ```
   - The Param appears in the UI under "Trigger DAG w/ config" — paste the
     JSON object as the value.

2. **Watch tasks** in order:
   - `audit_to_minio` (~10s, 1 area × 1 page)
   - `load_facts` (~3–8 min for Aveiro alone — Pass 1 ~3 pages, Pass 2 ~80
     parallel calls, Pass 3 ~1k–3k RE API calls)
   - `validate_facts` (seconds)

3. **Expected log lines** (from `_ensure_payload`):
   ```
   Pass 1 complete: 80–100 unique developments across 1 areas
   Pass 2 starting: ~85 dev detail pages, max_workers=4
   Pass 3 starting (RE API): ~1500 unit detail fetches, max_workers=4
   Payload ready: 85 devs (80+ enriched), 1500 units (1450+ enriched, 30 stubs, 0 RE API errors)
   ```

4. **Verify expected tables exist:**
   ```sql
   \dt bronze_listings.idealista_*
   -- expect:
   --   idealista_developments
   --   idealista_developments_state
   --   idealista_development_units
   --   idealista_development_units_state
   ```

5. **Aveiro-scope sanity SQL:**
   ```sql
   -- (a) load succeeded
   SELECT status FROM bronze_listings._dlt_loads WHERE load_id = '<from validate_facts>';

   -- (b) row counts in band
   SELECT count(*) FROM bronze_listings.idealista_developments
    WHERE _dlt_valid_to IS NULL AND area_key='aveiro';        -- 20–200
   SELECT count(*) FROM bronze_listings.idealista_development_units
    WHERE _dlt_valid_to IS NULL;                              -- 100–3000

   -- (c) field-population spot check (each ≥ 90%)
   SELECT
     avg((property_price IS NOT NULL)::int)               AS pct_price,
     avg((latitude IS NOT NULL)::int)                     AS pct_lat,
     avg((jsonb_array_length(property_images) > 0)::int) AS pct_images
   FROM bronze_listings.idealista_development_units WHERE _dlt_valid_to IS NULL;

   -- (d) TLD sanity — no Spanish leakage
   SELECT count(*) FROM bronze_listings.idealista_development_units
    WHERE _dlt_valid_to IS NULL AND country IS NOT NULL AND country <> 'pt';
   -- expect: 0

   -- (e) heartbeat parity — every Pass-2 unit_link has a heartbeat
   SELECT count(DISTINCT unit_id) FROM bronze_listings.idealista_development_units_state
    WHERE last_seen_date = current_date;
   -- expect: matches sum(jsonb_array_length(unit_links)) from idealista_developments
   ```

6. **Spot-check 5 random `unit_id`s** by visiting their idealista URLs and
   confirming `property_price`, `bedroom_count`, `address` match.

7. **Re-trigger Aveiro within an hour**; confirm 0 new SCD2 versions opened
   (steady-state idempotence).

8. **Reconcile Pass 3 cost**: log line "Pass 3 counters" × $0.0015 should
   match the ZenRows dashboard delta to ±5%.

Only after all 8 pass: clear the Param override and let the Wednesday
weekly cron run full 7-distrito scope. **Refine the cost band in this doc
based on the Aveiro × 7 extrapolation.**

## Aveiro test override — semantics

- `target_areas_override` is an Airflow Param, threaded through the source
  factory (`idealista_developments_facts_source(target_areas=...)`) →
  `_ensure_payload(target_areas=...)`.
- **No module-state mutation.** TARGET_AREAS in `source.py` is never modified
  at runtime; the override is a function arg.
- Auditable: the override value is recorded in the Airflow run config and
  surfaced in the validate_facts log line as `override_used=True`.
- When override is set, the row-count bands in validate_facts are skipped
  (those bands assume full 7-distrito scope). Pass 2/3 floors and ceilings
  still apply.
- To clear: trigger the DAG without config, or set `"target_areas_override": null`.

## Operating notes

- **Pagination assumption.** `_build_discovery_url` uses `pagina-{n}.htm`
  (idealista's documented URL convention). If page-2 of any area returns
  empty cards on Day 0, find the actual paginator URL and update the helper.
- **DataDome HTML drift affects Pass 1+2 only.** Pass 3 uses the RE API
  endpoint and is not subject to HTML drift; failures there manifest as
  4xx/5xx (caught by the error-rate ceiling) or stub responses (caught by
  the stub-rate ceiling).
- **Pass 3 throughput.** Aggregate ~6–8 req/s with `max_workers=4` and
  `0.5s` per-worker delay. Legacy `idealista_ingestion` self-throttles to
  ~0.67 req/s — we run ~12× faster. If the error-rate ceiling trips on Day 0
  with 429s, drop `PASS2_PASS3_MAX_WORKERS` from 4 → 2 in `source.py`.
- **Cost spikes.** A misconfigured slug that returns thousands of cards
  from a wrong region can multiply the bill. Watch the Pass 1 log line
  `Pass 1 complete: N unique developments across M areas` after each run.
- **Re-runs are cheap for unchanged devs.** SCD2 only opens a new version
  when row_hash changes. The fetch side is fully repeated every run; there
  is no fetch-side incremental skip on this pipeline (unlike the resale DAG
  which uses a 30-day refresh window).
- **Inactive units stay in bronze.** When `last_deactivated_at` is set,
  the unit row is still written (it counts as a real SCD2 transition and
  enables time-on-market analytics). Silver should add `WHERE status='active'`
  or filter by the heartbeat floor for a "currently active" view.

## Rollback

If the pipeline mis-loads and you need to start over:

1. Pause the DAG in the Airflow UI.
2. Run `rollback_idealista.sql` (drops the four bronze tables and clears
   dlt state for this pipeline).
3. Delete the dlt state dir on the scheduler host:
   ```bash
   docker compose exec airflow-scheduler rm -rf /opt/airflow/dlt_state/idealista_developments
   ```
4. Re-enable the DAG and trigger a fresh run.
