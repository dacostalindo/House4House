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

-- CRUS zoning (national ~236,920 polygons) enriched with normalized zone_category
-- + PDM constraint resolution via JOIN on dim_pdm_constraint.
--
-- CONSTRAINT LAYERING — sprint-09 wedge plan:
--   Layer 1 (this PR): PDM constraints (per-município Regulamento)
--     - applicable_pdm_constraint_keys  → dim_pdm_constraint matches
--   Layer 2 (next PRs, NOT in this model): other regulatory sources
--     - SRUP constraints (RAN/REN/IC/DPH/ZPE/...) — resolved at query time via
--       fn_assess_polygon's ST_Intersects against the 14 silver_regulatory.srup_*
--       layers + dim_constraint_severity. Stays a query-time spatial JOIN
--       because the geometry IS the legal servidão; pre-computing per-zoning-
--       polygon would multiply storage by ~20 with little benefit.
--     - Flood constraints (silver_geo.floodplains, ARPSI T20/T100/T1000) — same
--       pattern: spatial JOIN at query time in fn_assess_polygon.
--     - LNEG aquifers + geology + LiDAR terrain slope — same pattern.
--   This silver model intentionally only carries the PDM constraint pre-join
--   because zone_pattern matching is a string ILIKE (not spatial) and is cheap
--   to materialize. Spatial JOINs stay query-time.
--
-- PDM constraint resolution rules:
--   1. ILIKE match on land_designation (zone-specific, e.g. '%Esp%Hab%Tipo 1%')
--   2. 'ALL_PDM' umbrella (applies to every polygon in município)
--   3. 'ALL_SOLO_URBANO' / 'ALL_SOLO_RUSTICO' (based on land_classification)
-- Overlay slugs (EEM, POC_OMG_*, PORNDSJ, ZONAS_INUNDAVEIS, PATRIMONIO_*, etc.)
-- are stored in dim_pdm_constraint but NOT pre-joined here — they require
-- spatial JOINs to overlay layers that don't yet exist in silver and will be
-- resolved at query time in fn_assess_polygon (sprint-09 keystone).
--
-- Coverage 2026-06-03: only Aveiro (DTCC 0105) onboarded; other municípios get
-- applicable_pdm_constraint_count = 0 until their PDMs are extracted.

WITH zoning_base AS (

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
        -- subcategoria = land_designation with the redundant <classification> - <category>
        -- prefix stripped. Derived by taking everything after the LAST hyphen.
        -- For designations with no hyphen (e.g. "Curso de água"), returns the
        -- original verbatim. Verified 2026-06-03 against all 25 Aveiro
        -- distinct designations — each yields a clean subcategoria with the
        -- prefix stripped (e.g. "Solo Urbano - Espaços Habitacionais - Espaço
        -- Habitacional Tipo 1" → "Espaço Habitacional Tipo 1"). This lets
        -- dim_pdm_constraint.zone_pattern be exact-match strings instead of
        -- wildcard-heavy ILIKE patterns, reducing false-positive risk when
        -- scaling to other municípios.
        TRIM(REGEXP_REPLACE(o.land_designation, '^.*-\s*', ''))    AS subcategoria,
        o.area_ha,
        o.geom,
        o.geom_wgs84,
        o.pdm_publication_date,
        o.feature_id
    FROM {{ ref('stg_crus_ordenamento') }} o

),

pdm_match AS (

    SELECT
        z.zone_key,
        ARRAY_AGG(d.pdm_constraint_key ORDER BY d.pdm_constraint_key)
            FILTER (WHERE d.pdm_constraint_key IS NOT NULL)
                                                              AS applicable_pdm_constraint_keys,
        COUNT(d.pdm_constraint_key)::INTEGER                  AS applicable_pdm_constraint_count
    FROM zoning_base z
    LEFT JOIN {{ ref('dim_pdm_constraint') }} d
        ON d.municipality_code = z.municipality_code
        AND (
            'ALL_PDM' = ANY(d.zone_pattern)
            OR ('ALL_SOLO_URBANO'  = ANY(d.zone_pattern) AND z.land_classification = 'Solo Urbano')
            OR ('ALL_SOLO_RUSTICO' = ANY(d.zone_pattern) AND z.land_classification = 'Solo Rústico')
            OR z.subcategoria = ANY(d.zone_pattern)
            -- zone_pattern is TEXT[] — array of every value the row matches:
            -- {primary_pattern, ...cross_ref_srup_layers}. silver_geo.zoning
            -- only consumes subcategoria + umbrella slugs from the array;
            -- SRUP-layer overlay values in the array are consumed by
            -- silver_regulatory.srup_constraints (joined via spatial intersect
            -- + s.constraint_code = ANY(d.zone_pattern)).
        )
    GROUP BY z.zone_key

)

SELECT
    zb.zone_key,
    zb.municipality_code,
    zb.municipality_name,
    zb.land_classification,
    zb.land_category,
    zb.land_designation,
    zb.subcategoria,
    zb.zone_category,
    zb.area_ha,
    zb.geom,
    zb.geom_wgs84,
    zb.pdm_publication_date,

    pm.applicable_pdm_constraint_keys,
    pm.applicable_pdm_constraint_count,

    NOW() AS _updated_at
FROM zoning_base zb
LEFT JOIN pdm_match pm ON pm.zone_key = zb.zone_key
