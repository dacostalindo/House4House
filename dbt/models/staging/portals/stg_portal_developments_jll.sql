-- Canonical JLL development staging — normalizes bronze_listings.jll_developments
-- to the 13-column cross-portal schema consumed by silver_unified_developments
-- (sprint-09 Slice B-prime PR-C). Sibling of stg_portal_developments_remax /
-- _zome / _idealista.
--
-- JLL quirks (per [[portal-field-map]]):
--   - Cleanest of the 4 portals: typed `municipality` / `parish` / `district`
--     columns + double-precision `gps_lat` / `gps_lon` — no casts needed.
--   - `has_gps_location` is an explicit reliability flag; geom is dropped when
--     it is FALSE even if coords are present.
--   - JLL exposes no public listing URL (no URL field in the API payload),
--     so `listing_url` is NULL.
--   - 0 Aveiro coverage as of the 2026-05-20 audit — JLL operates only in
--     Lisboa/Porto/Faro/Setúbal. This model contributes 0 rows to the v1
--     Aveiro-scoped silver; building it now future-proofs the silver UNION
--     for the sprint-10 portal expansion.
--
-- DISTINCT ON guard: defensive against the dlt SCD2 close-row miss documented
-- in PR-B1 (stg_portal_developments_remax). Keeps all 4 portal staging models
-- consistent + robust.

WITH active_latest AS (
    SELECT DISTINCT ON (development_id) *
    FROM {{ source('bronze_listings', 'jll_developments') }}
    WHERE development_id IS NOT NULL
      AND _dlt_valid_to IS NULL
    ORDER BY development_id, _dlt_valid_from DESC
),

dev_typed AS (
    SELECT
        'jll'::TEXT                                                  AS portal,
        development_id::TEXT                                         AS portal_dev_id,
        COALESCE(title, name)                                        AS canonical_name,
        address                                                      AS address_text,
        UPPER(TRIM(municipality))                                    AS concelho,
        parish                                                       AS parish,
        zip_code                                                     AS postal_code,
        CASE
            WHEN has_gps_location AND gps_lat IS NOT NULL AND gps_lon IS NOT NULL
            THEN ST_Transform(
                ST_SetSRID(ST_MakePoint(gps_lon, gps_lat), 4326),
                3763
            )
        END                                                          AS geom_3763,
        CASE
            WHEN has_gps_location AND gps_lat IS NOT NULL AND gps_lon IS NOT NULL
            THEN ST_SetSRID(ST_MakePoint(gps_lon, gps_lat), 4326)
        END                                                          AS geom_4326,
        total_fractions::INTEGER                                     AS total_units,
        NULL::TEXT                                                   AS listing_url,
        jsonb_build_object(
            'uid', uid,
            'district', district,
            'status', status,
            'availability', availability,
            'condition', condition,
            'year', year,
            'total_available_fractions', total_available_fractions,
            'min_property_formatted_price', min_property_formatted_price,
            'max_property_formatted_price', max_property_formatted_price
        )                                                            AS raw_meta
    FROM active_latest
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
