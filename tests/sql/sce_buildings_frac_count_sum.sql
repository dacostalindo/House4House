-- Test #9 (Appendix C) — silver_sce_buildings frac_count conservation.
-- Invariant: frac_count counts distinct frações, not certificate documents.
-- A fração re-certified over time (energy certs expire ~10y and are re-issued,
-- also on sale) holds several cert documents but is one physical unit — it must
-- be counted once. Unlabelled certs (no `fraction`) fall back to doc_number, so
-- two distinct houses on the same street are never merged into one unit.

BEGIN;

SELECT plan(4);

CREATE TEMP TABLE stg_sce_fixture (
    doc_number          TEXT,
    fraction            TEXT,
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
    -- Cluster 1: "rua a 1", 3 certs within 30m — but DOC-1/DOC-2 are the same
    -- fração A re-certified, so the building has only 2 frações (A, B).
    ('DOC-1', 'A', 'rua a 1', 'B', '2023-01-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(0, 0),   3763), 'nominatim'),
    ('DOC-2', 'A', 'rua a 1', 'A', '2024-06-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(15, 0),  3763), 'nominatim'),
    ('DOC-3', 'B', 'rua a 1', 'C', '2023-03-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(25, 0),  3763), 'nominatim'),
    -- Cluster 2: "rua b 5", 2 certs 500m away — both unlabelled (houses).
    -- They must NOT collapse: distinct units keyed by doc_number.
    ('DOC-4', '',  'rua b 5', 'A', '2023-04-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(500, 0), 3763), 'nominatim'),
    ('DOC-5', '',  'rua b 5', 'B', '2023-05-01', 'Valido', 'AVEIRO', 'Aveiro', 0.900,
     ST_SetSRID(ST_MakePoint(510, 0), 3763), 'nominatim'),
    -- Rows the model filters OUT (freguesia_centroid + null geom)
    ('DOC-6', 'A', 'rua c 7', 'A', '2023-06-01', 'Valido', 'AVEIRO', 'Aveiro', 0.200,
     ST_SetSRID(ST_MakePoint(0, 0),   3763), 'freguesia_centroid'),
    ('DOC-7', 'A', 'rua d 9', 'A', '2023-07-01', 'Valido', 'AVEIRO', 'Aveiro', NULL,
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
fracao_grain AS (
    SELECT DISTINCT ON (
        cluster_id, normalized_address,
        COALESCE(NULLIF(TRIM(fraction), ''), doc_number)
    )
        *
    FROM clustered
    ORDER BY
        cluster_id, normalized_address,
        COALESCE(NULLIF(TRIM(fraction), ''), doc_number),
        issued_date DESC, doc_number DESC
),
buildings AS (
    SELECT
        cluster_id,
        normalized_address,
        COUNT(*)::int AS frac_count
    FROM fracao_grain
    GROUP BY cluster_id, normalized_address
)
SELECT
    DENSE_RANK() OVER (ORDER BY cluster_id, normalized_address)::bigint AS sce_building_id,
    normalized_address,
    frac_count
FROM buildings;

-- 5 nominatim certs, but only 4 distinct frações (DOC-1/DOC-2 collapse).
SELECT is(
    (SELECT COALESCE(SUM(frac_count), 0)::bigint FROM silver_result),
    4::bigint,
    'SUM(frac_count) counts each fração once — the re-certified fração A on rua a 1 collapses'
);

SELECT is(
    (SELECT COUNT(*)::int FROM silver_result),
    2,
    'Two distinct buildings from the two non-overlapping clusters'
);

SELECT is(
    (SELECT frac_count FROM silver_result WHERE normalized_address = 'rua a 1'),
    2,
    'rua a 1: 3 certs but 2 frações — fração A re-certified collapses to one unit'
);

SELECT is(
    (SELECT frac_count FROM silver_result WHERE normalized_address = 'rua b 5'),
    2,
    'rua b 5: 2 unlabelled house certs stay distinct — never merged'
);

SELECT * FROM finish();

ROLLBACK;
