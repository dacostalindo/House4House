-- Test #8 (Appendix C) — silver_sce_buildings within-cluster address dedup.
-- Asserts that GROUP BY (cluster_id, normalized_address) collapses rows with
-- identical normalized_address into one building, but splits rows with distinct
-- normalized_address even when they share a coordinate.
--
-- The Appendix A Python normalizer is tested separately (tests/enrichment/
-- test_sce_address_norm.py). This test inserts pre-normalized values to exercise
-- the silver model's grouping logic only.

BEGIN;

SELECT plan(2);

CREATE TEMP TABLE stg_sce_fixture (
    doc_number          TEXT,
    normalized_address  TEXT,
    energy_class        TEXT,
    issued_date         DATE,
    status              TEXT,
    municipality        TEXT,
    parish              TEXT,
    geocode_confidence  NUMERIC(4, 3),
    geom_3763           geometry(Point, 3763),
    geocode_source      TEXT
);

-- Pair 1 (at coord A): two rows with the SAME normalized_address → 1 building.
-- This is what happens after the normalizer collapses "Rua Dr. Mário Sacramento"
-- and "rua dr mario sacramento" to the same string.
--
-- Pair 2 (at coord B, 200m north — separate cluster): two rows at the SAME coord
-- with DISTINCT normalized_addresses → 2 buildings. Tests that the GROUP BY does
-- NOT silently merge them based on coords alone (the case Decision 5 trades
-- multi-frontage correctness for).
INSERT INTO stg_sce_fixture VALUES
    ('DOC-1A', 'rua dr mario sacramento', 'A', '2023-01-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(0, 0),   3763), 'nominatim'),
    ('DOC-1B', 'rua dr mario sacramento', 'B', '2023-02-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(0, 0),   3763), 'nominatim'),
    ('DOC-2A', 'rua a 1',                 'A', '2023-01-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(0, 200), 3763), 'nominatim'),
    ('DOC-2B', 'rua b 5',                 'A', '2023-01-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(0, 200), 3763), 'nominatim');

CREATE TEMP TABLE silver_result AS
WITH
nominatim_hits AS (
    SELECT *
    FROM stg_sce_fixture
    WHERE geocode_source = 'nominatim'
      AND geom_3763 IS NOT NULL
      AND normalized_address IS NOT NULL
),
clustered AS (
    SELECT
        *,
        ST_ClusterDBSCAN(geom_3763, eps := 30, minpoints := 1) OVER () AS cluster_id
    FROM nominatim_hits
),
buildings AS (
    SELECT
        cluster_id,
        normalized_address,
        COUNT(*)::int                              AS frac_count,
        ARRAY_AGG(doc_number ORDER BY doc_number)  AS member_doc_numbers
    FROM clustered
    GROUP BY cluster_id, normalized_address
)
SELECT
    DENSE_RANK() OVER (ORDER BY cluster_id, normalized_address)::bigint AS sce_building_id,
    cluster_id,
    normalized_address,
    frac_count,
    member_doc_numbers
FROM buildings;

-- Pair 1: identical normalized_address at same coord → 1 building, frac_count=2
SELECT is(
    (SELECT frac_count FROM silver_result WHERE normalized_address = 'rua dr mario sacramento'),
    2,
    'Identical normalized_address rows at same coord merge into one building'
);

-- Pair 2: distinct normalized_addresses at same coord → 2 buildings (NOT merged)
SELECT is(
    (SELECT COUNT(DISTINCT normalized_address)::int
     FROM silver_result
     WHERE normalized_address IN ('rua a 1', 'rua b 5')),
    2,
    'Distinct normalized_addresses at same coord produce two separate buildings'
);

SELECT * FROM finish();

ROLLBACK;
