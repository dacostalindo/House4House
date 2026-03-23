-- COS 2023 (Carta de Uso e Ocupação do Solo) — Land Use/Cover Map
-- Source: bronze_geo.raw_cos2023 (GPKG from DGT, ~784K polygons)
-- GPKG layer: COS2023v1
-- GPKG fields: ID, COS23_n4_C, COS23_n4_L, AREA_ha
-- PostgreSQL lowercases column names, so GPKG "COS23_n4_C" → bronze "cos23_n4_c"

SELECT
    id,
    cos23_n4_c              AS land_use_code,   -- e.g. "1.1.1.1"
    cos23_n4_l              AS land_use_label,   -- e.g. "Áreas edificadas residenciais..."
    area_ha,
    geom                    AS geom_pt,          -- EPSG:3763 (PT-TM06/ETRS89)
    ST_Transform(geom, 4326) AS geom_4326        -- EPSG:4326 (WGS84)
FROM {{ source('bronze_geo', 'raw_cos2023') }}
