-- Sourced from the OGC API path (raw_srup_ran_ogc) as of 2026-05-13.
-- The legacy WFS path (raw_srup_ran via pipelines/gis/srup/) was retired the
-- same day after the OGC API (`ogcapi.dgterritorio.gov.pt/collections/srup_ran`)
-- was confirmed to cover the same data nationally.
--
-- Note: OGC field names differ from the legacy WFS (lowercase snake_case
-- vs uppercase PT all-caps). Mapping:
--   WFS CONCELHO   → OGC municipios   (national list, comma-separated text)
--   WFS SERVIDAO   → OGC servidao
--   WFS DINAMICA   → (no equivalent in OGC; dropped)
--   WFS RIGOR      → (no equivalent in OGC; dropped)
--   WFS AUTOR      → (no equivalent in OGC; dropped)
--   WFS DATA       → OGC serv_data
-- New OGC-only fields: designacao, tipologia, lei_tipo, serv_dr,
-- serv_hiperligacao, serv_lei.
SELECT
    feature_id,
    'ran'::TEXT                          AS category,
    layer_name                           AS feature_type,
    TRIM(properties->>'municipios')      AS municipality,
    TRIM(properties->>'servidao')        AS restriction_type,
    TRIM(properties->>'designacao')      AS designation,
    TRIM(properties->>'tipologia')       AS typology,
    TRIM(properties->>'lei_tipo')        AS law_type,
    TRIM(properties->>'serv_data')       AS restriction_date,
    TRIM(properties->>'serv_dr')         AS dr_reference,
    TRIM(properties->>'serv_lei')        AS restriction_law,
    TRIM(properties->>'serv_hiperligacao') AS restriction_url,
    properties,
    geom,
    ST_Transform(geom, 4326) AS geom_wgs84,
    _source_url,
    _load_timestamp
FROM {{ source('bronze_regulatory', 'raw_srup_ran_ogc') }}
WHERE geom IS NOT NULL
