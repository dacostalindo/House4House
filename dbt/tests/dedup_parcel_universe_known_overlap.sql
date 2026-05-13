-- Sprint-08 Activity 4 dedup correctness test (Appendix C Test #12).
--
-- Assert: no BUPI parcel in `parcel_universe` overlaps a cadastro parcel by
-- ≥50% of its area. If any such row exists, the dedup CTE in
-- `parcel_universe.sql` (which drops BUPI rows that overlap cadastro by
-- ≥50%) failed to apply.
--
-- dbt singular test convention: passes when the SELECT returns zero rows.

WITH overlaps AS (
    SELECT
        b.parcel_id AS bupi_parcel_id,
        c.parcel_id AS cadastro_parcel_id,
        b.area_m2 AS bupi_area_m2,
        ST_Area(ST_Intersection(b.geom_pt, c.geom_pt)) AS overlap_m2,
        ST_Area(ST_Intersection(b.geom_pt, c.geom_pt)) / NULLIF(b.area_m2, 0) AS overlap_ratio
    FROM {{ ref('parcel_universe') }} b
    JOIN {{ ref('parcel_universe') }} c
      ON ST_Intersects(b.geom_pt, c.geom_pt)
    WHERE b.source = 'bupi'
      AND c.source = 'cadastro'
      AND b.area_m2 > 0
      AND ST_Area(ST_Intersection(b.geom_pt, c.geom_pt)) >= 0.5 * b.area_m2
)

SELECT *
FROM overlaps
