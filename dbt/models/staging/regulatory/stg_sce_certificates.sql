-- SCE Energy Certificates — PCE / CE / DCR
-- Source: bronze_regulatory.raw_sce_certificates (JSONL from SCE portal scraper)
-- Each record is one document per apartment/fraction. PCEs are pre-construction
-- certificates (a proxy for upcoming construction); CEs are issued on completion;
-- DCRs accompany construction declarations. Multiple records at the same address
-- = multi-unit building.
--
-- Geocoding LEFT JOIN (Sprint-08 Activity 7, 2026-05-15):
--   Pulls (lat, lng) + clustering key from bronze_enrichment.raw_sce_geocoded,
--   populated by the sce_geocode DAG (Nominatim → freguesia-centroid cascade).
--   LEFT JOIN preserves row count when a doc_number is not yet geocoded
--   (Test #1 — regression: row count unchanged after the JOIN). The resulting
--   geom_4326 / geom_3763 columns are what sprint-09 Slice B's
--   silver_sce_buildings consumes for ST_ClusterDBSCAN.

WITH deduplicated AS (
    SELECT DISTINCT ON (doc_number)
        *
    FROM {{ source('bronze_regulatory', 'raw_sce_certificates') }}
    ORDER BY doc_number, _scrape_date DESC
)

SELECT
    d.doc_number,
    d.morada                                  AS address,
    d.fracao                                  AS fraction,
    d.localidade                              AS locality,
    UPPER(TRIM(d.concelho))                   AS municipality,
    d.estado                                  AS status,
    d.doc_substituto                          AS replacement_doc,
    TRIM(d.tipo_documento)                    AS document_type,
    UPPER(TRIM(d.classe_energetica))          AS energy_class,
    CASE
        WHEN d.data_emissao ~ '^\d{4}/\d{2}/\d{2}$'
        THEN TO_DATE(d.data_emissao, 'YYYY/MM/DD')
    END                                       AS issued_date,
    CASE
        WHEN d.data_validade ~ '^\d{4}/\d{2}/\d{2}$'
        THEN TO_DATE(d.data_validade, 'YYYY/MM/DD')
    END                                       AS valid_until,
    TRIM(d.freguesia_detail)                  AS parish,
    d.perito_num                              AS expert_number,
    d.conservatoria                           AS land_registry,
    d.sob_o_num                               AS registry_number,
    d.artigo_matricial                        AS matrix_article,
    d.fracao_autonoma                         AS autonomous_fraction,
    d.tipo_documento ILIKE '%Pré%'
        OR d.tipo_documento ILIKE '%DCR%'     AS is_pce,
    d.query_distrito                          AS src_distrito_code,
    d.query_concelho                          AS src_concelho_code,
    d.query_freguesia                         AS src_freguesia_code,

    -- ── Geocoding (sprint-08 Activity 7) ──
    g.address_lat,
    g.address_lng,
    g.geocode_source,
    g.geocode_confidence,
    g.normalized_address,
    CASE
        WHEN g.address_lat IS NOT NULL AND g.address_lng IS NOT NULL
        THEN ST_SetSRID(ST_MakePoint(g.address_lng::float, g.address_lat::float), 4326)
    END                                       AS geom_4326,
    CASE
        WHEN g.address_lat IS NOT NULL AND g.address_lng IS NOT NULL
        THEN ST_Transform(
            ST_SetSRID(ST_MakePoint(g.address_lng::float, g.address_lat::float), 4326),
            3763
        )
    END                                       AS geom_3763,

    d._scrape_date                            AS scrape_date,
    d._ingested_at                            AS loaded_at
FROM deduplicated d
LEFT JOIN {{ source('bronze_enrichment', 'raw_sce_geocoded') }} g
    ON g.doc_number = d.doc_number
WHERE d.doc_number IS NOT NULL
