SELECT
    series_id,
    domain_id,
    dataset_id,
    series_name,
    period                          AS period_raw,
    value,
    unit,
    status,
    _batch_id
FROM {{ source('bronze_macro', 'raw_bpstat') }}
WHERE value IS NOT NULL
