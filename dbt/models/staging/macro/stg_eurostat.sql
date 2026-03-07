SELECT
    dataset_code,
    freq,
    purchase,
    unit,
    geo,
    time_period                     AS period_raw,
    value,
    status,
    _batch_id
FROM {{ source('bronze_macro', 'raw_eurostat') }}
WHERE value IS NOT NULL
