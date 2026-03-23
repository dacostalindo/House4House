# SRUP — Property Constraints (DGTERRITORIO)

**Servidoes e Restricoes de Utilidade Publica** — property constraint/restriction data from PDM Condicionantes. Heritage protection zones, agricultural reserves, and public water domain restrictions. Critical for property valuation: parcels inside these zones face building restrictions.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | DGTERRITORIO — Direcao-Geral do Territorio |
| Page | https://www.dgterritorio.gov.pt/sistemas-informacao |
| Auth | None required (public WFS) |
| Format | GeoJSON via OGC WFS 2.0.0 |
| CRS | ETRS89 / PT-TM06 — **EPSG:3763** |
| Coverage | Continental Portugal (national endpoints) |
| Refresh | Updated as restrictions change (infrequent) |

---

## What it contains

Phase 1 ingests 3 of 4 high-value SRUP categories:

| Category | Full Name | Feature Types | ~Features |
|----------|-----------|--------------|-----------|
| **IC** | Imoveis Classificados | Heritage zones (polygon) + locations (point) | ~3,676 |
| **RAN** | Reserva Agricola Nacional | Agricultural reserve polygons | ~268 |
| **DPH** | Dominio Publico Hidrico | Conditioned + prohibited water zones | ~7 |

Phase 2 (not yet implemented): **REN** (Reserva Ecologica Nacional) — requires BBOX filtering due to dataset size, served via 5 regional endpoints.

### Fields

All WFS properties are stored as JSONB in the bronze layer. Key fields per category:

**IC** (21 fields): `CLASSIFICACAO`, `DESIGNACAO`, `ESTADO`, `MUNICIPIOS`, `FREGUESIAS`, `SERVIDAO`, `SERV_LEI`, `AREA_HA`, `TUTELA`, ...

**RAN** (7 fields): `CONCELHO`, `SERVIDAO`, `DINAMICA`, `RIGOR`, `AUTOR`, `DATA`, `ID`

**DPH** (18 fields): `DESIGNACAO`, `MUNICIPIOS`, `SERVIDAO`, `SERV_LEI`, `AREA_HA`, `ESTADO`, `TUTELA`, ...

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI -> **srup_ingestion** -> **Trigger DAG w/ config**:

```json
{}
```

To process specific categories only:

```json
{"categories": ["ic", "ran"]}
```

### 2. What happens

```
resolve_categories              determine which to process (all or filtered)
  |
check_wfs_availability.expand()  parallel GetCapabilities per endpoint
  |
fetch_srup_features.expand()     parallel WFS GetFeature per category
  |  (normalize field names, combine feature types)
  |
save_to_minio.expand()           parallel uploads
  |
cleanup_temp -> log_summary -> trigger_bronze
```

### 3. Where it lands

```
s3://raw/srup/{category}/{YYYYMMDD}/{category}.geojson
```

Example: `s3://raw/srup/ic/20260319/ic.geojson`

### 4. Bronze load

After ingestion completes, trigger **`srup_bronze_load`** from the Airflow UI (no config needed). Also triggered automatically by the ingestion DAG.

---

## DAGs

### `srup_ingestion` — WFS -> MinIO

```
resolve_categories -> check_wfs.expand() -> fetch_features.expand() -> save_to_minio.expand() -> cleanup -> log_summary
```

| Setting | Value |
|---------|-------|
| Schedule | None (manual trigger) |
| Max active tasks | 2 (parallel category processing) |
| Retries | 2 (5-minute delay) |
| Tags | `srup`, `constraints`, `ingestion`, `gis`, `minio` |

### `srup_bronze_load` — MinIO -> PostGIS -> dbt

```
fetch_from_minio -> create_tables -> load_categories -> validate_counts -> trigger_dbt
```

| Setting | Value |
|---------|-------|
| Schedule | None (triggered by ingestion or manual) |
| Idempotency | TRUNCATE + INSERT per table |
| dbt trigger | `TriggerDagRunOperator` -> `dbt_srup_build` |
| Downstream models | `stg_srup_ic`, `stg_srup_ran`, `stg_srup_dph` |
| Tags | `srup`, `bronze`, `postgis`, `constraints` |

---

## Bronze schema

### Per-category tables — shared schema with JSONB properties

Each table (`raw_srup_ic`, `raw_srup_ran`, `raw_srup_dph`) has the same structure:

| Column | Type | Description |
|--------|------|-------------|
| `feature_id` | INTEGER | Feature ID from WFS |
| `category` | VARCHAR(10) | SRUP category key |
| `feature_type` | TEXT | WFS feature type identifier |
| `properties` | JSONB | All WFS properties as JSON |
| `geom` | GEOMETRY(GEOMETRY, 3763) | Boundary in PT-TM06 |
| `_source_url` | TEXT | MinIO object path |
| `_load_timestamp` | TIMESTAMPTZ | Ingestion timestamp |

### Indexes

- GIST on `geom`
- GIN on `properties`

### Key relationships

- `properties->>'MUNICIPIOS'` text-matches to CAOP municipality names
- Spatial join to listings via `ST_Intersects(listing.geom, constraint.geom)`
- Spatial join to cadastro parcels via `ST_Intersects(parcel.geom, constraint.geom)`

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| No REN data | REN requires BBOX filtering per municipality (full fetch times out) | Phase 2 — add BBOX support |
| DPH very small | Only 7 features nationally — may be incomplete | Verify against DGT portal |
| JSONB properties | Field extraction requires `properties->>'FIELD'` in dbt | By design — avoids schema coupling |
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
pipelines/gis/srup/
├── __init__.py                    # Package marker
├── srup_config.py                 # WFS endpoints, field normalization
├── srup_ingestion_dag.py          # DAG: WFS -> MinIO
├── srup_bronze_dag.py             # DAG: MinIO -> PostGIS bronze tables
├── verify_srup_endpoints.py       # Endpoint verification script
└── README.md                      # This file
```

### Adding REN (Phase 2)

1. Add `SRUPEndpointConfig` entries for REN regional endpoints with `bbox_srid=4326`
2. Add municipality BBOX coordinates to config
3. Update `get_feature_url()` to accept BBOX parameter
4. Add `raw_srup_ren` to `BRONZE_TABLES`
5. Create `stg_srup_ren.sql` staging model
