{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_geology_geom ON {{ this }} USING GIST(geom)",
            "CREATE INDEX IF NOT EXISTS idx_geology_geom_pt ON {{ this }} USING GIST(geom_pt)",
            "CREATE INDEX IF NOT EXISTS idx_geology_era ON {{ this }} (era)",
            "CREATE INDEX IF NOT EXISTS idx_geology_period ON {{ this }} (geological_period)"
        ]
    )
}}

-- silver_geo.geology — LNEG CGP500k national geology polygons (~282 rows).
-- Contextual layer — fn_assess_polygon reads lithology_code + era + period
-- in its JSONB readout but does NOT treat geology as a hard constraint
-- (locked decisions 11+17: 1:500k codes are too coarse for Eurocode 7
-- Geotechnical Categories; v2 = per-formation lookup with citations or
-- DRASTIC integration once depth-to-water + recharge data lands).
--
-- Dual-CRS canonical per [[2026-05-10-dual-crs-storage]].

SELECT
    ROW_NUMBER() OVER (ORDER BY g.feature_id)::BIGINT AS geology_key,
    g.feature_id,
    g.lithology_code,
    g.lithology_description,
    g.lithology_description_extra,
    g.eon,
    g.era,
    g.geological_period,
    g.epoch,
    g.chrono_zone,
    g.plutonic_intrusions,
    g.geom,
    g.geom_pt,
    g._loaded_at,
    NOW() AS _updated_at
FROM {{ ref('stg_lneg_geology') }} g
