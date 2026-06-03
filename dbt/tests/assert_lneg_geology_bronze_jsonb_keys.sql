-- silver-dq-baseline Rule 0 — Schema discovery precedes derivation.
-- Asserts the JSONB key set in bronze_geology.raw_lneg_geology_500k matches
-- what stg_lneg_geology.sql is built for. Fails when LNEG adds or removes a
-- key upstream — that's the signal to re-run discovery + update the staging
-- SQL header comment + extraction list.
--
-- Pattern: dbt singular test passes when SELECT returns zero rows.
-- The set comparison returns 1 row when the key set differs, 0 otherwise.
--
-- Empty-bronze short-circuit: in CI Tier-1, bronze is bootstrapped from
-- empty stubs (no rows → no JSONB keys → array_agg returns NULL → would
-- always mismatch). Skip the check when bronze is empty; the test fires
-- meaningfully only against a populated warehouse.

SELECT 1 AS jsonb_key_drift
WHERE (SELECT COUNT(*) FROM {{ source('bronze_geology', 'raw_lneg_geology_500k') }}) > 0
  AND (
      SELECT array_agg(DISTINCT k ORDER BY k)
      FROM {{ source('bronze_geology', 'raw_lneg_geology_500k') }},
           jsonb_object_keys(properties) k
  ) IS DISTINCT FROM ARRAY[
      'Código',
      'Descrição',
      'Descrição1',
      'Eonotema',
      'Eratema',
      'Intrusões_plutónicas',
      'Intrusões_plutónicas1',
      'OBJECTID',
      'Série',
      'Sistema',
      'Zona'
  ]
