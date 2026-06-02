{{ config(tags=['lneg', 'aquifer']) }}

-- LNEG Sistemas Aquíferos — national aquifer-system polygons (~63 rows).
-- Generic JSONB properties unpacked into typed columns. Exposes raw bronze
-- fields only — no `aquifer_vulnerability` derived in v1 (locked decision 17:
-- proper DRASTIC/GOD frameworks require depth-to-water + recharge + soil
-- media + vadose-zone impact, none of which are in this bronze).
--
-- Dual-CRS naming per [[2026-05-10-dual-crs-storage]] canonical:
-- geom = 4326, geom_pt = 3763.

SELECT
    feature_id,
    TRIM(properties->>'CodigoInag')             AS codigo_inag,
    TRIM(properties->>'NomeCompleto')           AS aquifer_name,
    TRIM(properties->>'SistemaAquifero')        AS aquifer_system,
    TRIM(properties->>'Idade')                  AS aquifer_age,
    TRIM(properties->>'IDUnidadeHidrogeologica') AS hydrogeo_unit_id,
    ST_Transform(geom, 4326)                    AS geom,
    geom                                        AS geom_pt,
    _source_url,
    _load_timestamp                             AS _loaded_at
FROM {{ source('bronze_hydrology', 'raw_lneg_aquiferos') }}
WHERE geom IS NOT NULL
