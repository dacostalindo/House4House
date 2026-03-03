# S09/S10/S11 — OpenStreetMap Portugal (Geofabrik)

Single GeoPackage covering three project sources: **POIs** (walkability), **Transport** (accessibility), and **Road Network** (drive-time routing).

---

## Source

| Property | Value |
|----------|-------|
| Publisher | Geofabrik GmbH (OSM extract) |
| Page | https://download.geofabrik.de/europe/portugal.html |
| Format | GeoPackage (`.gpkg`) inside a `.zip` archive |
| CRS | WGS 84 — **EPSG:4326** (geographic, not projected) |
| Coverage | All of Portugal (continental + islands) |
| Refresh | Daily on Geofabrik; monthly ingestion is sufficient |
| File size | ~800 MB compressed, ~1.5 GB extracted |

---

## What it contains

18 layers, ~4.5M features:

### S09 — POIs (for walkability & amenity scoring)

| Layer | Geometry | Features | Key fclass values |
|-------|----------|----------|-------------------|
| `gis_osm_pois_free` | Point | 174K | restaurant, cafe, supermarket, pharmacy, bank, school, hospital, ... |
| `gis_osm_pois_a_free` | Polygon | 130K | park, school, swimming_pool, sports_centre, graveyard, ... |
| `gis_osm_pofw_free` | Point | 2K | places of worship |
| `gis_osm_pofw_a_free` | Polygon | 11K | places of worship (areas) |

### S10 — Transport (for accessibility scoring)

| Layer | Geometry | Features | Key fclass values |
|-------|----------|----------|-------------------|
| `gis_osm_transport_free` | Point | 49K | bus_stop (47K), railway_station (321), tram_stop (247), ... |
| `gis_osm_transport_a_free` | Polygon | 1K | bus_station, railway_station, airport (areas) |
| `gis_osm_railways_free` | Line | 11K | rail (8.6K), light_rail (1.1K), subway (341), tram (229) |

### S11 — Road Network (for OSRM routing)

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

---

## CRS note

This file uses **WGS 84 (EPSG:4326)**, not PT-TM06 (EPSG:3763) like CAOP and BGRI. Spatial joins in the silver layer will need `ST_Transform` to align coordinate systems.

---

## Bronze Schema

After ingestion to MinIO, DAG **`s09_osm_bronze_load`** loads all 18 GPKG layers into PostGIS.
Full-refresh (TRUNCATE + INSERT), idempotent, no schedule — trigger manually.
All tables in `bronze_location` schema. CRS is EPSG:4326.

### S09 — POIs

| Table | Source layer | Rows | Geometry | Fields |
|-------|-------------|------|----------|--------|
| `raw_osm_pois` | gis_osm_pois_free | 174,233 | POINT | osm_id, code, fclass, name |
| `raw_osm_pois_a` | gis_osm_pois_a_free | 129,605 | MULTIPOLYGON | osm_id, code, fclass, name |
| `raw_osm_pofw` | gis_osm_pofw_free | 1,669 | POINT | osm_id, code, fclass, name |
| `raw_osm_pofw_a` | gis_osm_pofw_a_free | 11,412 | MULTIPOLYGON | osm_id, code, fclass, name |

### S10 — Transport

| Table | Source layer | Rows | Geometry | Fields |
|-------|-------------|------|----------|--------|
| `raw_osm_transport` | gis_osm_transport_free | 48,917 | POINT | osm_id, code, fclass, name |
| `raw_osm_transport_a` | gis_osm_transport_a_free | 1,144 | MULTIPOLYGON | osm_id, code, fclass, name |
| `raw_osm_railways` | gis_osm_railways_free | 10,567 | LINESTRING | osm_id, code, fclass, name, layer, bridge, tunnel |

### S11 — Roads & Traffic

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

## After ingestion

Trigger **`s09_osm_bronze_load`** from the Airflow UI (no config needed).
It finds the latest GPKG in MinIO automatically.

---

## Updating

Trigger a new ingestion run with the current month as version:

```json
{"version": "2026-04"}
```

Then re-trigger **`s09_osm_bronze_load`** to refresh the bronze tables.
Each version is stored separately in MinIO — no overwrites.
