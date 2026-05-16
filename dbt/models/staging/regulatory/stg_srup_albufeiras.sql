{{ config(tags=['srup']) }}

-- SRUP Albufeiras de Águas Públicas Classificadas — public-reservoir
-- protection zones. OGC source, 10 properties keys fully unpacked
-- (`fid` duplicates feature_id). zone_type = the 3-tier classification
-- (protegida / condicionada / livre) from tipologia.
-- See wiki/concepts/srup-constraint-model.md + srup-properties-schema.md.

SELECT
    feature_id,
    'Albufeiras'::TEXT                      AS constraint_code,
    CASE
        WHEN properties->>'tipologia' ILIKE '%PROTEGIDA%'    THEN 'protegida'
        WHEN properties->>'tipologia' ILIKE '%CONDICIONADA%' THEN 'condicionada'
        ELSE 'livre'
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
FROM {{ source('bronze_regulatory', 'raw_srup_albufeiras') }}
WHERE geom IS NOT NULL
