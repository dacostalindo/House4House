# {PIPELINE_NAME} — {SHORT_DESCRIPTION} ({PROVIDER})

{One-paragraph summary: what this data is, why it matters to the project.}

---

## Source

| Property | Value |
|----------|-------|
| Publisher | {Provider name and acronym} |
| Page | {URL to data portal or documentation} |
| Auth | {None required / API key / etc.} |
| Format | {GeoPackage / GeoJSON via WFS / GeoJSON via OGC API / etc.} |
| CRS | {CRS name} — **EPSG:{code}** |
| Coverage | {Geographic scope and feature count} |
| Refresh | {Update frequency: static, annual, daily, etc.} |

---

## What it contains

{Description of the data model: geometry type, classification system, hierarchies.}

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `field_name` | TYPE | Description |
| ... | ... | ... |

{Optional: additional context tables for classification systems, variable groups, etc.}

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI -> **{dag_id}** -> **Trigger DAG** {w/ config if parameters needed}.

{If parameters: show example JSON config.}

### 2. What happens

```
{ASCII flow diagram of the ingestion steps}
```

### 3. Where it lands

```
s3://raw/{prefix}/{version_or_date}/{filename}
```

### 4. Bronze load

After ingestion completes, trigger **`{bronze_dag_id}`** from the Airflow UI.
{Any notes on automatic triggering.}

---

## DAGs

### `{ingestion_dag_id}` — {Source} -> MinIO

```
{task1} -> {task2} -> {task3} -> ...
```

| Setting | Value |
|---------|-------|
| Schedule | {None (manual trigger) / cron / etc.} |
| Tags | `{tag1}`, `{tag2}`, ... |

### `{bronze_dag_id}` — MinIO -> PostGIS -> dbt

```
{task1} -> {task2} -> {task3} -> ...
```

| Setting | Value |
|---------|-------|
| Schedule | {None (manual trigger) / triggered by ingestion} |
| Idempotency | {TRUNCATE + INSERT / DELETE + INSERT per partition / etc.} |
| dbt trigger | {TriggerDagRunOperator details} |
| Downstream models | {stg_xxx -> silver_xxx} |
| Tags | `{tag1}`, `{tag2}`, ... |

---

## Bronze schema

### `{schema}.{table}` — {approximate row count} rows

| Column | Type | Description |
|--------|------|-------------|
| `column_name` | TYPE | Description |
| ... | ... | ... |
| `geom` | GEOMETRY({type}, {srid}) | {Description} |
| `_load_timestamp` | TIMESTAMPTZ | Ingestion timestamp |

### Indexes

- `idx_{name}_geom` — GIST on `geom`
- `idx_{name}_{col}` — B-tree on `{col}`

### Key relationships

- {Join keys to other tables}

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| {Issue} | {Detail} | {Workaround or plan} |

---

## Configuration

### Environment

| Variable | Where | Value |
|----------|-------|-------|
| `MINIO_ENDPOINT` | Airflow Variable | `minio:9000` |
| `MINIO_ACCESS_KEY` | Airflow Variable | Set via `airflow-init` in `docker-compose.yml` |
| `MINIO_SECRET_KEY` | Airflow Variable | Set via `airflow-init` in `docker-compose.yml` |

### Directory structure

```
pipelines/gis/{pipeline}/
├── __init__.py                    # Package marker
├── {pipeline}_config.py           # Configuration (URLs, fields, validation)
├── {pipeline}_ingestion_dag.py    # DAG: Source -> MinIO
├── {pipeline}_bronze_dag.py       # DAG: MinIO -> PostGIS bronze table
└── README.md                      # This file
```

### Updating

{Instructions for refreshing data: new version, URL changes, adding municipalities, etc.}
