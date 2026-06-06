-- Canonical Idealista development staging — normalizes
-- bronze_listings.idealista_developments to the 13-column cross-portal schema
-- consumed by silver_unified_developments (sprint-09 Slice B-prime PR-C).
-- Sibling of stg_portal_developments_remax / _zome.
--
-- Idealista quirks (per [[portal-field-map]]):
--   - canonical_name lives in `title`, not `name`. `title` is structured
--     `Empreendimento <NAME> anuncia <agency>, <freguesia> — idealista` —
--     extract NAME via regex (100% match on the Aveiro-distrito scrape, 85/85).
--   - address_text uses bronze `name` — the richest field, a street-level
--     address (e.g. "Rua de São Martinho s/n, Anta").
--   - Idealista exposes coords AND admin geography only at unit grain, not
--     dev grain. The unit_agg CTE rolls units up per development:
--       - geom = AVG of geocoded unit points.
--       - concelho/parish from `location_hierarchy`, an ordered
--         [distrito, concelho, freguesia] JSONB array (freguesia absent in
--         the 2-element form). This is reliable where the dev-level
--         `address_text` is not — e.g. dev 33035356 ("The Unique") has
--         address_text "Glória e Vera Cruz" (a freguesia) but the hierarchy
--         correctly gives concelho = Aveiro. The hierarchy is identical
--         across all units of a development (verified 85/85, 2026-05-20).
--   - No dev-grain postal code.
--
-- DISTINCT ON guard: defensive against the dlt SCD2 close-row miss documented
-- in PR-B1 (stg_portal_developments_remax). Keeps all 4 portal staging models
-- consistent + robust.

WITH active_latest AS (
    SELECT DISTINCT ON (development_id) *
    FROM {{ source('bronze_listings', 'idealista_developments') }}
    WHERE development_id IS NOT NULL
      AND _dlt_valid_to IS NULL
    ORDER BY development_id, _dlt_valid_from DESC
),

-- Roll the development's units up to dev grain: centroid + admin geography.
-- location_hierarchy is dev-constant, so MODE() just picks that single value.
unit_agg AS (
    SELECT
        development_id,
        AVG(latitude)  AS avg_lat,
        AVG(longitude) AS avg_lng,
        COUNT(*) FILTER (WHERE latitude IS NOT NULL AND longitude IS NOT NULL)
            AS n_geocoded_units,
        MODE() WITHIN GROUP (ORDER BY location_hierarchy) AS location_hierarchy
    FROM {{ source('bronze_listings', 'idealista_development_units') }}
    WHERE development_id IS NOT NULL
      AND _dlt_valid_to IS NULL
    GROUP BY development_id
)

, dev_typed AS (
    SELECT
        'idealista'::TEXT                                            AS portal,
        d.development_id::TEXT                                       AS portal_dev_id,
        (regexp_match(d.title, '^Empreendimento (.+?) anuncia '))[1] AS canonical_name,
        d.name                                                       AS address_text,
        UPPER(TRIM(u.location_hierarchy ->> 1))                      AS concelho,
        u.location_hierarchy ->> 2                                   AS parish,
        NULL::TEXT                                                   AS postal_code,
        CASE
            WHEN u.avg_lat IS NOT NULL AND u.avg_lng IS NOT NULL
            THEN ST_Transform(
                ST_SetSRID(ST_MakePoint(u.avg_lng::FLOAT, u.avg_lat::FLOAT), 4326),
                3763
            )
        END                                                          AS geom_3763,
        CASE
            WHEN u.avg_lat IS NOT NULL AND u.avg_lng IS NOT NULL
            THEN ST_SetSRID(ST_MakePoint(u.avg_lng::FLOAT, u.avg_lat::FLOAT), 4326)
        END                                                          AS geom_4326,
        d.units_count::INTEGER                                       AS total_units,
        d.development_url                                            AS listing_url,
        jsonb_build_object(
            'title_raw', d.title,
            'location_hierarchy', u.location_hierarchy,
            'area_slug', d.area_slug,
            'min_price', d.min_price,
            'typology_summary', d.typology_summary,
            'is_completed', d.is_completed,
            'promoter_name', d.promoter_name,
            'n_geocoded_units', u.n_geocoded_units
        )                                                            AS raw_meta
    FROM active_latest d
    LEFT JOIN unit_agg u USING (development_id)
)

SELECT
    db.*,
    {{ normalize_dev_name('canonical_name') }}                       AS match_name,
    g.geo_key,
    g.concelho_name                                                  AS geo_concelho_name,
    g.freguesia_name                                                 AS geo_parish_name,
    NOW()::TIMESTAMPTZ                                               AS _loaded_at
FROM dev_typed db
LEFT JOIN LATERAL (
    SELECT g.geo_key, g.concelho_name, g.freguesia_name
    FROM {{ ref('dim_geography') }} g
    WHERE g.is_current
      AND ST_Contains(g.freguesia_geom_pt, db.geom_3763)
    LIMIT 1
) g ON TRUE
