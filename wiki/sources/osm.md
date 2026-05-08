---
title: OpenStreetMap Portugal (Geofabrik)
type: source
last_verified: 2026-05-08
tags: [gis, community, geofabrik, geopackage, multi-layer]
---

## For future Claude

This is a source page about the OpenStreetMap PT extract via Geofabrik. It documents the 18-layer GeoPackage ingest (~4.5M features), the WGS84 (EPSG:4326) CRS quirk vs. our PT-TM06 stack, and the role as the canonical "everyday geography" layer (POIs, roads, buildings) complementing the regulatory-GIS sources. Read this page before editing [pipelines/gis/osm/osm_config.py](../../pipelines/gis/osm/osm_config.py).

## Source

- **Official name**: OpenStreetMap Portugal (Geofabrik daily extract)
- **Owner**: community (OSM contributors; Geofabrik repackages as country GeoPackages)
- **Protocol**: GeoPackage bulk download (.zip → .gpkg)
- **Base endpoint**: `https://download.geofabrik.de/europe/portugal-latest-free.gpkg.zip` — STABLE permalink, always points to the latest daily extract
- **License**: ODbL (Open Database License)
- **Schedule**: manual trigger

## Schema

Bronze tables (one per OSM theme; 18 layers grouped):

- **POIs** (4 layers, ~174k points + 130k polygons): `osm_pois` covering restaurants, supermarkets, schools, parks, hospitals
- **Transport** (3 layers): `osm_transport` (stops, stations, modes)
- **Roads/Traffic** (3 layers, 1.55M linestrings): `osm_roads` — full network with routing attributes (highway class, surface, lanes, oneway)
- **Context layers** (5+):
  - `osm_buildings` — 2.1M polygons
  - `osm_landuse` — 492k polygons (residential, commercial, industrial)
  - `osm_natural`, `osm_places`, `osm_water`

Total: ~4.5M features across 18 layers.

## Quirks

- **WGS84 (EPSG:4326)** — geographic coordinates, NOT projected. UNLIKE every other regulatory-GIS source in the stack ([[caop]], [[bgri]], [[apa]], [[srup-ogc]] etc. are all PT-TM06 / EPSG:3763). dbt staging reprojects OSM to EPSG:3763 for spatial joins.
- **Geofabrik "latest" URL** always resolves to the most recent daily extract. NOT a versioned permalink. To capture a specific date, parameterize the URL with the dated form (`portugal-YYYYMMDD-free.gpkg.zip`) — Geofabrik retains ~7 days of snapshots.
- **Validation**: file size ≥ 500 MB, feature count per layer ∈ [1, 3M].
- **POI quality varies by region**: urban areas (Lisboa, Porto) have rich POI density; rural areas thin. Listing-feature engineering ("number of supermarkets within 1km") is more reliable in cities.
- **Highway classifications**: OSM's `highway` tag (motorway / trunk / primary / secondary / tertiary / residential / service / track) maps roughly to PT regulatory road classes. The `osm_roads` layer is the routable network; combining it with [[srup-ogc]]'s `rede_viaria` (regulatory road network) gives both routing AND regulatory-status semantics.
- **Buildings layer is permissive**: includes residential, commercial, agricultural, and ancillary structures. Distinguishing residential-buildings from sheds requires joining on the `building` tag value (yes/house/apartments/residential = likely residential; barn/shed/garage = ancillary).
- **Cross-source role**: OSM is the "everyday geography" complement to the regulatory stack. Where [[caop]] gives administrative boundaries, [[bupi]]/[[cadastro]] give property parcels, [[bgri]] gives census subsections, OSM gives the POIs/roads/buildings overlay that turns those polygons into a navigable feature space.

## Companion services (built from the same OSM data)

The OSM ingest doesn't just produce wiki-source bronze tables — it also feeds two long-running query services. Both are built from the same `portugal-latest-free.gpkg.zip` extract; rebuild on each new OSM ingest:

- **OSRM routing engine** (3 profiles: car / walking / cycling on ports `5050` / `5051` / `5052`): self-hosted via Docker, built from the OSM PBF using OSRM's contraction-hierarchies preprocessor. Used by silver-layer features like "drive-time to nearest school". Profiles map to the standard OSRM `car.lua` / `foot.lua` / `bicycle.lua` configs.
- **Nominatim geocoder** (port `8088`, image `mediagis/nominatim:4.4`): self-hosted geocoding for listing addresses → coordinates and reverse-geocoding for parcel centroids → place names. First startup on a fresh PT import takes ~30-45 min; data persisted on a Docker volume so subsequent restarts are fast.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read).
