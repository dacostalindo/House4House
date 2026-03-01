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

## After ingestion

The pipeline intentionally does **not** load into PostGIS.

Next steps:
1. Download the `.gpkg` from MinIO (bucket `raw`, path `caop/{version}/...`)
2. Explore it in QGIS: inspect field names, value formats, `dtmnfr` / `dtmn` / `dt` code structure, geometry quality
3. Design `bronze_geo.raw_caop_*` DDL based on actual field names/types
4. Build the bronze loading pipeline (`ogr2ogr` → PostGIS)

The `validate_gis_file` task logs the full field list for every layer — check the Airflow task logs for a quick preview without downloading.

---

## Updating for a new release

No code changes needed. Just re-trigger with the new `version` and `download_url`.

If DGT changes the layer naming convention, update `_caop_layer_names()` in [caop_config.py](caop_config.py).
