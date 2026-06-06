-- Canonical Zome development staging — normalizes bronze_listings.zome_developments
-- to the 13-column cross-portal schema consumed by silver_unified_developments
-- (sprint-09 Slice B-prime PR-C). Sibling of stg_portal_developments_remax.
--
-- Zome quirks (per [[portal-field-map]]):
--   - Geocoords are stored as VARCHAR — cast via NULLIF + ::FLOAT.
--   - `regiao` is a JSONB int-array of region codes (not a free-text address);
--     address_text is composed from the localizacaolevel* hierarchy instead.
--   - No dev-level postal code.
--   - Total units = available + reserved + sold (Zome doesn't store a single total).
--
-- DISTINCT ON guard: defensive against the dlt SCD2 close-row miss documented
-- in PR-B1 (stg_portal_developments_remax). zome_developments verified 0 dupes
-- at the 2026-05-20 clean re-scrape, but the guard keeps all 4 portal staging
-- models consistent + robust.

WITH active_latest AS (
    SELECT DISTINCT ON (venture_id) *
    FROM {{ source('bronze_listings', 'zome_developments') }}
    WHERE venture_id IS NOT NULL
      AND _dlt_valid_to IS NULL
    ORDER BY venture_id, _dlt_valid_from DESC
),

dev_typed AS (
    SELECT
        'zome'::TEXT                                                          AS portal,
        venture_id::TEXT                                                      AS portal_dev_id,
        nome                                                                  AS canonical_name,
        NULLIF(TRIM(CONCAT_WS(', ', localizacaolevel3, localizacaolevel2)), '') AS address_text,
        UPPER(TRIM(localizacaolevel2))                                        AS concelho,
        localizacaolevel3                                                     AS parish,
        NULL::TEXT                                                            AS postal_code,
        CASE
            WHEN NULLIF(geocoordinateslat, '') IS NOT NULL
             AND NULLIF(geocoordinateslong, '') IS NOT NULL
            THEN ST_Transform(
                ST_SetSRID(ST_MakePoint(geocoordinateslong::FLOAT, geocoordinateslat::FLOAT), 4326),
                3763
            )
        END                                                                   AS geom_3763,
        CASE
            WHEN NULLIF(geocoordinateslat, '') IS NOT NULL
             AND NULLIF(geocoordinateslong, '') IS NOT NULL
            THEN ST_SetSRID(ST_MakePoint(geocoordinateslong::FLOAT, geocoordinateslat::FLOAT), 4326)
        END                                                                   AS geom_4326,
        (
            COALESCE(imoveisdisponiveis, 0)
            + COALESCE(imoveisreservados, 0)
            + COALESCE(imoveisvendidos, 0)
        )::INTEGER                                                            AS total_units,
        url_user_link                                                         AS listing_url,
        jsonb_build_object(
            'emid', emid,
            'precosemformatacao', precosemformatacao,
            'tipologiagrupos', tipologiagrupos,
            'imoveisdisponiveis', imoveisdisponiveis,
            'imoveisreservados', imoveisreservados,
            'imoveisvendidos', imoveisvendidos,
            'idestado', idestado,
            'deschub', deschub
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
