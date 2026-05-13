{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_parcel_universe_geom_pt ON {{ this }} USING GIST(geom_pt)",
            "CREATE INDEX IF NOT EXISTS idx_parcel_universe_geom_4326 ON {{ this }} USING GIST(geom_4326)",
            "CREATE INDEX IF NOT EXISTS idx_parcel_universe_concelho ON {{ this }} (concelho_code)",
            "CREATE INDEX IF NOT EXISTS idx_parcel_universe_source ON {{ this }} (source)"
        ]
    )
}}

-- Aveiro município (concelho_code = '0105') parcel universe.
--
-- UNION of:
--   stg_cadastro  — formal/legal cadastre (DGT OGC API), covers 2000-2007 survey areas only
--   stg_bupi      — modern simplified cadastre (RGG), fills gaps where cadastro is absent
--
-- Spatial dedup: cadastro is authoritative where present. A BUPI row is
-- dropped from the universe if ≥50% of its area overlaps a cadastro parcel
-- (same plot from both systems → keep only the cadastro version).
--
-- v1 wedge scope: Aveiro município only. National rollout deferred to v2;
-- to extend, drop the `WHERE concelho_code = '0105'` filter in the two CTEs.

WITH cadastro_aveiro AS (
    SELECT
        'cadastro:' || cadastral_ref           AS parcel_id,
        'cadastro'::TEXT                       AS source,
        cadastral_ref,
        NULL::TEXT                             AS process_id,
        NULL::TEXT                             AS matrix_number,
        admin_unit_code                        AS dicofre,
        LEFT(admin_unit_code, 4)               AS concelho_code,
        area_m2,
        geom_pt,
        geom_4326
    FROM {{ ref('stg_cadastro') }}
    WHERE admin_unit_code LIKE '0105%'   -- Aveiro município (4-digit concelho prefix)
      AND geom_pt IS NOT NULL
),

bupi_aveiro AS (
    SELECT
        'bupi:' || process_id::TEXT            AS parcel_id,
        'bupi'::TEXT                           AS source,
        NULL::TEXT                             AS cadastral_ref,
        process_id::TEXT                       AS process_id,
        matrix_number,
        dicofre,
        LEFT(dicofre, 4)                       AS concelho_code,
        area_m2,
        geom_pt,
        geom_4326
    FROM {{ ref('stg_bupi') }}
    WHERE dicofre LIKE '0105%'           -- Aveiro município
      AND geom_pt IS NOT NULL
),

-- BUPI rows where ≥50% of the area overlaps a cadastro parcel get
-- dropped — cadastro is authoritative for those locations.
bupi_dedup_drops AS (
    SELECT DISTINCT b.parcel_id
    FROM bupi_aveiro b
    JOIN cadastro_aveiro c
      ON ST_Intersects(b.geom_pt, c.geom_pt)
    WHERE b.area_m2 > 0
      AND ST_Area(ST_Intersection(b.geom_pt, c.geom_pt)) >= 0.5 * b.area_m2
)

SELECT * FROM cadastro_aveiro
UNION ALL
SELECT * FROM bupi_aveiro
WHERE parcel_id NOT IN (SELECT parcel_id FROM bupi_dedup_drops)
