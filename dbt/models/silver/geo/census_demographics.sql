{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_cd_geo_key ON {{ this }} (geo_key)",
            "CREATE INDEX IF NOT EXISTS idx_cd_freg ON {{ this }} (freguesia_code)"
        ]
    )
}}

-- BGRI Census 2021 aggregated from 203K subsections to 3,049 freguesias.
-- Enriched with INE Census 2021 indicators: building condition, employment,
-- education, foreign population, mean age, and commuting time.

WITH bgri_agg AS (
    SELECT
        dtmnfr21 AS freguesia_code,

        -- Population
        SUM(n_individuos)::INTEGER                     AS total_population,
        SUM(n_individuos_0_14)::INTEGER                AS pop_0_14,
        SUM(n_individuos_15_24)::INTEGER               AS pop_15_24,
        SUM(n_individuos_25_64)::INTEGER               AS pop_25_64,
        SUM(n_individuos_65_ou_mais)::INTEGER          AS pop_65_plus,

        -- Weighted average age (true median not computable from bands)
        CASE
            WHEN SUM(n_individuos) > 0 THEN
                ROUND(((
                    SUM(n_individuos_0_14) * 7.0
                    + SUM(n_individuos_15_24) * 19.5
                    + SUM(n_individuos_25_64) * 44.5
                    + SUM(n_individuos_65_ou_mais) * 77.5
                ) / NULLIF(SUM(n_individuos), 0))::NUMERIC, 1)
            ELSE NULL
        END                                            AS median_age,

        -- Aging index: (65+ / 0-14) × 100
        CASE
            WHEN SUM(n_individuos_0_14) > 0 THEN
                ROUND((SUM(n_individuos_65_ou_mais)
                    / SUM(n_individuos_0_14) * 100)::NUMERIC, 2)
            ELSE NULL
        END                                            AS aging_index,

        -- Households
        SUM(n_agregados_domesticos_privados)::INTEGER  AS total_households,
        CASE
            WHEN SUM(n_agregados_domesticos_privados) > 0 THEN
                ROUND((SUM(n_individuos)
                    / SUM(n_agregados_domesticos_privados))::NUMERIC, 1)
            ELSE NULL
        END                                            AS avg_household_size,
        -- Small households (1-2 person); BGRI only splits 1-2 vs 3+
        CASE
            WHEN SUM(n_agregados_domesticos_privados) > 0 THEN
                ROUND((SUM(n_adp_1_ou_2_pessoas)
                    / SUM(n_agregados_domesticos_privados) * 100)::NUMERIC, 2)
            ELSE NULL
        END                                            AS small_household_pct,

        -- Dwellings
        SUM(n_alojamentos_total)::INTEGER              AS total_dwellings,
        SUM(n_alojamentos_fam_class_rhabitual)::INTEGER AS occupied_dwellings,
        SUM(n_alojamentos_fam_class_vagos_ou_resid_secundaria)::INTEGER AS vacant_dwellings,
        CASE
            WHEN SUM(n_alojamentos_total) > 0 THEN
                ROUND((SUM(n_alojamentos_fam_class_vagos_ou_resid_secundaria)
                    / SUM(n_alojamentos_total) * 100)::NUMERIC, 2)
            ELSE NULL
        END                                            AS vacancy_rate,

        -- Tenure
        CASE
            WHEN SUM(n_alojamentos_fam_class_rhabitual) > 0 THEN
                ROUND((SUM(n_rhabitual_prop_ocup)
                    / SUM(n_alojamentos_fam_class_rhabitual) * 100)::NUMERIC, 2)
            ELSE NULL
        END                                            AS owner_occupied_pct,
        CASE
            WHEN SUM(n_alojamentos_fam_class_rhabitual) > 0 THEN
                ROUND((SUM(n_rhabitual_arrendados)
                    / SUM(n_alojamentos_fam_class_rhabitual) * 100)::NUMERIC, 2)
            ELSE NULL
        END                                            AS renter_pct

    FROM {{ source('bronze_ine', 'raw_bgri') }}
    GROUP BY dtmnfr21
),

ine_building_aging AS (
    SELECT geographic_code AS freguesia_code,
           value           AS building_aging_ratio
    FROM {{ ref('stg_ine_indicators') }}
    WHERE indicator_code = '0012575'
),

ine_building_repair AS (
    SELECT geographic_code AS freguesia_code,
           value           AS buildings_repair_needed_pct
    FROM {{ ref('stg_ine_indicators') }}
    WHERE indicator_code = '0012581'
),

-- Employment (Census 2021, MF total)
ine_unemployment_rate AS (
    SELECT geographic_code AS freguesia_code, value AS unemployment_rate
    FROM {{ ref('stg_ine_indicators') }}
    WHERE indicator_code = '0012328' AND dim_3 = 'T'
),
ine_activity_rate AS (
    SELECT geographic_code AS freguesia_code, value AS activity_rate
    FROM {{ ref('stg_ine_indicators') }}
    WHERE indicator_code = '0012317' AND dim_3 = 'T'
),
ine_employees_pct AS (
    SELECT geographic_code AS freguesia_code, value AS employees_pct
    FROM {{ ref('stg_ine_indicators') }}
    WHERE indicator_code = '0012341' AND dim_3 = 'T'
),

-- Education (Census 2021, MF total)
ine_higher_ed AS (
    SELECT geographic_code AS freguesia_code, value AS higher_education_pct
    FROM {{ ref('stg_ine_indicators') }}
    WHERE indicator_code = '0012316' AND dim_3 = 'T'
),
ine_lower_secondary AS (
    SELECT geographic_code AS freguesia_code, value AS lower_secondary_pct
    FROM {{ ref('stg_ine_indicators') }}
    WHERE indicator_code = '0012315' AND dim_3 = 'T'
),
ine_upper_secondary AS (
    SELECT geographic_code AS freguesia_code, value AS upper_secondary_pct
    FROM {{ ref('stg_ine_indicators') }}
    WHERE indicator_code = '0012327' AND dim_3 = 'T'
),
ine_no_education AS (
    SELECT geographic_code AS freguesia_code, value AS no_education_pct
    FROM {{ ref('stg_ine_indicators') }}
    WHERE indicator_code = '0012323' AND dim_3 = 'T'
),

-- Foreign population (Census 2021, MF total)
ine_foreign_pct AS (
    SELECT geographic_code AS freguesia_code, value AS foreign_nationality_pct
    FROM {{ ref('stg_ine_indicators') }}
    WHERE indicator_code = '0012314' AND dim_3 = 'T'
),

-- Age & commuting (Census 2021, no dimensions)
ine_mean_age AS (
    SELECT geographic_code AS freguesia_code, value AS mean_age
    FROM {{ ref('stg_ine_indicators') }}
    WHERE indicator_code = '0012374' AND LENGTH(geographic_code) = 6
),
ine_commuting AS (
    SELECT geographic_code AS freguesia_code, value AS avg_commuting_time_min
    FROM {{ ref('stg_ine_indicators') }}
    WHERE indicator_code = '0012331' AND LENGTH(geographic_code) = 6
)

SELECT
    g.geo_key,
    b.freguesia_code,
    g.distrito_code,
    g.distrito_name,
    g.concelho_code,
    g.concelho_name,
    g.freguesia_name,

    -- Population
    b.total_population,
    b.pop_0_14,
    b.pop_15_24,
    b.pop_25_64,
    b.pop_65_plus,
    b.median_age,
    b.aging_index,

    -- Households
    b.total_households,
    b.avg_household_size,
    b.small_household_pct,

    -- Dwellings
    b.total_dwellings,
    b.occupied_dwellings,
    b.vacant_dwellings,
    b.vacancy_rate,
    b.owner_occupied_pct,
    b.renter_pct,

    -- INE building condition indicators
    ba.building_aging_ratio,
    br.buildings_repair_needed_pct,

    -- INE employment indicators (Census 2021, MF total)
    ur.unemployment_rate,
    ar.activity_rate,
    ep.employees_pct,

    -- INE education indicators (Census 2021, MF total)
    he.higher_education_pct,
    ls.lower_secondary_pct,
    us.upper_secondary_pct,
    ne.no_education_pct,

    -- INE foreign population (Census 2021, MF total)
    fp.foreign_nationality_pct,

    -- INE age & commuting (Census 2021)
    ma.mean_age       AS ine_mean_age,
    ct.avg_commuting_time_min,

    2021::SMALLINT AS census_year,
    NOW()          AS _updated_at

FROM bgri_agg b
LEFT JOIN {{ ref('dim_geography') }} g
    ON b.freguesia_code = g.freguesia_code
LEFT JOIN ine_building_aging ba
    ON b.freguesia_code = ba.freguesia_code
LEFT JOIN ine_building_repair br
    ON b.freguesia_code = br.freguesia_code
LEFT JOIN ine_unemployment_rate ur
    ON b.freguesia_code = ur.freguesia_code
LEFT JOIN ine_activity_rate ar
    ON b.freguesia_code = ar.freguesia_code
LEFT JOIN ine_employees_pct ep
    ON b.freguesia_code = ep.freguesia_code
LEFT JOIN ine_higher_ed he
    ON b.freguesia_code = he.freguesia_code
LEFT JOIN ine_lower_secondary ls
    ON b.freguesia_code = ls.freguesia_code
LEFT JOIN ine_upper_secondary us
    ON b.freguesia_code = us.freguesia_code
LEFT JOIN ine_no_education ne
    ON b.freguesia_code = ne.freguesia_code
LEFT JOIN ine_foreign_pct fp
    ON b.freguesia_code = fp.freguesia_code
LEFT JOIN ine_mean_age ma
    ON b.freguesia_code = ma.freguesia_code
LEFT JOIN ine_commuting ct
    ON b.freguesia_code = ct.freguesia_code
