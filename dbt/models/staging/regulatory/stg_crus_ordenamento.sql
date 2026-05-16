-- Sourced from the national OGC API path (raw_crus_national_ogc) as of 2026-05-13.
-- The legacy per-município WFS path (raw_crus_ordenamento) was retired in the same commit
-- after the OGC API was confirmed to cover the same data nationally; see wiki/log.md.
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
FROM {{ source('bronze_regulatory', 'raw_crus_national_ogc') }}
WHERE geom IS NOT NULL
