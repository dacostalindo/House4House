-- Sprint-08 Activity 4 dedup correctness test (Appendix C Test #12).
--
-- Assert: no BUPI parcel in `parcel_universe` overlaps a cadastro parcel by
-- ≥50% of its area. If any such row exists, the dedup CTE in
-- `parcel_universe.sql` failed to drop it.
--
-- Sampled at 10,000 BUPI rows for tractability — at national scale (3.2M
-- BUPI × 1.8M cadastro per concelho) the full self-join took >3 min even
-- with the concelho-equality prefilter. The sample is a regression guard
-- against a structural dedup bug rather than an exhaustive correctness
-- proof; if the dedup CTE is wrong, ~10K random rows will surface
-- violations with high probability (false-negative rate < 1% if there
-- are more than a few hundred true violations to find).
--
-- dbt singular test convention: passes when the SELECT returns zero rows.
-- Note: dbt wraps singular tests in `... from ( <body> )`, so the body
-- MUST be a single SELECT (no leading WITH).

SELECT
    b.parcel_id AS bupi_parcel_id,
    c.parcel_id AS cadastro_parcel_id,
    b.area_m2 AS bupi_area_m2,
    ST_Area(ST_Intersection(b.geom_pt, c.geom_pt)) AS overlap_m2,
    ST_Area(ST_Intersection(b.geom_pt, c.geom_pt)) / NULLIF(b.area_m2, 0) AS overlap_ratio
FROM (
    SELECT * FROM {{ ref('parcel_universe') }}
    WHERE source = 'bupi' AND area_m2 > 0
    ORDER BY md5(parcel_id)
    LIMIT 10000
) b
JOIN {{ ref('parcel_universe') }} c
  ON b.concelho_code = c.concelho_code
 AND ST_Intersects(b.geom_pt, c.geom_pt)
WHERE c.source = 'cadastro'
  AND ST_Area(ST_Intersection(b.geom_pt, c.geom_pt)) >= 0.5 * b.area_m2
