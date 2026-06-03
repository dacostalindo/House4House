-- silver_geo.land_use category invariants (regression + completeness).
--
-- Asserts that:
--   #1 — every silver row's land_use_category matches dim_cos_nomenclature.category_en
--   #2 — every distinct land_use_code in silver has a matching dim_cos_nomenclature
--        row (no NULL category — caught dropped/added L4 codes if DGT publishes
--        a new COS revision before we update the dim)
--   #3 — the is_forest flag matches L5 (Florestas), NOT L4 (agroforestry)
--
-- Why this test exists: the previous inline CASE in silver_geo.land_use was
-- off-by-one for L4-L9 (4→forest instead of agroforestry, 9→ocean instead of
-- water, etc.). The bug stayed invisible during Aveiro smoke-test scope
-- (Aveiro is predominantly L1∈{1,2,3} which were already correctly mapped)
-- and surfaced only when WS4 PR B populated land_use nationally for the
-- first time. Now sourced from dim_cos_nomenclature (DGT 2024 Série 2 spec,
-- Anexo 1 pp. 12-13) — this test pins the contract.
--
-- All assertions are empty-silver-safe: COUNT(*) WHERE NOT condition = 0
-- on empty silver returns 0, trivially passing in CI Tier-1.

BEGIN;

SELECT plan(3);

-- #1 — silver.land_use_category equals dim.category_en for every row.
SELECT is(
    (SELECT COUNT(*)::int FROM silver_geo.land_use l
     LEFT JOIN gold_analytics.dim_cos_nomenclature d
       ON d.code_l4 = l.land_use_code
     WHERE l.land_use_category IS DISTINCT FROM d.category_en),
    0,
    'Test #1 — every silver row land_use_category equals dim_cos_nomenclature.category_en'
);

-- #2 — no silver row has a land_use_code that is missing from the dim.
-- A non-zero result means either the DGT published a new L4 class or the
-- bronze loaded a malformed code. Investigate before re-pinning.
SELECT is(
    (SELECT COUNT(*)::int FROM silver_geo.land_use l
     LEFT JOIN gold_analytics.dim_cos_nomenclature d
       ON d.code_l4 = l.land_use_code
     WHERE d.code_l4 IS NULL),
    0,
    'Test #2 — every silver land_use_code resolves to a dim_cos_nomenclature row'
);

-- #3 — is_forest matches L5 (Florestas) exactly, NOT L4 (agroforestry).
-- The previous bug had `LIKE '4.%' AS is_forest`, which silently flagged
-- ~41k agroforestry polygons as forest at national scale.
SELECT is(
    (SELECT COUNT(*)::int FROM silver_geo.land_use
     WHERE is_forest IS DISTINCT FROM (land_use_code LIKE '5.%')),
    0,
    'Test #3 — is_forest equals (land_use_code LIKE ''5.%'') on every row'
);

SELECT * FROM finish();

ROLLBACK;
