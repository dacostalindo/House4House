{{ config(tags=['srup']) }}

-- SRUP Servidões Aeronáuticas (airport/aerodrome/radio-beacon zones).
-- OGC source, 10 properties keys fully unpacked. zone_type splits the
-- obstacle-clearance area (hard gate) from the general servidão and the
-- public-buildings protection zone.
-- See wiki/concepts/srup-constraint-model.md + srup-properties-schema.md.

SELECT
    feature_id,
    'Aeronautica'::TEXT                     AS constraint_code,
    CASE
        WHEN properties->>'tipologia' ILIKE '%DESOBSTRU%'  THEN 'area_desobstrucao'
        WHEN properties->>'tipologia' ILIKE '%- SERVIDÃO%' THEN 'servidao'
        ELSE 'zona_protecao'
    END                                     AS zone_type,
    TRIM(properties->>'designacao')         AS designation,
    TRIM(properties->>'servidao')           AS restriction_type,
    TRIM(properties->>'tipologia')          AS typology,
    TRIM(properties->>'lei_tipo')           AS law_type,
    TRIM(properties->>'serv_lei')           AS restriction_law,
    TRIM(properties->>'serv_dr')            AS dr_reference,
    TRIM(properties->>'serv_data')          AS restriction_date,
    TRIM(COALESCE(properties->>'serv_hiperligacao', properties->>'serv_hiper', properties->>'serv_hiperlig')) AS restriction_url,
    TRIM(properties->>'municipios')         AS municipality,
    properties,
    geom,
    ST_Transform(geom, 4326)                AS geom_wgs84,
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_srup_aeronautica') }}
WHERE geom IS NOT NULL
