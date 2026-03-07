SELECT
    indicator_code,
    indicator_name,
    last_updated,
    time_period,
    geocod                          AS geographic_code,
    geodsg                          AS geographic_name,
    dim_3,
    dim_3_t                         AS dim_3_name,
    dim_4,
    dim_4_t                         AS dim_4_name,
    dim_5,
    dim_5_t                         AS dim_5_name,
    valor                           AS value,
    ind_string,
    sinal_conv,
    sinal_conv_desc,
    _batch_id,
    _api_extraction_ts
FROM {{ source('bronze_ine', 'raw_indicators') }}
WHERE valor IS NOT NULL
