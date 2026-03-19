# COS 2023 — Land Use & Cover Map (DGT)

**Carta de Uso e Ocupacao do Solo** — the national land use/land cover map for continental Portugal. 4-level hierarchical classification system with ~784K polygons. Foundation source for land-use enrichment of property listings.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | DGT — Direcao-Geral do Territorio |
| Page | https://dados.gov.pt/en/datasets/carta-de-uso-e-ocupacao-do-solo-cos-serie-2-nova/ |
| Auth | None required (public download) |
| Format | GeoPackage (`.gpkg`) inside a `.zip` archive |
| CRS | ETRS89 / PT-TM06 — **EPSG:3763** (projected, metres) |
| Coverage | Continental Portugal (~784K polygons) |
| Refresh | Periodic — ~5 years (2018, 2023) |

---

## What it contains

Land use/cover polygons classified with a 4-level hierarchical system:

| Level | Examples |
|-------|---------|
| 1 | 1=Artificial, 2=Agriculture, 3=Pasture, 4=Forest, 5=Herbaceous, 6=Open, 7=Wetlands, 8=Water |
| 2 | 1.1=Urban fabric, 1.2=Industrial/commercial, 2.1=Annual crops |
| 3 | 1.1.1=Continuous urban, 1.1.2=Discontinuous urban |
| 4 | 1.1.1.1=Continuous vertical residential, 1.1.1.2=Continuous horizontal residential |

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `ID` | INTEGER | Feature ID |
| `COS23_n4_C` | VARCHAR(10) | 4-level land-use code (e.g. "1.1.1.1") |
| `COS23_n4_L` | TEXT | Human-readable label |
| `AREA_ha` | DOUBLE PRECISION | Polygon area in hectares |

### GPKG layers

| Layer | Description |
|-------|-------------|
| `COS2023v1` | Main data layer (784K polygons) |
| `layer_styles` | QGIS styling — ignored in pipeline |

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI -> **cos2023_ingestion** -> **Trigger DAG w/ config**:

```json
{"version": "2023"}
```

### 2. What happens

```
HEAD https://geo2.dgterritorio.gov.pt/.../COS2023v1-S2-gpkg.zip
  |
stream download -> /tmp/          4 MB chunks, SHA-256 on the fly
  |  (zip extracted automatically)
pyogrio.list_layers()             assert COS2023v1 present
pyogrio.read_info()               log fields, CRS, feature count
  |
minio.fput_object()               upload raw .gpkg
  |
cleanup /tmp/
log_run_metadata
```

### 3. Where it lands

```
s3://raw/cos/{version}/COS2023v1-S2.gpkg
```

### 4. Bronze load

After ingestion completes, trigger **`cos2023_bronze_load`** from the Airflow UI (no config needed). It finds the latest GPKG in MinIO automatically.

---

## DAGs

### `cos2023_ingestion` — DGT -> MinIO

```
check_source -> download_file -> validate_gis_file -> upload_to_minio -> cleanup_temp -> log_run_metadata
```

| Setting | Value |
|---------|-------|
| Schedule | None (manual trigger) |
| Tags | `cos`, `land-use`, `dgt`, `p1`, `ingestion`, `gis`, `minio` |

### `cos2023_bronze_load` — MinIO -> PostGIS -> dbt

```
find_latest_gpkg -> create_table -> load_layer -> validate_counts -> trigger_dbt_pipeline
```

| Setting | Value |
|---------|-------|
| Schedule | None (triggered by ingestion or manual) |
| Idempotency | TRUNCATE + INSERT |
| Batch size | 5,000 rows per insert |
| dbt trigger | `TriggerDagRunOperator` -> `dbt_cos_build` |
| Downstream models | `stg_cos2023` -> `land_use` |
| Tags | `cos`, `land-use`, `dgt`, `bronze`, `postgis` |

---

## Bronze schema

### `bronze_geo.raw_cos2023` — ~784,000 rows

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Feature ID |
| `cos23_n4_c` | VARCHAR(10) | 4-level land-use code |
| `cos23_n4_l` | TEXT | Human-readable label |
| `area_ha` | DOUBLE PRECISION | Polygon area (hectares) |
| `geom` | GEOMETRY(MULTIPOLYGON, 3763) | Boundary in PT-TM06 |
| `_source_url` | TEXT | Download URL used |
| `_load_timestamp` | TIMESTAMPTZ | Ingestion timestamp |

### Indexes

- GIST on `geom`
- B-tree on `cos23_n4_c`

### Key relationships

- Spatial join to `raw_caop_freguesias` via `ST_Within(ST_PointOnSurface(geom), freguesia.geom)`
- `cos23_n4_c` first character maps to level-1 category (1=Artificial, etc.)

---

## Silver model (`land_use.sql`)

The dbt silver model enriches COS polygons with:
- Hierarchy decomposition (level 1-4 codes split out)
- Boolean flags: `is_urban`, `is_residential`, `is_forest`, `is_agricultural`
- Freguesia assignment via spatial join
- Dual geometry: EPSG:3763 (`geom`) + WGS84 (`geom_wgs84`)

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| Large dataset | ~784K polygons, bronze load takes ~15 min | Batch insert (5000 rows) keeps memory manageable |
| ~5 year refresh cycle | 2023 is latest; next expected ~2028 | Sufficient for current use case |
| No coordinate transform needed | Already in EPSG:3763 | N/A |

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
pipelines/gis/cos/
├── __init__.py                    # Package marker
├── cos_config.py                  # Download URL, version, validation thresholds
├── cos_ingestion_dag.py           # DAG: DGT -> MinIO (uses gis_ingestion_template)
├── cos_bronze_dag.py              # DAG: MinIO -> PostGIS (uses gpkg_bronze_template)
└── README.md                      # This file
```

### Updating for a new release

When COS 2028 (or next version) is released:
1. Update `download_url` in `cos_config.py`
2. Trigger ingestion with `{"version": "2028"}`
3. Update `expected_layers` if DGT changes layer naming
4. Review silver model if classification system changes
