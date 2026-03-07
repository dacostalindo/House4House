{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_cd_geo_key ON {{ this }} (geo_key)",
            "CREATE INDEX IF NOT EXISTS idx_cd_freg ON {{ this }} (freguesia_code)"
        ]
    )
}}

-- TODO (Sprint 5): Aggregate BGRI census data to deeper demographic columns.
-- Depends on: stg_bgri_freguesia_agg, stg_ine_indicators, dim_geography
--
-- Transformations needed:
--   stg_bgri_freguesia_agg  → extend with age band columns, dwelling stats
--   stg_ine_indicators      → aging_index, employment_rate (indicator_code lookup)
--   JOIN dim_geography       → resolve geo_key from freguesia_code

SELECT
    NULL::INTEGER           AS geo_key,
    NULL::CHAR(6)           AS freguesia_code,
    NULL::INTEGER           AS total_population,
    NULL::INTEGER           AS pop_0_14,
    NULL::INTEGER           AS pop_15_24,
    NULL::INTEGER           AS pop_25_64,
    NULL::INTEGER           AS pop_65_plus,
    NULL::NUMERIC(4,1)      AS median_age,
    NULL::NUMERIC(6,2)      AS aging_index,
    NULL::INTEGER           AS total_households,
    NULL::INTEGER           AS total_dwellings,
    NULL::INTEGER           AS vacant_dwellings,
    NULL::NUMERIC(5,2)      AS vacancy_rate,
    NULL::SMALLINT          AS census_year,
    NOW()                   AS _updated_at
WHERE FALSE
