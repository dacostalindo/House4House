# ECB — Euribor Interest Rates (ECB)

**European Central Bank** — 3 Euribor monthly rate series fetched from the ECB Statistical Data Warehouse SDMX REST API. Key input for mortgage affordability modelling.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | ECB — European Central Bank |
| API | `https://data-api.ecb.europa.eu/service/data/FM/{series_key}` |
| Auth | None required (public API) |
| Format | SDMX-JSON (raw, stored as-is in MinIO) |
| CRS | N/A (macro-economic data, Euro area aggregate) |
| Coverage | Euro area (U2) |
| Refresh | Monthly ingestion (`0 6 1 * *` — 1st of each month at 06:00 UTC) |

---

## What it fetches

3 Euribor rate series (monthly averages):

| Series Key | Name | Frequency | Description |
|------------|------|-----------|-------------|
| `M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA` | euribor_3m | Monthly | Euribor 3-month rate (monthly average) |
| `M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA` | euribor_6m | Monthly | Euribor 6-month rate (monthly average) |
| `M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA` | euribor_12m | Monthly | Euribor 12-month rate (monthly average) |

### How it complements other sources

| Gap | ECB fills with | Join path |
|-----|----------------|-----------|
| No financing context in listings | Euribor benchmark rates for mortgage cost modelling | Temporal join on observation month |
| No historical rate trends | Monthly time-series from 1999 to present | Direct time-series enrichment |
| INE mortgage rates are national only | Euribor provides the Euro area benchmark underlying Portuguese variable-rate mortgages | Complementary: INE spread = national rate − Euribor |

---

## How it works

```
GET https://data-api.ecb.europa.eu/service/data/FM/{series_key}?format=jsondata
  ↓  (×3 series, sequential with 1s delay, 3 retries each)
raw SDMX-JSON saved to temp dir
  ↓
upload to MinIO as-is:
  s3://raw/ecb/{series_key}/{timestamp}.json
  ↓
cleanup temp dirs
log_run_metadata (structured summary)
trigger ecb_bronze_load
```

Each run appends a new timestamped file — full audit trail, no overwrites.

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI → **ecb_api_ingestion** → **Trigger DAG**.

No configuration parameters needed — all series keys are defined in [ecb_config.py](ecb_config.py).

### 2. Where it lands

```
s3://raw/ecb/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA/20260301T060000Z.json
s3://raw/ecb/M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA/20260301T060000Z.json
s3://raw/ecb/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA/20260301T060000Z.json
```

### 3. Bronze load

After ingestion completes, **`ecb_bronze_load`** is auto-triggered. It reads the latest JSON per series from MinIO automatically. Can also be triggered manually from the Airflow UI (no config needed).

---

## DAGs

### `ecb_api_ingestion` — ECB SDMX API → MinIO

```
check_api_availability → fetch_indicator.expand(3) → upload_to_minio → cleanup + log_run_metadata → trigger_downstream
```

| Setting | Value |
|---------|-------|
| Schedule | `0 6 1 * *` (monthly, 1st of each month at 06:00 UTC) |
| Orchestration | Auto-triggers `ecb_bronze_load` after completion (`wait_for_completion=True`) |
| Tags | `ingestion`, `api`, `minio`, `ecb`, `euribor`, `interest_rates`, `macro` |

### `ecb_bronze_load` — MinIO → PostGIS → dbt

```
list_minio_files → create_table → load_indicators → validate_counts → trigger_dbt_pipeline
```

| Setting | Value |
|---------|-------|
| Schedule | None (auto-triggered by `ecb_api_ingestion`, or manual) |
| Idempotency | DELETE + INSERT per series key |
| dbt trigger | `TriggerDagRunOperator` → `dbt_scoped_build` with selector `stg_ecb+` |
| Downstream models | `stg_ecb` → `macro_timeseries` (Euribor interest rates) |
| Tags | `ecb`, `bronze`, `euribor`, `postgis` |

---

## Bronze schema

### `bronze_macro.raw_ecb`

Source-oriented: flattens SDMX observations into one row per (series × period). Values stored as-is from the API. ~1,158 rows (386 per series, 1994–present).

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL | Auto-increment primary key |
| `_ingested_at` | TIMESTAMPTZ | Ingestion timestamp |
| `_source` | VARCHAR(30) | Always `'ecb_sdmx'` |
| `_batch_id` | VARCHAR(50) | Batch identifier (e.g. `'20260301T060000'`) |
| `series_key` | VARCHAR(100) | ECB series key (e.g. `'M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA'`) |
| `series_name` | VARCHAR(50) | Short name (e.g. `'euribor_3m'`) |
| `time_period` | VARCHAR(20) | Observation period (e.g. `'2024-12'`) |
| `value` | NUMERIC(12,7) | Rate value (e.g. `2.0113000`) |
| `unit` | VARCHAR(20) | SDMX unit code (e.g. `'PCPA'` = percent per annum) |
| `obs_status` | VARCHAR(10) | Observation status (`'A'` = normal) |
| `obs_conf` | VARCHAR(10) | Confidentiality flag (`'F'` = free) |

### Indexes

- `idx_ecb_series_key` — `(series_key)`
- `idx_ecb_series_period` — `(series_key, time_period)`

---

## SDMX-JSON response structure

The ECB API returns data in SDMX-JSON format:

```json
{
  "header": {"id": "...", "prepared": "2026-03-01T06:00:00Z"},
  "dataSets": [{
    "series": {
      "0:0:0:0:0:0:0": {
        "observations": {
          "0": [3.045],
          "1": [2.634],
          "2": [2.482]
        }
      }
    }
  }],
  "structure": {
    "dimensions": {
      "series": [...],
      "observation": [{
        "id": "TIME_PERIOD",
        "values": [
          {"id": "1999-01", "name": "1999-01"},
          {"id": "1999-02", "name": "1999-02"},
          {"id": "1999-03", "name": "1999-03"}
        ]
      }]
    }
  }
}
```

Key paths:
- **Observations:** `dataSets[0].series["0:0:0:0:0:0:0"].observations` — keyed by index, value is `[rate]`
- **Dates:** `structure.dimensions.observation[0].values[i].id` — maps observation index to date string

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| Euro area aggregate only | No country-level breakdown | Sufficient for Portuguese mortgage modelling (PT uses Euribor) |
| Monthly frequency only | No daily or weekly rates | Monthly aligns with mortgage payment cycles |
| Series key in URL path | SDMX uses path-based keys, not query params | Template extended with `code_in_path=True` |

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
pipelines/api/ecb/
├── __init__.py                    # Package marker
├── ecb_config.py                  # Series keys, API URL, config
├── ecb_ingestion_dag.py           # DAG: ECB SDMX API → MinIO
├── ecb_bronze_dag.py              # DAG: MinIO → PostGIS bronze table
└── README.md                      # This file
```

### Adding series

Add a new `APIIndicator` entry to `ECB_INDICATORS` in [ecb_config.py](ecb_config.py). Then add the series key to `SERIES_KEYS` and `SERIES_NAMES` in [ecb_bronze_dag.py](ecb_bronze_dag.py). No other code changes needed.

To find series keys:
1. Browse https://data.ecb.europa.eu → search for a dataset → inspect the series key in the URL
2. Use the ECB SDMX dataflow catalog: `GET https://data-api.ecb.europa.eu/service/dataflow/ECB`
