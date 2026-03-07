{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_pois_geom ON {{ this }} USING GIST(geom)",
            "CREATE INDEX IF NOT EXISTS idx_pois_geom_pt ON {{ this }} USING GIST(geom_pt)",
            "CREATE INDEX IF NOT EXISTS idx_pois_fclass ON {{ this }} (fclass)",
            "CREATE INDEX IF NOT EXISTS idx_pois_cat ON {{ this }} (category)"
        ]
    )
}}

-- TODO (Sprint 5): Clean OSM POIs and assign category groupings.
-- Depends on: stg_osm_pois, dim_geography
--
-- Transformations needed:
--   osm_id TEXT → BIGINT cast
--   fclass → category mapping (CASE expression):
--     'restaurant','cafe','fast_food' → 'food'
--     'pharmacy','hospital','clinic' → 'health'
--     'bank','atm' → 'finance'
--     'supermarket','mall','convenience' → 'retail'
--     'school','university','kindergarten' → 'education'
--     'park','nature_reserve' → 'green_space'
--     all others → 'other'
--   geom EPSG:4326 → geom_pt EPSG:3763 via ST_Transform
--   spatial join with dim_geography → geo_key

SELECT
    NULL::BIGINT            AS poi_key,
    NULL::BIGINT            AS osm_id,
    NULL::VARCHAR(300)      AS name,
    NULL::VARCHAR(50)       AS fclass,
    NULL::VARCHAR(30)       AS category,
    NULL::INTEGER           AS geo_key,
    NULL::NUMERIC(10,7)     AS latitude,
    NULL::NUMERIC(10,7)     AS longitude,
    NULL::GEOMETRY          AS geom,
    NULL::GEOMETRY          AS geom_pt,
    NOW()                   AS _updated_at
WHERE FALSE
