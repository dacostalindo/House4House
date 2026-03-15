{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_pois_geom ON {{ this }} USING GIST(geom)",
            "CREATE INDEX IF NOT EXISTS idx_pois_geom_pt ON {{ this }} USING GIST(geom_pt)",
            "CREATE INDEX IF NOT EXISTS idx_pois_src_cat ON {{ this }} (source_category)",
            "CREATE INDEX IF NOT EXISTS idx_pois_cat ON {{ this }} (category)",
            "CREATE INDEX IF NOT EXISTS idx_pois_source ON {{ this }} (source)"
        ]
    )
}}

-- POIs from OSM (point + polygon features), classified into 10 unified categories.
-- Polygons converted to interior points via ST_PointOnSurface.
-- Spatial-joined to dim_geography for geo_key + admin hierarchy.
-- ~304K rows from Geofabrik Portugal gis_osm_pois + gis_osm_pois_a layers.

WITH classified AS (
    SELECT
        osm_id::BIGINT              AS osm_id,
        name,
        fclass,
        CASE
            WHEN fclass IN ('restaurant','cafe','fast_food','bar','pub',
                            'bakery','butcher','greengrocer','beverages',
                            'food_court','biergarten')                    THEN 'food'
            WHEN fclass IN ('supermarket','convenience','mall','department_store',
                            'clothes','shoe_shop','jeweller','gift_shop','kiosk',
                            'bookshop','sports_shop','florist','furniture_shop',
                            'stationery','newsagent','mobile_phone_shop',
                            'beauty_shop','hairdresser','optician','chemist',
                            'doityourself','garden_centre','general',
                            'outdoor_shop','toy_shop','car_dealership',
                            'computer_shop','video_shop','market_place',
                            'laundry','travel_agent','bicycle_shop',
                            'car_rental','car_wash','car_sharing')        THEN 'retail'
            WHEN fclass IN ('pharmacy','hospital','clinic','dentist',
                            'doctors','veterinary','nursing_home')        THEN 'health'
            WHEN fclass IN ('school','university','kindergarten',
                            'college','library')                          THEN 'education'
            WHEN fclass IN ('bank','atm')                                 THEN 'finance'
            WHEN fclass IN ('park','dog_park','playground',
                            'picnic_site','camp_site')                    THEN 'green_space'
            WHEN fclass IN ('hotel','hostel','guesthouse','motel','chalet',
                            'swimming_pool','sports_centre','cinema','theatre',
                            'nightclub','museum','arts_centre','zoo',
                            'theme_park','ice_rink','pitch','stadium',
                            'track','golf_course','caravan_site')         THEN 'leisure'
            WHEN fclass IN ('post_office','police','fire_station','town_hall',
                            'courthouse','community_centre','prison',
                            'embassy','public_building','graveyard',
                            'toilet','drinking_water')                    THEN 'public_service'
            WHEN fclass IN ('tourist_info','viewpoint','attraction','monument',
                            'memorial','castle','fort','ruins','archaeological',
                            'lighthouse','windmill','water_mill','battlefield',
                            'alpine_hut','artwork','fountain',
                            'wayside_cross','wayside_shrine')             THEN 'tourism'
            ELSE 'other'
        END AS category,
        geom
    FROM {{ ref('stg_osm_pois') }}
)

SELECT
    ROW_NUMBER() OVER (ORDER BY c.osm_id)::BIGINT  AS poi_key,
    'osm'::VARCHAR(20)                              AS source,
    c.osm_id::TEXT                                  AS source_id,
    c.name,
    c.category,
    c.fclass                                        AS source_category,
    g.geo_key,
    g.distrito_code,
    g.distrito_name,
    g.concelho_code,
    g.concelho_name,
    g.freguesia_name,
    ST_Y(c.geom)::NUMERIC(10,7)                    AS latitude,
    ST_X(c.geom)::NUMERIC(10,7)                    AS longitude,
    c.geom,
    ST_Transform(c.geom, 3763)                      AS geom_pt,
    NOW()                                           AS _updated_at
FROM classified c
LEFT JOIN {{ ref('dim_geography') }} g
    ON ST_Within(c.geom, g.freguesia_geom)
