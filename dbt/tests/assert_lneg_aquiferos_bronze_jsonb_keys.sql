-- silver-dq-baseline Rule 0 — Schema discovery precedes derivation.
-- Asserts the JSONB key set in bronze_hydrology.raw_lneg_aquiferos matches
-- what stg_lneg_aquiferos.sql is built for. Fails when LNEG adds or removes
-- a key upstream — that's the signal to re-run discovery + update the
-- staging SQL header comment + extraction list.
--
-- Pattern: dbt singular test passes when SELECT returns zero rows.

SELECT 1 AS jsonb_key_drift
WHERE (
    SELECT array_agg(DISTINCT k ORDER BY k)
    FROM {{ source('bronze_hydrology', 'raw_lneg_aquiferos') }},
         jsonb_object_keys(properties) k
) IS DISTINCT FROM ARRAY[
    'CodigoInag',
    'Idade',
    'IDUnidadeHidrogeologica',
    'NomeCompleto',
    'OBJECTID',
    'SistemaAquifero'
]
