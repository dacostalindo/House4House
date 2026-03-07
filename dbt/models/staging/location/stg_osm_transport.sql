SELECT
    osm_id,
    code                            AS osm_code,
    fclass,
    name,
    geom,
    _load_timestamp
FROM {{ source('bronze_location', 'raw_osm_transport') }}
WHERE geom IS NOT NULL
