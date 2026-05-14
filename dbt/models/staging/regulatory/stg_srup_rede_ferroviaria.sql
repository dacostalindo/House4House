{{ config(tags=['srup']) }}

-- SRUP Rede Ferroviária — UNION of raw_srup_rede_ferroviaria (line servidão)
-- and raw_srup_rede_ferroviaria_estacoes (station/halt yards). Both OGC
-- sources, 11 properties keys each, fully unpacked (`fid` duplicates
-- feature_id; `codigo` is the extra; feature_id is NOT unique post-union).
-- zone_type: active vs inactive line vs station — see
-- wiki/concepts/srup-constraint-model.md + srup-properties-schema.md.

WITH unioned AS (
    SELECT
        feature_id, properties, geom, _source_url, _load_timestamp,
        CASE
            WHEN properties->>'tipologia' ILIKE '%sem explora%'
              OR properties->>'tipologia' ILIKE '%antigo%'
                THEN 'servidao_ferroviaria_inativa'
            ELSE 'servidao_ferroviaria_ativa'
        END AS zone_type
    FROM {{ source('bronze_regulatory', 'raw_srup_rede_ferroviaria') }}

    UNION ALL

    SELECT
        feature_id, properties, geom, _source_url, _load_timestamp,
        'servidao_ferroviaria_estacao'::TEXT AS zone_type
    FROM {{ source('bronze_regulatory', 'raw_srup_rede_ferroviaria_estacoes') }}
)

SELECT
    feature_id,
    'RedeFerroviaria'::TEXT                 AS constraint_code,
    zone_type,
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
FROM unioned
WHERE geom IS NOT NULL
