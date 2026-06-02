-- silver_geo.aquifers + silver_geo.geology invariants (sprint-09 WS4 quick-wins batch).
-- Covers silver-dq-baseline Rules 1 (spatial dual-CRS) + 3 (row-count parity).
-- Surrogate-key Rule 2 covered by dbt YAML.
--
-- Tests:
--   #28  ST_IsValid across both aquifers + geology
--   #28b ST_SRID correctness on both layers
--   #29  silver aquifers count == bronze aquifers count (geom NOT NULL)
--   #29b silver geology count == bronze geology count (geom NOT NULL)
--   #30  geological_era_code = LEFT(lithology_code, 1) on every geology row

BEGIN;

SELECT plan(5);

-- #28 — ST_IsValid on both layers combined
SELECT is(
    (SELECT COUNT(*)::int FROM (
        SELECT 1 FROM silver_geo.aquifers
         WHERE NOT (ST_IsValid(geom) AND ST_IsValid(geom_pt))
        UNION ALL
        SELECT 1 FROM silver_geo.geology
         WHERE NOT (ST_IsValid(geom) AND ST_IsValid(geom_pt))
    ) invalid),
    0,
    'Test #28 — every aquifer + geology row has valid geom AND geom_pt'
);

-- #28b — ST_SRID correctness on both layers
SELECT is(
    (SELECT COUNT(*)::int FROM (
        SELECT 1 FROM silver_geo.aquifers
         WHERE ST_SRID(geom) <> 4326 OR ST_SRID(geom_pt) <> 3763
        UNION ALL
        SELECT 1 FROM silver_geo.geology
         WHERE ST_SRID(geom) <> 4326 OR ST_SRID(geom_pt) <> 3763
    ) bad_srid),
    0,
    'Test #28b — every aquifer + geology row has SRID(geom)=4326 AND SRID(geom_pt)=3763'
);

-- #29 — aquifers row-count parity
SELECT is(
    (SELECT COUNT(*)::int FROM silver_geo.aquifers),
    (SELECT COUNT(*)::int FROM bronze_hydrology.raw_lneg_aquiferos
     WHERE geom IS NOT NULL),
    'Test #29 — silver aquifers count equals bronze non-NULL-geom count'
);

-- #29b — geology row-count parity
SELECT is(
    (SELECT COUNT(*)::int FROM silver_geo.geology),
    (SELECT COUNT(*)::int FROM bronze_geology.raw_lneg_geology_500k
     WHERE geom IS NOT NULL),
    'Test #29b — silver geology count equals bronze non-NULL-geom count'
);

-- #30 — geological_era_code derivation invariant
SELECT is(
    (SELECT COUNT(*)::int FROM silver_geo.geology
     WHERE geological_era_code <> LEFT(lithology_code, 1)),
    0,
    'Test #30 — geological_era_code equals LEFT(lithology_code, 1) on every row'
);

SELECT * FROM finish();

ROLLBACK;
