# Cadastro Predial — Property Parcel Boundaries (DGTERRITORIO)

Legal property parcel boundaries from the Portuguese national cadastre. Partial coverage — only municipalities surveyed between 2000-2007. Used for parcel-level spatial joins with listings and zoning data.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | DGTERRITORIO — Direcao-Geral do Territorio |
| Page | https://ogcapi.dgterritorio.gov.pt |
| Auth | None required (public API) |
| Format | GeoJSON via OGC API Features |
| CRS | WGS 84 — **EPSG:4326** (transformed to EPSG:3763 on load) |
| Coverage | Partial — municipalities surveyed 2000-2007 (~1.79M parcels) |
| Refresh | Static (cadastral survey data, updated infrequently) |

---

## What it contains

Property parcel polygons with cadastral references and official areas. Each feature represents one legal property parcel.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `nationalcadastralreference` | TEXT | Unique cadastral ID (e.g. AAA000338225) |
| `areavalue` | DOUBLE PRECISION | Official parcel area in m2 |
| `administrativeunit` | VARCHAR(6) | DTCC code (distrito + municipio + freguesia) |
| `inspireid` | TEXT | EU INSPIRE standard identifier |
| `label` | TEXT | Property label |
| `beginlifespanversion` | TIMESTAMPTZ | Record creation date |
| `validfrom` | TIMESTAMPTZ | Validity start |
| `validto` | TIMESTAMPTZ | Validity end |

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI -> **cadastro_ingestion** -> **Trigger DAG**.

No configuration parameters needed.

### 2. What happens

```
GET {endpoint}?limit=1                validate API is reachable
  |
paginate all features                 limit=1000, offset increments, 2s delay
  |  (streams features to temp GeoJSON to avoid OOM)
  |
minio.fput_object()                   upload GeoJSON with metadata
  |
trigger bronze load DAG
```

### 3. Where it lands

```
s3://raw/cadastro/{YYYYMMDD}/cadastro.geojson
```

### 4. Bronze load

Triggered automatically after ingestion. Can also be triggered manually from **`cadastro_bronze_load`** in the Airflow UI.

---

## DAGs

### `cadastro_ingestion` — OGC API -> MinIO

```
check_api_availability -> fetch_cadastro_features -> save_to_minio -> trigger_bronze
```

| Setting | Value |
|---------|-------|
| Schedule | None (manual trigger) |
| Retries | 2 (5-minute delay) |
| Tags | `cadastro`, `parcels`, `dgt`, `ingestion`, `gis`, `minio` |

### `cadastro_bronze_load` — MinIO -> PostGIS -> dbt

```
fetch_from_minio -> create_table -> load_features -> validate_counts -> trigger_dbt
```

| Setting | Value |
|---------|-------|
| Schedule | None (triggered by ingestion or manual) |
| Idempotency | TRUNCATE + INSERT |
| dbt trigger | `TriggerDagRunOperator` -> `dbt_cadastro_build` |
| Downstream models | `stg_cadastro` |
| Tags | `cadastro`, `bronze`, `parcels`, `postgis` |

---

## Bronze schema

### `bronze_regulatory.raw_cadastro` — ~1,790,000 rows

| Column | Type | Description |
|--------|------|-------------|
| `inspireid` | TEXT | EU INSPIRE identifier |
| `nationalcadastralreference` | TEXT | Unique cadastral ID |
| `areavalue` | DOUBLE PRECISION | Official parcel area (m2) |
| `administrativeunit` | VARCHAR(6) | DTCC code |
| `label` | TEXT | Property label |
| `validfrom` | TIMESTAMPTZ | Validity start |
| `validto` | TIMESTAMPTZ | Validity end |
| `beginlifespanversion` | TIMESTAMPTZ | Record creation date |
| `geom` | GEOMETRY(MULTIPOLYGON, 3763) | Parcel boundary in PT-TM06 |
| `_source_url` | TEXT | API URL used for ingestion |
| `_load_timestamp` | TIMESTAMPTZ | Ingestion timestamp |

### Indexes

- `idx_cadastro_geom` — GIST on `geom`
- `idx_cadastro_ref` — B-tree on `nationalcadastralreference`
- `idx_cadastro_admin` — B-tree on `administrativeunit`

### Key relationships

- `administrativeunit` (first 4 chars) joins to CAOP `raw_caop_municipios.dtmn`
- `administrativeunit` (all 6 chars) joins to CAOP `raw_caop_freguesias.dtmnfr`

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| Partial coverage | Only municipalities surveyed 2000-2007 (mostly rural Alentejo/Algarve) | No fix — cadastral survey expansion is ongoing nationally |
| Large dataset | ~1.79M features, pagination takes ~60 min | Rate-limited to 2s between pages to be respectful to API |
| No incremental load | Full TRUNCATE + INSERT on each run | Acceptable given infrequent updates |

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
pipelines/gis/cadastro/
├── __init__.py                    # Package marker
├── cadastro_config.py             # API endpoint, pagination, field mapping
├── cadastro_ingestion_dag.py      # DAG: OGC API -> MinIO
├── cadastro_bronze_dag.py         # DAG: MinIO -> PostGIS bronze table
└── README.md                      # This file
```

### Updating

No code changes needed. Re-trigger `cadastro_ingestion` to refresh the data. Each run overwrites the previous bronze table.
