-- Cadastro Predial — Official Property Parcel Boundaries
-- Source: bronze_regulatory.raw_cadastro (GeoJSON from DGT OGC API)
-- OGC API properties: inspireid, nationalcadastralreference, areavalue,
--   administrativeunit, label, validfrom, validto, beginlifespanversion
-- Bronze DAG maps these 1:1 via props.get("fieldname")

SELECT
    nationalcadastralreference              AS cadastral_ref,      -- e.g. "AAA000338225"
    areavalue                               AS area_m2,            -- official parcel area in m²
    administrativeunit                      AS admin_unit_code,    -- 6-digit DTCC code (e.g. "080809")
    label,
    beginlifespanversion                    AS record_date,
    geom                                    AS geom_pt,            -- EPSG:3763 (transformed from 4326 in bronze)
    ST_Transform(geom, 4326)                AS geom_4326,          -- EPSG:4326 (WGS84)
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_cadastro') }}
WHERE geom IS NOT NULL
