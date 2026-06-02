-- silver_market.ine_indicators_long invariants (sprint-09 WS4 quick-wins batch).
-- Covers silver-dq-baseline Rule 3 (row-count parity) + silver-derived
-- invariants (freguesia/concelho substring derivation, indicator_category backfill catch).
--
-- Tests:
--   #31  silver row count == bronze WHERE valor IS NOT NULL count
--        (no silver-side filter — bronze loader is the gate per locked decision 13)
--   #32  freguesia_code derivation correctness across both INE coding schemes
--   #33  concelho_code derivation correctness across both INE coding schemes
--   #34  indicator_category IS NOT NULL on every silver row
--        (catches bronze backfill miss after the schema migration)

BEGIN;

SELECT plan(4);

-- #31 — Bronze→silver row-count parity (Rule 3). Bronze stg already filters
-- valor IS NOT NULL; silver inherits.
SELECT is(
    (SELECT COUNT(*)::int FROM silver_market.ine_indicators_long),
    (SELECT COUNT(*)::int FROM bronze_ine.raw_indicators WHERE valor IS NOT NULL),
    'Test #31 — silver row count equals bronze WHERE valor IS NOT NULL'
);

-- #32 — freguesia_code: 6-char → as-is; 9-char → RIGHT 6; else NULL
SELECT is(
    (SELECT COUNT(*)::int FROM silver_market.ine_indicators_long
     WHERE NOT (
        CASE
            WHEN LENGTH(geographic_code) = 6 THEN freguesia_code = geographic_code
            WHEN LENGTH(geographic_code) = 9 THEN freguesia_code = RIGHT(geographic_code, 6)
            ELSE freguesia_code IS NULL
        END
     )),
    0,
    'Test #32 — freguesia_code derived correctly (6-char as-is, 9-char RIGHT-6, else NULL)'
);

-- #33 — concelho_code: 4-digit → as-is; 7-char → RIGHT 4; 6-char → LEFT 4;
-- 9-char → SUBSTRING(4, 4); else NULL
SELECT is(
    (SELECT COUNT(*)::int FROM silver_market.ine_indicators_long
     WHERE NOT (
        CASE
            WHEN LENGTH(geographic_code) = 4 AND geographic_code ~ '^\d+$' THEN concelho_code = geographic_code
            WHEN LENGTH(geographic_code) = 7 THEN concelho_code = RIGHT(geographic_code, 4)
            WHEN LENGTH(geographic_code) = 6 THEN concelho_code = LEFT(geographic_code, 4)
            WHEN LENGTH(geographic_code) = 9 THEN concelho_code = SUBSTRING(geographic_code FROM 4 FOR 4)
            ELSE concelho_code IS NULL
        END
     )),
    0,
    'Test #33 — concelho_code derived correctly across both CAOP-flat + NUTS3-prefixed schemes'
);

-- #34 — indicator_category populated on every row (backfill catch)
SELECT is(
    (SELECT COUNT(*)::int FROM silver_market.ine_indicators_long
     WHERE indicator_category IS NULL),
    0,
    'Test #34 — indicator_category IS NOT NULL on every row (bronze backfill complete)'
);

SELECT * FROM finish();

ROLLBACK;
