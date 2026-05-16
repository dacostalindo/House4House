{{ config(tags=['srup']) }}

-- SRUP Reserva Ecológica Nacional — linear watercourse lines/beds
-- (MultiLineString). OGC source, 20 properties keys fully unpacked. No
-- serv_dr / serv_hiper keys in this layer (dr_reference / restriction_url
-- resolve to NULL). fn_assess_polygon buffers this by 10 m (DL 166/2008
-- margem). `compriment` is the watercourse length in metres.
-- See wiki/concepts/srup-constraint-model.md + srup-properties-schema.md.

SELECT
    feature_id,
    'REN_linear'::TEXT                      AS constraint_code,
    'linha_de_agua'::TEXT                   AS zone_type,
    TRIM(properties->>'designacao')         AS designation,
    TRIM(properties->>'servidao')           AS restriction_type,
    TRIM(properties->>'tipologia')          AS typology,
    TRIM(properties->>'lei_tipo')           AS law_type,
    TRIM(properties->>'serv_lei')           AS restriction_law,
    TRIM(properties->>'serv_dr')            AS dr_reference,
    TRIM(properties->>'serv_data')          AS restriction_date,
    TRIM(COALESCE(properties->>'serv_hiperligacao', properties->>'serv_hiper', properties->>'serv_hiperlig')) AS restriction_url,
    TRIM(COALESCE(properties->>'municipios', properties->>'concelho', properties->>'conselho', properties->>'municipio')) AS municipality,
    NULLIF(TRIM(properties->>'compriment'), '')::DOUBLE PRECISION AS compriment,
    TRIM(properties->>'classifica')         AS classifica,
    TRIM(properties->>'codigoobje')         AS codigoobje,
    TRIM(properties->>'dinamica')           AS dinamica,
    TRIM(properties->>'dtcc')               AS dtcc,
    TRIM(properties->>'estado')             AS estado,
    TRIM(properties->>'geometria_')         AS geometria_,
    TRIM(properties->>'id')                 AS id,
    TRIM(properties->>'id1')                AS id1,
    TRIM(properties->>'id_servdao')         AS id_servdao,
    TRIM(properties->>'id_servida')         AS id_servida,
    TRIM(properties->>'regiao')             AS regiao,
    properties,
    geom,
    ST_Transform(geom, 4326)                AS geom_wgs84,
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_srup_ren_linear') }}
WHERE geom IS NOT NULL
