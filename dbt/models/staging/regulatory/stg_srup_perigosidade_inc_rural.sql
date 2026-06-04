{{ config(tags=['srup']) }}

-- SRUP Perigosidade de Incêndio Rural — wildfire-risk classification map.
-- Source: bronze_regulatory.raw_srup_perigosidade_inc_rural (1.78M national
-- features; ~3.1k for Aveiro). Each feature is a MultiPolygon classified
-- in one of 5 tipologias: Muito Alta / Alta / Média / Baixa / Muito Baixa.
--
-- Aveiro PDM Art. 51 makes this layer the PRIMARY GATE for Solo Rústico
-- construction:
--   - Art. 51/1/a: hard prohibition where tipologia ∈ {alta, muito_alta}
--                 outside áreas edificadas consolidadas
--   - Art. 51/1/b: conditional permission where tipologia ∈ {média, baixa,
--                 muito_baixa} subject to 50m faixa de proteção + parecer CMDF
--
-- Legal basis: Decreto-Lei 124/2006 (am. DL 14/2019, DL 82/2021) +
-- per-município PMDFCI (Plano Municipal de Defesa da Floresta Contra Incêndios).
-- Authority: CMDF (Comissão Municipal de Defesa da Floresta).
--
-- Uniform 17-column SRUP contract — same shape as stg_srup_ran/zpe/etc.

SELECT
    feature_id,
    'Perigosidade_Incendio_Rural'::TEXT     AS constraint_code,
    -- Normalize tipologia to kebab-case slug aligned with dim_constraint_severity:
    --   Muito Alta  → perigosidade_muito_alta
    --   Alta        → perigosidade_alta
    --   Média       → perigosidade_media
    --   Baixa       → perigosidade_baixa
    --   Muito Baixa → perigosidade_muito_baixa
    --   NULL/other  → perigosidade_nao_classificada
    CASE
        WHEN UPPER(TRIM(properties->>'tipologia')) = 'MUITO ALTA' THEN 'perigosidade_muito_alta'
        WHEN UPPER(TRIM(properties->>'tipologia')) = 'ALTA'       THEN 'perigosidade_alta'
        WHEN UPPER(TRIM(properties->>'tipologia')) = 'MÉDIA'      THEN 'perigosidade_media'
        WHEN UPPER(TRIM(properties->>'tipologia')) = 'MEDIA'      THEN 'perigosidade_media'
        WHEN UPPER(TRIM(properties->>'tipologia')) = 'BAIXA'      THEN 'perigosidade_baixa'
        WHEN UPPER(TRIM(properties->>'tipologia')) = 'MUITO BAIXA' THEN 'perigosidade_muito_baixa'
        ELSE 'perigosidade_nao_classificada'
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
    properties,
    geom,
    ST_Transform(geom, 4326)                AS geom_wgs84,
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_srup_perigosidade_inc_rural') }}
WHERE geom IS NOT NULL
