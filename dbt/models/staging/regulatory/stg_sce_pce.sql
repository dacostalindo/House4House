-- SCE Pre-Energy Certificates (PCE) — Proxy for New Construction
-- Source: bronze_regulatory.raw_sce_pce (JSONL from SCE portal scraper)
-- Each record is one pre-certificate per apartment/fraction.
-- Multiple PCEs at the same address = multi-unit building.

WITH deduplicated AS (
    SELECT DISTINCT ON (doc_number)
        *
    FROM {{ source('bronze_regulatory', 'raw_sce_pce') }}
    ORDER BY doc_number, _scrape_date DESC
)

SELECT
    doc_number,
    morada                                  AS address,
    fracao                                  AS fraction,
    localidade                              AS locality,
    UPPER(TRIM(concelho))                   AS municipality,
    estado                                  AS status,
    doc_substituto                          AS replacement_doc,
    TRIM(tipo_documento)                    AS document_type,
    UPPER(TRIM(classe_energetica))          AS energy_class,
    CASE
        WHEN data_emissao ~ '^\d{4}/\d{2}/\d{2}$'
        THEN TO_DATE(data_emissao, 'YYYY/MM/DD')
    END                                     AS issued_date,
    CASE
        WHEN data_validade ~ '^\d{4}/\d{2}/\d{2}$'
        THEN TO_DATE(data_validade, 'YYYY/MM/DD')
    END                                     AS valid_until,
    TRIM(freguesia_detail)                  AS parish,
    perito_num                              AS expert_number,
    conservatoria                           AS land_registry,
    sob_o_num                               AS registry_number,
    artigo_matricial                        AS matrix_article,
    fracao_autonoma                         AS autonomous_fraction,
    tipo_documento ILIKE '%Pré%'
        OR tipo_documento ILIKE '%DCR%'     AS is_pce,
    query_distrito                          AS src_distrito_code,
    query_concelho                          AS src_concelho_code,
    query_freguesia                         AS src_freguesia_code,
    _scrape_date                            AS scrape_date,
    _ingested_at                            AS loaded_at
FROM deduplicated
WHERE doc_number IS NOT NULL
