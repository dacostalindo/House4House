# dbt — House4House Transformation Layer

Silver and gold layer transformations for the House4House data warehouse. Runs inside Airflow containers via `dbt-postgres 1.9`.

---

## Setup

| Component | Detail |
|-----------|--------|
| Adapter | `dbt-postgres==1.9.0` (installed in Airflow image) |
| Profile | `house4house` → PostGIS warehouse (`house4house` DB) |
| Connection | Environment variables: `WAREHOUSE_HOST`, `WAREHOUSE_PORT`, `WAREHOUSE_DB`, `WAREHOUSE_USER`, `WAREHOUSE_PASSWORD` |
| Profiles dir | `DBT_PROFILES_DIR=/opt/airflow/dbt` (set in docker-compose.yml) |
| Mount | `./dbt:/opt/airflow/dbt` |

### How to run

```bash
# Via Airflow UI — trigger the dbt_gold_build DAG

# Or manually from the scheduler container:
docker exec house4house-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt && dbt deps && dbt run && dbt test"

# Run a specific model:
docker exec house4house-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt && dbt run --select dim_geography"
```

### Custom schema macro

dbt normally prepends the target schema to custom schemas (e.g. `gold_analytics` becomes `gold_analytics_gold_analytics`). The macro in `macros/get_custom_schema.sql` overrides this so `+schema: gold_analytics` writes to exactly `gold_analytics`.

---

## Project variables

| Variable | Default | Used in | Purpose |
|----------|---------|---------|---------|
| `caop_year` | `2025` | `dim_geography` | CAOP boundary version year. Override: `dbt run --vars '{caop_year: 2026}'` |

---

## Models

### Staging (views in `staging_dbt`)

Thin transformations on bronze tables. Materialized as views — no data copy, always fresh.

#### stg_caop_freguesias

- **Source**: `bronze_geo.raw_caop_freguesias` (3,049 rows)
- **Transforms**:
  - Renames `dtmnfr` → `freguesia_code`, derives `distrito_code` (first 2 chars), `concelho_code` (first 4 chars)
  - Renames Portuguese column names to English (`freguesia`, `municipio`, `distrito_ilha`, `nuts*`)
  - Adds `ST_Transform(geom, 4326)` as `geom_4326` (native CRS is EPSG:3763 PT-TM06)
  - Passes through `area_ha` and native `geom` as `geom_pt`

#### stg_caop_distritos

- **Source**: `bronze_geo.raw_caop_distritos` (18 rows)
- **Transforms**: Renames `dt` → `distrito_code`, `distrito` → `distrito_name`

#### stg_caop_municipios

- **Source**: `bronze_geo.raw_caop_municipios` (278 rows)
- **Transforms**: Renames `dtmn` → `concelho_code`, `municipio` → `concelho_name`

#### stg_bgri_freguesia_agg

- **Source**: `bronze_ine.raw_bgri` (203,264 subsections → 3,049 freguesia aggregates)
- **Transforms**:
  - Groups by `dtmnfr21` (freguesia code from Census 2021)
  - `population_2021` = `SUM(n_individuos)` — total resident individuals
  - `households_2021` = `SUM(n_agregados_domesticos_privados)` — private domestic households
  - `weighted_avg_age` — estimated from age band midpoints (see note below)

**Age calculation**: BGRI provides 4 age bands, not individual ages. True median cannot be computed. We calculate a weighted average using band midpoints:

| Band | Count column | Midpoint |
|------|-------------|----------|
| 0–14 | `n_individuos_0_14` | 7.0 |
| 15–24 | `n_individuos_15_24` | 19.5 |
| 25–64 | `n_individuos_25_64` | 44.5 |
| 65+ | `n_individuos_65_ou_mais` | 77.5 |

Formula: `SUM(count * midpoint) / SUM(total_individuals)`. The 65+ midpoint of 77.5 is an assumption (actual range is 65–100+). This produces a reasonable proxy but is **not a true median age**. The column is named `weighted_avg_age` in staging and aliased to `median_age` in dim_geography for compatibility with the target schema.

---

### Gold (tables in `gold_analytics`)

#### dim_geography

The backbone dimension — every property, transaction, and metric ties back to geography at the freguesia level.

- **Output**: `gold_analytics.dim_geography` — 3,049 rows
- **Materialization**: Table (full refresh, ~6 seconds)
- **Sources**: `stg_caop_freguesias` LEFT JOIN `stg_bgri_freguesia_agg`
- **Tests**: 10 (unique + not_null on `geo_key`, `freguesia_code`; not_null on codes, names, geometries, area)

**Column mapping**:

| Column | Source | Logic |
|--------|--------|-------|
| `geo_key` | Derived | `ROW_NUMBER() OVER (ORDER BY freguesia_code)` — deterministic integer surrogate key |
| `distrito_code` | CAOP | First 2 chars of `dtmnfr` |
| `distrito_name` | CAOP | `distrito_ilha` column |
| `concelho_code` | CAOP | First 4 chars of `dtmnfr` |
| `concelho_name` | CAOP | `municipio` column |
| `freguesia_code` | CAOP | `dtmnfr` (6-digit INE code) |
| `freguesia_name` | CAOP | `freguesia` column |
| `nut_i`, `nut_ii`, `nut_iii` | CAOP | Direct from `nuts1`, `nuts2`, `nuts3` |
| `postal_code_4` | — | NULL (no source data yet; needs CTT mapping or Nominatim enrichment) |
| `freguesia_geom` | CAOP | `ST_Transform(geom, 4326)` — WGS84 for display and OSM spatial joins |
| `freguesia_geom_pt` | CAOP | Native `geom` in EPSG:3763 — PT-TM06 for metric distance queries |
| `centroid` | Derived | `ST_Centroid(geom_4326)` — point in EPSG:4326 |
| `area_km2` | CAOP | `area_ha / 100.0` |
| `population_2021` | BGRI | `SUM(n_individuos)` per freguesia |
| `households_2021` | BGRI | `SUM(n_agregados_domesticos_privados)` per freguesia |
| `pop_density_km2` | Derived | `population_2021 / area_km2` |
| `median_age` | BGRI | Weighted average from age bands (see stg_bgri_freguesia_agg above) |
| `foreign_resident_pct` | — | NULL (not in BGRI synthesis file; needs INE API supplementary data) |
| `source_caop_year` | Variable | `{{ var('caop_year') }}` — defaults to 2025 |
| `valid_from` | Variable | `{{ var('caop_year') }}-01-01` |
| `valid_to` | — | NULL (current record) |
| `is_current` | — | TRUE |

**Indexes** (created via `post_hook`):
- GIST on `freguesia_geom` and `freguesia_geom_pt` (spatial queries)
- B-tree on `freguesia_code` and `concelho_code` (lookups and joins)

**Known gaps**:

| Issue | Detail | Resolution |
|-------|--------|------------|
| 302 freguesias with NULL census data | CAOP 2025 has 3,049 codes; BGRI 2021 has 2,882. The 302 mismatches are from the 2013 LAU reform — CAOP 2025 uses updated codes that don't exist in Census 2021. | LEFT JOIN ensures all 3,049 appear. Future: build a CAOP↔BGRI code reconciliation mapping. |
| `median_age` is a weighted average | BGRI only provides 4 age bands, not individual ages. | Documented above. True median requires INE API microdata. |
| `postal_code_4` is NULL | No postal code mapping loaded yet. | Future: CTT postal code boundaries or Nominatim reverse geocoding of centroids. |
| `foreign_resident_pct` is NULL | Not in BGRI synthesis file. | Future: source from INE API indicator for foreign residents by freguesia. |
| National population total is 8.77M (not 10.3M) | Due to the 302 missing freguesia matches, some population is unaccounted for. The 2,747 matched freguesias cover 8.77M of the ~10.3M total. | Will improve with code reconciliation. |

---

## Airflow integration

**DAG**: `dbt_gold_build` ([dbt_gold_dag.py](../pipelines/dbt/dbt_gold_dag.py))

```
dbt_deps → dbt_run (--select gold) → dbt_test (--select gold)
```

- Schedule: None (manual trigger)
- Tags: `dbt`, `gold`, `analytics`
- Trigger after all bronze loads are complete

---

## Directory structure

```
dbt/
├── dbt_project.yml          # Project config, variables, materialization defaults
├── profiles.yml             # Warehouse connection (env vars)
├── packages.yml             # dbt_utils
├── macros/
│   └── get_custom_schema.sql  # Schema override (gold_analytics, not default_gold_analytics)
├── models/
│   ├── staging/
│   │   ├── _staging__sources.yml       # Source definitions (bronze_geo, bronze_ine)
│   │   ├── stg_caop_freguesias.sql
│   │   ├── stg_caop_distritos.sql
│   │   ├── stg_caop_municipios.sql
│   │   └── stg_bgri_freguesia_agg.sql
│   └── gold/
│       ├── _gold__models.yml           # Tests (unique, not_null)
│       └── dim_geography.sql
├── target/                  # (gitignored) compiled SQL, run artifacts
├── dbt_packages/            # (gitignored) installed packages
└── logs/                    # (gitignored) dbt logs
```
