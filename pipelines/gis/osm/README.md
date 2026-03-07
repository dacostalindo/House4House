# OSM Portugal — POIs, Transport & Road Network (Geofabrik)

Single GeoPackage covering three project sources: **POIs** (walkability), **Transport** (accessibility), and **Road Network** (drive-time routing). Includes self-hosted OSRM routing engine and Nominatim geocoder.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | Geofabrik GmbH (OSM extract) |
| Page | https://download.geofabrik.de/europe/portugal.html |
| Auth | None required (public download) |
| Format | GeoPackage (`.gpkg`) inside a `.zip` archive |
| CRS | WGS 84 — **EPSG:4326** (geographic, not projected) |
| Coverage | All of Portugal (continental + islands) |
| Refresh | Daily on Geofabrik; monthly ingestion is sufficient |
| File size | ~800 MB compressed, ~1.5 GB extracted |

---

## What it contains

18 layers, ~4.5M features:

### POIs (for walkability & amenity scoring)

| Layer | Geometry | Features | Key fclass values |
|-------|----------|----------|-------------------|
| `gis_osm_pois_free` | Point | 174K | restaurant, cafe, supermarket, pharmacy, bank, school, hospital, ... |
| `gis_osm_pois_a_free` | Polygon | 130K | park, school, swimming_pool, sports_centre, graveyard, ... |
| `gis_osm_pofw_free` | Point | 2K | places of worship |
| `gis_osm_pofw_a_free` | Polygon | 11K | places of worship (areas) |

### Transport (for accessibility scoring)

| Layer | Geometry | Features | Key fclass values |
|-------|----------|----------|-------------------|
| `gis_osm_transport_free` | Point | 49K | bus_stop (47K), railway_station (321), tram_stop (247), ... |
| `gis_osm_transport_a_free` | Polygon | 1K | bus_station, railway_station, airport (areas) |
| `gis_osm_railways_free` | Line | 11K | rail (8.6K), light_rail (1.1K), subway (341), tram (229) |

### Road Network (for OSRM routing)

| Layer | Geometry | Features | Key fclass values |
|-------|----------|----------|-------------------|
| `gis_osm_roads_free` | Line | 1.55M | residential (406K), track (344K), tertiary (76K), primary (49K), motorway (11K), ... |
| `gis_osm_traffic_free` | Point | 172K | crossing, traffic_signals, fuel, parking |
| `gis_osm_traffic_a_free` | Polygon | 60K | parking (56K), fuel, marina |

### Context layers

| Layer | Geometry | Features | Description |
|-------|----------|----------|-------------|
| `gis_osm_buildings_a_free` | Polygon | 2.1M | Building footprints |
| `gis_osm_landuse_a_free` | Polygon | 492K | Residential, commercial, industrial zones |
| `gis_osm_natural_free` | Point | 227K | Natural features |
| `gis_osm_natural_a_free` | Polygon | 2K | Natural areas |
| `gis_osm_places_free` | Point | 31K | Cities, towns, villages |
| `gis_osm_places_a_free` | Polygon | 1K | Place boundaries |
| `gis_osm_water_a_free` | Polygon | 56K | Water bodies |
| `gis_osm_waterways_free` | Line | 119K | Rivers, streams |

### Common schema

All layers share these fields:

| Field | Type | Description |
|-------|------|-------------|
| `osm_id` | string | OpenStreetMap node/way ID |
| `code` | integer | Geofabrik numeric code |
| `fclass` | string | Feature classification (e.g. `restaurant`, `bus_stop`, `motorway`) |
| `name` | string | Feature name (may be null) |

Additional fields per layer type:
- **roads**: `ref`, `oneway`, `maxspeed`, `layer`, `bridge`, `tunnel`
- **railways**: `layer`, `bridge`, `tunnel`
- **places**: `population`
- **buildings**: `type`
- **waterways**: `width`

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI → **s09_osm_ingestion** → **Trigger DAG w/ config**:

```json
{"version": "2026-03"}
```

### 2. What happens

```
HEAD https://download.geofabrik.de/europe/portugal-latest-free.gpkg.zip
  ↓
stream download → /tmp/          4 MB chunks, SHA-256 on the fly
  ↓ (zip extracted automatically)
pyogrio.list_layers()            log all 18 layers
pyogrio.read_info() × 18        log fields, CRS, geometry type, feature count
  ↓
minio.fput_object()              upload raw .gpkg (~1.5 GB)
  ↓
cleanup /tmp/
log_run_metadata
```

### 3. Where it lands

```
s3://raw/osm/2026-03/portugal.gpkg
```

### 4. Bronze load

After ingestion completes, trigger **`s09_osm_bronze_load`** from the Airflow UI (no config needed). It finds the latest GPKG in MinIO automatically.

---

## DAGs

### `s09_osm_ingestion` — Geofabrik GPKG → MinIO

```
check_source → download_file → validate_gis_file → upload_to_minio → cleanup_temp → log_run_metadata
```

| Setting | Value |
|---------|-------|
| Schedule | None (manual trigger) |
| Tags | `ingestion`, `gis`, `osm` |

### `s09_osm_bronze_load` — MinIO → PostGIS → dbt

```
find_latest_gpkg → load_layer.expand(18) → validate_counts → trigger_dbt_pipeline
```

| Setting | Value |
|---------|-------|
| Schedule | None (manual trigger) |
| Idempotency | TRUNCATE + INSERT |
| dbt trigger | `TriggerDagRunOperator` → `dbt_scoped_build` with selector `stg_osm_pois+ stg_osm_transport+` |
| Downstream models | `stg_osm_pois` → `osm_pois` (Sprint 5), `stg_osm_transport` → `transport_stops` (Sprint 5) |
| Tags | `osm`, `bronze`, `postgis` |

### `osm_pbf_ingestion` — Geofabrik PBF → MinIO

```
check_source → download_pbf → upload_to_minio → cleanup_temp
```

| Setting | Value |
|---------|-------|
| Schedule | None (manual trigger) |
| Tags | `ingestion`, `osm`, `pbf` |

### `osrm_build` — MinIO PBF → OSRM routing data

```
download_pbf_from_minio → extract.expand(3 profiles) → contract.expand(3 profiles)
```

| Setting | Value |
|---------|-------|
| Schedule | None (manual trigger) |
| Tags | `osrm`, `routing` |

---

## Bronze schema

All tables in `bronze_location` schema. CRS is EPSG:4326.

### POIs

| Table | Source layer | Rows | Geometry | Fields |
|-------|-------------|------|----------|--------|
| `raw_osm_pois` | gis_osm_pois_free | 174,233 | POINT | osm_id, code, fclass, name |
| `raw_osm_pois_a` | gis_osm_pois_a_free | 129,605 | MULTIPOLYGON | osm_id, code, fclass, name |
| `raw_osm_pofw` | gis_osm_pofw_free | 1,669 | POINT | osm_id, code, fclass, name |
| `raw_osm_pofw_a` | gis_osm_pofw_a_free | 11,412 | MULTIPOLYGON | osm_id, code, fclass, name |

### Transport

| Table | Source layer | Rows | Geometry | Fields |
|-------|-------------|------|----------|--------|
| `raw_osm_transport` | gis_osm_transport_free | 48,917 | POINT | osm_id, code, fclass, name |
| `raw_osm_transport_a` | gis_osm_transport_a_free | 1,144 | MULTIPOLYGON | osm_id, code, fclass, name |
| `raw_osm_railways` | gis_osm_railways_free | 10,567 | LINESTRING | osm_id, code, fclass, name, layer, bridge, tunnel |

### Roads & Traffic

| Table | Source layer | Rows | Geometry | Fields |
|-------|-------------|------|----------|--------|
| `raw_osm_roads` | gis_osm_roads_free | 1,548,602 | LINESTRING | osm_id, code, fclass, name, ref, oneway, maxspeed, layer, bridge, tunnel |
| `raw_osm_traffic` | gis_osm_traffic_free | 171,817 | POINT | osm_id, code, fclass, name |
| `raw_osm_traffic_a` | gis_osm_traffic_a_free | 59,551 | MULTIPOLYGON | osm_id, code, fclass, name |

### Context layers

| Table | Source layer | Rows | Geometry | Extra fields |
|-------|-------------|------|----------|--------------|
| `raw_osm_buildings_a` | gis_osm_buildings_a_free | 2,097,898 | MULTIPOLYGON | + type |
| `raw_osm_landuse_a` | gis_osm_landuse_a_free | 492,471 | MULTIPOLYGON | — |
| `raw_osm_natural` | gis_osm_natural_free | 226,615 | POINT | — |
| `raw_osm_natural_a` | gis_osm_natural_a_free | 1,619 | MULTIPOLYGON | — |
| `raw_osm_places` | gis_osm_places_free | 31,471 | POINT | + population |
| `raw_osm_places_a` | gis_osm_places_a_free | 694 | MULTIPOLYGON | + population |
| `raw_osm_water_a` | gis_osm_water_a_free | 56,193 | MULTIPOLYGON | — |
| `raw_osm_waterways` | gis_osm_waterways_free | 119,218 | LINESTRING | + width |

**Total: 5,183,696 features across 18 tables.**

All tables include `geom` (GEOMETRY, 4326) and `_load_timestamp` (TIMESTAMPTZ).

### Key field: `fclass`

The `fclass` column is the primary classification — e.g. `restaurant`, `bus_stop`, `motorway`, `residential`. This is the main filter for building walkability scores, transport accessibility, and neighbourhood analytics in the silver layer.

---

## OSRM routing engine

Three OSRM instances provide HTTP routing APIs for car, walking, and cycling profiles. Built from the same Geofabrik Portugal data using Contraction Hierarchies (CH).

### Architecture

```
Geofabrik PBF (~700 MB)
  ↓  osm_pbf_ingestion DAG (download to MinIO)
s3://raw/osm-pbf/{version}/portugal-latest.osm.pbf
  ↓  osrm_build DAG (extract + contract × 3 profiles)
osrm_data volume:
  /data/car/portugal-latest.osrm*
  /data/walking/portugal-latest.osrm*
  /data/cycling/portugal-latest.osrm*
  ↓  osrm-routed (3 Docker services)
HTTP API on ports 5050 (car), 5051 (walking), 5052 (cycling)
```

### Services

| Service | Profile | Port | API base |
|---------|---------|------|----------|
| `osrm-car` | car.lua | 5050 | `http://localhost:5050/route/v1/driving/` |
| `osrm-walking` | foot.lua | 5051 | `http://localhost:5051/route/v1/walking/` |
| `osrm-cycling` | bicycle.lua | 5052 | `http://localhost:5052/route/v1/cycling/` |

### How to build OSRM data

```bash
# 1. Start all services
docker compose up -d

# 2. Download PBF (Airflow UI → osm_pbf_ingestion → Trigger with {"version": "2026-Q1"})
# 3. Build routing data (Airflow UI → osrm_build → Trigger DAG)
# 4. Restart OSRM services to load new data
docker compose restart osrm-car osrm-walking osrm-cycling

# 5. Test
curl "http://localhost:5050/route/v1/driving/-9.1393,38.7223;-8.6291,41.1579"
```

---

## Nominatim geocoder

Self-hosted OSM-based geocoder for forward and reverse geocoding of Portuguese addresses.

| Property | Value |
|----------|-------|
| Image | `mediagis/nominatim:4.4` |
| Port | 8088 (host) → 8080 (container) |
| Data | Downloads Portugal PBF from Geofabrik on first startup |
| Import | One-time (~30-45 min), data persisted in `nominatim_data` volume |
| Internal URL | `http://nominatim:8080` (for Airflow DAGs) |

### API examples

```bash
# Forward geocoding
curl "http://localhost:8088/search?q=Rua+Augusta+100+Lisboa&format=json"

# Reverse geocoding
curl "http://localhost:8088/reverse?lat=38.7223&lon=-9.1393&format=json"

# Structured search
curl "http://localhost:8088/search?street=Avenida+dos+Aliados&city=Porto&format=json"
```

### First startup

The Nominatim container automatically downloads the Portugal PBF and imports it on first start. This takes ~30-45 minutes. Subsequent restarts are fast (data is persisted in the `nominatim_data` volume).

### Updating

To refresh the geocoding data, remove the volume and restart:

```bash
docker compose down nominatim
docker volume rm house4house_nominatim_data
docker compose up -d nominatim
# Wait ~30-45 min for re-import
```

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| CRS mismatch | EPSG:4326 vs EPSG:3763 for CAOP/BGRI | `ST_Transform` in silver layer spatial joins |
| Large file size | ~1.5 GB extracted GPKG | Stream download with chunking; sufficient disk space needed |
| OSRM rebuild required after update | New PBF needs extract + contract (~1h per profile) | Run `osrm_build` DAG then restart containers |

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
pipelines/gis/osm/
├── __init__.py                    # Package marker
├── osm_config.py                  # Layer list, download URL, validation thresholds
├── osm_ingestion_dag.py           # DAG: Geofabrik GPKG → MinIO
├── osm_bronze_dag.py              # DAG: MinIO GPKG → PostGIS bronze tables
├── osm_pbf_ingestion_dag.py       # DAG: Geofabrik PBF → MinIO (for OSRM)
├── osrm_build_dag.py              # DAG: PBF → OSRM routing data (3 profiles)
└── README.md                      # This file
```

### Updating

Trigger a new ingestion run with the current month as version:

```json
{"version": "2026-04"}
```

Then re-trigger **`s09_osm_bronze_load`** to refresh the bronze tables. Each version is stored separately in MinIO — no overwrites.

OSRM update frequency: quarterly. Re-trigger `osm_pbf_ingestion` → `osrm_build` → restart OSRM containers.
