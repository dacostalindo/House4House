{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_land_use_geom ON {{ this }} USING GIST(geom)",
            "CREATE INDEX IF NOT EXISTS idx_land_use_geom_wgs84 ON {{ this }} USING GIST(geom_wgs84)",
            "CREATE INDEX IF NOT EXISTS idx_land_use_code ON {{ this }} (land_use_code)",
            "CREATE INDEX IF NOT EXISTS idx_land_use_cat ON {{ this }} (land_use_category)",
            "CREATE INDEX IF NOT EXISTS idx_land_use_freg ON {{ this }} (freguesia_code)"
        ]
    )
}}

-- COS 2023 land-use/cover enriched with hierarchy, classification flags,
-- and dominant freguesia assignment via spatial join to CAOP.
-- ~784K polygons covering all mainland Portugal.

WITH classified AS (
    SELECT
        id,
        land_use_code,
        land_use_label,
        area_ha,

        -- Hierarchy decomposition
        split_part(land_use_code, '.', 1)                                          AS land_use_level1,
        split_part(land_use_code, '.', 1) || '.' || split_part(land_use_code, '.', 2) AS land_use_level2,
        split_part(land_use_code, '.', 1) || '.' || split_part(land_use_code, '.', 2)
            || '.' || split_part(land_use_code, '.', 3)                            AS land_use_level3,

        -- Level 1 category label
        CASE split_part(land_use_code, '.', 1)
            WHEN '1' THEN 'artificial'
            WHEN '2' THEN 'agriculture'
            WHEN '3' THEN 'pasture'
            WHEN '4' THEN 'forest'
            WHEN '5' THEN 'shrubland'
            WHEN '6' THEN 'sparse_vegetation'
            WHEN '7' THEN 'wetland'
            WHEN '8' THEN 'water'
            WHEN '9' THEN 'ocean'
            ELSE 'other'
        END AS land_use_category,

        -- Boolean flags
        land_use_code LIKE '1.%'  AS is_urban,
        land_use_code LIKE '1.1%' AS is_residential,
        land_use_code LIKE '2.%'  AS is_agricultural,
        land_use_code LIKE '4.%'  AS is_forest,

        geom_pt,
        geom_4326
    FROM {{ ref('stg_cos2023') }}
),

-- Assign each COS polygon to a freguesia using its interior point.
-- Using ST_PointOnSurface (guaranteed inside the polygon) instead of
-- ST_Intersection area (too expensive for 784K × 3K polygon pairs).
with_freguesia AS (
    SELECT
        c.*,
        f.freguesia_code,
        f.concelho_code,
        f.distrito_code
    FROM classified c
    LEFT JOIN {{ ref('stg_caop_freguesias') }} f
        ON ST_Within(ST_PointOnSurface(c.geom_pt), f.geom_pt)
)

SELECT
    ROW_NUMBER() OVER (ORDER BY id)::BIGINT AS land_use_key,
    id,
    land_use_code,
    land_use_label,
    area_ha,
    land_use_level1,
    land_use_level2,
    land_use_level3,
    land_use_category,
    is_urban,
    is_residential,
    is_agricultural,
    is_forest,
    freguesia_code,
    concelho_code,
    distrito_code,
    geom_pt  AS geom,
    geom_4326 AS geom_wgs84,
    NOW()    AS _updated_at
FROM with_freguesia
