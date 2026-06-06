-- Canonical imovirtual development staging — normalizes
-- bronze_listings.imovirtual_developments to the 13-column cross-portal schema
-- consumed by silver_unified_developments. 5th portal arm (Sprint-09 follow-up).
--
-- imovirtual quirks (per [[portal-field-map]] / 2026-06-05 onboarding decision):
--   - Concelho/parish/distrito are TYPED + come directly from
--     location.reverseGeocoding — no parsing, no compose, no UPPER guesswork.
--   - Dev-level lat/lon are double precision floats (no VARCHAR cast).
--   - TWO unit counts in bronze: total_units = number_of_units_in_project
--     (TRUE project size) and listed_units_count = paginatedUnits.totalResults
--     (currently-advertised subset). We expose the TRUE total here — this is
--     imovirtual's data-quality edge over idealista (which only ever reports
--     the listed subset). listed_units_count goes to raw_meta for inspection.
--   - total_units is a TEXT pivot from topInformation.values[0] — NULLIF + cast.
--   - listing_url is bronze `url` (full /pt/empreendimento/{slug}/ URL).
--   - No dev-level postal code (reverseGeocoding stops at parish).
--
-- DISTINCT ON guard: consistent with the other 4 staging models — defensive
-- against SCD2 close-row misses across runs.

WITH active_latest AS (
    SELECT DISTINCT ON (development_id) *
    FROM {{ source('bronze_listings', 'imovirtual_developments') }}
    WHERE development_id IS NOT NULL
      AND _dlt_valid_to IS NULL
    ORDER BY development_id, _dlt_valid_from DESC
),

dev_typed AS (
    SELECT
        'imovirtual'::TEXT                                                    AS portal,
        development_id::TEXT                                                  AS portal_dev_id,
        name                                                                  AS canonical_name,
        address_text                                                          AS address_text,
        UPPER(TRIM(concelho))                                                 AS concelho,
        parish                                                                AS parish,
        NULL::TEXT                                                            AS postal_code,
        CASE
            WHEN gps_lat IS NOT NULL AND gps_lon IS NOT NULL
            THEN ST_Transform(
                ST_SetSRID(ST_MakePoint(gps_lon, gps_lat), 4326),
                3763
            )
        END                                                                   AS geom_3763,
        CASE
            WHEN gps_lat IS NOT NULL AND gps_lon IS NOT NULL
            THEN ST_SetSRID(ST_MakePoint(gps_lon, gps_lat), 4326)
        END                                                                   AS geom_4326,
        NULLIF(total_units::TEXT, '')::INTEGER                                AS total_units,
        url                                                                   AS listing_url,
        jsonb_build_object(
            'slug', slug,
            'status', status,
            'category_type', category_type,
            'distrito', distrito,
            'listed_units_count', listed_units_count,
            'price_per_m_from', price_per_m_from,
            'area_from', area_from,
            'area_to', area_to,
            'state', state,
            'offered_estates_type', offered_estates_type,
            'promoter_id', promoter_id,
            'promoter_name', promoter_name,
            'created_at', created_at,
            'modified_at', modified_at
        )                                                                     AS raw_meta
    FROM active_latest
)

SELECT
    db.*,
    {{ normalize_dev_name('canonical_name') }}                                AS match_name,
    g.geo_key,
    g.concelho_name                                                           AS geo_concelho_name,
    g.freguesia_name                                                          AS geo_parish_name,
    NOW()::TIMESTAMPTZ                                                        AS _loaded_at
FROM dev_typed db
LEFT JOIN LATERAL (
    SELECT g.geo_key, g.concelho_name, g.freguesia_name
    FROM {{ ref('dim_geography') }} g
    WHERE g.is_current
      AND ST_Contains(g.freguesia_geom_pt, db.geom_3763)
    LIMIT 1
) g ON TRUE
