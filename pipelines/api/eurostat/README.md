# Eurostat — House Price Index (HPI)

**Eurostat** — 1 dataset with ~31K observations across 38 EU/EEA countries, 3 purchase types, 4 units, and 83 quarters. Quarterly house price index (2015=100) for EU-wide benchmarking.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | Eurostat (European Commission) |
| API | `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/prc_hpi_q` |
| Auth | None required (public API) |
| Format | JSON-stat 2.0 (raw, stored as-is in MinIO) |
| CRS | N/A (macro-economic data, national level) |
| Coverage | EU/EEA (38 geo entities including PT, ES, EU, EA aggregates) |
| Refresh | Quarterly (`0 6 5 1,4,7,10 *` — 5th of Jan/Apr/Jul/Oct at 06:00 UTC) |

---

## What it fetches

1 dataset: `PRC_HPI_Q` — House Price Index (2015=100), quarterly data.

### Dimensions

| Dimension | Size | Values |
|-----------|------|--------|
| `freq` | 1 | Q (Quarterly) |
| `purchase` | 3 | TOTAL, DW_NEW (new dwellings), DW_EXST (existing dwellings) |
| `unit` | 4 | I10_Q (2010=100), I15_Q (2015=100), RCH_Q (quarterly change %), RCH_A (annual change %) |
| `geo` | 38 | EU, EU27_2020, EA, EA20, BE, BG, CZ, DK, DE, EE, IE, ES, FR, HR, IT, CY, LV, LT, LU, HU, MT, NL, AT, PL, **PT**, RO, SI, SK, FI, SE, IS, NO, CH, UK, TR |
| `time` | 83 | 2005-Q1 to 2025-Q3 |

### Status flags

| Flag | Meaning |
|------|---------|
| `p` | Provisional |
| `b` | Break in time series |
| `d` | Definition differs (see metadata) |
| `e` | Estimated |
| `\|C` | Confidential |

### How it complements other sources

| Gap | Eurostat fills with | Join path |
|-----|--------------------|-----------|
| BPStat has PT-only prices | EU-wide HPI for cross-country comparison | Temporal join on quarter |
| No benchmark for PT price trends | PT vs EU average, PT vs Spain, PT vs Euro area | Direct comparison on same time_period |
| INE has no EU context | Harmonised price index across all EU members | Temporal enrichment |

---

## How it works

```
GET https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/prc_hpi_q?format=JSON&lang=EN
  ↓  (1 request, ~31K observations, full dataset)
raw JSON-stat saved to temp dir
  ↓
upload to MinIO as-is:
  s3://raw/eurostat/prc_hpi_q/{timestamp}.json
  ↓
cleanup temp dirs
log_run_metadata (structured summary)
trigger eurostat_bronze_load
```

Each run appends a new timestamped file — full audit trail, no overwrites.

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI → **eurostat_api_ingestion** → **Trigger DAG**.

No configuration parameters needed — dataset code is defined in [eurostat_config.py](eurostat_config.py).

### 2. Where it lands

```
s3://raw/eurostat/prc_hpi_q/20260305T060000Z.json
```

### 3. Bronze load

After ingestion completes, **`eurostat_bronze_load`** is auto-triggered. It reads the latest JSON from MinIO automatically. Can also be triggered manually from the Airflow UI (no config needed).

---

## DAGs

### `eurostat_api_ingestion` — Eurostat API → MinIO

```
check_api_availability → fetch_indicator(1) → upload_to_minio → cleanup + log_run_metadata → trigger_downstream
```

| Setting | Value |
|---------|-------|
| Schedule | `0 6 5 1,4,7,10 *` (quarterly, 5th of Jan/Apr/Jul/Oct at 06:00 UTC) |
| Orchestration | Auto-triggers `eurostat_bronze_load` after completion (`wait_for_completion=True`) |
| Tags | `ingestion`, `api`, `minio`, `eurostat`, `macro`, `housing_prices`, `hpi` |

### `eurostat_bronze_load` — MinIO → PostGIS

```
list_minio_files → create_table → load_datasets → validate_counts
```

| Setting | Value |
|---------|-------|
| Schedule | None (auto-triggered by `eurostat_api_ingestion`, or manual) |
| Idempotency | DELETE + INSERT per dataset_code |
| Tags | `eurostat`, `bronze`, `macro`, `postgis` |

---

## Bronze schema

### `bronze_macro.raw_eurostat`

Source-oriented: unrolls JSON-stat cube dimensions into one row per observation. Values stored as-is from the API.

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| `id` | BIGSERIAL | — | Auto-increment primary key |
| `_ingested_at` | TIMESTAMPTZ | — | Ingestion timestamp |
| `_source` | VARCHAR(30) | — | Always `'eurostat'` |
| `_batch_id` | VARCHAR(50) | — | Batch identifier |
| `dataset_code` | VARCHAR(30) | constant | `'prc_hpi_q'` |
| `freq` | CHAR(1) | dimension `freq` | Always `'Q'` (Quarterly) |
| `purchase` | VARCHAR(20) | dimension `purchase` | `TOTAL`, `DW_NEW`, `DW_EXST` |
| `unit` | VARCHAR(20) | dimension `unit` | `I10_Q`, `I15_Q`, `RCH_Q`, `RCH_A` |
| `geo` | VARCHAR(10) | dimension `geo` | ISO country code or aggregate (`PT`, `ES`, `EU`, `EA`) |
| `time_period` | VARCHAR(10) | dimension `time` | Quarter string (e.g. `2024-Q1`) |
| `value` | NUMERIC(12,4) | `value[flat_idx]` | Index value or rate of change |
| `status` | VARCHAR(10) | `status[flat_idx]` | Quality flag (`p`, `b`, `d`, `e`) |

### Indexes

- `idx_eurostat_geo_time` — `(geo, time_period)`
- `idx_eurostat_dataset` — `(dataset_code)`

---

## JSON-stat 2.0 response structure

Eurostat returns [JSON-stat 2.0](https://json-stat.org/) — a cube-based format with pure dimensional indexing (no `extension.series` unlike BPStat):

```json
{
  "version": "2.0",
  "class": "dataset",
  "label": "House price index (2015 = 100) - quarterly data",
  "id": ["freq", "purchase", "unit", "geo", "time"],
  "size": [1, 3, 4, 38, 83],
  "value": {"0": 84.59, "1": 86.03, ...},
  "status": {"36841": "p", ...},
  "dimension": {
    "freq": {"category": {"index": {"Q": 0}}},
    "purchase": {"category": {"index": {"TOTAL": 0, "DW_NEW": 1, "DW_EXST": 2}}},
    "unit": {"category": {"index": {"I10_Q": 0, "I15_Q": 1, "RCH_Q": 2, "RCH_A": 3}}},
    "geo": {"category": {"index": {"EU": 0, ..., "PT": 27, ...}}},
    "time": {"category": {"index": {"2005-Q1": 0, ...}}}
  }
}
```

**Row-major indexing:** `flat_idx = freq_pos × (3×4×38×83) + purchase_pos × (4×38×83) + unit_pos × (38×83) + geo_pos × 83 + time_pos`

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| No server-side filtering | API ignores geo/unit query params — always returns full dataset | Small enough to fetch everything (~31K values) |
| Quarterly only | No monthly or annual granularity | Sufficient for housing price benchmarking |
| Lag | Data typically available ~3 months after quarter end | Standard for official statistics |
| Some gaps | Not all countries have data for all quarters | Status flags indicate data quality |

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
pipelines/api/eurostat/
├── __init__.py                    # Package marker
├── eurostat_config.py             # Dataset code, API URL, config
├── eurostat_ingestion_dag.py      # DAG: Eurostat API → MinIO
├── eurostat_bronze_dag.py         # DAG: MinIO → PostGIS bronze table
└── README.md                      # This file
```

### Adding datasets

Add a new `APIIndicator` entry to `EUROSTAT_INDICATORS` in [eurostat_config.py](eurostat_config.py) with the Eurostat dataset code (e.g. `prc_hicp_midx` for HICP). The bronze DAG will need a corresponding flattening function if the dimension structure differs.
