-- Test #7 (Appendix C) — silver_sce_buildings DBSCAN clustering correctness.
-- Asserts that ST_ClusterDBSCAN(eps=30m, minpoints=1) groups 2 SCE rows 20m apart
-- into one cluster, and isolates a 3rd row 100m away into its own cluster.
--
-- Self-contained: TEMP fixtures + inlined replica of the silver_sce_buildings
-- DBSCAN+GROUP BY pipeline. No dependency on the live materialized table.

BEGIN;

SELECT plan(3);

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

INSERT INTO stg_sce_fixture VALUES
    ('DOC-A', 'rua x 1', 'A', '2023-01-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(0, 0),   3763), 'nominatim'),
    ('DOC-B', 'rua x 1', 'A', '2023-02-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(20, 0),  3763), 'nominatim'),  -- 20 m east → same cluster
    ('DOC-C', 'rua x 1', 'A', '2023-03-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(100, 0), 3763), 'nominatim');  -- 100 m east → separate cluster

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

SELECT is(
    (SELECT COUNT(*)::int FROM silver_result),
    2,
    '3 input rows (2 within 30m + 1 at 100m) produce exactly 2 buildings'
);

SELECT is(
    (SELECT frac_count FROM silver_result WHERE 'DOC-A' = ANY(member_doc_numbers)),
    2,
    'A + B (20m apart) merge into one building with frac_count=2'
);

SELECT is(
    (SELECT frac_count FROM silver_result WHERE 'DOC-C' = ANY(member_doc_numbers)),
    1,
    'C (100m from A) lands in its own building with frac_count=1'
);

SELECT * FROM finish();

ROLLBACK;
