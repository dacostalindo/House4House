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

-- COS 2023 (Série 2) land-use/cover enriched with the full L1-L3 PT
-- nomenclature via JOIN on dim_cos_nomenclature, classification flags,
-- and dominant freguesia assignment via spatial join to CAOP.
-- ~842K polygons covering all mainland Portugal.

WITH classified AS (
    SELECT
        s.id,
        s.land_use_code,
        s.land_use_label,
        s.area_ha,

        -- L1-L3 codes (derived) + L1 PT name + L2 PT name + L3 PT name +
        -- English category bucket all sourced from dim_cos_nomenclature.
        -- Use dim values verbatim — single source of truth per DGT spec.
        d.code_l1   AS land_use_level1,
        d.code_l2   AS land_use_level2,
        d.code_l3   AS land_use_level3,
        d.label_l1_pt AS land_use_level1_label_pt,
        d.label_l2_pt AS land_use_level2_label_pt,
        d.label_l3_pt AS land_use_level3_label_pt,
        d.category_en AS land_use_category,

        -- Boolean flags. is_forest matches L5 (Florestas), NOT L4 (agroforestry).
        s.land_use_code LIKE '1.%'  AS is_urban,
        s.land_use_code LIKE '1.1%' AS is_residential,
        s.land_use_code LIKE '2.%'  AS is_agricultural,
        s.land_use_code LIKE '5.%'  AS is_forest,

        s.geom_pt,
        s.geom_4326
    FROM {{ ref('stg_cos2023') }} s
    LEFT JOIN {{ ref('dim_cos_nomenclature') }} d
        ON d.code_l4 = s.land_use_code
),

-- Assign each COS polygon to a freguesia using its interior point.
-- Using ST_PointOnSurface (guaranteed inside the polygon) instead of
-- ST_Intersection area (too expensive for 842K × 3K polygon pairs).
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
    land_use_level1_label_pt,
    land_use_level2_label_pt,
    land_use_level3_label_pt,
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
