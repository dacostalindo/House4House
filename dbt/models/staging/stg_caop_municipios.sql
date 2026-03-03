SELECT
    dtmn            AS concelho_code,
    municipio       AS concelho_name
FROM {{ source('bronze_geo', 'raw_caop_municipios') }}
