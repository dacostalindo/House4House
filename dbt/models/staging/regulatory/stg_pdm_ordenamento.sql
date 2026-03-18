SELECT
    feature_id,
    municipality_code,
    TRIM(municipality_name)  AS municipality_name,
    TRIM(classe)             AS land_classification,
    TRIM(categoria)          AS land_category,
    TRIM(designacao)         AS land_designation,
    area_ha,
    TRIM(escala)             AS map_scale,
    data_publicacao_pdm      AS pdm_publication_date,
    geom,
    ST_Transform(geom, 4326) AS geom_wgs84,
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_pdm_ordenamento') }}
WHERE geom IS NOT NULL
