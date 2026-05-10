---
title: Data quality framework
type: plan
last_verified: 2026-05-10
tags: [architecture, data-quality, dbt-tests, great-expectations, plan]
---

## For future Claude

This is the **data-quality** page — dbt tests + Great Expectations strategy + the `metadata.pipeline_runs` table that captures every DAG run. Read this when adding a new test, debugging a quality failure, deciding "should this be a dbt test or a GE check?", or scoping coverage for a new silver/gold model. Companion to [[bronze-permissive]] (where validation does NOT belong) and [[ingest-flows]] (which surface fires which check).

## What it is

Two-layer data-quality framework:

1. **dbt tests** — schema-level + column-level constraints declared in `schema.yml` files alongside silver and gold models. Run via `dag_data_quality.py` daily, after `dag_dbt_gold` completes.
2. **Great Expectations checks** — domain-specific quality rules that don't fit dbt's "uniqueness / nullability / range / referential / accepted-values" primitives. Run on a separate cadence per check.

Plus `metadata.pipeline_runs` — the per-DAG-run audit trail that downstream quality DAGs query for freshness alerts.

## Why two layers

Per [[bronze-permissive]]'s no-validation-in-bronze rule, all data quality lives DOWNSTREAM of bronze. dbt is the natural validation boundary — its tests run against materialized silver/gold models, and `dbt build` fails the pipeline on a test failure (which is the right behavior).

But dbt tests have a coverage gap:
- They check **shape** (uniqueness, NULL rate, range, referential integrity, accepted values, FK).
- They don't check **distribution drift** (is the median price-per-sqm shifting?), **cross-source consistency** (do listings geocoded to the same address agree on price?), **temporal patterns** (is the daily ingest rate dropping?), or **spatial integrity** (are all geocoded points actually inside Portugal?).

Great Expectations fills the gap. Its checks are slower + heavier than dbt tests, so they run less frequently (hourly for freshness, daily for distribution + spatial). They also provide better expectation-style reporting for the results that need to surface to a human.

## dbt test layer

Per README §13.1 (silver_properties.unified_listings example):

```yaml
# models/silver/silver_properties/schema.yml
models:
  - name: unified_listings
    columns:
      - name: listing_key
        tests: [unique, not_null]
      - name: price_eur
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 1000
              max_value: 50000000
      - name: useful_area_m2
        tests:
          - dbt_utils.accepted_range:
              min_value: 5
              max_value: 10000
      - name: latitude
        tests:
          - dbt_utils.accepted_range:
              min_value: 36.9    # Cabo de São Vicente
              max_value: 42.2    # northern PT border
      - name: longitude
        tests:
          - dbt_utils.accepted_range:
              min_value: -9.6    # Atlantic coast
              max_value: -6.1    # Spanish border
      - name: energy_class
        tests:
          - accepted_values:
              values: ['A+', 'A', 'B', 'B-', 'C', 'D', 'E', 'F']
      - name: geo_key
        tests:
          - relationships:
              to: ref('dim_geography')
              field: geo_key
```

**Conventions:**
- Every silver + gold table has a `schema.yml` next to its `.sql` model.
- Every table has at minimum a `unique` + `not_null` test on its primary key.
- Range tests use `dbt_utils.accepted_range` (not `dbt_expectations` — keeping the test plugin set minimal).
- Spatial latitude/longitude bounds use the PT-specific bounding box above.
- Referential integrity (`relationships`) tests every FK that participates in a silver/gold join.

## Great Expectations layer

Per README §13.2, the rule table (with severity):

| Check | Table | Rule | Severity |
|---|---|---|---|
| Freshness | `bronze_listings.raw_idealista` | Max 2 days since last ingest | Critical |
| Volume | `bronze_listings.raw_idealista` | Daily ingest > 1000 records | Warning |
| Null rate | `unified_listings.geo_key` | < 5% null | Critical |
| Distribution | `unified_listings.price_per_sqm` | Median €500-€20,000 | Warning |
| Referential | All silver tables | All `geo_key` references valid | Critical |
| Spatial | All geocoded tables | All points within Portugal bbox | Critical |
| Volume | `bronze_regulatory.raw_bupi` | ≥ 3M rows after load | Critical |
| Not null | `parcel_buildability.process_id` | 0% null | Critical |
| Not null | `parcel_buildability.dicofre` | 0% null | Critical |
| Range | `parcel_buildability.building_coverage_pct` | 0.0 to 1.0 | Warning |
| Range | `development_sites.opportunity_score` | 0 to 100 | Warning |
| Referential | `site_parcels.site_key` | All FK valid → `development_sites` | Critical |
| Accepted values | `parcel_buildability.zone_category` | Solo Urbano, Solo Rústico, NULL | Warning |

**Severity policy:**
- **Critical** → fail the DAG; fire `on_failure_callback` alert
- **Warning** → log to `metadata.pipeline_runs` with `status='warning'`; surface in the `dag_freshness_monitor` summary; do not block downstream

**Cadence:**
- Freshness checks: hourly (in `dag_freshness_monitor`)
- Volume + null-rate + referential + spatial: daily (in `dag_data_quality`, after dbt Gold completes)
- Distribution + accepted-values + range: daily (same DAG)

## metadata.pipeline_runs

The audit trail every DAG run writes to. Per README §13.3:

```sql
CREATE TABLE metadata.pipeline_runs (
    run_id               BIGSERIAL PRIMARY KEY,
    dag_id               VARCHAR(100),
    task_id              VARCHAR(100),
    source               VARCHAR(50),
    target_table         VARCHAR(100),
    run_start            TIMESTAMPTZ,
    run_end              TIMESTAMPTZ,
    status               VARCHAR(20),    -- success | failure | warning | skipped
    records_ingested     INTEGER,
    records_rejected     INTEGER,
    error_message        TEXT,
    batch_id             VARCHAR(50)
);
```

**Conventions:**
- Every ingestion DAG writes one row per task execution (success or failure).
- `records_ingested` + `records_rejected` populated for ingest tasks; NULL for transformation / quality tasks.
- `batch_id` ties multiple task rows from the same logical run together.
- `dag_freshness_monitor` queries this table hourly to detect "DAG X hasn't completed in N hours" conditions.
- `metadata.pipeline_runs` is the only `metadata.*` table. Other "metadata"-flavored content (dbt run results, lint state) lives in dbt-managed tables under the `metadata` schema by Cosmos's convention.

## Where each check belongs

A decision tree for "is this a dbt test or a GE check?":

1. **Is the rule expressible as `unique` / `not_null` / `accepted_values` / `accepted_range` / `relationships`?** → dbt test (lighter, runs on every `dbt build`).
2. **Does the rule require querying the table's distribution (median, percentiles)?** → Great Expectations.
3. **Does the rule require cross-table or temporal context (freshness, drift)?** → Great Expectations.
4. **Does the rule require a spatial predicate (point-in-polygon, ST_Contains)?** → can be either; default to Great Expectations to keep dbt model files focused on data shape rather than spatial logic.

## See also

- [[bronze-permissive]] — the no-validation-in-bronze rule that pushes all quality work to silver+
- [[medallion-layering]] — which schemas hold what
- [[ingest-flows]] — Flow-D and Flow-E quality checks differ from Flow-A/B/C
- [[orchestration]] — `dag_data_quality` + `dag_freshness_monitor` schedule
- [[infra]] — where `metadata.pipeline_runs` lives
- [[2026-05-08-idealista-enrichment-architecture]] — Phase 5 enrichment dead-letter-table convention
- README §13 — the canonical source for this content
