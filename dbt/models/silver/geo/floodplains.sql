{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_floodplains_geom ON {{ this }} USING GIST(geom)",
            "CREATE INDEX IF NOT EXISTS idx_floodplains_geom_pt ON {{ this }} USING GIST(geom_pt)",
            "CREATE INDEX IF NOT EXISTS idx_floodplains_constraint ON {{ this }} (constraint_code, zone_type)"
        ]
    )
}}

-- silver_geo.floodplains — APA ARPSI as the 15th constraint layer alongside
-- the 14 stg_srup_*. Denormalizes severity + buffer_m from
-- dim_constraint_severity so fn_assess_polygon can skip the JOIN in the hot
-- path. Two zone_types per locked decision 3:
--   T100  → severity 3 (hard gate, DL 115/2010 non-aedificandi default)
--   T1000 → severity 2 (conditioned, buildable with mitigation per PT planning practice)
--
-- Dual-CRS canonical naming per [[2026-05-10-dual-crs-storage]] (geom=4326,
-- geom_pt=3763). Adjacent SRUP siblings still use the legacy `geom`(3763) +
-- `geom_wgs84`(4326) pattern; migration to canonical is sprint-10 cleanup.

SELECT
    ROW_NUMBER() OVER (ORDER BY a.feature_id)::BIGINT AS floodplain_id,
    a.feature_id,
    a.constraint_code,
    a.zone_type,
    a.return_period_years,
    a.hydrographic_region,
    a.location,
    a.designation,
    a.publication_date,
    d.severity,
    d.buffer_m,
    a.geom,
    a.geom_pt,
    a._loaded_at,
    NOW() AS _updated_at
FROM {{ ref('stg_apa_arpsi') }} a
LEFT JOIN {{ ref('dim_constraint_severity') }} d
       ON d.constraint_code = a.constraint_code
      AND d.zone_type = a.zone_type
