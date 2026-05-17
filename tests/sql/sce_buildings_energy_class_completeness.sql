-- Test #10 (Appendix C) — silver_sce_buildings energy_class_dist completeness.
-- Invariant: for every silver row, every distinct energy_class value contributed
-- by its member SCE certificates appears as a key in energy_class_dist (JSONB),
-- and the bucket counts sum to frac_count for members with non-null
-- energy_class.

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

-- One cluster, 6 members across all 7 PT energy classes (with one duplicate to
-- exercise bucket counting). Goal: assert energy_class_dist captures every
-- distinct class present.
INSERT INTO stg_sce_fixture VALUES
    ('DOC-A+',  'rua x 1', 'A+', '2023-01-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(0, 0),  3763), 'nominatim'),
    ('DOC-A',   'rua x 1', 'A',  '2023-02-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(2, 0),  3763), 'nominatim'),
    ('DOC-A2',  'rua x 1', 'A',  '2023-03-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(4, 0),  3763), 'nominatim'),  -- second A (bucket count → 2)
    ('DOC-B',   'rua x 1', 'B',  '2023-04-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(6, 0),  3763), 'nominatim'),
    ('DOC-C',   'rua x 1', 'C',  '2023-05-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(8, 0),  3763), 'nominatim'),
    ('DOC-D',   'rua x 1', 'D',  '2023-06-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(10, 0), 3763), 'nominatim'),
    -- NULL energy_class — should be dropped from the histogram (won't inflate
    -- any bucket) but DOES count toward frac_count.
    ('DOC-NULL','rua x 1', NULL, '2023-07-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(12, 0), 3763), 'nominatim');

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
energy_class_per_building AS (
    SELECT cluster_id, normalized_address, energy_class, COUNT(*)::int AS class_count
    FROM clustered
    WHERE energy_class IS NOT NULL
    GROUP BY 1, 2, 3
),
energy_class_dist_per_building AS (
    SELECT
        cluster_id,
        normalized_address,
        jsonb_object_agg(energy_class, class_count) AS energy_class_dist
    FROM energy_class_per_building
    GROUP BY 1, 2
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
    b.cluster_id,
    b.frac_count,
    COALESCE(e.energy_class_dist, '{}'::jsonb) AS energy_class_dist
FROM buildings b
LEFT JOIN energy_class_dist_per_building e USING (cluster_id, normalized_address);

-- 6 distinct energy_class keys present in members (A+, A, B, C, D); NULL excluded.
SELECT is(
    (SELECT array_agg(k ORDER BY k)
     FROM jsonb_object_keys((SELECT energy_class_dist FROM silver_result)) k),
    ARRAY['A', 'A+', 'B', 'C', 'D']::text[],
    'energy_class_dist contains every non-null energy_class present in members'
);

-- Bucket counts: A=2, A+=1, B=1, C=1, D=1
SELECT is(
    (SELECT (energy_class_dist->>'A')::int FROM silver_result),
    2,
    'Bucket count for A reflects the 2 A-grade members (DOC-A + DOC-A2)'
);

-- Sum of bucket counts = members with non-null energy_class (6 of 7).
SELECT is(
    (SELECT (
        SELECT SUM(v::int)
        FROM jsonb_each_text(energy_class_dist) e(k, v)
     ) FROM silver_result),
    6::bigint,
    'SUM of energy_class_dist bucket counts equals members with non-null energy_class'
);

SELECT * FROM finish();

ROLLBACK;
