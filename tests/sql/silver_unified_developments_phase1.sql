-- silver_unified_developments — Phase 1 portal-dedup invariants.
--
-- Exercises the four contracts that the name-driven dedup must hold:
--   #21  Cross-portal merge: similar names in the same concelho collapse to one
--        unified row, with both portals in portal_refs.
--   #22  Boilerplate normalization: "Empreendimento JC Barrocas Apartments" and
--        "JC Barrocas Apartments" merge despite the empreendimento prefix.
--   #23  Same-coord different-name stays split: 4 distinct developments sharing
--        one coordinate (the Coimbra parish-centroid case) produce 4 rows.
--   #24  Cross-concelho separation: same-named developments in different
--        concelhos never merge, regardless of name similarity.
--
-- Fixture-driven, BEGIN/ROLLBACK-wrapped. Replicates the model's Phase 1 inline
-- (portal_pre → portal_devs) with a TEMP fixture replacing the staging UNION.

BEGIN;

SELECT plan(5);

CREATE TEMP TABLE portal_members_fixture (
    portal          TEXT,
    portal_dev_id   TEXT,
    canonical_name  TEXT,
    concelho        TEXT,
    parish          TEXT,
    geom_3763       geometry(Point, 3763),
    total_units     BIGINT
);

INSERT INTO portal_members_fixture VALUES
    -- #21 Cross-portal merge: 200m apart, "The Unique" / "Unique"
    ('idealista', '33035356', 'The Unique', 'AVEIRO', 'Glória e Vera Cruz',
     ST_SetSRID(ST_MakePoint(160000, 220000), 3763), 3),
    ('remax',     '8238',     'Unique',     'AVEIRO', 'Glória e Vera Cruz',
     ST_SetSRID(ST_MakePoint(160200, 220000), 3763), 5),

    -- #22 Boilerplate strip: "Empreendimento JC Barrocas Apartments" / "JC Barrocas Apartments"
    ('idealista', 'JCB-1', 'JC Barrocas Apartments', 'AVEIRO', 'Glória e Vera Cruz',
     ST_SetSRID(ST_MakePoint(161000, 221000), 3763), 9),
    ('zome',      '194987', 'Empreendimento JC Barrocas Apartments', 'AVEIRO', 'Glória e Vera Cruz',
     ST_SetSRID(ST_MakePoint(161200, 221000), 3763), 19),

    -- #23 Same-coord different-name: 4 distinct devs at one point in Coimbra
    ('remax', 'R-1', 'Concrete Residences', 'COIMBRA', 'Sé Nova',
     ST_SetSRID(ST_MakePoint(200000, 250000), 3763), 5),
    ('remax', 'R-2', 'RIVER VIEW', 'COIMBRA', 'Sé Nova',
     ST_SetSRID(ST_MakePoint(200000, 250000), 3763), 5),
    ('remax', 'R-3', 'Voluta', 'COIMBRA', 'Sé Nova',
     ST_SetSRID(ST_MakePoint(200000, 250000), 3763), 5),
    ('remax', 'R-4', 'Urbanização Alto da Guarda Inglesa', 'COIMBRA', 'Sé Nova',
     ST_SetSRID(ST_MakePoint(200000, 250000), 3763), 5),

    -- #24 Cross-concelho: same name, different concelhos
    ('idealista', 'SL-A', 'Sea Lux', 'AVEIRO', 'Aradas',
     ST_SetSRID(ST_MakePoint(159000, 219000), 3763), 5),
    ('zome',      'SL-B', 'Sea Lux', 'PORTO',  'Bonfim',
     ST_SetSRID(ST_MakePoint(180000, 460000), 3763), 5);

-- ── Inline Phase-1 pipeline (verbatim from silver_unified_developments.sql) ──
CREATE TEMP TABLE phase1_result AS
WITH RECURSIVE
portal_members AS (
    SELECT * FROM portal_members_fixture
),
portal_pre AS (
    SELECT portal, portal_dev_id, canonical_name, concelho, parish, geom_3763, total_units,
        TRIM(regexp_replace(
            regexp_replace(
                regexp_replace(
                    translate(lower(COALESCE(canonical_name, '')),
                              'áàâãäçéèêëíìîïóòôõöúùûü', 'aaaaaceeeeiiiiooooouuuu'),
                    '\mt[0-9]+([-+/][0-9]+)*\M', ' ', 'g'),
                '\m(empreendimento|edificio|the)\M', ' ', 'g'),
            '[^a-z0-9]+', ' ', 'g')) AS clean_name,
        translate(lower(COALESCE(concelho, '')),
                  'áàâãäçéèêëíìîïóòôõöúùûü', 'aaaaaceeeeiiiiooooouuuu') AS norm_concelho
    FROM portal_members
),
portal_named AS (
    SELECT portal, portal_dev_id, canonical_name, concelho, parish, geom_3763, total_units,
        portal || ':' || portal_dev_id AS member_id,
        CASE portal WHEN 'jll' THEN 1 WHEN 'zome' THEN 2 WHEN 'remax' THEN 3 ELSE 4 END AS priority,
        CASE WHEN norm_concelho <> '' AND clean_name LIKE '% ' || norm_concelho
             THEN TRIM(LEFT(clean_name, length(clean_name) - length(norm_concelho) - 1))
             ELSE clean_name END AS name_key
    FROM portal_pre
),
member_tokens AS (
    SELECT p.member_id, p.concelho, t.token
    FROM portal_named p, unnest(string_to_array(p.name_key, ' ')) AS t(token)
    WHERE p.name_key <> '' AND t.token <> ''
),
token_counts AS (
    SELECT member_id, COUNT(*) AS n_tokens FROM member_tokens GROUP BY member_id
),
shared AS (
    SELECT a.member_id AS u, b.member_id AS v, COUNT(*) AS shared_tokens
    FROM member_tokens a JOIN member_tokens b
      ON a.token = b.token AND a.concelho = b.concelho AND a.member_id < b.member_id
    GROUP BY a.member_id, b.member_id
),
name_pairs AS (
    SELECT s.u, s.v
    FROM shared s
    JOIN token_counts ca ON ca.member_id = s.u
    JOIN token_counts cb ON cb.member_id = s.v
    JOIN portal_named pa ON pa.member_id = s.u
    JOIN portal_named pb ON pb.member_id = s.v
    WHERE s.shared_tokens::numeric
            / (ca.n_tokens + cb.n_tokens - s.shared_tokens)::numeric >= 0.6
      AND (pa.geom_3763 IS NULL OR pb.geom_3763 IS NULL
           OR ST_DWithin(pa.geom_3763, pb.geom_3763, 1000))
),
edges AS (
    SELECT u, v FROM name_pairs
    UNION ALL SELECT v AS u, u AS v FROM name_pairs
    UNION ALL SELECT member_id AS u, member_id AS v FROM portal_named
),
walk AS (
    SELECT u AS member_id, u AS reached FROM edges
    UNION
    SELECT w.member_id, e.v FROM walk w JOIN edges e ON e.u = w.reached
),
components AS (
    SELECT member_id, MIN(reached) AS dev_key FROM walk GROUP BY member_id
),
portal_keyed AS (
    SELECT pn.*, co.dev_key
    FROM portal_named pn JOIN components co ON co.member_id = pn.member_id
),
portal_by_portal AS (
    SELECT dev_key, portal, jsonb_agg(portal_dev_id ORDER BY portal_dev_id) AS ids
    FROM portal_keyed GROUP BY dev_key, portal
),
portal_dev_refs AS (
    SELECT dev_key, jsonb_object_agg(portal, ids) AS portal_refs, COUNT(*)::int AS n_portal_contributors
    FROM portal_by_portal GROUP BY dev_key
),
portal_dev_name AS (
    SELECT dev_key,
           MODE() WITHIN GROUP (ORDER BY canonical_name) FILTER (WHERE canonical_name IS NOT NULL) AS dominant_name,
           MODE() WITHIN GROUP (ORDER BY concelho) AS concelho_text
    FROM portal_keyed GROUP BY dev_key
)
SELECT n.dev_key, n.dominant_name, n.concelho_text, r.portal_refs, r.n_portal_contributors
FROM portal_dev_name n JOIN portal_dev_refs r USING (dev_key);

-- ── Assertions ────────────────────────────────────────────────────────────

-- 8 distinct developments out of 10 fixture rows: 1 + 1 + 4 + 2 = 8.
SELECT is(
    (SELECT COUNT(*)::int FROM phase1_result),
    8,
    '10 portal members produce 8 unified rows (1 Unique merge + 1 JC Barrocas merge + 4 Coimbra + 2 cross-concelho)'
);

-- #21: The Unique row has both idealista and remax in portal_refs.
SELECT is(
    (SELECT portal_refs ?& ARRAY['idealista','remax']
     FROM phase1_result
     WHERE dominant_name IN ('The Unique','Unique') AND concelho_text='AVEIRO'),
    TRUE,
    'Test #21 — "The Unique" + "Unique" merged into one row with both portals'
);

-- #22: JC Barrocas row has both idealista and zome (boilerplate stripped).
SELECT is(
    (SELECT portal_refs ?& ARRAY['idealista','zome']
     FROM phase1_result
     WHERE dominant_name ILIKE '%Barrocas%' AND concelho_text='AVEIRO'),
    TRUE,
    'Test #22 — "Empreendimento JC Barrocas Apartments" + "JC Barrocas Apartments" merged (boilerplate strip)'
);

-- #23: 4 distinct rows in Coimbra (different names, same coord → not merged).
SELECT is(
    (SELECT COUNT(*)::int FROM phase1_result WHERE concelho_text='COIMBRA'),
    4,
    'Test #23 — 4 same-coord different-name devs stay split into 4 unified rows'
);

-- #24: Cross-concelho "Sea Lux" stays as 2 separate rows.
SELECT is(
    (SELECT COUNT(*)::int FROM phase1_result WHERE dominant_name='Sea Lux'),
    2,
    'Test #24 — same-named devs in different concelhos never merge'
);

SELECT * FROM finish();

ROLLBACK;
