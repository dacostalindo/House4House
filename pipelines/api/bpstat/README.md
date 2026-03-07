# BPStat — Banco de Portugal (BPStat)

**Banco de Portugal** — 16 datasets across 3 statistical domains fetched from the public BPStat REST API. Housing credit, interest rates, and housing price data for mortgage affordability and market trajectory modelling.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | Banco de Portugal |
| API | `https://bpstat.bportugal.pt/data/v1/domains/{domain_id}/datasets/{dataset_id}` |
| Auth | None required (public API) |
| Format | JSON-stat 2.0 (raw, stored as-is in MinIO) |
| CRS | N/A (macro-economic data, national level) |
| Coverage | Portugal |
| Refresh | Monthly ingestion (`0 6 15 * *` — 15th of each month at 06:00 UTC) |

---

## What it fetches

16 datasets across 3 domains (~311 series):

### Domain 186 — Housing credit (4 datasets, 40 series)

| Dataset ID | Name | Series | Content |
|------------|------|--------|---------|
| `d45bb68e...` | housing_credit_volumes | 13 | Loan volumes, repayment distributions, amortization |
| `6a83b46f...` | housing_credit_rates | 19 | Interest rates by type (fixed, floating, mixed) |
| `85c2d956...` | housing_credit_fixed_rate_term | 6 | By initial fixed rate term |
| `63e87...` | housing_credit_floating | 2 | Floating rate loan shares |

### Domain 21 — Interest rates (10 datasets, 253 series)

| Dataset ID | Name | Series | Content |
|------------|------|--------|---------|
| `07d36f66...` | ir_credit_purpose_fixed_rate | 23 | Credit by purpose with fixed rate terms |
| `0a8ba349...` | ir_credit_sectors | 17 | Credit metrics by institutional sectors |
| `5e42e781...` | ir_credit_purpose_metrics | 5 | Credit purpose with metrics across sectors |
| `6eaa8db9...` | ir_fixed_rate_counterparty | 40 | Fixed rate terms by counterparty data |
| `851facff...` | ir_original_maturity | 47 | Credit by original maturity |
| `9744c7a7...` | ir_step_values_flows | 8 | Step values with flows/stocks/prices |
| `9ab0b6dd...` | ir_step_values_fixed_rate | 17 | Step values with fixed rate terms |
| `c4db40b7...` | ir_credit_items | 24 | Credit metrics by source and items |
| `ec7b2a0f...` | ir_maturity_counterparty | 70 | Maturity by counterparty sectors |
| `f648a7e7...` | ir_maturity_sectors | 12 | Flows/stocks/prices by maturity |

### Domain 39 — Housing prices (2 datasets, 18 series)

| Dataset ID | Name | Series | Content |
|------------|------|--------|---------|
| `b8cc6628...` | housing_price_indicators | 10 | Housing price statistics |
| `da133c09...` | housing_price_indices | 8 | Transaction price indices (new/existing) |

### Not included

**Domain 18 — Household debt** (~16.8K series) is excluded. It's mostly corporate debt data. The housing-specific subset (16 series in dataset `56ebacd8...`) can be added later by appending an `APIIndicator` entry to [bpstat_config.py](bpstat_config.py).

### How it complements other sources

| Gap | BPStat fills with | Join path |
|-----|-------------------|-----------|
| No lending context in listings | Mortgage volumes, LTV ratios, repayment distributions | Temporal join on observation month |
| ECB Euribor is Euro area only | Portuguese-specific mortgage interest rates | Direct comparison: BPStat rate − Euribor = spread |
| INE has no credit data | Housing credit flows, stocks, new business volumes | Temporal enrichment |
| No housing price benchmarks | BdP housing price indices (complement INE) | Temporal join on observation quarter |

---

## How it works

```
GET https://bpstat.bportugal.pt/data/v1/domains/{domain_id}/datasets/{dataset_id}?lang=EN
  ↓  (×16 datasets, sequential with 2s delay, 3 retries each)
raw JSON-stat saved to temp dir
  ↓
upload to MinIO as-is:
  s3://raw/bpstat/{domain_id}/datasets/{dataset_id}/{timestamp}.json
  ↓
cleanup temp dirs
log_run_metadata (structured summary)
trigger bpstat_bronze_load
```

Each run appends a new timestamped file — full audit trail, no overwrites.

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI → **bpstat_api_ingestion** → **Trigger DAG**.

No configuration parameters needed — all dataset codes are defined in [bpstat_config.py](bpstat_config.py).

### 2. Where it lands

```
s3://raw/bpstat/186/datasets/d45bb68e792a6b1b2fc36d6a90da4f20/20260315T060000Z.json
s3://raw/bpstat/21/datasets/07d36f662cea4b19f4b2c2cf5435771d/20260315T060000Z.json
...
```

### 3. Bronze load

After ingestion completes, **`bpstat_bronze_load`** is auto-triggered. It reads the latest JSON per dataset from MinIO automatically. Can also be triggered manually from the Airflow UI (no config needed).

---

## DAGs

### `bpstat_api_ingestion` — BPStat API → MinIO

```
check_api_availability → fetch_indicator.expand(16) → upload_to_minio → cleanup + log_run_metadata → trigger_downstream
```

| Setting | Value |
|---------|-------|
| Schedule | `0 6 15 * *` (monthly, 15th of each month at 06:00 UTC) |
| Orchestration | Auto-triggers `bpstat_bronze_load` after completion (`wait_for_completion=True`) |
| Tags | `ingestion`, `api`, `minio`, `bpstat`, `macro`, `mortgage`, `lending`, `housing_prices` |

### `bpstat_bronze_load` — MinIO → PostGIS → dbt

```
list_minio_files → create_table → load_datasets → validate_counts → trigger_dbt_pipeline
```

| Setting | Value |
|---------|-------|
| Schedule | None (auto-triggered by `bpstat_api_ingestion`, or manual) |
| Idempotency | DELETE + INSERT per dataset_id |
| dbt trigger | `TriggerDagRunOperator` → `dbt_scoped_build` with selector `stg_bpstat+` |
| Downstream models | `stg_bpstat` → `macro_timeseries` (housing credit, interest rates, housing prices) |
| Tags | `bpstat`, `bronze`, `macro`, `postgis` |

---

## Bronze schema

### `bronze_macro.raw_bpstat`

Source-oriented: flattens JSON-stat observations into one row per (series × period). Values stored as-is from the API.

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL | Auto-increment primary key |
| `_ingested_at` | TIMESTAMPTZ | Ingestion timestamp |
| `_source` | VARCHAR(30) | Always `'bpstat'` |
| `_batch_id` | VARCHAR(50) | Batch identifier (e.g. `'20260315T060000'`) |
| `domain_id` | INTEGER | BPStat domain (e.g. `186`, `21`, `39`) |
| `dataset_id` | VARCHAR(50) | Dataset hash (e.g. `'d45bb68e792a6b1b2fc36d6a90da4f20'`) |
| `series_id` | INTEGER | Unique series identifier (e.g. `12710732`) |
| `series_name` | TEXT | Full series label (includes dimension breakdown) |
| `period` | VARCHAR(20) | Observation date (e.g. `'2024-12-31'`) |
| `value` | NUMERIC(20,6) | Numeric value |
| `unit` | VARCHAR(100) | Unit from metric dimension (e.g. `'Percentage'`, `'Millions of euros'`) |
| `status` | VARCHAR(10) | Observation quality flag (`'F'` = final) |

### Indexes

- `idx_bpstat_series_id` — `(series_id)`
- `idx_bpstat_dataset` — `(dataset_id)`
- `idx_bpstat_series_period` — `(series_id, period)`

---

## JSON-stat 2.0 response structure

BPStat returns data in [JSON-stat 2.0](https://json-stat.org/) format — a cube-based format:

```json
{
  "version": "2.0",
  "class": "dataset",
  "id": ["17", "18", "19", "29", "40", "63", "66", "70", "reference_date"],
  "size": [1, 1, 2, 1, 1, 1, 2, 1, 86],
  "value": {"0": 5.93, "1": 3.51, "86": 2.07, ...},
  "status": {"0": "F", "1": "F", ...},
  "dimension": {
    "reference_date": {
      "category": {"index": ["2018-12-31", "2019-01-31", ...]}
    },
    "17": {
      "label": "Credit purpose",
      "category": {"label": {"5388": "Permanent residential property"}}
    }
  },
  "extension": {
    "series": [
      {"id": 12710771, "label": "New business volume...", "dimension_category": [...]}
    ]
  },
  "role": {"time": ["reference_date"], "metric": ["29"]}
}
```

Key paths:
- **Observations:** `value` — flat dict, row-major indexed across all dimensions
- **Dates:** `dimension.reference_date.category.index` — ordered date list
- **Series:** `extension.series[i]` — series ID, label, and dimension category mapping
- **Index math:** position = Σ(dim_position × stride), where stride = product of subsequent dimension sizes

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| National level only | No regional breakdown (unlike INE) | Sufficient for national mortgage modelling |
| Domain 18 excluded | Household debt (~16.8K series, mostly corporate) | Add housing-specific subset (16 series) later if needed |
| End-of-month dates | Periods are `"YYYY-MM-DD"` (last day of month) | Silver layer normalizes to `"YYYY-MM"` |
| Large datasets | Domain 21 has 253 series across 10 datasets | Handled by batch insert with page_size=1000 |

---

## Configuration

### Environment

| Variable | Where | Value |
|----------|-------|-------|
| `MINIO_ENDPOINT` | Airflow Variable | `minio:9000` |
| `MINIO_ACCESS_KEY` | Airflow Variable | Set via `airflow-init` in `docker-compose.yml` |
| `MINIO_SECRET_KEY` | Airflow Variable | Set via `airflow-init` in `docker-compose.yml` |
| `WAREHOUSE_HOST` | Airflow Variable | `warehouse` |

### Directory structure

```
pipelines/api/bpstat/
├── __init__.py                    # Package marker
├── bpstat_config.py               # Dataset codes, API URL, config
├── bpstat_ingestion_dag.py        # DAG: BPStat API → MinIO
├── bpstat_bronze_dag.py           # DAG: MinIO → PostGIS bronze table
└── README.md                      # This file
```

### Adding datasets

Add a new `APIIndicator` entry to `BPSTAT_INDICATORS` in [bpstat_config.py](bpstat_config.py) with `code="{domain_id}/datasets/{dataset_id}"`. No other code changes needed — the bronze DAG dynamically reads dataset codes from the config.

To find dataset IDs:
1. Browse https://bpstat.bportugal.pt → choose a domain → inspect dataset IDs
2. Use the API: `GET https://bpstat.bportugal.pt/data/v1/domains/{domain_id}/datasets/?lang=EN`
