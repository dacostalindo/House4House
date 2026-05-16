{{ config(tags=['srup']) }}

-- SRUP Imóveis Classificados / Património Cultural — legacy WFS source
-- (raw_srup_ic, UPPERCASE property keys), 21 keys fully unpacked. zone_type
-- splits `monumento` (the classified monument itself — Point geometry) from
-- `zona_protecao` (the ZEP / protection zone — Polygon / GeometryCollection).
-- CLASSIFICACAO carries the monument class (MN/IIP/ZEP/...) → mapped to typology.
-- See wiki/concepts/srup-constraint-model.md + srup-properties-schema.md.

SELECT
    feature_id,
    'IC'::TEXT                              AS constraint_code,
    CASE
        WHEN ST_GeometryType(geom) = 'ST_Point' THEN 'monumento'
        ELSE 'zona_protecao'
    END                                     AS zone_type,
    TRIM(properties->>'DESIGNACAO')         AS designation,
    TRIM(properties->>'SERVIDAO')           AS restriction_type,
    TRIM(properties->>'CLASSIFICACAO')      AS typology,
    TRIM(properties->>'LEI_TIPO')           AS law_type,
    TRIM(properties->>'SERV_LEI')           AS restriction_law,
    TRIM(properties->>'SERV_DR')            AS dr_reference,
    TRIM(properties->>'SERV_DATA')          AS restriction_date,
    TRIM(properties->>'SERV_HIPERLINK')     AS restriction_url,
    TRIM(properties->>'MUNICIPIOS')         AS municipality,
    NULLIF(TRIM(properties->>'AREA_HA'), '')::DOUBLE PRECISION AS area_ha,
    TRIM(properties->>'ESTADO')             AS estado,
    TRIM(properties->>'FREGUESIAS')         AS freguesias,
    TRIM(properties->>'GEOMETRIA_AUTOR')    AS geometria_autor,
    TRIM(properties->>'GEOMETRIA_DATA')     AS geometria_data,
    TRIM(properties->>'GEOMETRIA_RIGOR')    AS geometria_rigor,
    TRIM(properties->>'ID')                 AS id,
    TRIM(properties->>'LOCAL')              AS local,
    TRIM(properties->>'NOTAS_GEOREF')       AS notas_georef,
    TRIM(properties->>'REGIAO')             AS regiao,
    TRIM(properties->>'SITUACAO')           AS situacao,
    TRIM(properties->>'TUTELA')             AS tutela,
    properties,
    geom,
    ST_Transform(geom, 4326)                AS geom_wgs84,
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_srup_ic') }}
WHERE geom IS NOT NULL
