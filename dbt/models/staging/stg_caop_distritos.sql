SELECT
    dt              AS distrito_code,
    distrito        AS distrito_name
FROM {{ source('bronze_geo', 'raw_caop_distritos') }}
