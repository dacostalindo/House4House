{{ config(tags=['apa', 'flood']) }}

-- APA ARPSI floodplain — EU Floods Directive (DL 115/2010) flood polygons.
-- Bronze table is already typed; this view derives constraint_code + zone_type
-- so downstream joins to gold.dim_constraint_severity work on the same
-- (constraint_code, zone_type) compound key the 14 SRUP layers use.
--
-- Dual-CRS naming follows the canonical ADR [[2026-05-10-dual-crs-storage]]:
-- geom = 4326 (display), geom_pt = 3763 (distance/area in metres). The 14
-- SRUP siblings use the legacy `geom`(3763) + `geom_wgs84`(4326) — to be
-- migrated to canonical in a sprint-10 cleanup.

-- Discovery (run against bronze 2026-06-02):
--   SELECT return_period_years, COUNT(*) FROM bronze_hydrology.raw_apa_arpsi_floodplain GROUP BY 1 ORDER BY 1;
--   Result: 20→47, 100→94, 1000→47. Three bands, not two.

SELECT
    feature_id,
    'ARPSI_Floodplain'::TEXT                AS constraint_code,
    CASE return_period_years
        WHEN 20   THEN 'T20'
        WHEN 100  THEN 'T100'
        WHEN 1000 THEN 'T1000'
    END                                     AS zone_type,
    return_period_years,
    TRIM(river_basin)                       AS hydrographic_region,
    TRIM(location)                          AS location,
    TRIM(designation)                       AS designation,
    publication_date::DATE                  AS publication_date,
    -- ST_MakeValid: 132/188 ARPSI polygons have ring self-intersections /
    -- nested shells upstream (verified 2026-06-02). Cleaning at staging keeps
    -- silver geometries valid for downstream ST_Intersects without changing
    -- semantics (MakeValid preserves coverage; just topologically repairs).
    ST_Transform(ST_MakeValid(geom), 4326)  AS geom,
    ST_MakeValid(geom)                      AS geom_pt,
    _source_url,
    _load_timestamp                         AS _loaded_at
FROM {{ source('bronze_hydrology', 'raw_apa_arpsi_floodplain') }}
WHERE geom IS NOT NULL
