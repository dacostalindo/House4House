{{ config(tags=['srup']) }}

-- SRUP Rede Viária — road non-aedificandi servidão. OGC source, 11 properties
-- keys fully unpacked (`fid` duplicates feature_id; `codigo` is the extra).
-- zone_type = road class; fn_assess_polygon buffers from the axis (50/35/20 m
-- by class) via dim_constraint_severity.buffer_ref = 'axis'.
-- See wiki/concepts/srup-constraint-model.md + srup-properties-schema.md.

SELECT
    feature_id,
    'RedeViaria'::TEXT                      AS constraint_code,
    CASE
        WHEN properties->>'tipologia' ILIKE '%(IP)%'
          OR properties->>'tipologia' ILIKE '%Auto-estrada%' THEN 'servidao_rodoviaria_ip'
        WHEN properties->>'tipologia' ILIKE '%(IC)%'         THEN 'servidao_rodoviaria_ic'
        ELSE 'servidao_rodoviaria_local'
    END                                     AS zone_type,
    TRIM(properties->>'designacao')         AS designation,
    TRIM(properties->>'servidao')           AS restriction_type,
    TRIM(properties->>'tipologia')          AS typology,
    TRIM(properties->>'lei_tipo')           AS law_type,
    TRIM(properties->>'serv_lei')           AS restriction_law,
    TRIM(properties->>'serv_dr')            AS dr_reference,
    TRIM(properties->>'serv_data')          AS restriction_date,
    TRIM(COALESCE(properties->>'serv_hiperligacao', properties->>'serv_hiper', properties->>'serv_hiperlig')) AS restriction_url,
    TRIM(COALESCE(properties->>'municipios', properties->>'concelho', properties->>'conselho', properties->>'municipio')) AS municipality,
    TRIM(properties->>'codigo')             AS codigo,
    properties,
    geom,
    ST_Transform(geom, 4326)                AS geom_wgs84,
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_srup_rede_viaria') }}
WHERE geom IS NOT NULL
