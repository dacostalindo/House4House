# CRUS — Vectorized PDM Zoning (DGTERRITORIO)

**Carta do Regime de Uso do Solo** — nationally standardized land-use zoning extracted from each municipality's active PDM (Plano Diretor Municipal). Classifies all land into Solo Urbano / Solo Rustico with detailed sub-categories. The vector equivalent of the PDM Ordenamento plan.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | DGTERRITORIO — Direcao-Geral do Territorio |
| Page | https://dados.gov.pt (search "CRUS") |
| Auth | None required (public WFS) |
| Format | GeoJSON via OGC WFS 2.0.0 |
| CRS | ETRS89 / PT-TM06 — **EPSG:3763** |
| Coverage | Per-municipality (5 configured: Aveiro, Lisboa, Porto, Coimbra, Leiria) |
| Refresh | Updated when municipality's PDM changes |

---

## What it contains

Zoning polygons classified according to the national land-use regime. Each polygon represents a distinct zoning area from the municipality's active PDM.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `ID` | INTEGER | Feature ID |
| `DTCC` | VARCHAR(4) | Municipality code (e.g. "0105") |
| `Municipio` | VARCHAR(100) | Municipality name |
| `Classe` | VARCHAR(50) | Land class: "Solo Urbano" or "Solo Rustico" |
| `Categoria` | VARCHAR(200) | Land category (e.g. "Espaco Habitacional") |
| `Designacao_PlantaOrdenamento` | TEXT | Full PDM zoning designation |
| `Area_Ha` | DOUBLE PRECISION | Polygon area in hectares |
| `Escala_PlantaOrdenamento` | VARCHAR(10) | Source map scale (e.g. "1/10000") |
| `Data_PublicacaoPDM` | TIMESTAMPTZ | PDM publication date |
| `Fonte` | VARCHAR(30) | Data source |
| `Autor` | VARCHAR(10) | Author (typically "DGT") |

### Configured municipalities

| Code | Name | Feature Type | ~Features |
|------|------|-------------|-----------|
| 0105 | Aveiro | `gmgml:CRUS_Aveiro_V` | ~1,500 |
| 1106 | Lisboa | `gmgml:CRUS_Lisboa_V` | ~2,000 |
| 1312 | Porto | `gmgml:CRUS_Porto_V` | ~800 |
| 0603 | Coimbra | `gmgml:CRUS_Coimbra_V` | ~1,200 |
| 1009 | Leiria | `gmgml:CRUS_Leiria_V` | ~900 |

### Field normalization

WFS responses use accented Portuguese field names that vary across municipalities. The pipeline normalizes all field names by:
1. Stripping diacritics (`c` -> `c`, `a` -> `a`)
2. Applying explicit renames (Porto's `ID1` -> `ID`, `Data_PubliccaoPDM` -> `Data_PublicacaoPDM`)

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI -> **crus_ingestion** -> **Trigger DAG w/ config**:

```json
{}
```

To process specific municipalities only:

```json
{"municipalities": ["0105", "1106"]}
```

### 2. What happens

```
resolve_municipalities              determine which to process (all or filtered)
  |
check_wfs_availability.expand()     parallel GetCapabilities per municipality
  |
fetch_crus_features.expand()        parallel WFS GetFeature (single request each)
  |  (normalize field names, filter to known fields)
  |
save_to_minio.expand()              parallel uploads
  |
cleanup_temp -> log_summary
```

### 3. Where it lands

```
s3://raw/crus/{municipality_lower}/{YYYYMMDD}/crus.geojson
```

Example: `s3://raw/crus/aveiro/20260319/crus.geojson`

### 4. Bronze load

After ingestion completes, trigger **`crus_bronze_load`** from the Airflow UI (no config needed).

---

## DAGs

### `crus_ingestion` — WFS -> MinIO

```
resolve_municipalities -> check_wfs.expand() -> fetch_features.expand() -> save_to_minio.expand() -> cleanup -> log_summary
```

| Setting | Value |
|---------|-------|
| Schedule | None (manual trigger) |
| Max active tasks | 2 (parallel municipality processing) |
| Retries | 2 (5-minute delay) |
| Tags | `crus`, `zoning`, `ingestion`, `gis`, `minio` |

### `crus_bronze_load` — MinIO -> PostGIS -> dbt

```
fetch_from_minio -> create_table -> load_features (per municipality) -> validate_counts -> trigger_dbt
```

| Setting | Value |
|---------|-------|
| Schedule | None (triggered by ingestion or manual) |
| Idempotency | Per-municipality DELETE + INSERT (single table for all municipalities) |
| dbt trigger | `TriggerDagRunOperator` -> `dbt_crus_build` |
| Downstream models | `stg_crus_ordenamento` -> `zoning` |
| Tags | `crus`, `bronze`, `postgis`, `zoning` |

---

## Bronze schema

### `bronze_regulatory.raw_crus_ordenamento` — ~5,472 rows (all municipalities combined)

| Column | Type | Description |
|--------|------|-------------|
| `feature_id` | INTEGER | Feature ID |
| `municipality_code` | VARCHAR(4) | DTCC code |
| `municipality_name` | VARCHAR(100) | Municipality name |
| `classe` | VARCHAR(50) | Land class (Solo Urbano / Solo Rustico) |
| `categoria` | VARCHAR(200) | Land category |
| `designacao` | TEXT | Full PDM designation |
| `area_ha` | DOUBLE PRECISION | Polygon area (hectares) |
| `escala` | VARCHAR(10) | Source map scale |
| `data_publicacao_pdm` | TIMESTAMPTZ | PDM publication date |
| `fonte` | VARCHAR(30) | Data source |
| `autor` | VARCHAR(10) | Author |
| `geom` | GEOMETRY(GEOMETRY, 3763) | Zoning boundary in PT-TM06 |
| `_source_url` | TEXT | WFS URL used |
| `_load_timestamp` | TIMESTAMPTZ | Ingestion timestamp |

### Indexes

- `idx_crus_ord_geom` — GIST on `geom`
- `idx_crus_ord_muni` — B-tree on `municipality_code`

### Key relationships

- `municipality_code` joins to CAOP `raw_caop_municipios.dtmn`
- Spatial join to listings via `ST_Within(listing.geom_pt, zoning.geom)`

---

## Silver model (`zoning.sql`)

The dbt silver model maps CRUS categories to simplified zone types:
- `urban_consolidated`, `urban_expansion`, `urban_residential`
- `rural_agricultural`, `rural_forest`, etc.
- Dual geometry: EPSG:3763 + WGS84

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| Limited municipality coverage | Only 5 municipalities configured | Add more by appending to `MUNICIPALITIES` in `crus_config.py` |
| No WFS pagination | DGTERRITORIO ignores STARTINDEX; all features in one request | OK — all municipalities have <2,000 features |
| Accented field names vary | Porto uses `ID1`, Aveiro has `Data_PubliccaoPDM` | Handled by `normalize_field_name()` in config |

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
pipelines/gis/crus/
├── __init__.py                    # Package marker
├── crus_config.py                 # WFS endpoints, municipalities, field normalization
├── crus_ingestion_dag.py          # DAG: WFS -> MinIO
├── crus_bronze_dag.py             # DAG: MinIO -> PostGIS bronze table
└── README.md                      # This file
```

### Adding a new municipality

1. Find the municipality's CRUS WFS endpoint on SNIT (URL pattern: `SDISNITWFSCRUS_{DTCC}_1`)
2. Verify the feature type name via GetCapabilities (typically `gmgml:CRUS_{Name}_V`)
3. Add a `CRUSMunicipalityConfig` entry in `crus_config.py`:

```python
CRUSMunicipalityConfig("XXXX", "MunicipalityName", "gmgml:CRUS_Name_V"),
```

4. Re-trigger the ingestion DAG
