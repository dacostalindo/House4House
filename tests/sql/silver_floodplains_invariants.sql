-- silver_geo.floodplains invariants (sprint-09 WS4 quick-wins batch).
-- Covers silver-dq-baseline Rules 1 (spatial dual-CRS), 3 (row-count parity),
-- and 4 (FK denormalization). Surrogate-key Rule 2 covered by dbt YAML.
--
-- Tests:
--   #25  ST_IsValid on both geom + geom_pt
--   #25b ST_SRID matches column name (geom=4326, geom_pt=3763)
--   #26  silver row count == bronze row count where geom IS NOT NULL
--   #27  severity NOT NULL after LEFT JOIN to dim_constraint_severity (FK miss catch)

BEGIN;

SELECT plan(4);

-- #25 — ST_IsValid on both CRS columns
SELECT is(
    (SELECT COUNT(*)::int FROM silver_geo.floodplains
     WHERE NOT (ST_IsValid(geom) AND ST_IsValid(geom_pt))),
    0,
    'Test #25 — every floodplain row has valid geom AND geom_pt geometries'
);

-- #25b — ST_SRID correctness (Rule 1 enforcement at runtime, complements dbt YAML)
SELECT is(
    (SELECT COUNT(*)::int FROM silver_geo.floodplains
     WHERE ST_SRID(geom) <> 4326 OR ST_SRID(geom_pt) <> 3763),
    0,
    'Test #25b — every floodplain row has ST_SRID(geom)=4326 AND ST_SRID(geom_pt)=3763'
);

-- #26 — Bronze→silver row-count parity (silver-dq-baseline Rule 3)
SELECT is(
    (SELECT COUNT(*)::int FROM silver_geo.floodplains),
    (SELECT COUNT(*)::int FROM bronze_hydrology.raw_apa_arpsi_floodplain
     WHERE geom IS NOT NULL),
    'Test #26 — silver row count equals bronze non-NULL-geom row count'
);

-- #27 — FK denormalization integrity (silver-dq-baseline Rule 4)
SELECT is(
    (SELECT COUNT(*)::int FROM silver_geo.floodplains WHERE severity IS NULL),
    0,
    'Test #27 — severity IS NOT NULL on every row (FK to dim_constraint_severity intact)'
);

SELECT * FROM finish();

ROLLBACK;
