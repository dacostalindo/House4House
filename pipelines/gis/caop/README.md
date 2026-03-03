# S08 — CAOP Boundaries (DGT)

**Carta Administrativa Oficial de Portugal** — the official Portuguese administrative boundary dataset, published annually by DGT (Direção-Geral do Território).

This is a **P0 / foundation source**. Every entity in the warehouse (listing, census record, POI, etc.) resolves to a `freguesia` via a spatial join against this dataset. It must be loaded before anything else.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | DGT — Direção-Geral do Território |
| Page | https://www.dgterritorio.gov.pt/cartografia/caop |
| Format | GeoPackage (`.gpkg`), sometimes distributed as `.zip` |
| CRS | ETRS89 / PT-TM06 — **EPSG:3763** (projected) or ETRS89 geographic — **EPSG:4258** |
| Coverage | Continental Portugal only (`cont_*` layers) |
| Refresh | Annual — no fixed date |

---

## Layers

The GeoPackage contains three primary administrative boundary layers plus auxiliary layers (NUTS hierarchy, edge lines, style tables). Only the three below are validated:

| Layer | Level | ~Features |
|-------|-------|-----------|
| `cont_distritos` | Distrito | 18 |
| `cont_municipios` | Concelho/Município | 278 |
| `cont_freguesias` | Freguesia | ~3,049 |

Auxiliary layers present in the file (not validated): `cont_areas_administrativas`, `cont_nuts1`, `cont_nuts2`, `cont_nuts3`, `cont_trocos`, `layer_styles`, `inf_fonte_troco`.

> **Note:** Azores and Madeira are published as separate files (`RAA_*`, `RAM_*`).
> This pipeline covers continental Portugal only. Island coverage is out of scope for MVP.

---

## How to run

### 1. Find the download URL

Go to the DGT CAOP page and locate the GeoPackage download link for the current release. DGT does not use a stable permalink — the URL changes every year. The file may be a raw `.gpkg` or a `.zip` wrapping a `.gpkg`; the pipeline handles both.

### 2. Trigger the DAG

Open the Airflow UI → **s08_caop_ingestion** → **Trigger DAG w/ config**:

```json
{
  "version": "2025",
  "download_url": "<paste .gpkg or .zip URL here>"
}
```

`version` controls the MinIO storage path (`s3://raw/caop/{version}/...`). Layer names are fixed (not derived from the version).

### 3. What happens

```
HEAD {download_url}              check source is reachable
  ↓
stream download → /tmp/          4 MB chunks, SHA-256 computed on the fly
  ↓ (if .zip: extract inner .gpkg automatically)
pyogrio.list_layers()            assert cont_distritos, cont_municipios, cont_freguesias present
pyogrio.read_info() × all layers log fields, CRS, feature count for every layer
  ↓
minio.fput_object()              upload raw .gpkg with SHA-256 as object metadata
  ↓
cleanup /tmp/                    remove temp file
log_run_metadata                 structured summary in Airflow task logs
```

### 4. Where it lands

```
s3://raw/caop/{version}/{filename}.gpkg
```

Example: `s3://raw/caop/2025/Continente_CAOP2025.gpkg`

---

## Validation behaviour

| Check | On failure |
|-------|-----------|
| HTTP status ≠ 2xx | Hard fail — DAG stops at task 1 |
| File < 10 MB | Hard fail — likely truncated download |
| Expected layer missing | Hard fail — layer names may have changed, update `_caop_layer_names()` |
| Feature count outside [10, 5000] | Hard fail — applies to `cont_distritos`, `cont_municipios`, `cont_freguesias` only |
| CRS ≠ EPSG:3763/4258 | **Warning only** — file still uploaded; reprojection handled in silver |

---

## Bronze Schema

After ingestion to MinIO, DAG **`s08_caop_bronze_load`** loads the GPKG into PostGIS.
Full-refresh (TRUNCATE + INSERT), idempotent, no schedule — trigger manually.

### `bronze_geo.raw_caop_freguesias` — 3,049 rows

| Column | Type | Description |
|--------|------|-------------|
| `dtmnfr` | VARCHAR(6) | DICOFRE code (distrito 2 + municipio 2 + freguesia 2) |
| `freguesia` | TEXT | Parish name |
| `municipio` | TEXT | Municipality name |
| `distrito_ilha` | TEXT | District name |
| `nuts3_cod` | VARCHAR(10) | NUTS III code |
| `nuts3` | TEXT | NUTS III name |
| `nuts2` | TEXT | NUTS II name |
| `nuts1` | TEXT | NUTS I name |
| `area_ha` | DOUBLE PRECISION | Area in hectares |
| `perimetro_km` | INTEGER | Perimeter in km |
| `designacao_simplificada` | TEXT | Simplified designation |
| `geom` | GEOMETRY(MULTIPOLYGON, 3763) | Boundary in ETRS89 / PT-TM06 |
| `_load_timestamp` | TIMESTAMPTZ | Ingestion timestamp |

### `bronze_geo.raw_caop_municipios` — 278 rows

| Column | Type | Description |
|--------|------|-------------|
| `dtmn` | VARCHAR(4) | Municipality code (distrito 2 + municipio 2) |
| `municipio` | TEXT | Municipality name |
| `distrito_ilha` | TEXT | District name |
| `nuts3_cod` | VARCHAR(10) | NUTS III code |
| `nuts3` | TEXT | NUTS III name |
| `nuts2` | TEXT | NUTS II name |
| `nuts1` | TEXT | NUTS I name |
| `area_ha` | DOUBLE PRECISION | Area in hectares |
| `perimetro_km` | INTEGER | Perimeter in km |
| `n_freguesias` | INTEGER | Number of parishes |
| `geom` | GEOMETRY(MULTIPOLYGON, 3763) | Boundary in ETRS89 / PT-TM06 |
| `_load_timestamp` | TIMESTAMPTZ | Ingestion timestamp |

### `bronze_geo.raw_caop_distritos` — 18 rows

| Column | Type | Description |
|--------|------|-------------|
| `dt` | VARCHAR(2) | District code |
| `distrito` | TEXT | District name |
| `nuts1_cod` | VARCHAR(10) | NUTS I code |
| `nuts1` | TEXT | NUTS I name |
| `area_ha` | DOUBLE PRECISION | Area in hectares |
| `perimetro_km` | INTEGER | Perimeter in km |
| `n_municipios` | INTEGER | Number of municipalities |
| `n_freguesias` | DOUBLE PRECISION | Number of parishes |
| `geom` | GEOMETRY(MULTIPOLYGON, 3763) | Boundary in ETRS89 / PT-TM06 |
| `_load_timestamp` | TIMESTAMPTZ | Ingestion timestamp |

### Key relationships

- `dtmnfr` = `dtmn` prefix (4 chars) → joins to municipios
- `dtmn` = `dt` prefix (2 chars) → joins to distritos
- `dtmnfr` is the primary join key for spatial lookups across the warehouse

---

## After ingestion

Trigger **`s08_caop_bronze_load`** from the Airflow UI (no config needed).
It finds the latest GPKG in MinIO automatically.

The `validate_gis_file` task in the ingestion DAG logs the full field list for every layer — check the Airflow task logs for a quick preview without downloading.

---

## Updating for a new release

No code changes needed. Just re-trigger the ingestion DAG with the new `version` and `download_url`, then re-trigger the bronze load DAG.

If DGT changes the layer naming convention, update `_caop_layer_names()` in [caop_config.py](caop_config.py).
