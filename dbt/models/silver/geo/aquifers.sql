{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_aquifers_geom ON {{ this }} USING GIST(geom)",
            "CREATE INDEX IF NOT EXISTS idx_aquifers_geom_pt ON {{ this }} USING GIST(geom_pt)",
            "CREATE INDEX IF NOT EXISTS idx_aquifers_codigo ON {{ this }} (codigo_inag)"
        ]
    )
}}

-- silver_geo.aquifers — LNEG Sistemas Aquíferos national polygons (~63 rows).
-- Contextual layer — fn_assess_polygon reads aquifer_name + aquifer_age in its
-- JSONB readout but does NOT treat aquifer presence as a constraint (locked
-- decision 11+17: DL 382/99 captação protection zones are a different layer;
-- no public PT regulation maps 1:500k aquifer polygons to construction tiers).
--
-- Dual-CRS canonical per [[2026-05-10-dual-crs-storage]].

SELECT
    ROW_NUMBER() OVER (ORDER BY a.codigo_inag, a.feature_id)::BIGINT AS aquifer_key,
    a.feature_id,
    a.codigo_inag,
    a.aquifer_name,
    a.aquifer_system,
    a.aquifer_age,
    a.hydrogeo_unit_id,
    a.geom,
    a.geom_pt,
    a._loaded_at,
    NOW() AS _updated_at
FROM {{ ref('stg_lneg_aquiferos') }} a
