{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_macro_ind ON {{ this }} (indicator_code, observation_date)",
            "CREATE INDEX IF NOT EXISTS idx_macro_geo ON {{ this }} (geo, observation_date)",
            "CREATE INDEX IF NOT EXISTS idx_macro_src ON {{ this }} (source, observation_date)"
        ]
    )
}}

-- Unified macro-economic time series from BPStat, ECB, and Eurostat.
-- Period strings parsed to DATE. Change rates computed via LAG window functions.

WITH bpstat AS (
    SELECT
        'BPSTAT_' || series_id              AS indicator_code,
        series_name                         AS indicator_name,
        CASE domain_id
            WHEN '186' THEN 'housing_credit'
            WHEN '21'  THEN 'interest_rates'
            WHEN '39'  THEN 'housing_prices'
            ELSE 'other'
        END                                 AS category,
        'bpstat'                            AS source,
        'PT'                                AS geo,

        -- BPStat periods are end-of-month dates: '2025-12-31', '2025-09-30'
        -- Normalize to start-of-month for consistency
        DATE_TRUNC('month', period_raw::DATE)::DATE AS observation_date,

        -- All BPStat series in this dataset are monthly
        'M'                                 AS period_type,

        value,
        CASE unit
            WHEN 'Taxa de desconto'                                THEN 'Discount rate'
            WHEN 'Taxa de final de ano'                            THEN 'Year-end rate'
            WHEN 'Taxa de redesconto'                              THEN 'Rediscount rate'
            WHEN 'Taxa de variação da média móvel de 4 trimestres' THEN '4-quarter moving avg change rate'
            ELSE unit
        END                                 AS unit
    FROM {{ ref('stg_bpstat') }}
),

ecb AS (
    SELECT
        series_key                          AS indicator_code,
        series_name                         AS indicator_name,
        'interest_rates'                    AS category,
        'ecb'                               AS source,
        'EU'                                AS geo,

        -- Parse ECB periods: '2024-01' → monthly, '2024-Q1' → quarterly
        CASE
            WHEN period_raw ~ '^\d{4}-\d{2}$' THEN
                TO_DATE(period_raw || '-01', 'YYYY-MM-DD')
            WHEN period_raw ~ '^\d{4}-Q[1-4]$' THEN
                MAKE_DATE(LEFT(period_raw, 4)::INT, (RIGHT(period_raw, 1)::INT - 1) * 3 + 1, 1)
            WHEN period_raw ~ '^\d{4}$' THEN
                MAKE_DATE(period_raw::INT, 1, 1)
        END                                 AS observation_date,

        CASE
            WHEN period_raw ~ '^\d{4}-\d{2}$' THEN 'M'
            WHEN period_raw ~ '^\d{4}-Q' THEN 'Q'
            WHEN period_raw ~ '^\d{4}$' THEN 'A'
        END                                 AS period_type,

        value,
        CASE unit
            WHEN 'PCPA' THEN 'Percentage per annum'
            ELSE unit
        END                                 AS unit
    FROM {{ ref('stg_ecb') }}
),

eurostat AS (
    SELECT
        'EUROSTAT_' || dataset_code || '_' || purchase || '_' || unit
                                            AS indicator_code,
        dataset_code || ' — ' || purchase || ' (' ||
            CASE unit
                WHEN 'I10_Q' THEN 'Index 2010=100'
                WHEN 'I15_Q' THEN 'Index 2015=100'
                WHEN 'RCH_A' THEN 'Annual change %'
                WHEN 'RCH_Q' THEN 'Quarterly change %'
                ELSE unit
            END || ')'
                                            AS indicator_name,
        'housing_prices'                    AS category,
        'eurostat'                          AS source,
        geo,

        -- Parse Eurostat periods: '2024-Q1' → quarterly
        CASE
            WHEN period_raw ~ '^\d{4}-Q[1-4]$' THEN
                MAKE_DATE(LEFT(period_raw, 4)::INT, (RIGHT(period_raw, 1)::INT - 1) * 3 + 1, 1)
            WHEN period_raw ~ '^\d{4}-\d{2}$' THEN
                TO_DATE(period_raw || '-01', 'YYYY-MM-DD')
            WHEN period_raw ~ '^\d{4}$' THEN
                MAKE_DATE(period_raw::INT, 1, 1)
        END                                 AS observation_date,

        CASE
            WHEN period_raw ~ 'Q' THEN 'Q'
            WHEN period_raw ~ '^\d{4}-\d{2}$' THEN 'M'
            WHEN period_raw ~ '^\d{4}$' THEN 'A'
        END                                 AS period_type,

        value,
        CASE unit
            WHEN 'I10_Q' THEN 'Index (2010=100)'
            WHEN 'I15_Q' THEN 'Index (2015=100)'
            WHEN 'RCH_A' THEN 'Annual rate of change (%)'
            WHEN 'RCH_Q' THEN 'Quarterly rate of change (%)'
            ELSE unit
        END                                 AS unit
    FROM {{ ref('stg_eurostat') }}
),

unioned AS (
    SELECT * FROM bpstat
    UNION ALL
    SELECT * FROM ecb
    UNION ALL
    SELECT * FROM eurostat
),

-- Compute change rates via LAG window functions
-- Partitioned by (indicator_code, geo) to compare like-for-like
with_changes AS (
    SELECT
        indicator_code,
        indicator_name,
        category,
        source,
        geo,
        observation_date,
        period_type,
        value,
        unit,

        -- Month-on-month % change (monthly series only)
        CASE WHEN period_type = 'M' THEN
            ROUND(
                (value - LAG(value, 1) OVER w)
                / NULLIF(ABS(LAG(value, 1) OVER w), 0) * 100,
                4
            )
        END                                 AS mom_change,

        -- Quarter-on-quarter % change
        CASE WHEN period_type IN ('Q', 'M') THEN
            ROUND(
                (value - LAG(value, CASE period_type WHEN 'M' THEN 3 ELSE 1 END) OVER w)
                / NULLIF(ABS(LAG(value, CASE period_type WHEN 'M' THEN 3 ELSE 1 END) OVER w), 0) * 100,
                4
            )
        END                                 AS qoq_change,

        -- Year-on-year % change
        ROUND(
            (value - LAG(value, CASE period_type WHEN 'M' THEN 12 WHEN 'Q' THEN 4 ELSE 1 END) OVER w)
            / NULLIF(ABS(LAG(value, CASE period_type WHEN 'M' THEN 12 WHEN 'Q' THEN 4 ELSE 1 END) OVER w), 0) * 100,
            4
        )                                   AS yoy_change

    FROM unioned
    WHERE observation_date IS NOT NULL
      AND value IS NOT NULL
    WINDOW w AS (
        PARTITION BY indicator_code, geo
        ORDER BY observation_date
    )
)

SELECT
    ROW_NUMBER() OVER (
        ORDER BY source, indicator_code, geo, observation_date
    )::BIGINT                               AS id,
    indicator_code,
    indicator_name,
    category,
    source,
    geo,
    observation_date,
    period_type,
    value,
    unit,
    mom_change,
    qoq_change,
    yoy_change,
    NOW()                                   AS _updated_at
FROM with_changes
