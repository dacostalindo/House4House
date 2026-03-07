SELECT
    dtmnfr                          AS freguesia_code,
    LEFT(dtmnfr, 2)                 AS distrito_code,
    LEFT(dtmnfr, 4)                 AS concelho_code,
    freguesia                       AS freguesia_name,
    municipio                       AS concelho_name,
    distrito_ilha                   AS distrito_name,
    nuts1                           AS nut_i,
    nuts2                           AS nut_ii,
    nuts3                           AS nut_iii,
    area_ha,
    geom                            AS geom_pt,
    ST_Transform(geom, 4326)        AS geom_4326
FROM {{ source('bronze_geo', 'raw_caop_freguesias') }}
