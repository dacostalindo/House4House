{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_zoning_geom ON {{ this }} USING GIST(geom)",
            "CREATE INDEX IF NOT EXISTS idx_zoning_geom_wgs84 ON {{ this }} USING GIST(geom_wgs84)",
            "CREATE INDEX IF NOT EXISTS idx_zoning_muni ON {{ this }} (municipality_code)"
        ]
    )
}}

SELECT
    ROW_NUMBER() OVER (ORDER BY o.municipality_code, o.feature_id)::BIGINT AS zone_key,
    o.municipality_code,
    o.municipality_name,
    o.land_classification,
    o.land_category,
    o.land_designation,
    CASE
        -- Urban zones (Solo Urbano)
        WHEN o.land_classification = 'Solo Urbano' AND o.land_category LIKE '%Urbanizado%' THEN 'urban_consolidated'
        WHEN o.land_classification = 'Solo Urbano' AND o.land_category LIKE '%Urbanizáve%' THEN 'urban_expansion'
        WHEN o.land_classification = 'Solo Urbano' AND o.land_category LIKE '%Habitacional%' THEN 'urban_residential'
        WHEN o.land_classification = 'Solo Urbano' AND o.land_category LIKE '%Central%' THEN 'urban_central'
        WHEN o.land_classification = 'Solo Urbano' AND o.land_category LIKE '%Atividades Económicas%' THEN 'urban_economic'
        WHEN o.land_classification = 'Solo Urbano' AND o.land_category LIKE '%Verde%' THEN 'urban_green'
        WHEN o.land_classification = 'Solo Urbano' AND o.land_category LIKE '%Uso Especial%' THEN 'urban_special'
        WHEN o.land_classification = 'Solo Urbano' AND o.land_category LIKE '%Equipamento%' THEN 'urban_special'
        WHEN o.land_classification = 'Solo Urbano' THEN 'urban_other'
        -- Rural zones (Solo Rústico)
        WHEN o.land_classification = 'Solo Rústico' AND o.land_category LIKE '%Agríco%' THEN 'rural_agricultural'
        WHEN o.land_classification = 'Solo Rústico' AND o.land_category LIKE '%Aglomerado Rural%' THEN 'rural_settlement'
        WHEN o.land_classification = 'Solo Rústico' AND o.land_category LIKE '%Florestal%' THEN 'rural_forest'
        WHEN o.land_classification = 'Solo Rústico' AND o.land_category LIKE '%Natural%' THEN 'rural_natural'
        WHEN o.land_classification = 'Solo Rústico' AND o.land_category LIKE '%Turístic%' THEN 'rural_tourism'
        WHEN o.land_classification = 'Solo Rústico' AND o.land_category LIKE '%Equipamento%' THEN 'rural_special'
        WHEN o.land_classification = 'Solo Rústico' THEN 'rural_other'
        ELSE 'other'
    END AS zone_category,

    -- Sprint-08 Activity 5: density rule extraction from `land_designation`.
    -- The PDM Planta de Ordenamento freetext mixes Portuguese number formats
    -- (1,5 / 1.5) — `replace(...,',','.')` before ::numeric cast. Defaults
    -- to NULL when the regex doesn't match.
    --
    -- max_floors: "3 pisos", "max 4 piso", "até 5 pisos" → captures integer
    (regexp_match(o.land_designation, '(\d+)\s*pisos?', 'i'))[1]::INTEGER
        AS max_floors,
    -- max_density_index: "índice 0,8", "índice = 1.2", "Indice: 0,5" → captures decimal
    NULLIF(REPLACE((regexp_match(o.land_designation, 'índice\s*[:=]?\s*([\d,.]+)', 'i'))[1], ',', '.'), '')::NUMERIC(6,4)
        AS max_density_index,
    -- max_coverage_ratio: "cobertura 40%", "cobertura: 25,5%" → captures percentage as decimal
    NULLIF(REPLACE((regexp_match(o.land_designation, 'cobertura\s*[:=]?\s*([\d,.]+)\s*%', 'i'))[1], ',', '.'), '')::NUMERIC(6,4)
        AS max_coverage_ratio,

    o.area_ha,
    o.geom,
    o.geom_wgs84,
    o.pdm_publication_date,
    NOW() AS _updated_at
FROM {{ ref('stg_crus_ordenamento') }} o
