---
title: Dual-CRS storage on every spatial table (geom 4326 + geom_pt 3763)
type: decision
last_verified: 2026-05-10
tags: [spatial, crs, postgis, decision]
confidence: high
---

## For future Claude

This is a decision record about storing every spatial table's geometry in BOTH WGS84 (EPSG:4326) and PT-TM06/ETRS89 (EPSG:3763), rejecting single-CRS storage. The decision is small individually but cascades into 14+ source pages, [[spatial-strategy]] concept, and every silver-layer model. Read this when adding a new spatial source, considering a CRS migration, or asked "why two columns?"

## Decision

**Every spatial table in House4House stores geometry in two columns:**

- `geom GEOMETRY(<TYPE>, 4326)` — WGS84, used for display, web maps, point-in-polygon predicates
- `geom_pt GEOMETRY(<TYPE>, 3763)` — PT-TM06/ETRS89, used for distance and area calculations in metres

The `geom_pt` column is materialized at silver-layer creation via `ST_Transform(geom, 3763)`. Both columns get GIST indexes (per [[spatial-strategy]]).

## Why

1. **WGS84 is the universal display + ingest format.** Every external source returns geometries in either 4326 or a regional projection that we transform to 4326 at ingest. Kepler.gl + Leaflet + Streamlit + Metabase + every web map renderer expects 4326. Forcing the warehouse storage to one CRS for display means storing 4326.
2. **PT-TM06 is the only meaningful distance-and-area CRS for PT.** `ST_DWithin(geom, other_geom, 500)` in 4326 measures degrees (varies by latitude — 1° latitude is ~111 km, but 1° longitude in PT is ~85 km, and the variance compounds across queries). In 3763, the threshold is metres. The semantic difference is the difference between "find listings within 500m of metro" working correctly and producing wrong results.
3. **Materializing both is cheap.** ~12 bytes per geometry (point) × ~20M total spatial rows = ~240 MB total. Storage cost: trivial. Index storage: ~2× a single CRS. Query CPU savings: every distance query avoids per-row reprojection, which is dominant cost for large `ST_DWithin` joins.
4. **Single-CRS-with-inline-reprojection is a footgun.** `ST_DWithin(geom, ST_Transform(other.geom, 3763), 500)` works but defeats the GIST index on `other.geom`'s CRS and forces a per-row reprojection. We've seen [[osm]] queries that took 30+ minutes degrade to seconds when the OSM data is materialized to `geom_pt` at staging.

## Options considered

1. **Dual-CRS storage with materialization** (chosen) — see Decision.
2. **Single-CRS storage in 4326 + inline reprojection on distance queries** — rejected because (a) inline `ST_Transform` on a join's right-hand side breaks the GIST index plan; (b) per-query CPU compounds across many DAGs.
3. **Single-CRS storage in 3763** — rejected because every external display tool (Kepler, Streamlit, Metabase tiles) expects 4326; we'd add reprojection at the application layer instead, defeating the purpose.
4. **Single-CRS storage in 4326 + view-based `geom_pt` projection** — rejected because views don't materialize the projection — every query against the view re-reprojects. Same footgun as option 2.
5. **Dual-CRS storage but compute geom_pt on-demand via stored procedure** — rejected for same reason; on-demand computation defeats the index.

## Consequences

- Every silver-layer spatial model `ADD COLUMN geom_pt` + `UPDATE ... SET geom_pt = ST_Transform(geom, 3763)` at materialization (in dbt models per [[medallion-layering]]).
- Every spatial source page documents the source's native CRS so dbt staging knows whether a transform is needed at silver creation.
- Storage cost: ~240 MB across the warehouse (negligible relative to total 28-30 GB).
- Index cost: ~2× a single-CRS solution (still small).
- A future migration to a different projected CRS (e.g., new PT national grid release) is a swap of `3763` for the new EPSG everywhere + a re-materialization sweep. Documented as a single-line `ST_Transform` change per silver model.
- Cross-source spatial joins always join on `geom_pt` in 3763 (per [[spatial-strategy]] query patterns) — consistent behavior across all 14 GIS sources.
- `ST_Within` / `ST_Intersects` boolean predicates are CRS-invariant — they work correctly on either column as long as both inputs share the CRS. Convention: use `geom` for boolean, `geom_pt` for distance/area.

## Status

`accepted` — locked 2026-05-10 as part of PR 7. Phase 1+ silver-layer models already follow this convention; this ADR formalizes it. High confidence; the cost analysis is well-bounded and the alternative-considered cases are concrete failure modes we'd actually hit.

## See also

- [[spatial-strategy]] — the concept page operationalizing this decision
- [[2026-05-10-postgis-as-warehouse]] — the warehouse choice this depends on
- [[medallion-layering]] — silver-layer is where `geom_pt` materializes
- [[ingest-flows]] — Flow C ingests into bronze; Flow D + Flow E + silver-layer transforms add `geom_pt`
- All 14 GIS source pages — each documents its native CRS
- README §9.1 — the canonical source for this content
