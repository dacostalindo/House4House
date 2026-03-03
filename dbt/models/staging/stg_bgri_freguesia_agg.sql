-- Aggregate BGRI census subsections (203K rows) to freguesia level (3,049 rows)
SELECT
    dtmnfr21                                            AS freguesia_code,
    SUM(n_individuos)::INTEGER                          AS population_2021,
    SUM(n_agregados_domesticos_privados)::INTEGER       AS households_2021,
    -- Weighted average age from age bands (true median not computable from bands)
    CASE
        WHEN SUM(n_individuos) > 0 THEN
            ROUND(((
                SUM(n_individuos_0_14) * 7.0
                + SUM(n_individuos_15_24) * 19.5
                + SUM(n_individuos_25_64) * 44.5
                + SUM(n_individuos_65_ou_mais) * 77.5
            ) / NULLIF(SUM(n_individuos), 0))::NUMERIC, 1)
        ELSE NULL
    END                                                 AS weighted_avg_age
FROM {{ source('bronze_ine', 'raw_bgri') }}
GROUP BY dtmnfr21
