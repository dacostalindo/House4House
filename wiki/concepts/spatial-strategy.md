---
title: Spatial strategy — CRS, indexing, query patterns
type: concept
last_verified: 2026-05-10
tags: [spatial, postgis, crs, indexing, h3, concept]
---

## For future Claude

This is a concept page about the project's spatial strategy: dual-CRS storage convention (geom in 4326 + geom_pt in 3763 on every spatial table), spatial indexing patterns (GIST + H3), common query templates (proximity, POI density, zoning lookup), and the location-score computation logic. Read this when adding a new spatial source, writing a new spatial query, debugging a slow spatial join, or scoping spatial-feature engineering. Companion to [[medallion-layering]] (where spatial data lives in the warehouse) and [[ingest-flows]] (Flow C + Flow E ingest spatial data).

## What it is

The set of conventions that make PostGIS performant + maintainable across 14+ spatial sources, three use-cases, and ~20M total spatial features:

1. **Dual-CRS storage** — every spatial table stores geometry in BOTH WGS84 (EPSG:4326) for display + joins AND PT-TM06 (EPSG:3763) for distance + area computations.
2. **GIST indexes everywhere** — every geometry column gets a `GIST` index. Non-negotiable.
3. **H3 hex index for fast aggregation** — listing-grain aggregations use H3 resolution 9 hexagons (~0.1 km²).
4. **Composite location-score formula** — UC-1 location-score follows a documented weighting (transport 25% + walkability 25% + education 20% + healthcare 15% + shopping access 15%).

Locked via [[2026-05-10-dual-crs-storage]].

## Why

**Why dual-CRS, not single-CRS:**

- WGS84 (4326) is the universal display + join CRS. Web map tiles, GeoJSON, all source ingests, [[osm]] native CRS — all 4326. Storing in 4326 means Kepler.gl + Streamlit + Metabase + every external map renderer "just works."
- PT-TM06 (3763) is projected (metres). Distance + area calculations require a projected CRS to be meaningful. `ST_DWithin(geom, other_geom, 500)` in 4326 measures degrees (varies by latitude); in 3763 measures metres consistently across PT.
- Storing both is cheap (~12 bytes/row × ~20M rows = ~240 MB total). Storing one + reprojecting on every query is expensive (per-query CPU + index miss).

**Why GIST not BRIN or SP-GIST:**

- GIST is the PostGIS default for 2D geometry; mature, well-tuned, broad operator support (`&&`, `~`, `~=`, `@>`, `<@`).
- BRIN is excellent for spatially-clustered tables (like raster tiles) but loses on point-data clustered loosely.
- SP-GIST has wins in some use cases but the marginal benefit doesn't justify the operator-coverage gap.

**Why H3 resolution 9:**

- ~0.1 km² hexagons (~316m edge length) match the listing-density grain in urban PT (typical Lisboa concelho ~25-100 listings/km², so ~3-10 listings per H3 hex).
- Resolution 9 is the sweet spot for "listing density per neighbourhood" aggregations: coarser (resolution 7) loses detail; finer (resolution 11) explodes hex count.
- H3 is hierarchical — resolution 9 hexes nest cleanly within resolution 8 / 7 for multi-scale views.

**Why this composite location-score formula:**

- Transport (25%) — proximity to fast transit is the dominant accessibility signal in PT urban markets.
- Walkability (25%) — POI density within 500m walking distance; correlates with day-to-day quality-of-life.
- Education (20%) — school quality is a primary buyer driver; weight reflects this.
- Healthcare (15%) — secondary but persistent driver.
- Shopping access (15%) — supermarket/retail access; lower weight because correlated with walkability.
- Sums to 100. Calibrated against held-out price observations during Sprint 5 hedonic work.

## How

### Coordinate Reference Systems

Per README §9.1:

| CRS | EPSG | Usage |
|---|---|---|
| WGS84 | 4326 | Storage default, display, web maps, listing geocoding inputs |
| PT-TM06/ETRS89 | 3763 | Distance calculations in metres, area computations, accurate spatial joins |

Convention: every spatial table has both columns:

```sql
geom    GEOMETRY(POINT, 4326)    -- For display and joins
geom_pt GEOMETRY(POINT, 3763)    -- For ST_DWithin distance queries in metres
```

Maintained via dbt staging: `geom_pt = ST_Transform(geom, 3763)` materialized at silver-layer creation time. Source pages (e.g., [[apa]], [[caop]]) document each source's native CRS — server-side reprojection (where supported) lands data in 3763 directly.

### Spatial Indexing

Standard GIST index on every geometry column:

```sql
CREATE INDEX idx_<table>_geom    USING GIST (geom);
CREATE INDEX idx_<table>_geom_pt USING GIST (geom_pt);
```

H3 hex index for fast aggregation (resolution 9 ≈ 0.1 km²):

```sql
ALTER TABLE silver_properties.unified_listings
    ADD COLUMN h3_index_9 VARCHAR(15);
CREATE INDEX idx_listings_h3 ON silver_properties.unified_listings (h3_index_9);
```

H3 indexes are computed at silver-layer materialization via the `h3_lat_lng_to_cell()` PostGIS function (or equivalent Python pre-compute, depending on `pg_extension` availability).

### Common spatial query patterns

```sql
-- Find all listings within 500m of a metro station
SELECT l.*
FROM silver_properties.unified_listings l
JOIN silver_location.transport_stops t
    ON ST_DWithin(l.geom_pt, t.geom_pt, 500)
WHERE t.stop_type = 'metro' AND l.is_active = TRUE;

-- Count POIs within walking distance (Flow E spatial composition)
SELECT l.listing_key,
       COUNT(*) FILTER (WHERE p.category = 'food') AS food_500m,
       COUNT(*) FILTER (WHERE p.category = 'shopping') AS shopping_500m
FROM silver_properties.unified_listings l
JOIN bronze_location.raw_osm_pois p
    ON ST_DWithin(l.geom_pt, ST_Transform(p.geom, 3763), 500)
WHERE l.is_active = TRUE
GROUP BY l.listing_key;

-- Property zoning lookup (point-in-polygon)
SELECT l.*, z.zone_category, z.max_floors
FROM silver_properties.unified_listings l
JOIN silver_geo.zoning z
    ON ST_Within(l.geom, z.geom)    -- 4326 OK for boolean point-in-polygon
WHERE l.listing_key = 12345;
```

**Pattern notes:**
- `ST_DWithin` always uses `geom_pt` (3763) when the threshold is in metres.
- `ST_Within` / `ST_Intersects` boolean predicates can use 4326 — they're CRS-invariant for "is point inside polygon" if both inputs share the CRS.
- `ST_Transform` inline (e.g., `ST_Transform(p.geom, 3763)` in the OSM POI example) is the escape hatch when a source's native CRS hasn't been pre-transformed in staging. [[osm]] is the main offender (native EPSG:4326 unlike most regulatory PT sources at 3763).

### Location-score computation

Per README §9.4 — UC-1 location-score formula:

```
Transport score (0-100):
  40 pts: Metro/train proximity
    40 if <500m, 30 if 500-1000m, 20 if 1-2km, 0 if >2km
  30 pts: Bus coverage (scaled by stops within 500m)
  20 pts: Route diversity (scaled by unique routes within 500m)
  10 pts: Interchange bonus (within 500m of interchange)

Walkability score (0-100):
  Category-weighted POI density within 500m:
    Supermarkets    (wt 20)
    Restaurants/Cafés (wt 15)
    Pharmacies      (wt 15)
    Parks           (wt 15)
    Banks           (wt 10)
    Gyms            (wt 10)
    Other retail    (wt 10)
    Entertainment   (wt 5)

Overall location score:
  transport     * 0.25 +
  walkability   * 0.25 +
  education     * 0.20 +
  healthcare    * 0.15 +
  shopping_access * 0.15
```

Education + healthcare scores deferred to Sprint 7 (per [[milestones]] MVP hedonic feature coverage); the formula handles NULL contributions via mean imputation at the model layer.

## See also

- [[medallion-layering]] — bronze/silver/gold layout where spatial data flows
- [[ingest-flows]] — Flow C (GIS bulk) + Flow E (spatial composition for UC-3)
- [[2026-05-10-dual-crs-storage]] — the locked decision behind this strategy
- [[2026-05-10-postgis-as-warehouse]] — the warehouse that powers all this
- All 14 GIS source pages: [[apa]], [[bgri]], [[bupi]], [[cadastro]], [[caop]], [[cos]], [[crus]], [[crus-ogc]], [[lidar]], [[lneg]], [[osm]], [[srup]], [[srup-ogc]], [[aveiro-pmot]]
- [[UC-1]], [[UC-3]] — use cases that depend most heavily on this strategy
- [[infra]] — PostgreSQL configuration (`shared_buffers=8GB` etc.) that makes spatial queries performant
- README §9 — the canonical source for this content
