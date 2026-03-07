{{ config(materialized='table') }}

-- Date dimension 2000-01-01 to 2035-12-31 (~13,149 rows).
-- Generated via dbt_utils.date_spine. No CSV seed needed.

WITH date_spine AS (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2000-01-01' as date)",
        end_date="cast('2036-01-01' as date)"
    ) }}
)

SELECT
    TO_CHAR(date_day, 'YYYYMMDD')::INTEGER  AS date_key,
    date_day::DATE                          AS full_date,
    EXTRACT(YEAR FROM date_day)::SMALLINT   AS year,
    EXTRACT(QUARTER FROM date_day)::SMALLINT AS quarter,
    EXTRACT(MONTH FROM date_day)::SMALLINT  AS month,
    TO_CHAR(date_day, 'FMMonth')            AS month_name,
    EXTRACT(WEEK FROM date_day)::SMALLINT   AS week_of_year,
    EXTRACT(DAY FROM date_day)::SMALLINT    AS day_of_month,
    EXTRACT(ISODOW FROM date_day)::SMALLINT AS day_of_week,
    EXTRACT(ISODOW FROM date_day) IN (6, 7) AS is_weekend,
    EXTRACT(QUARTER FROM date_day)::SMALLINT AS fiscal_quarter,
    EXTRACT(YEAR FROM date_day)::TEXT || 'Q' || EXTRACT(QUARTER FROM date_day)::TEXT
                                            AS ine_quarter_label
FROM date_spine
