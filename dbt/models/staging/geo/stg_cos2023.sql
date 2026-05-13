-- COS 2023 (Carta de Uso e Ocupação do Solo) — Land Use/Cover Map
-- Sourced from the OGC API path (raw_cos_national_ogc) as of 2026-05-13.
-- The legacy bulk-GeoPackage path (raw_cos2023 via pipelines/gis/cos/) was retired
-- the same day after the OGC API was confirmed to publish the same dataset.
-- Bbox-filtered to Aveiro distrito for the v1 wedge scope.
--
-- Field mapping: COS23_n4_C / COS23_n4_L keep their names verbatim from the OGC API.
-- `id` → `feature_id` (OGC uses `objectid`). New columns from OGC: municipio,
-- nutsii, nutsiii (not in legacy GeoPackage); preserved for downstream filtering.

SELECT
    feature_id              AS id,
    municipio,
    nutsii,
    nutsiii,
    cos23_n4_c              AS land_use_code,   -- e.g. "1.1.1.1"
    cos23_n4_l              AS land_use_label,   -- e.g. "Áreas edificadas residenciais..."
    area_ha,
    geom                    AS geom_pt,          -- EPSG:3763 (PT-TM06/ETRS89)
    ST_Transform(geom, 4326) AS geom_4326        -- EPSG:4326 (WGS84)
FROM {{ source('bronze_geo', 'raw_cos_national_ogc') }}
