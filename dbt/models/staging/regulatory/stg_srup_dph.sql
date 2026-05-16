{{ config(tags=['srup']) }}

-- SRUP Domínio Público Hídrico — legacy WFS source (raw_srup_dph, UPPERCASE
-- property keys), 18 keys fully unpacked. No CLASSIFICACAO key → typology is
-- NULL. zone_type is carried explicitly in SERVIDAO: splits `non_aedificandi`
-- (construction prohibited) from `ocupacao_condicionada` (conditioned on APA
-- authorization). See wiki/concepts/srup-constraint-model.md + srup-properties-schema.md.

SELECT
    feature_id,
    'DPH'::TEXT                             AS constraint_code,
    CASE
        WHEN properties->>'SERVIDAO' ILIKE '%NON AEDIFICANDI%' THEN 'non_aedificandi'
        ELSE 'ocupacao_condicionada'
    END                                     AS zone_type,
    TRIM(properties->>'DESIGNACAO')         AS designation,
    TRIM(properties->>'SERVIDAO')           AS restriction_type,
    CAST(NULL AS TEXT)                      AS typology,
    TRIM(properties->>'LEI_TIPO')           AS law_type,
    TRIM(properties->>'SERV_LEI')           AS restriction_law,
    TRIM(properties->>'SERV_DR')            AS dr_reference,
    TRIM(properties->>'SERV_DATA')          AS restriction_date,
    TRIM(properties->>'SERV_HIPERLINK')     AS restriction_url,
    TRIM(properties->>'MUNICIPIOS')         AS municipality,
    NULLIF(TRIM(properties->>'AREA_HA'), '')::DOUBLE PRECISION AS area_ha,
    TRIM(properties->>'ESTADO')             AS estado,
    TRIM(properties->>'GEOMETRIA_AUTOR')    AS geometria_autor,
    TRIM(properties->>'GEOMETRIA_DATA')     AS geometria_data,
    TRIM(properties->>'GEOMETRIA_RIGOR')    AS geometria_rigor,
    TRIM(properties->>'ID')                 AS id,
    TRIM(properties->>'LOCAL')              AS local,
    TRIM(properties->>'REGIAO')             AS regiao,
    TRIM(properties->>'SITUACAO')           AS situacao,
    TRIM(properties->>'TUTELA')             AS tutela,
    properties,
    geom,
    ST_Transform(geom, 4326)                AS geom_wgs84,
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_srup_dph') }}
WHERE geom IS NOT NULL
