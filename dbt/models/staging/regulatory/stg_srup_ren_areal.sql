{{ config(tags=['srup']) }}

-- SRUP Reserva Ecológica Nacional — areal zones. OGC source, 24 properties
-- keys fully unpacked. zone_type splits `reserva_ecologica` (the constraint)
-- from `exclusao` (land formally excluded from REN — NOT a constraint,
-- severity 0). `fid` duplicates feature_id; the geom_*/reg_n/peca_grafi/etc.
-- keys are provenance metadata (see srup-properties-schema.md).
-- See wiki/concepts/srup-constraint-model.md.

SELECT
    feature_id,
    'REN_areal'::TEXT                       AS constraint_code,
    CASE
        WHEN properties->>'tipologia' ILIKE '%exclus%' THEN 'exclusao'
        ELSE 'reserva_ecologica'
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
    NULLIF(TRIM(properties->>'area_ha'), '')::DOUBLE PRECISION AS area_ha,
    TRIM(properties->>'classifica')         AS classifica,
    TRIM(properties->>'codigoobje')         AS codigoobje,
    TRIM(properties->>'dinamica')           AS dinamica,
    TRIM(properties->>'dtcc')               AS dtcc,
    TRIM(properties->>'fid_1')              AS fid_1,
    TRIM(properties->>'geom_autor')         AS geom_autor,
    TRIM(properties->>'geom_data')          AS geom_data,
    TRIM(properties->>'geom_rigor')         AS geom_rigor,
    TRIM(properties->>'id')                 AS id,
    TRIM(properties->>'peca_grafi')         AS peca_grafi,
    TRIM(properties->>'regiao')             AS regiao,
    TRIM(properties->>'reg_n')              AS reg_n,
    TRIM(properties->>'tutela')             AS tutela,
    properties,
    geom,
    ST_Transform(geom, 4326)                AS geom_wgs84,
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_srup_ren_areal') }}
WHERE geom IS NOT NULL
