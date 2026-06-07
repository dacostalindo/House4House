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
-- Portal scope: idealista, RE/MAX, Zome, JLL, imovirtual. SCE is intentionally *not* merged
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
-- (a) name normalization lives in each staging model via the
--     normalize_dev_name() macro — deaccent + strip typology codes T1/T2/T1+1 +
--     strip boilerplate empreendimento/edifício/the + punctuation→space. Each
--     staging row exposes a `match_name` column ready to feed the dedup.
-- (b) admin geography is CAOP-resolved per staging row by point-in-polygon
--     against dim_geography.freguesia_geom_pt — staging exposes geo_concelho_name,
--     geo_parish_name, geo_key. The dedup's same-concelho gate joins on
--     COALESCE(geo_concelho_name, concelho) — CAOP wins when geom resolved,
--     portal-text fallback for NULL-geom devs (idealista today).
-- (c) trailing-concelho strip ("… , Aveiro" → "…") stays here because it needs
--     the cross-cutting join_concelho context staging can't supply uniformly.
-- Two parallel edge generators link portal listings — both gated on
-- same-concelho — and the UNION of edges feeds connected components:
--   (1) Token-Jaccard ≥ 0.6 on whitespace-split tokens — catches subset names
--       ("JC Barrocas" ↔ "JC Barrocas Apartments" = 0.667).
--   (2) Char-trigram Jaccard ≥ 0.6 on the whitespace-stripped clean_name —
--       catches whitespace-collapse variants ("VIANOVA" ↔ "Via Nova" = 1.0)
--       that the token signal is structurally blind to.
-- The 1km distance ceiling was removed 2026-06-06: portal pins disagree by
-- 3-4km on identical-named devs in the same concelho (worse than the original
-- 200-300m audit number), so distance was vetoing correct merges. Same name +
-- same concelho is sufficient evidence; both edge generators require Jaccard
-- ≥ 0.6 which is stricter than the geographic gate ever was.
--
-- Geometry hierarchy — the development takes geom + concelho + parish from the
-- highest-priority portal present that has coordinates:
--   JLL > Zome > RE/MAX > imovirtual > idealista.
-- imovirtual sits at slot 4 (above idealista, below RE/MAX) — typed dev-level
-- pin + reverseGeocoding are cleaner than RE/MAX in principle, but coverage is
-- unverified at silver-build time so the conservative slot wins for v1. See the
-- 2026-06-06 addendum on the imovirtual onboarding decision for the rank-change
-- rationale. geo_key (Decision 10) resolved by point-in-polygon of the unified
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
    {% set staging_models = [
        'stg_portal_developments_idealista',
        'stg_portal_developments_remax',
        'stg_portal_developments_zome',
        'stg_portal_developments_jll',
        'stg_portal_developments_imovirtual',
    ] %}
    {% for m in staging_models %}
    SELECT portal, portal_dev_id, canonical_name, concelho, parish, geom_3763, total_units,
           match_name, geo_concelho_name, geo_parish_name, geo_key
    FROM {{ ref(m) }}
    {% if not loop.last %}UNION ALL{% endif %}
    {% endfor %}
),

-- join_concelho: CAOP-resolved concelho when geom hit a freguesia polygon,
--   portal-text concelho otherwise. Deaccented + lowercased so the same-concelho
--   gate aligns with the deaccented match_name (case + accent normalization).
-- priority: geo-source rank (lower wins) — JLL > Zome > RE/MAX > imovirtual > idealista.
portal_keyed_pre AS (
    SELECT
        pm.*,
        portal || ':' || portal_dev_id AS member_id,
        CASE portal
            WHEN 'jll' THEN 1
            WHEN 'zome' THEN 2
            WHEN 'remax' THEN 3
            WHEN 'imovirtual' THEN 4
            ELSE 5
        END AS priority,
        translate(lower(COALESCE(geo_concelho_name, concelho, '')),
                  'áàâãäçéèêëíìîïóòôõöúùûü', 'aaaaaceeeeiiiiooooouuuu') AS join_concelho
    FROM portal_members pm
),

-- name_key: match_name minus a trailing concelho name (e.g. "… , aveiro") —
-- cross-cutting because it needs join_concelho, which the staging models
-- couldn't supply uniformly (different signals across portals + CAOP).
portal_named AS (
    SELECT
        pk.*,
        CASE
            WHEN join_concelho <> ''
             AND match_name LIKE '% ' || join_concelho
            THEN TRIM(LEFT(match_name, length(match_name) - length(join_concelho) - 1))
            ELSE match_name
        END AS name_key
    FROM portal_keyed_pre pk
),

-- ── Edge generator 1: token-Jaccard on whitespace-split tokens ───────────
member_tokens AS (
    SELECT DISTINCT p.member_id, p.join_concelho, t.token
    FROM portal_named p,
         unnest(string_to_array(p.name_key, ' ')) AS t(token)
    WHERE p.name_key <> '' AND t.token <> ''
),

token_counts AS (
    SELECT member_id, COUNT(*) AS n_tokens FROM member_tokens GROUP BY member_id
),

shared_tokens AS (
    SELECT a.member_id AS u, b.member_id AS v, COUNT(*) AS n_shared
    FROM member_tokens a
    JOIN member_tokens b
      ON a.token = b.token
     AND a.join_concelho = b.join_concelho
     AND a.member_id < b.member_id
    GROUP BY a.member_id, b.member_id
),

name_pairs_token AS (
    SELECT s.u, s.v
    FROM shared_tokens s
    JOIN token_counts ca ON ca.member_id = s.u
    JOIN token_counts cb ON cb.member_id = s.v
    WHERE s.n_shared::numeric
            / (ca.n_tokens + cb.n_tokens - s.n_shared)::numeric >= 0.6
),

-- ── Edge generator 2: char-trigram Jaccard on whitespace-stripped name ───
-- Catches "VIANOVA" ↔ "Via Nova" which token-Jaccard scores at 0.0.
-- DISTINCT collapses repeated trigrams to set semantics. Skip names shorter
-- than 3 chars (no trigrams exist).
member_trigrams AS (
    SELECT DISTINCT
        p.member_id,
        p.join_concelho,
        substring(regexp_replace(p.name_key, '\s+', '', 'g') FROM g FOR 3) AS trigram
    FROM portal_named p,
         generate_series(1, length(regexp_replace(p.name_key, '\s+', '', 'g')) - 2) AS g
    WHERE length(regexp_replace(p.name_key, '\s+', '', 'g')) >= 3
),

trigram_counts AS (
    SELECT member_id, COUNT(*) AS n_trigrams FROM member_trigrams GROUP BY member_id
),

shared_trigrams AS (
    SELECT a.member_id AS u, b.member_id AS v, COUNT(*) AS n_shared
    FROM member_trigrams a
    JOIN member_trigrams b
      ON a.trigram = b.trigram
     AND a.join_concelho = b.join_concelho
     AND a.member_id < b.member_id
    GROUP BY a.member_id, b.member_id
),

name_pairs_trigram AS (
    SELECT s.u, s.v
    FROM shared_trigrams s
    JOIN trigram_counts ca ON ca.member_id = s.u
    JOIN trigram_counts cb ON cb.member_id = s.v
    WHERE s.n_shared::numeric
            / (ca.n_trigrams + cb.n_trigrams - s.n_shared)::numeric >= 0.6
),

-- UNION of the two edge generators. Either signal is sufficient; connected
-- components don't care which one produced the edge.
name_pairs AS (
    SELECT u, v FROM name_pairs_token
    UNION
    SELECT u, v FROM name_pairs_trigram
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
    -- Geom + admin geography from the highest-priority portal that has
    -- coordinates (the top_portal pick). Geom is the centroid of that portal's
    -- contributing members; concelho/parish/geo_key are taken from the SAME
    -- portal so they don't drift from where the pin actually lands. Devs with
    -- no geom anywhere fall through via LEFT JOIN and carry NULL geom +
    -- NULL admin (handled by COALESCE with the no-geom-fallback CTE below).
    SELECT
        k.dev_key,
        ST_Centroid(ST_Collect(k.geom_3763))            AS geom_3763,
        MODE() WITHIN GROUP (ORDER BY COALESCE(k.geo_concelho_name, k.concelho))
                                                        AS concelho_from_geo_portal,
        MODE() WITHIN GROUP (ORDER BY COALESCE(k.geo_parish_name, k.parish))
                                                        AS parish_from_geo_portal,
        MODE() WITHIN GROUP (ORDER BY k.geo_key)        AS geo_key_from_geo_portal
    FROM portal_keyed k
    JOIN top_portal tp ON tp.dev_key = k.dev_key AND k.portal = tp.geo_portal
    WHERE k.geom_3763 IS NOT NULL
    GROUP BY k.dev_key
),

portal_dev_concelho_fallback AS (
    -- No-geom fallback: when NO portal contributor has coordinates the
    -- top_portal pick is empty and portal_dev_geo carries NULLs. Use a
    -- MODE-vote across all members so the dev still gets concelho/parish
    -- (parish text from idealista's location_hierarchy etc.).
    SELECT
        k.dev_key,
        MODE() WITHIN GROUP (ORDER BY COALESCE(k.geo_concelho_name, k.concelho))
                                                        AS concelho_fallback,
        MODE() WITHIN GROUP (ORDER BY COALESCE(k.geo_parish_name, k.parish))
                                                        AS parish_fallback,
        MODE() WITHIN GROUP (ORDER BY k.geo_key)        AS geo_key_fallback
    FROM portal_keyed k
    GROUP BY k.dev_key
),

portal_devs AS (
    -- Driver: portal_dev_refs (every dev_key with ≥1 portal contributor).
    -- Admin geography (concelho/parish/geo_key) follows the chosen geom when
    -- the dev has a pin; falls back to MODE-vote across all members when no
    -- contributor has geom (idealista-style devs).
    SELECT
        r.dev_key,
        g.geom_3763,
        COALESCE(g.concelho_from_geo_portal, fb.concelho_fallback) AS concelho_resolved,
        COALESCE(g.parish_from_geo_portal,   fb.parish_fallback)   AS parish_resolved,
        COALESCE(g.geo_key_from_geo_portal,  fb.geo_key_fallback)  AS geo_key_resolved,
        nm.dominant_name,
        r.portal_refs, r.portal_unit_counts, r.n_portal_contributors
    FROM portal_dev_refs r
    JOIN portal_dev_name nm                  USING (dev_key)
    LEFT JOIN portal_dev_geo g               USING (dev_key)
    LEFT JOIN portal_dev_concelho_fallback fb USING (dev_key)
)

SELECT
    -- Tiebreak on dev_key for stable IDs on no-geom devs (ST_X/ST_Y on NULL
    -- returns NULL; PG default NULLS LAST puts them at the end deterministically).
    ROW_NUMBER() OVER (ORDER BY ST_X(pd.geom_3763), ST_Y(pd.geom_3763), pd.dev_key)::bigint
                                                                  AS unified_development_id,
    pd.geom_3763::geometry(Point, 3763)                           AS unified_geom_3763,
    ST_Transform(pd.geom_3763, 4326)::geometry(Point, 4326)       AS unified_geom_4326,
    pd.geo_key_resolved                                           AS geo_key,
    pd.concelho_resolved                                          AS concelho,
    pd.parish_resolved                                            AS parish,
    pd.dominant_name,
    pd.portal_unit_counts,
    pd.n_portal_contributors,
    pd.portal_refs,
    NOW()::timestamptz                                            AS _built_at
FROM portal_devs pd
