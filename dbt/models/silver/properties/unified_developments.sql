{{
    config(
        materialized='table',
        tags=['unified_developments', 'silver', 'cross_portal'],
        indexes=[
            {'columns': ['unified_geom_3763'], 'type': 'gist'},
            {'columns': ['unified_geom_4326'], 'type': 'gist'},
            {'columns': ['geo_key']},
            {'columns': ['concelho']}
        ]
    )
}}

-- unified_developments — one row per marketed real-estate development,
-- de-duplicated across the 4 listing portals. Sprint-09 Slice B-prime.
-- (Relocated 2026-06-05 from silver_regulatory → silver_properties, alongside
--  unified_listings; the model is about marketed properties, not regulation.)
--
-- Portal scope: idealista, RE/MAX, Zome, JLL. SCE is intentionally *not* merged
-- in: SCE buildings (certified physical buildings) and portal developments
-- (marketed projects) are different concepts that resist clean merging — no
-- shared identifier, no shared geocoding precision, no shared address grain.
-- Atlas Inspector / fn_assess_polygon query unified_developments AND
-- silver_sce_buildings side-by-side ("marketed developments here + certified
-- buildings here") instead of trying to fuse them into one row.
--
-- Phase 1 — portal dedup, name-driven. Portal coordinates disagree by 200-300m+
-- for the same development (RE/MAX can sit near the parish centroid, idealista
-- averages unit geocodes), so proximity is NOT the grouping key. Instead:
-- normalize the project name (deaccent; strip typology codes T1/T2/T1+1,
-- boilerplate words empreendimento/edifício/the, and a trailing concelho name;
-- punctuation → space), tokenize, and link two portal listings when their
-- word-sets have Jaccard overlap >= 0.6 AND they share a concelho. A 1km
-- distance ceiling is a guardrail (skipped when a coord is missing). Connected
-- components over those links → one development per component.
--
-- Geometry hierarchy — the development takes geom + concelho + parish from the
-- highest-priority portal present that has coordinates: JLL > Zome > RE/MAX >
-- idealista. geo_key (Decision 10) resolved by point-in-polygon of the unified
-- geom against dim_geography.freguesia_geom_pt.
--
-- Unit counts: portal_unit_counts (JSONB) exposes every portal's reported count
-- without picking an "authoritative" one — each portal's count has different
-- semantics (idealista = listed-units subset per the 2026-05-22 facade audit;
-- Zome = inventory; JLL = total fractions; RE/MAX = listings at RE/MAX). The
-- consumer reads the breakdown and decides what to display; no laundered total.
--
-- NOTE: unified_development_id is a within-build surrogate. The stable identity
-- of a development is the content of portal_refs.

WITH RECURSIVE

-- ── Phase 1: portal developments ──────────────────────────────────────────
-- NULL-geom portal devs are kept (they can still match by name); a development
-- with no geom-bearing member at all is dropped at portal_dev_geo.

portal_members AS (
    SELECT portal, portal_dev_id, canonical_name, concelho, parish, geom_3763, total_units
    FROM {{ ref('stg_portal_developments_idealista') }}
    UNION ALL
    SELECT portal, portal_dev_id, canonical_name, concelho, parish, geom_3763, total_units
    FROM {{ ref('stg_portal_developments_remax') }}
    UNION ALL
    SELECT portal, portal_dev_id, canonical_name, concelho, parish, geom_3763, total_units
    FROM {{ ref('stg_portal_developments_zome') }}
    UNION ALL
    SELECT portal, portal_dev_id, canonical_name, concelho, parish, geom_3763, total_units
    FROM {{ ref('stg_portal_developments_jll') }}
),

-- clean_name: lowercase, deaccent, strip typology codes (t1, t2, t1+1) and the
-- boilerplate words empreendimento/edifício/the, punctuation → space.
portal_pre AS (
    SELECT
        portal, portal_dev_id, canonical_name, concelho, parish, geom_3763, total_units,
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

-- name_key: clean_name minus a trailing concelho name (e.g. "… , Matosinhos").
-- priority: geo-source rank (lower wins) — JLL > Zome > RE/MAX > idealista.
portal_named AS (
    SELECT
        portal, portal_dev_id, canonical_name, concelho, parish, geom_3763, total_units,
        portal || ':' || portal_dev_id AS member_id,
        CASE portal WHEN 'jll' THEN 1 WHEN 'zome' THEN 2 WHEN 'remax' THEN 3 ELSE 4 END
            AS priority,
        CASE
            WHEN norm_concelho <> '' AND clean_name LIKE '% ' || norm_concelho
            THEN TRIM(LEFT(clean_name, length(clean_name) - length(norm_concelho) - 1))
            ELSE clean_name
        END AS name_key
    FROM portal_pre
),

member_tokens AS (
    SELECT p.member_id, p.concelho, t.token
    FROM portal_named p,
         unnest(string_to_array(p.name_key, ' ')) AS t(token)
    WHERE p.name_key <> '' AND t.token <> ''
),

token_counts AS (
    SELECT member_id, COUNT(*) AS n_tokens FROM member_tokens GROUP BY member_id
),

-- Shared word count for every same-concelho pair that shares at least one token.
shared AS (
    SELECT a.member_id AS u, b.member_id AS v, COUNT(*) AS shared_tokens
    FROM member_tokens a
    JOIN member_tokens b
      ON a.token = b.token
     AND a.concelho = b.concelho
     AND a.member_id < b.member_id
    GROUP BY a.member_id, b.member_id
),

-- "Same development": word-set Jaccard >= 0.6, within a 1km ceiling (skipped
-- when either coord is missing — name + concelho is sufficient there).
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
    SELECT u, v           FROM name_pairs
    UNION ALL
    SELECT v AS u, u AS v FROM name_pairs
    UNION ALL
    SELECT member_id AS u, member_id AS v FROM portal_named
),

-- Connected components: each member's dev_key is the MIN member_id reachable.
walk AS (
    SELECT u AS member_id, u AS reached FROM edges
    UNION
    SELECT w.member_id, e.v
    FROM walk w
    JOIN edges e ON e.u = w.reached
),

components AS (
    SELECT member_id, MIN(reached) AS dev_key
    FROM walk
    GROUP BY member_id
),

portal_keyed AS (
    SELECT pn.*, co.dev_key
    FROM portal_named pn
    JOIN components co ON co.member_id = pn.member_id
),

-- Per (development, portal): contributing ids + the portal's unit count.
portal_by_portal AS (
    SELECT
        dev_key, portal,
        jsonb_agg(portal_dev_id ORDER BY portal_dev_id) AS ids,
        SUM(total_units)                                AS units
    FROM portal_keyed
    GROUP BY dev_key, portal
),

portal_dev_refs AS (
    SELECT
        dev_key,
        jsonb_object_agg(portal, ids)   AS portal_refs,
        jsonb_object_agg(portal, units) AS portal_unit_counts,
        COUNT(*)::int                   AS n_portal_contributors
    FROM portal_by_portal
    GROUP BY dev_key
),

portal_dev_name AS (
    SELECT
        dev_key,
        MODE() WITHIN GROUP (ORDER BY canonical_name)
            FILTER (WHERE canonical_name IS NOT NULL) AS dominant_name
    FROM portal_keyed
    GROUP BY dev_key
),

-- Geometry hierarchy: the best-priority portal that actually has coordinates.
top_portal AS (
    SELECT DISTINCT ON (dev_key) dev_key, portal AS geo_portal
    FROM portal_keyed
    WHERE geom_3763 IS NOT NULL
    ORDER BY dev_key, priority
),

portal_dev_geo AS (
    -- Geom centroid for devs that have at least one geom-bearing contributor.
    -- Devs with no geom anywhere fall through to portal_devs via LEFT JOIN
    -- and carry NULL geom (refactor 2026-06-06 — previously dropped here,
    -- losing ~10 devs + ~60 listing FK joins in unified_listings_residential).
    SELECT
        k.dev_key,
        ST_Centroid(ST_Collect(k.geom_3763))            AS geom_3763
    FROM portal_keyed k
    JOIN top_portal tp ON tp.dev_key = k.dev_key AND k.portal = tp.geo_portal
    WHERE k.geom_3763 IS NOT NULL
    GROUP BY k.dev_key
),

portal_dev_concelho AS (
    -- Concelho/parish are derivable from ANY contributing portal regardless of
    -- geom presence; this CTE always has one row per dev_key.
    SELECT
        k.dev_key,
        MODE() WITHIN GROUP (ORDER BY k.concelho)       AS concelho_text,
        MODE() WITHIN GROUP (ORDER BY k.parish)         AS parish_text
    FROM portal_keyed k
    GROUP BY k.dev_key
),

portal_devs AS (
    -- Driver: portal_dev_refs (every dev_key with ≥1 portal contributor).
    -- LEFT JOIN portal_dev_geo (NULL geom when no contributor has it).
    -- LEFT JOIN portal_dev_concelho (always populated since name+concelho
    --   come from portal_keyed regardless of geom).
    SELECT
        r.dev_key,
        g.geom_3763,
        c.concelho_text,
        c.parish_text,
        nm.dominant_name,
        r.portal_refs, r.portal_unit_counts, r.n_portal_contributors
    FROM portal_dev_refs r
    JOIN portal_dev_name nm   USING (dev_key)
    LEFT JOIN portal_dev_concelho c USING (dev_key)
    LEFT JOIN portal_dev_geo g      USING (dev_key)
)

SELECT
    -- Tiebreak on dev_key for stable IDs on no-geom devs (ST_X/ST_Y on NULL
    -- returns NULL; PG default NULLS LAST puts them at the end deterministically).
    ROW_NUMBER() OVER (ORDER BY ST_X(pd.geom_3763), ST_Y(pd.geom_3763), pd.dev_key)::bigint
                                                                  AS unified_development_id,
    pd.geom_3763::geometry(Point, 3763)                           AS unified_geom_3763,
    ST_Transform(pd.geom_3763, 4326)::geometry(Point, 4326)       AS unified_geom_4326,
    dg.geo_key,
    COALESCE(dg.concelho_name, pd.concelho_text)                  AS concelho,
    COALESCE(dg.freguesia_name, pd.parish_text)                   AS parish,
    pd.dominant_name,
    pd.portal_unit_counts,
    pd.n_portal_contributors,
    pd.portal_refs,
    NOW()::timestamptz                                            AS _built_at
FROM portal_devs pd
LEFT JOIN LATERAL (
    SELECT g.geo_key, g.concelho_name, g.freguesia_name
    FROM {{ ref('dim_geography') }} g
    WHERE g.is_current
      AND ST_Contains(g.freguesia_geom_pt, pd.geom_3763)
    LIMIT 1
) dg ON TRUE
