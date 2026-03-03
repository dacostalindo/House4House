# API Ingestion Template

Reusable Airflow DAG factory for **Flow A** — REST API sources (INE, Eurostat, BPStat, ECB, Idealista).

---

## What it does

```
check_api_availability
         ↓
  fetch_indicator          ← dynamic task mapping (.expand), one per indicator
         ↓
  upload_to_minio          ← bronze: raw JSON as-is
      ↙       ↘
cleanup_temp  log_run_metadata
```

**Stops at raw JSON in MinIO.** No transformation — the raw API response is stored as-is for exploration. Transformation to Parquet/silver is handled in a separate pipeline once the schema is confirmed.

**Each indicator runs independently.** One failure does not stop others — Airflow's dynamic task mapping creates isolated task instances.

---

## Usage

```python
# 1. Define indicators
MY_INDICATORS = [
    APIIndicator(code="001", name="metric_a", description="...", category="housing",
                 endpoint_params={"Dim1": "T"}),
]

# 2. Define config
config = APIIngestionConfig(
    dag_id="my_source_ingestion",
    source_name="my_source",
    base_url="https://api.example.com",
    api_path="/data/v1/endpoint",
    default_params={"format": "json"},
    indicators=MY_INDICATORS,
    minio_bucket="raw",
    minio_prefix="my_source",
    ...
)

# 3. Instantiate the DAG (Airflow auto-discovers it)
dag = create_api_ingestion_dag(config)
```

---

## APIIngestionConfig fields

### DAG identity

| Field | Type | Description |
|-------|------|-------------|
| `dag_id` | `str` | Unique Airflow DAG ID |
| `source_name` | `str` | Short identifier used in log messages and MinIO paths |
| `description` | `str` | Human-readable description shown in Airflow UI |

### API connection

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `base_url` | `str` | — | Base URL (e.g. `https://www.ine.pt`) |
| `api_path` | `str` | — | Endpoint path (e.g. `/ine/json_indicador/pindica.jsp`) |
| `default_params` | `dict` | `{}` | Query params sent with every request |
| `code_param_name` | `str \| None` | `"varcd"` | Query param for the indicator code. `None` if code is in the URL path. |
| `request_timeout_seconds` | `int` | `60` | Per-request timeout |
| `max_retries` | `int` | `3` | Retry attempts with exponential backoff (via tenacity) |
| `retry_backoff_seconds` | `int` | `5` | Minimum backoff between retries |
| `rate_limit_delay_seconds` | `float` | `1.0` | Pause between sequential fetches |

### Indicators

| Field | Type | Description |
|-------|------|-------------|
| `indicators` | `list[APIIndicator]` | List of indicators to fetch. Each gets its own mapped task. |

### MinIO storage

| Field | Type | Description |
|-------|------|-------------|
| `minio_bucket` | `str` | Bucket name (default: `raw`) |
| `minio_prefix` | `str` | Path prefix (e.g. `ine` → `raw/ine/{code}/...`) |

Storage layout:

| Layer | Path | Strategy |
|-------|------|----------|
| Bronze | `s3://{bucket}/{prefix}/{code}/{timestamp}.json` | Append (timestamped audit trail) |

### Scheduling

| Field | Type | Description |
|-------|------|-------------|
| `schedule` | `str \| None` | Cron string, `@monthly`, or `None` for manual trigger |
| `start_date` | `datetime \| None` | Required for scheduled DAGs. Omit for manual-trigger DAGs. |

---

## Airflow Variables required

```bash
airflow variables set MINIO_ENDPOINT   localhost:9000
airflow variables set MINIO_ACCESS_KEY <key>
airflow variables set MINIO_SECRET_KEY <secret>
```

---

## Adding a new API source

1. Create `pipelines/api/{source}/` with:
   - `{source}_config.py` — indicator list + `APIIngestionConfig`
   - `{source}_ingestion_dag.py` — one-liner: `dag = create_api_ingestion_dag(CONFIG)`
   - `README.md` — source documentation

2. No template code changes needed.

---

## Dependencies

Added to `Dockerfile.airflow`:
- **tenacity** — retry with exponential backoff
- **requests** — HTTP client (already present for Flow C)
- **minio** — S3 upload (already present for Flow C)
