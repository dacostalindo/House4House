SELECT
    feature_id,
    category,
    feature_type,
    TRIM(properties->>'CONCELHO')  AS municipality,
    TRIM(properties->>'SERVIDAO')  AS restriction_type,
    TRIM(properties->>'DINAMICA')  AS dynamics,
    TRIM(properties->>'RIGOR')     AS accuracy,
    TRIM(properties->>'AUTOR')     AS author,
    TRIM(properties->>'DATA')      AS data_date,
    properties,
    geom,
    ST_Transform(geom, 4326) AS geom_wgs84,
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_srup_ran') }}
WHERE geom IS NOT NULL
