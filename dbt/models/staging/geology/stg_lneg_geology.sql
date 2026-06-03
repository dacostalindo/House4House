{{ config(tags=['lneg', 'geology']) }}

-- LNEG geology 1:500k (CGP500k) — national geological polygons (~282 rows).
-- Generic JSONB properties unpacked into typed columns. Exposes raw bronze
-- fields only — no `foundation_difficulty` in v1 (locked decisions 14+17:
-- 1:500k codes are too coarse for Eurocode 7 Geotechnical Categories; v2 path
-- is a per-formation lookup keyed on the full code with citations).
--
-- Dual-CRS naming per [[2026-05-10-dual-crs-storage]] canonical.
--
-- Discovery (run against bronze 2026-06-02):
--   SELECT DISTINCT jsonb_object_keys(properties) FROM bronze_geology.raw_lneg_geology_500k;
--   Result keys: Código, Descrição, Descrição1, Eonotema, Eratema, Sistema,
--   Série, Zona, Intrusões_plutónicas, Intrusões_plutónicas1, OBJECTID.
--
-- The wiki source page previously documented "Idade_Litologia" as the key
-- field; that was wrong — the actual schema uses `Código` for the lithology
-- code (e.g. 'gama', 'PEU', 'CTRVA2', 'a', 'J3A', 'g_14') and carries
-- structured chrono-stratigraphic context in separate fields: Eratema (era),
-- Sistema (geological period), Série (epoch), Zona, plus Descrição (rich
-- text label like "Aluviões"). No meaningful single-character era prefix on
-- the code itself — use `era` directly for grouping.

SELECT
    feature_id,
    TRIM(properties->>'Código')                 AS lithology_code,
    TRIM(properties->>'Descrição')              AS lithology_description,
    TRIM(properties->>'Descrição1')             AS lithology_description_extra,
    TRIM(properties->>'Eonotema')               AS eon,
    TRIM(properties->>'Eratema')                AS era,
    TRIM(properties->>'Sistema')                AS geological_period,
    TRIM(properties->>'Série')                  AS epoch,
    TRIM(properties->>'Zona')                   AS chrono_zone,
    TRIM(properties->>'Intrusões_plutónicas')   AS plutonic_intrusions,
    -- ST_MakeValid: 41/282 CGP500k polygons have ring self-intersections
    -- upstream (verified 2026-06-02). Cleaning at staging preserves area
    -- coverage while making geometries valid for downstream ST_Intersects.
    ST_Transform(ST_MakeValid(geom), 4326)      AS geom,
    ST_MakeValid(geom)                          AS geom_pt,
    _source_url,
    _load_timestamp                             AS _loaded_at
FROM {{ source('bronze_geology', 'raw_lneg_geology_500k') }}
WHERE geom IS NOT NULL
