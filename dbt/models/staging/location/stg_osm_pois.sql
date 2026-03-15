SELECT
    osm_id,
    code       AS osm_code,
    fclass,
    name,
    geom,
    'point'    AS geom_source,
    _load_timestamp
FROM {{ source('bronze_location', 'raw_osm_pois') }}
WHERE geom IS NOT NULL

UNION ALL

SELECT
    osm_id,
    code       AS osm_code,
    fclass,
    name,
    ST_PointOnSurface(geom) AS geom,
    'area'     AS geom_source,
    _load_timestamp
FROM {{ source('bronze_location', 'raw_osm_pois_a') }}
WHERE geom IS NOT NULL
