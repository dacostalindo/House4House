SELECT
    series_key,
    series_name,
    value,
    time_period                     AS period_raw,
    unit,
    obs_status,
    _batch_id
FROM {{ source('bronze_macro', 'raw_ecb') }}
WHERE value IS NOT NULL
