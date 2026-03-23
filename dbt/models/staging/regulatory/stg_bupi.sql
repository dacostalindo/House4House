-- BUPI — Simplified Cadastral Property Parcels (RGG)
-- Source: bronze_regulatory.raw_bupi (GPKG from dados.gov.pt, ~3.25M parcels)
-- GPKG layer: rgg_{date}_opendata (auto-detected)
-- GPKG fields: ProcessoId, NumeroMatriz, Dicofre, Concelho, Freguesia, Area_m2
-- PostgreSQL lowercases column names, so GPKG "ProcessoId" → bronze "processoid"

SELECT
    processoid                      AS process_id,
    numeromatriz                    AS matrix_number,
    dicofre,
    concelho                        AS municipality,
    freguesia                       AS parish,
    area_m2,
    geom                            AS geom_pt,          -- EPSG:3763 (PT-TM06/ETRS89)
    ST_Transform(geom, 4326)        AS geom_4326,        -- EPSG:4326 (WGS84)
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_bupi') }}
WHERE geom IS NOT NULL
  AND dicofre IS NOT NULL
  AND dicofre != ''
