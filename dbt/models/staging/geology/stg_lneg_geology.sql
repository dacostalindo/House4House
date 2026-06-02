{{ config(tags=['lneg', 'geology']) }}

-- LNEG geology 1:500k (CGP500k) — national geological polygons (~282 rows).
-- Generic JSONB properties unpacked into typed columns. Exposes raw bronze
-- fields + a descriptive era_code parse only — no `geological_era_label` and
-- no `foundation_difficulty` in v1 (locked decisions 14+17: 1:500k era prefix
-- is too coarse for Eurocode 7 Geotechnical Categories; v2 path is a per-
-- formation lookup keyed on full lithology_code with citations).
--
-- Dual-CRS naming per [[2026-05-10-dual-crs-storage]] canonical.

SELECT
    feature_id,
    TRIM(properties->>'Idade_Litologia')        AS lithology_code,
    LEFT(TRIM(properties->>'Idade_Litologia'), 1) AS geological_era_code,
    ST_Transform(geom, 4326)                    AS geom,
    geom                                        AS geom_pt,
    _source_url,
    _load_timestamp                             AS _loaded_at
FROM {{ source('bronze_geology', 'raw_lneg_geology_500k') }}
WHERE geom IS NOT NULL
