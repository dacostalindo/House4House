# BUPI — Simplified Cadastral Property Parcels (eBUPi)

**Representacao Grafica Georreferenciada (RGG)** — georeferenced property boundary polygons from the BUPi simplified cadastral registration system. 3.25M parcels covering 152 municipalities in continental Portugal. Key source for property-level spatial analysis and joins with land-use/zoning data.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | eBUPi — Estrutura de Missao para a Expansao do Sistema de Informacao Cadastral Simplificado |
| Page | https://dados.gov.pt/en/datasets/representacao-grafica-georreferenciada/ |
| Auth | None required (public download, CC-BY 4.0) |
| Format | GeoPackage (`.gpkg`) inside a `.zip` archive |
| CRS | ETRS89 / PT-TM06 — **EPSG:3763** (projected, metres) |
| Coverage | Continental Portugal (~3.25M parcels, 152 municipalities) |
| Refresh | Monthly |

---

## What it contains

Property boundary polygons registered through the BUPi simplified cadastral system. Each parcel has a parish code (Dicofre) enabling joins with CAOP administrative boundaries.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `ProcessoId` | INTEGER | BUPi process identifier (unique) |
| `NumeroMatriz` | TEXT | Property tax matrix number (may contain commas) |
| `Dicofre` | VARCHAR(6) | 6-digit parish code (distrito + concelho + freguesia) |
| `Concelho` | TEXT | Municipality name |
| `Freguesia` | TEXT | Parish name |
| `Area_m2` | DOUBLE PRECISION | Parcel area in square metres |

### Coverage highlights

- **Top municipalities**: Pombal (85K), Braganca (75K), Viseu (69K), Proenca-a-Nova (66K)
- **Parcel size**: median 1,735 m², mean 5,183 m² (skewed by large rural properties)
- **Total area**: ~16,852 km² (~18% of continental Portugal)

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI -> **bupi_ingestion** -> **Trigger DAG w/ config**:

```json
{"version": "2026-03"}
```

### 2. What happens

```
HEAD https://dados.gov.pt/.../opendata-rggs-continente.gpkg.zip
  |
stream download -> /tmp/          4 MB chunks, SHA-256 on the fly
  |  (zip extracted automatically)
pyogrio.list_layers()             auto-detect rgg_{date}_opendata layer
pyogrio.read_info()               log fields, CRS, feature count
  |
minio.fput_object()               upload raw .gpkg (~1.4 GB)
  |
cleanup /tmp/
log_run_metadata
```

### 3. Where it lands

```
s3://raw/bupi/{version}/opendata-rggs-continente.gpkg
```

### 4. Bronze load

After ingestion completes, trigger **`bupi_bronze_load`** from the Airflow UI (no config needed). It finds the latest GPKG in MinIO automatically.

---

## DAGs

### `bupi_ingestion` — dados.gov.pt -> MinIO

```
check_source -> download_file -> validate_gis_file -> upload_to_minio -> cleanup_temp -> log_run_metadata
```

| Setting | Value |
|---------|-------|
| Schedule | None (manual trigger) |
| Tags | `bupi`, `cadastro`, `property`, `p1`, `ingestion`, `gis`, `minio` |

### `bupi_bronze_load` — MinIO -> PostGIS -> dbt

```
find_latest_gpkg -> create_table -> load_layer -> validate_counts -> trigger_dbt_pipeline
```

| Setting | Value |
|---------|-------|
| Schedule | None (triggered by ingestion or manual) |
| Idempotency | TRUNCATE + INSERT |
| Batch size | 5,000 rows per insert (~650 batches for 3.25M rows) |
| dbt trigger | `TriggerDagRunOperator` -> `dbt_bupi_build` |
| Downstream models | `stg_bupi` |
| Tags | `bupi`, `cadastro`, `property`, `bronze`, `postgis` |

---

## Bronze schema

### `bronze_regulatory.raw_bupi` — ~3,250,000 rows

| Column | Type | Description |
|--------|------|-------------|
| `processoid` | INTEGER | BUPi process ID |
| `numeromatriz` | TEXT | Tax matrix number |
| `dicofre` | VARCHAR(6) | 6-digit parish code |
| `concelho` | TEXT | Municipality name |
| `freguesia` | TEXT | Parish name |
| `area_m2` | DOUBLE PRECISION | Parcel area (m²) |
| `geom` | GEOMETRY(MULTIPOLYGON, 3763) | Boundary in PT-TM06 |
| `_source_url` | TEXT | MinIO object path |
| `_load_timestamp` | TIMESTAMPTZ | Ingestion timestamp |

### Indexes

- GIST on `geom`
- B-tree on `dicofre`
- B-tree on `concelho`

### Key relationships

- `dicofre` joins to `raw_caop_freguesias.dtmnfr` for administrative hierarchy
- Spatial join to `raw_cos2023` for land-use classification per parcel
- Spatial join to `raw_crus_ordenamento` for zoning per parcel

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| Very large dataset | ~3.25M parcels, bronze load takes ~30-45 min | Batch insert (5000 rows) keeps memory manageable |
| Layer name changes monthly | GPKG layer is `rgg_{date}_opendata` | Auto-detect via `gpkg_layer=None` |
| Continental only | Madeira GPKG uses EPSG:5016 (different CRS) | Handle separately if needed |
| Declaration-based | Boundaries are self-declared by owners, not surveyed | Acceptable for analytical use |

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
pipelines/gis/bupi/
├── __init__.py                    # Package marker
├── bupi_config.py                 # Download URL, version, validation thresholds
├── bupi_ingestion_dag.py          # DAG: dados.gov.pt -> MinIO (uses gis_ingestion_template)
├── bupi_bronze_dag.py             # DAG: MinIO -> PostGIS (uses gpkg_bronze_template)
└── README.md                      # This file
```

### Updating for a new release

BUPI is updated monthly. To ingest a new release:
1. Update `download_url` in `bupi_config.py` with the new dados.gov.pt URL
2. Trigger ingestion with `{"version": "2026-04"}` (or appropriate month)
3. Bronze load will TRUNCATE and reload the full dataset
