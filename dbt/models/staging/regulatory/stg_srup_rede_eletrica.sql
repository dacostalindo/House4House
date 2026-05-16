{{ config(tags=['srup']) }}

-- SRUP Rede Elétrica — power-line faixa de protecção. OGC source, 11
-- properties keys fully unpacked (`fid` duplicates feature_id; `dtcc` is the
-- extra). zone_type = voltage class (AT vs MAT — carries the E-Redes vs REN
-- authority split). See wiki/concepts/srup-constraint-model.md + srup-properties-schema.md.

SELECT
    feature_id,
    'RedeEletrica'::TEXT                    AS constraint_code,
    CASE
        WHEN properties->>'tipologia' ILIKE '%Muito Alta%' THEN 'servidao_eletrica_mat'
        ELSE 'servidao_eletrica_at'
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
    TRIM(properties->>'dtcc')               AS dtcc,
    properties,
    geom,
    ST_Transform(geom, 4326)                AS geom_wgs84,
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_srup_rede_eletrica') }}
WHERE geom IS NOT NULL
