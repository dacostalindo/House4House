# BGRI Census 2021 — Statistical Geography & Demographics (INE)

**Base Geográfica de Referenciação de Informação** — the INE statistical geography grid bundled with Census 2021 variables. City-block level demographics with embedded geometry.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | INE — Instituto Nacional de Estatística |
| Page | https://mapas.ine.pt/download/index2021.phtml |
| Auth | None required (public download) |
| Format | GeoPackage (`.gpkg`) inside a `.zip` archive |
| CRS | ETRS89 / PT-TM06 — **EPSG:3763** (projected, metres) |
| Coverage | All of Portugal (continental + Azores + Madeira) |
| Refresh | Static — Census 2021. Next census ~2031. |

---

## What it contains

32 census variables at two geographic levels:

| Level | ~Features | Description |
|-------|-----------|-------------|
| Statistical subsection | ~120K–200K | City-block granularity |
| Statistical section | ~20K–40K | Aggregated subsections |

### Variable groups

**Buildings (12):**
`N_EDIFICIOS_CLASSICOS`, `N_EDIFICIOS_CLASS_CONST_1OU2_ALOJ`, `N_EDIFICIOS_CLASS_CONST_3OUMAIS`, `N_EDIFICIOS_EXCLUSIV_RESID`, `N_EDIFICIOS_1OU2_PISOS`, `N_EDIFICIOS_3MAIS_PISOS`, `N_EDIFICIOS_CONSTR_ANTES1945`, `N_EDIFICIOS_CONSTR_1946A1980`, `N_EDIFICIOS_CONSTR_1981A2000`, `N_EDIFICIOS_CONSTR_2001_2010`, `N_EDIFICIOS_CONSTR_2011_2021`, `N_EDIFICIOS_COM_NEC_REPARACAO`

**Dwellings (8):**
`N_ALOJAMENTOS_TOTAL`, `N_ALOJAMENTOS_FAMILIARES`, `N_ALOJAMENTOS_FAM_RHABITUAL`, `N_ALOJAMENTOS_VAGOS_SEC`, `N_RHABITUAL_ACESSIVEL`, `N_RHABITUAL_ESTACIONAMENTO`, `N_RHABITUAL_PROP_OCUP`, `N_RHABITUAL_ARRENDADOS`

**Households (5):**
`N_AGREGADOS_DOMESTICOS`, `N_ADP_1OU2_PESSOAS`, `N_ADP_3OUMAIS_PESSOAS`, `N_NUCLEOS_FAMILIARES`, `N_NUCLEOS_FAM_COM_FILHOS`

**Population (7):**
`N_INDIVIDUOS`, `N_INDIVIDUOS_H`, `N_INDIVIDUOS_M`, `N_INDIVIDUOS_0A14`, `N_INDIVIDUOS_15A24`, `N_INDIVIDUOS_25A64`, `N_INDIVIDUOS_65_OU_MAIS`

> **Not in the synthesis file:** education level, employment/unemployment rate, foreign-born %. These will be sourced from the INE API (pindica.jsp) as P1 supplements once the hedonic model requires them.

### Why BGRI instead of the INE Census API

| | BGRI (this pipeline) | INE API (pindica.jsp) |
|---|---|---|
| Granularity | Statistical subsection (city block) | Parish at best |
| Geometry | Included — each row is a polygon | None |
| Pipeline | Flow C — reuses GIS template | Flow A — separate template |
| Variables | 32 pre-joined columns (wide format) | One indicator per API call |

City-block granularity with embedded geometry makes BGRI directly usable for spatial joins against listings without a separate boundary join step.

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI → **s12_bgri_ingestion** → **Trigger DAG**.

No configuration parameters needed — the URL and version are hardcoded.

### 2. What happens

```
HEAD https://mapas.ine.pt/download/filesGPG/2021/portugal2021.zip
  ↓
stream download → /tmp/          4 MB chunks, SHA-256 on the fly
  ↓ (zip extracted automatically)
pyogrio.list_layers()            log all available layer names and feature counts
pyogrio.read_info() × all layers log fields, CRS, geometry type for each layer
  ↓
minio.fput_object()              upload raw .gpkg with SHA-256 as object metadata
  ↓
cleanup /tmp/
log_run_metadata                 structured summary in Airflow task logs
```

### 3. Where it lands

```
s3://raw/bgri/2021/portugal2021.gpkg
```

### 4. Bronze load

After ingestion completes, trigger **`s12_bgri_bronze_load`** from the Airflow UI (no config needed). It finds the latest GPKG in MinIO automatically.

---

## DAGs

### `s12_bgri_ingestion` — INE → MinIO

```
check_source → download_file → validate_gis_file → upload_to_minio → cleanup_temp → log_run_metadata
```

| Setting | Value |
|---------|-------|
| Schedule | None (manual trigger) |
| Tags | `ingestion`, `gis`, `bgri` |

### `s12_bgri_bronze_load` — MinIO → PostGIS

```
find_latest_gpkg → create_table → load_subsections → validate_counts
```

| Setting | Value |
|---------|-------|
| Schedule | None (manual trigger) |
| Idempotency | TRUNCATE + INSERT |
| Tags | `bgri`, `bronze`, `postgis` |

---

## Bronze schema

### `bronze_ine.raw_bgri` — 203,264 rows

| Column | Type | Description |
|--------|------|-------------|
| `objectid` | INTEGER | GPKG row ID |
| `bgri2021` | VARCHAR(20) | Statistical subsection code (11-char) |
| `dt21` | VARCHAR(2) | District code |
| `dtmn21` | VARCHAR(4) | Municipality code |
| `dtmnfr21` | VARCHAR(6) | Parish code (DICOFRE) |
| `dtmnfrsec21` | VARCHAR(10) | Section code |
| `secnum21` | VARCHAR(4) | Section number within parish |
| `ssnum21` | VARCHAR(4) | Subsection number within section |
| `secssnum21` | VARCHAR(8) | Section + subsection combined |
| `subseccao` | VARCHAR(20) | Subsection label |
| `nuts1` | VARCHAR(50) | NUTS I code |
| `nuts2` | VARCHAR(50) | NUTS II code |
| `nuts3` | VARCHAR(50) | NUTS III code |
| **Buildings (12)** | | |
| `n_edificios_classicos` | DOUBLE PRECISION | Classic buildings |
| `n_edificios_class_const_1_ou_2_aloj` | DOUBLE PRECISION | Buildings with 1-2 dwellings |
| `n_edificios_class_const_3_ou_mais_alojamentos` | DOUBLE PRECISION | Buildings with 3+ dwellings |
| `n_edificios_exclusiv_resid` | DOUBLE PRECISION | Exclusively residential buildings |
| `n_edificios_1_ou_2_pisos` | DOUBLE PRECISION | 1-2 storey buildings |
| `n_edificios_3_ou_mais_pisos` | DOUBLE PRECISION | 3+ storey buildings |
| `n_edificios_constr_antes_1945` | DOUBLE PRECISION | Built before 1945 |
| `n_edificios_constr_1946_1980` | DOUBLE PRECISION | Built 1946-1980 |
| `n_edificios_constr_1981_2000` | DOUBLE PRECISION | Built 1981-2000 |
| `n_edificios_constr_2001_2010` | DOUBLE PRECISION | Built 2001-2010 |
| `n_edificios_constr_2011_2021` | DOUBLE PRECISION | Built 2011-2021 |
| `n_edificios_com_necessidades_reparacao` | DOUBLE PRECISION | Buildings needing repair |
| **Dwellings (8)** | | |
| `n_alojamentos_total` | DOUBLE PRECISION | Total dwellings |
| `n_alojamentos_familiares` | DOUBLE PRECISION | Family dwellings |
| `n_alojamentos_fam_class_rhabitual` | DOUBLE PRECISION | Usual residence |
| `n_alojamentos_fam_class_vagos_ou_resid_secundaria` | DOUBLE PRECISION | Vacant or secondary |
| `n_rhabitual_acessivel_cadeiras_rodas` | DOUBLE PRECISION | Wheelchair accessible |
| `n_rhabitual_com_estacionamento` | DOUBLE PRECISION | With parking |
| `n_rhabitual_prop_ocup` | DOUBLE PRECISION | Owner-occupied |
| `n_rhabitual_arrendados` | DOUBLE PRECISION | Rented |
| **Households (5)** | | |
| `n_agregados_domesticos_privados` | DOUBLE PRECISION | Private domestic aggregates |
| `n_adp_1_ou_2_pessoas` | DOUBLE PRECISION | 1-2 person households |
| `n_adp_3_ou_mais_pessoas` | DOUBLE PRECISION | 3+ person households |
| `n_nucleos_familiares` | DOUBLE PRECISION | Family nuclei |
| `n_nucleos_familiares_com_filhos_tendo_o_mais_novo_menos_de_25` | DOUBLE PRECISION | Family nuclei with youngest child < 25 |
| **Population (7)** | | |
| `n_individuos` | DOUBLE PRECISION | Total population |
| `n_individuos_h` | DOUBLE PRECISION | Male population |
| `n_individuos_m` | DOUBLE PRECISION | Female population |
| `n_individuos_0_14` | DOUBLE PRECISION | Age 0-14 |
| `n_individuos_15_24` | DOUBLE PRECISION | Age 15-24 |
| `n_individuos_25_64` | DOUBLE PRECISION | Age 25-64 |
| `n_individuos_65_ou_mais` | DOUBLE PRECISION | Age 65+ |
| **Shape + Geometry** | | |
| `shape_length` | DOUBLE PRECISION | Perimeter length |
| `shape_area` | DOUBLE PRECISION | Area |
| `geom` | GEOMETRY(MULTIPOLYGON, 3763) | Boundary in ETRS89 / PT-TM06 |
| `_load_timestamp` | TIMESTAMPTZ | Ingestion timestamp |

### Key relationships

- `dtmnfr21` joins to CAOP `raw_caop_freguesias.dtmnfr`
- `dtmn21` joins to CAOP `raw_caop_municipios.dtmn`
- `bgri2021` is the most granular geographic key (city-block level)

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| Static 2021 snapshot | No time-series — single census point | INE API provides time-series supplements |
| Missing variables | Education, employment, foreign-born not in synthesis file | Source from INE API when hedonic model requires them |

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
pipelines/gis/bgri/
├── __init__.py                    # Package marker
├── bgri_config.py                 # Download URL, version, validation thresholds
├── bgri_ingestion_dag.py          # DAG: INE → MinIO
├── bgri_bronze_dag.py             # DAG: MinIO → PostGIS bronze table
└── README.md                      # This file
```

### Updating for a new census

Not applicable until the next census (~2031). At that point:
- Update `download_url` and `source_version` in [bgri_config.py](bgri_config.py)
- Update `expected_layers` if INE changes layer naming
