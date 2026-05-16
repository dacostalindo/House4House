{{ config(tags=['srup']) }}

-- SRUP Reserva Agrícola Nacional — sourced from the OGC API path
-- (raw_srup_ran_ogc) as of 2026-05-13. One of the 14 SRUP constraint
-- layers; uniform output schema (constraint_code + zone_type + the
-- constraint-relevant servidao/tipologia/lei fields). See
-- wiki/concepts/srup-constraint-model.md. Full properties unpacking is PR 3.

SELECT
    feature_id,
    'RAN'::TEXT                             AS constraint_code,
    'reserva_agricola'::TEXT                AS zone_type,
    TRIM(properties->>'designacao')         AS designation,
    TRIM(properties->>'servidao')           AS restriction_type,
    TRIM(properties->>'tipologia')          AS typology,
    TRIM(properties->>'lei_tipo')           AS law_type,
    TRIM(properties->>'serv_lei')           AS restriction_law,
    TRIM(properties->>'serv_dr')            AS dr_reference,
    TRIM(properties->>'serv_data')          AS restriction_date,
    TRIM(COALESCE(properties->>'serv_hiperligacao', properties->>'serv_hiper', properties->>'serv_hiperlig')) AS restriction_url,
    TRIM(COALESCE(properties->>'municipios', properties->>'concelho', properties->>'conselho', properties->>'municipio')) AS municipality,
    properties,
    geom,
    ST_Transform(geom, 4326)                AS geom_wgs84,
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_srup_ran_ogc') }}
WHERE geom IS NOT NULL
