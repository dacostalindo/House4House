{{
    config(
        materialized='table',
        indexes=[
            {'columns': ['geom_pt'], 'type': 'gist'},
            {'columns': ['geom_4326'], 'type': 'gist'},
            {'columns': ['concelho_code']},
            {'columns': ['source']}
        ]
    )
}}

-- National parcel universe.
--
-- UNION of:
--   stg_cadastro  — formal/legal cadastre (DGT OGC API), covers 2000-2007 survey areas only
--   stg_bupi      — modern simplified cadastre (RGG), fills gaps where cadastro is absent
--
-- Spatial dedup: cadastro is authoritative where present. A BUPI row is
-- dropped from the universe if ≥50% of its area overlaps a cadastro parcel
-- (same plot from both systems → keep only the cadastro version).
--
-- The dedup JOIN is concelho-prefiltered (same 4-digit concelho_code) BEFORE
-- the spatial test. Without this, the national-scale dedup would do a
-- 3.2M × 1.75M cross-product even with GIST. With the prefilter, the join
-- runs per-concelho — fast.
--
-- Indexes declared via dbt-postgres's native `indexes` config (NOT post_hook):
-- the post_hook CREATE INDEX path doesn't survive table rebuilds reliably
-- for this model (the swap-rename ordering drops the indexes).
--
-- v1 wedge consumers (sprint-09's gold.fn_assess_polygon) filter at query
-- time, e.g. WHERE concelho_code = '0105' for Aveiro município. The B-tree
-- index on concelho_code makes the filter free.

WITH cadastro_all AS (
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
    WHERE admin_unit_code IS NOT NULL
      AND geom_pt IS NOT NULL
),

bupi_all AS (
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
    WHERE dicofre IS NOT NULL
      AND geom_pt IS NOT NULL
),

-- BUPI rows where ≥50% of the area overlaps a cadastro parcel get
-- dropped — cadastro is authoritative for those locations. Concelho-equality
-- prefilter keeps the spatial join tractable at national scale.
bupi_dedup_drops AS (
    SELECT DISTINCT b.parcel_id
    FROM bupi_all b
    JOIN cadastro_all c
      ON b.concelho_code = c.concelho_code
     AND ST_Intersects(b.geom_pt, c.geom_pt)
    WHERE b.area_m2 > 0
      AND ST_Area(ST_Intersection(b.geom_pt, c.geom_pt)) >= 0.5 * b.area_m2
)

SELECT * FROM cadastro_all
UNION ALL
SELECT * FROM bupi_all
WHERE parcel_id NOT IN (SELECT parcel_id FROM bupi_dedup_drops)
