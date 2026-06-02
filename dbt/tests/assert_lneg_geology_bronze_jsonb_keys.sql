-- silver-dq-baseline Rule 0 — Schema discovery precedes derivation.
-- Asserts the JSONB key set in bronze_geology.raw_lneg_geology_500k matches
-- what stg_lneg_geology.sql is built for. Fails when LNEG adds or removes a
-- key upstream — that's the signal to re-run discovery + update the staging
-- SQL header comment + extraction list.
--
-- Pattern: dbt singular test passes when SELECT returns zero rows.
-- The set comparison returns 1 row when the key set differs, 0 otherwise.

SELECT 1 AS jsonb_key_drift
WHERE (
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
