{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_terrain_slope_raster_footprint_pt ON {{ this }} USING GIST(footprint_pt)",
            "CREATE INDEX IF NOT EXISTS idx_terrain_slope_raster_filename ON {{ this }} (filename)"
        ]
    )
}}

-- silver_geo.terrain_slope_raster — thin view over the 489-tile postgis_raster
-- registry. fn_assess_polygon (sprint-09 keystone) does
-- `ST_Clip(rast, drawn_polygon) + ST_SummaryStatsAgg` against this silver to
-- compute exact-per-polygon slope statistics — no parcel-proxy approximation.
--
-- `footprint_pt` is a GIST-indexed convex hull of each tile's raster extent
-- (EPSG:3763) — lets fn_assess_polygon pre-filter to the 1-4 raster tiles
-- overlapping a drawn polygon before the expensive ST_Clip.
--
-- See [[silver-dq-baseline]] Rule 0 + [[lidar]] for context.
-- Sprint-09 WS4 PR A (2026-06-03).

SELECT
    rid,
    rast,
    filename,
    ST_ConvexHull(rast)                     AS footprint_pt,    -- EPSG:3763
    ST_Transform(ST_ConvexHull(rast), 4326) AS footprint,        -- EPSG:4326 for display
    _load_timestamp                         AS _loaded_at,
    NOW()                                   AS _updated_at
FROM {{ source('bronze_terrain', 'raster_lidar_slope_2m') }}
