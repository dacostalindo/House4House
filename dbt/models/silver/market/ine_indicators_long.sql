{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_ine_long_code ON {{ this }} (indicator_code)",
            "CREATE INDEX IF NOT EXISTS idx_ine_long_freguesia ON {{ this }} (freguesia_code) WHERE freguesia_code IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_ine_long_concelho ON {{ this }} (concelho_code) WHERE concelho_code IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_ine_long_date ON {{ this }} (time_period_date) WHERE time_period_date IS NOT NULL"
        ]
    )
}}

-- silver_market.ine_indicators_long — long-form INE indicator timeseries
-- with parish/concelho/NUTS granularity. Distinct from silver_market.macro_timeseries
-- (national/EU rates+prices) per locked decision 16; see [[silver-dq-baseline]]
-- "Statistical-source silver topology" section.
--
-- No silver-side filter on indicator_code — bronze loader is gated by
-- INE_INDICATORS in ine_config.py, so every bronze row IS an active indicator
-- (locked decision 13, single source of truth).
--
-- INE uses TWO coding schemes for geographic_code in bronze; both handled here.
-- Verified 2026-06-02 against the full ~800K silver rows:
--
--   Scheme A — CAOP-style flat:
--     'PT'  → country; 1-char → NUTS1; 2-char → NUTS2; 3-char alphanumeric → NUTS3
--     (e.g. '11A', '16D'); 4-char digits → concelho (DTCC); 6-char → freguesia (DTMNFR,
--     can contain LETTERS for freguesia-unions, e.g. '0302FD').
--
--   Scheme B — INE NUTS3-prefixed hierarchical (newer indicators):
--     7-char → concelho (NUTS3-prefix (3) + DTCC (4), e.g. '11A1312' Porto).
--     9-char → freguesia (NUTS3-prefix (3) + DTMNFR (6), e.g. '11A131727' Mafamude).
--
-- v1 exposes only the CAOP-compatible trailing fragment via freguesia_code +
-- concelho_code so downstream models can JOIN to dim_geography regardless of
-- source scheme. No `geo_level` column — `freguesia_code IS NOT NULL` /
-- `concelho_code IS NOT NULL` cover the use case for fn_assess_polygon;
-- NUTS-level filtering (rarer) can use LENGTH(geographic_code) directly or be
-- added as a typed column in v2 if it becomes a common access pattern.

WITH parsed AS (
    SELECT
        indicator_code,
        indicator_name,
        indicator_category,
        time_period AS time_period_raw,
        CASE
            WHEN time_period ~ '^\d{4}$' THEN
                MAKE_DATE(time_period::INT, 1, 1)
            WHEN time_period ~ '^[1-4](st|nd|rd|th) Quarter \d{4}$' THEN
                MAKE_DATE(
                    RIGHT(time_period, 4)::INT,
                    (LEFT(time_period, 1)::INT - 1) * 3 + 1,
                    1
                )
            WHEN time_period ~ '^(January|February|March|April|May|June|July|August|September|October|November|December) \d{4}$' THEN
                TO_DATE(time_period, 'FMMonth YYYY')
        END AS time_period_date,
        TRIM(geographic_code) AS geographic_code,
        geographic_name,
        dim_3, dim_3_label,
        dim_4, dim_4_label,
        dim_5, dim_5_label,
        value,
        ind_string,
        sinal_conv,
        sinal_conv_desc,
        last_updated
    FROM {{ ref('stg_ine_indicators') }}
)
SELECT
    ROW_NUMBER() OVER (
        ORDER BY indicator_code, geographic_code, time_period_date NULLS LAST, dim_3, dim_4, dim_5
    )::BIGINT                                       AS indicator_long_key,
    indicator_code,
    indicator_name,
    indicator_category,
    time_period_raw,
    time_period_date,
    geographic_code,
    geographic_name,
    -- CAOP-compatible 6-char DTMNFR (digits OR letters for unions).
    --   6-char input → pass-through
    --   9-char input → RIGHT 6 chars (drop the NUTS3 prefix)
    --   else NULL
    CASE
        WHEN LENGTH(geographic_code) = 6 THEN geographic_code
        WHEN LENGTH(geographic_code) = 9 THEN RIGHT(geographic_code, 6)
    END                                             AS freguesia_code,
    -- CAOP-compatible 4-char DTCC, derived from any of:
    --   4-digit concelho → as-is
    --   7-char concelho → RIGHT 4
    --   6-char freguesia → LEFT 4
    --   9-char freguesia → SUBSTRING(4, 4) (positions 4..7 inclusive)
    --   else NULL
    CASE
        WHEN LENGTH(geographic_code) = 4 AND geographic_code ~ '^\d+$' THEN geographic_code
        WHEN LENGTH(geographic_code) = 7 THEN RIGHT(geographic_code, 4)
        WHEN LENGTH(geographic_code) = 6 THEN LEFT(geographic_code, 4)
        WHEN LENGTH(geographic_code) = 9 THEN SUBSTRING(geographic_code FROM 4 FOR 4)
    END                                             AS concelho_code,
    dim_3, dim_3_label,
    dim_4, dim_4_label,
    dim_5, dim_5_label,
    value,
    ind_string,
    sinal_conv,
    sinal_conv_desc,
    last_updated,
    NOW() AS _updated_at
FROM parsed
