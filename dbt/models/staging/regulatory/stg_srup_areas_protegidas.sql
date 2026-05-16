{{ config(tags=['srup']) }}

-- SRUP Áreas Protegidas (Parque/Reserva Natural, Paisagem Protegida, etc.).
-- OGC source, 11 properties keys fully unpacked (`fid` duplicates feature_id;
-- `codigo` is the layer-specific extra).
-- See wiki/concepts/srup-constraint-model.md + srup-properties-schema.md.

SELECT
    feature_id,
    'AreasProtegidas'::TEXT                 AS constraint_code,
    'area_protegida'::TEXT                  AS zone_type,
    TRIM(properties->>'designacao')         AS designation,
    TRIM(properties->>'servidao')           AS restriction_type,
    TRIM(properties->>'tipologia')          AS typology,
    TRIM(properties->>'lei_tipo')           AS law_type,
    TRIM(properties->>'serv_lei')           AS restriction_law,
    TRIM(properties->>'serv_dr')            AS dr_reference,
    TRIM(properties->>'serv_data')          AS restriction_date,
    TRIM(COALESCE(properties->>'serv_hiperligacao', properties->>'serv_hiper', properties->>'serv_hiperlig')) AS restriction_url,
    TRIM(properties->>'municipios')         AS municipality,
    TRIM(properties->>'codigo')             AS codigo,
    properties,
    geom,
    ST_Transform(geom, 4326)                AS geom_wgs84,
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_srup_areas_protegidas') }}
WHERE geom IS NOT NULL
