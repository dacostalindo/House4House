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

-- OSM transport stops classified by mode, reprojected to 3763,
-- and spatial-joined to dim_geography for geo_key.
-- ~48.9K rows from Geofabrik Portugal gis_osm_transport_free layer.

WITH classified AS (
    SELECT
        osm_id::BIGINT                              AS osm_id,
        name                                        AS stop_name,
        CASE fclass
            WHEN 'railway_station'  THEN 'rail'
            WHEN 'railway_halt'     THEN 'rail'
            WHEN 'bus_stop'         THEN 'bus'
            WHEN 'bus_station'      THEN 'bus'
            WHEN 'tram_stop'        THEN 'tram'
            WHEN 'subway_entrance'  THEN 'metro'
            WHEN 'ferry_terminal'   THEN 'ferry'
            WHEN 'taxi'             THEN 'taxi'
            WHEN 'airport'          THEN 'air'
            WHEN 'helipad'          THEN 'air'
            WHEN 'airfield'         THEN 'air'
            ELSE 'other'
        END                                         AS stop_type,
        geom
    FROM {{ ref('stg_osm_transport') }}
)

SELECT
    ROW_NUMBER() OVER (ORDER BY c.osm_id)::BIGINT   AS stop_key,
    c.stop_name,
    c.stop_type,
    NULL::VARCHAR(100)                               AS operator,
    NULL::BOOLEAN                                    AS is_interchange,
    g.geo_key,
    g.distrito_code,
    g.distrito_name,
    g.concelho_code,
    g.concelho_name,
    g.freguesia_name,
    ST_Y(c.geom)::NUMERIC(10,7)                     AS latitude,
    ST_X(c.geom)::NUMERIC(10,7)                     AS longitude,
    c.geom,
    ST_Transform(c.geom, 3763)                       AS geom_pt,
    FALSE                                            AS is_planned,
    NOW()                                            AS _updated_at
FROM classified c
LEFT JOIN {{ ref('dim_geography') }} g
    ON ST_Within(c.geom, g.freguesia_geom)
