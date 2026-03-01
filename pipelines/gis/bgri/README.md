# S12 — BGRI Census 2021 (INE)

**Base Geográfica de Referenciação de Informação** — the INE statistical geography grid bundled with Census 2021 variables. City-block level demographics with embedded geometry.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | INE — Instituto Nacional de Estatística |
| Page | https://mapas.ine.pt/download/index2021.phtml |
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

---

## Why BGRI instead of the INE Census API

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

---

## After ingestion

1. Read the `validate_gis_file` task logs to confirm layer names and field list
2. Update `expected_layers` in [bgri_config.py](bgri_config.py) with the actual layer names
3. Download the `.gpkg` from MinIO and open in QGIS to explore
4. Design `bronze_geo.raw_bgri_2021_subseccao` DDL based on actual column names
5. Build the bronze loading pipeline (`ogr2ogr` → PostGIS)

---

## Updating for a new census

Not applicable until the next census (~2031). At that point:
- Update `download_url` and `source_version` in [bgri_config.py](bgri_config.py)
- Update `expected_layers` if INE changes layer naming
