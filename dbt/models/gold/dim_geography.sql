{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_dim_geo_freguesia ON {{ this }} (freguesia_code)",
            "CREATE INDEX IF NOT EXISTS idx_dim_geo_concelho ON {{ this }} (concelho_code)",
            "CREATE INDEX IF NOT EXISTS idx_dim_geo_geom ON {{ this }} USING GIST (freguesia_geom)",
            "CREATE INDEX IF NOT EXISTS idx_dim_geo_geom_pt ON {{ this }} USING GIST (freguesia_geom_pt)"
        ]
    )
}}

WITH freg AS (
    SELECT * FROM {{ ref('stg_caop_freguesias') }}
),

bgri AS (
    SELECT * FROM {{ ref('stg_bgri_freguesia_agg') }}
)

SELECT
    ROW_NUMBER() OVER (ORDER BY freg.freguesia_code)::INTEGER
                                                    AS geo_key,
    freg.distrito_code,
    freg.distrito_name,
    freg.concelho_code,
    freg.concelho_name,
    freg.freguesia_code,
    freg.freguesia_name,
    freg.nut_i,
    freg.nut_ii,
    freg.nut_iii,
    NULL::CHAR(4)                                   AS postal_code_4,

    -- Dual-projection geometries
    freg.geom_4326                                  AS freguesia_geom,
    freg.geom_pt                                    AS freguesia_geom_pt,
    ST_Centroid(freg.geom_4326)                     AS centroid,

    -- Area
    ROUND((freg.area_ha / 100.0)::NUMERIC, 3)      AS area_km2,

    -- Census 2021 (aggregated from BGRI subsections)
    bgri.population_2021,
    bgri.households_2021,
    CASE
        WHEN freg.area_ha > 0 THEN
            ROUND(
                (bgri.population_2021 / (freg.area_ha / 100.0))::NUMERIC,
                2
            )
        ELSE NULL
    END                                             AS pop_density_km2,
    bgri.weighted_avg_age                           AS median_age,
    NULL::NUMERIC(5,2)                              AS foreign_resident_pct,

    -- SCD Type 2 metadata
    {{ var('caop_year') }}                           AS source_caop_year,
    ('{{ var('caop_year') }}-01-01')::DATE           AS valid_from,
    NULL::DATE                                      AS valid_to,
    TRUE                                            AS is_current

FROM freg
LEFT JOIN bgri ON freg.freguesia_code = bgri.freguesia_code
