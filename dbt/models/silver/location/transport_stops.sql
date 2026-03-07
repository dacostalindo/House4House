{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_ts_geom ON {{ this }} USING GIST(geom)",
            "CREATE INDEX IF NOT EXISTS idx_ts_geom_pt ON {{ this }} USING GIST(geom_pt)",
            "CREATE INDEX IF NOT EXISTS idx_ts_type ON {{ this }} (stop_type)"
        ]
    )
}}

-- TODO (Sprint 5): Clean and classify OSM transport stops.
-- Depends on: stg_osm_transport, dim_geography
--
-- Transformations needed:
--   fclass → stop_type mapping:
--     'railway_station' → 'rail', 'bus_stop' → 'bus',
--     'subway_entrance' → 'metro', 'tram_stop' → 'tram', 'ferry_terminal' → 'ferry'
--   geom EPSG:4326 → geom_pt EPSG:3763 via ST_Transform
--   spatial join with dim_geography (ST_Within) → geo_key
--   osm_id TEXT → BIGINT cast

SELECT
    NULL::BIGINT            AS stop_key,
    NULL::VARCHAR(200)      AS stop_name,
    NULL::VARCHAR(30)       AS stop_type,
    NULL::VARCHAR(100)      AS operator,
    NULL::BOOLEAN           AS is_interchange,
    NULL::INTEGER           AS geo_key,
    NULL::NUMERIC(10,7)     AS latitude,
    NULL::NUMERIC(10,7)     AS longitude,
    NULL::GEOMETRY          AS geom,
    NULL::GEOMETRY          AS geom_pt,
    NULL::BOOLEAN           AS is_planned,
    NOW()                   AS _updated_at
WHERE FALSE
