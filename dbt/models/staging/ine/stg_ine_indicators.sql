-- INE dim_X vs dim_X_t (per official pindicaMeta.jsp endpoint):
--   dim_X    = INE category CODE within the dimension (e.g. 'T' total, '1', '2',
--              '11', '16D'). Stable convention: 'T' always = total.
--   dim_X_t  = INE displayable LABEL. Inconsistent shape: sometimes a short
--              code ('M', 'F'), sometimes a full label ('5 - 9 years').
-- Renamed to `dim_X_label` (not `_name`) because the value isn't always a
-- human-readable name. Full descriptions ('Males', 'Females') require the
-- pindicaMeta.jsp endpoint, which we don't currently fetch.

SELECT
    indicator_code,
    indicator_name,
    indicator_category,
    last_updated,
    time_period,
    geocod                          AS geographic_code,
    geodsg                          AS geographic_name,
    dim_3,
    dim_3_t                         AS dim_3_label,
    dim_4,
    dim_4_t                         AS dim_4_label,
    dim_5,
    dim_5_t                         AS dim_5_label,
    valor                           AS value,
    ind_string,
    sinal_conv,
    sinal_conv_desc,
    _batch_id,
    _api_extraction_ts
FROM {{ source('bronze_ine', 'raw_indicators') }}
WHERE valor IS NOT NULL
