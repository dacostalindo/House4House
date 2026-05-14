{{ config(tags=['srup']) }}

-- SRUP Defesa Militar — UNION of raw_srup_defesa_militar (servidão zones)
-- and raw_srup_defesa_militar_zonas (graduated Zona 1-4 / terreno militar).
-- Both OGC sources, 10 properties keys each, fully unpacked. zone_type
-- collapses the graduation into `nucleo` (terreno militar / Zona 1 /
-- "MILITAR - SERVIDÃO") and `zona_protecao` (everything else).
-- See wiki/concepts/srup-constraint-model.md + srup-properties-schema.md.

WITH unioned AS (
    SELECT feature_id, properties, geom, _source_url, _load_timestamp
    FROM {{ source('bronze_regulatory', 'raw_srup_defesa_militar') }}
    UNION ALL
    SELECT feature_id, properties, geom, _source_url, _load_timestamp
    FROM {{ source('bronze_regulatory', 'raw_srup_defesa_militar_zonas') }}
)

SELECT
    feature_id,
    'DefesaMilitar'::TEXT                   AS constraint_code,
    CASE
        WHEN properties->>'tipologia' ILIKE '%TERRENO MILITAR%'
          OR properties->>'tipologia' ILIKE '%- SERVIDÃO%'
          OR properties->>'tipologia' ILIKE '%ZONA 1%'
          OR properties->>'tipologia' ILIKE '%ZONA1%'
            THEN 'nucleo'
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
FROM unioned
WHERE geom IS NOT NULL
