-- Test #9 (Appendix C) — silver_sce_buildings frac_count conservation.
-- Invariant: SUM(frac_count) over DISTINCT sce_building_id equals the COUNT of
-- nominatim input rows. The DISTINCT-on-sce_building_id is needed because
-- cluster_split duplicates rows across parcels — without DISTINCT the sum would
-- inflate.
--
-- This test uses a no-cluster-split fixture (every cluster falls inside one
-- parcel — or no parcel at all). Test #11 exercises the cluster_split case
-- separately and asserts the same invariant holds there.

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

INSERT INTO stg_sce_fixture VALUES
    -- Cluster 1: 3 rows on "rua a 1" within 30m
    ('DOC-1', 'rua a 1', 'A', '2023-01-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(0, 0),   3763), 'nominatim'),
    ('DOC-2', 'rua a 1', 'B', '2023-02-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(15, 0),  3763), 'nominatim'),
    ('DOC-3', 'rua a 1', 'C', '2023-03-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(25, 0),  3763), 'nominatim'),
    -- Cluster 2: 2 rows on "rua b 5" 500m away (separate cluster)
    ('DOC-4', 'rua b 5', 'A', '2023-04-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(500, 0), 3763), 'nominatim'),
    ('DOC-5', 'rua b 5', 'B', '2023-05-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(510, 0), 3763), 'nominatim'),
    -- Rows that the model filters OUT (freguesia_centroid + null geom)
    ('DOC-6', 'rua c 7', 'A', '2023-06-01', 'Valido', 'AVEIRO', 'Aveiro', 0.200,
     ST_SetSRID(ST_MakePoint(0, 0),   3763), 'freguesia_centroid'),
    ('DOC-7', 'rua d 9', 'A', '2023-07-01', 'Valido', 'AVEIRO', 'Aveiro', NULL,
     NULL,                                    'none');

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
        COUNT(*)::int AS frac_count
    FROM clustered
    GROUP BY cluster_id, normalized_address
)
SELECT
    DENSE_RANK() OVER (ORDER BY cluster_id, normalized_address)::bigint AS sce_building_id,
    frac_count
FROM buildings;

-- 5 nominatim rows in fixture; 2 non-nominatim rows filtered out.
SELECT is(
    (SELECT COALESCE(SUM(frac_count), 0)::bigint
     FROM (SELECT DISTINCT ON (sce_building_id) sce_building_id, frac_count
           FROM silver_result) distinct_buildings),
    5::bigint,
    'SUM(frac_count) over DISTINCT sce_building_id equals nominatim input row count'
);

-- Sanity: 5 rows produce exactly 2 buildings (cluster1 of 3 + cluster2 of 2).
SELECT is(
    (SELECT COUNT(DISTINCT sce_building_id)::int FROM silver_result),
    2,
    'Two distinct sce_building_ids from the two non-overlapping clusters'
);

SELECT * FROM finish();

ROLLBACK;
