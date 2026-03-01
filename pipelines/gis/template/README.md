# GIS Ingestion Template

Reusable Airflow DAG factory for **Flow C** — GIS file sources (CAOP, OSM, PDM, ARU).

---

## What it does

```
check_source_availability
         ↓
    download_file
         ↓
   validate_gis_file        ← logs full layer report: fields, types, CRS, feature count
         ↓
   upload_to_minio
      ↙       ↘
cleanup_temp  log_run_metadata
```

**Stops at MinIO.** No PostGIS loading, no `ogr2ogr`. The validation report is the primary tool for understanding a new source before designing its bronze schema.

---

## Usage

```python
# 1. Define a config
config = GISIngestionConfig(
    dag_id="my_source_ingestion",
    source_name="my_source",
    download_url="https://...",       # or "var:<KEY>" or "param:<KEY>"
    expected_format="gpkg",
    expected_layers=["layer_a"],
    ...
)

# 2. Instantiate the DAG (Airflow auto-discovers it)
dag = create_gis_ingestion_dag(config)
```

---

## GISIngestionConfig fields

### DAG identity

| Field | Type | Description |
|-------|------|-------------|
| `dag_id` | `str` | Unique Airflow DAG ID |
| `source_name` | `str` | Short identifier used in log messages and MinIO paths |
| `description` | `str` | Human-readable description shown in Airflow UI |

### Source

| Field | Type | Description |
|-------|------|-------------|
| `download_url` | `str` | See URL resolution below |
| `expected_format` | `str` | File extension: `gpkg`, `zip`, `shp`, `geojson`, `pbf` |

### Validation

These are intentionally loose sanity checks — not schema enforcement.
Schema enforcement is the bronze layer's job.

| Field | Type | Description |
|-------|------|-------------|
| `expected_layers` | `list[str]` | Layer names that must be present. Empty list = skip check |
| `layer_name_fn` | `Callable[[str], list[str]]` | Alternative to `expected_layers` for dynamic layer name resolution. Receives the resolved version string — use it or ignore it. |
| `expected_crs_epsg` | `int \| list[int] \| None` | Assert CRS. `None` = accept any. List = accept any of the given EPSG codes. Warning only — never a hard fail. |
| `min_feature_count` | `int` | Minimum features per layer. Hard failure if breached — applied to expected layers only, not auxiliary layers. |
| `max_feature_count` | `int` | Maximum features per layer. Hard failure if breached — applied to expected layers only, not auxiliary layers. |
| `min_file_size_bytes` | `int` | Minimum file size in bytes. Hard failure if breached. |

### MinIO storage

| Field | Type | Description |
|-------|------|-------------|
| `minio_bucket` | `str` | Bucket name, e.g. `raw` |
| `minio_prefix` | `str` | Path prefix, e.g. `caop` → stored at `raw/caop/{version}/{filename}` |

### Scheduling

| Field | Type | Description |
|-------|------|-------------|
| `schedule` | `str \| None` | Cron string, `@monthly`, or `None` for manual trigger |
| `start_date` | `datetime \| None` | Required for scheduled DAGs (controls backfill). Omit for manual-trigger DAGs — defaults to yesterday UTC. |

### Version

| Field | Type | Description |
|-------|------|-------------|
| `source_version` | `str \| None` | Static version label (e.g. `"2021"` for Census). Set `None` to read from trigger param at runtime. |
| `version_param_key` | `str` | `dag_run.conf` key to read when `source_version=None`. Default: `"version"` |

### DAG params

| Field | Type | Description |
|-------|------|-------------|
| `dag_params` | `dict` | Params shown in the Airflow "Trigger DAG w/ config" dialog. Format: `{"key": {"default": ..., "description": ...}}` |

---

## URL resolution

`download_url` supports three formats:

| Format | Resolved from |
|--------|--------------|
| `"https://..."` | Used as-is |
| `"var:KEY"` | Airflow Variable `KEY` (set once, stable URLs) |
| `"param:KEY"` | `dag_run.conf["KEY"]` at trigger time (URLs that change per release) |

---

## Airflow Variables required

```bash
airflow variables set MINIO_ENDPOINT   localhost:9000
airflow variables set MINIO_ACCESS_KEY <key>
airflow variables set MINIO_SECRET_KEY <secret>
```

---

## What the validation report contains

For each layer found in the file, `validate_gis_file` logs:

```
[layer_name]
  Features  : 3049
  CRS       : EPSG:3763
  Geometry  : MultiPolygon
  Fields    : ['dtmnfr', 'freguesia', 'municipio', 'distrito_ilha', ...]
```

All layers in the file are reported — including auxiliary layers not in `expected_layers`.
Feature count bounds are only enforced on expected layers.

This output is the input to bronze schema design.

---

## GIS library

The template uses **pyogrio** (not fiona) for all GIS file operations.
pyogrio bundles its own GDAL wheels, so no system GDAL packages are needed
in the Docker image — this avoids compilation failures on ARM64 (Apple Silicon).
