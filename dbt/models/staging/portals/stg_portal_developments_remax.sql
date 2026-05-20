-- Canonical RE/MAX development staging — normalizes bronze_listings.remax_developments
-- to the 13-column cross-portal schema consumed by silver_unified_developments
-- (sprint-09 Slice B-prime PR-C).
--
-- Pattern: this is the TEMPLATE for the 4 stg_portal_developments_<portal>.sql
-- models. PR-B1 ships RE/MAX; PR-B2/B3/B4 mirror this shape for Zome, Idealista, JLL.
--
-- RE/MAX coords caveat (documented in [[portal-field-map]] Notes column, 2026-05-18
-- audit): coordinates are parish-centroid-precision, not development-precise.
-- 51% of RE/MAX devs have NULL coords; the 49% with coords often share lat/lng
-- with neighbouring devs in the same parish. Downstream PR-C uses name-similarity
-- (Levenshtein connected-components) to disambiguate same-coord clusters.
--
-- SCD2 multi-active defensive guard (PR-B1 audit 2026-05-19): bronze occasionally
-- has 2 rows with `_dlt_valid_to IS NULL` for the same `development_id`. The
-- dlt SCD2 merge config is correct (strategy=scd2 + primary_key=development_id);
-- the bug is dlt 1.x's close-row UPDATE occasionally missing on the previous
-- version's row_hash when a new version is inserted. Empirical rate (2026-05-19
-- audit): 2 of 603 remax_devs (0.33%), 55 of 8,266 remax_listings (0.67%), 6 of
-- 12,440 remax_plots, etc. Fresh re-scrapes have 0 dupes (idealista re-scrape
-- 2026-05-18 confirmed clean) — historical artifact. DISTINCT ON pattern picks
-- the latest `_dlt_valid_from` per PK. Same idiom as
-- `dbt/models/staging/regulatory/stg_sce_certificates.sql`. Logged as a sprint-10
-- portal data-quality follow-up: investigate dlt SCD2 close-row miss + consider
-- periodic clean re-scrapes.

WITH active_latest AS (
    SELECT DISTINCT ON (development_id) *
    FROM {{ source('bronze_listings', 'remax_developments') }}
    WHERE development_id IS NOT NULL
      AND _dlt_valid_to IS NULL
    ORDER BY development_id, _dlt_valid_from DESC
)

SELECT
    'remax'::TEXT                                                  AS portal,
    development_id::TEXT                                           AS portal_dev_id,
    name                                                           AS canonical_name,
    NULLIF(TRIM(CONCAT_WS(', ', region_name3, region_name2)), '')  AS address_text,
    UPPER(TRIM(region_name2))                                      AS concelho,
    region_name3                                                   AS parish,
    zip_code                                                       AS postal_code,
    CASE
        WHEN latitude IS NOT NULL AND longitude IS NOT NULL
        THEN ST_Transform(
            ST_SetSRID(ST_MakePoint(longitude::FLOAT, latitude::FLOAT), 4326),
            3763
        )
    END                                                            AS geom_3763,
    CASE
        WHEN latitude IS NOT NULL AND longitude IS NOT NULL
        THEN ST_SetSRID(ST_MakePoint(longitude::FLOAT, latitude::FLOAT), 4326)
    END                                                            AS geom_4326,
    listings_count::INTEGER                                        AS total_units,
    'https://www.remax.pt/empreendimentos/' || slug                AS listing_url,
    jsonb_build_object(
        'region_name1', region_name1,
        'minimum_price', minimum_price,
        'agent_name', agent_name,
        'office_name', office_name,
        'publish_date', publish_date
    )                                                              AS raw_meta,
    NOW()::TIMESTAMPTZ                                             AS _loaded_at
FROM active_latest
