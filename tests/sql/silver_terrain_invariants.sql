-- silver_geo.terrain_slope_raster invariants (sprint-09 WS4 PR A).
-- Covers silver-dq-baseline Rules 1 (spatial SRID), 2 (surrogate unique),
-- 3 (row-count parity vs bronze), plus a raster-specific band invariant.
--
-- Tests:
--   #35 surrogate uniqueness (rid + filename)
--   #36 silver row count == bronze raster row count (parity)
--   #37 ST_SRID(footprint_pt)=3763 AND ST_SRID(footprint)=4326 on every row
--   #38 every raster is single-band Float32 (gdaldem slope output shape)
--
-- All tests are empty-bronze-safe: COUNT(*) WHERE NOT condition = 0 on empty
-- silver returns 0, trivially passing in CI Tier-1.

BEGIN;

SELECT plan(4);

-- #35 — surrogate key uniqueness (Rule 2)
SELECT is(
    (SELECT (COUNT(*) - COUNT(DISTINCT rid))::int
     FROM silver_geo.terrain_slope_raster),
    0,
    'Test #35 — every silver row has unique rid'
);

-- #36 — bronze→silver row-count parity (Rule 3)
SELECT is(
    (SELECT COUNT(*)::int FROM silver_geo.terrain_slope_raster),
    (SELECT COUNT(*)::int FROM bronze_terrain.raster_lidar_slope_2m),
    'Test #36 — silver row count equals bronze raster row count'
);

-- #37 — SRID invariants on the footprint columns (Rule 1)
SELECT is(
    (SELECT COUNT(*)::int FROM silver_geo.terrain_slope_raster
     WHERE ST_SRID(footprint_pt) <> 3763 OR ST_SRID(footprint) <> 4326),
    0,
    'Test #37 — every footprint has SRID(footprint_pt)=3763 AND SRID(footprint)=4326'
);

-- #38 — raster band sanity (gdaldem slope produces single-band Float32)
SELECT is(
    (SELECT COUNT(*)::int FROM silver_geo.terrain_slope_raster
     WHERE NOT (ST_NumBands(rast) = 1 AND ST_BandPixelType(rast, 1) = '32BF')),
    0,
    'Test #38 — every raster is single-band Float32 (gdaldem slope output)'
);

SELECT * FROM finish();

ROLLBACK;
