-- stg_portal_listings_zome — canonical-schema staging for Zome listings.
-- bronze_listings.zome_listings is dlt SCD2-managed: filter _dlt_valid_to IS NULL
-- to take the current version per pid.
--
-- Floor plans: zome stores in aplantsgallery JSONB OBJECT (not array) with
-- 3-resolution keys {hres, lres, mres}. The hres array mixes real floor plans
-- with generic photos; we filter URLs whose basename starts with "planta" to
-- isolate the ~27% of listings with actual floor plans. zome URLs are direct
-- public links to images.zome.pt — no CDN prefix needed.
--
-- Areas: areabrutaconst = gross (ABC), areautilhab = useful, areaimplement =
-- footprint, areaterreno = land/lot.

WITH latest AS (
    -- DISTINCT ON guards against dlt SCD2 close-row duplicates (~6% rate on
    -- zome — wiki/sprints/sprint-09 status 2026-05-19, worst across portals).
    SELECT DISTINCT ON (pid) *
    FROM {{ source('bronze_listings', 'zome_listings') }}
    WHERE _dlt_valid_to IS NULL
      AND pid IS NOT NULL
    ORDER BY pid, _dlt_valid_from DESC
)

SELECT
    -- Identity
    'zome'::TEXT                                                     AS source,
    pid::TEXT                                                        AS source_listing_id,
    MD5('zome|' || pid::TEXT)::TEXT                                  AS listing_hash,
    COALESCE(url_detail_view_link,
             'https://www.zome.pt/imovel/' || pid::TEXT)             AS listing_url,

    -- Operation: idtiponegocio 1=venda, 2=arrendamento (typical Zome encoding)
    CASE idtiponegocio
        WHEN 1 THEN 'sale'
        WHEN 2 THEN 'rent'
        ELSE NULL
    END                                                              AS operation_type,

    -- Pricing: precosemformatacao is the numeric one
    NULLIF(precosemformatacao, 0)::NUMERIC                           AS price_eur,

    -- Areas
    areabrutaconst::NUMERIC                                          AS gross_area_m2,
    areautilhab::NUMERIC                                             AS useful_area_m2,
    areaimplement::NUMERIC                                           AS implantation_area_m2,
    areaterreno::NUMERIC                                             AS land_area_m2,
    NULL::BOOLEAN                                                    AS net_area_suspicious,

    -- Rooms
    LEAST(totalquartossuite, 15)                                     AS num_rooms,
    LEAST(attr_wcs, 10)                                              AS num_bathrooms,
    NULL::TEXT                                                       AS floor_raw,

    -- Property type
    tipoimovel                                                       AS property_type,
    txttipologiaimovel                                               AS property_subtype,
    CASE LOWER(COALESCE(tipoimovel, ''))
        WHEN 'apartamento'   THEN 'Apartment'
        WHEN 'apartment'     THEN 'Apartment'
        WHEN 'moradia'       THEN 'House'
        WHEN 'house'         THEN 'House'
        WHEN 'villa'         THEN 'Villa'
        WHEN 'duplex'        THEN 'Duplex'
        WHEN 'estudio'       THEN 'Studio'
        WHEN 'comercial'     THEN 'Commercial'
        ELSE 'Other'
    END                                                              AS property_type_canonical,

    -- Typology — extract T0..T5 from tipologiaimovel (varchar holding JSON string)
    -- or txttipologiaimovel (plain text)
    CASE
        WHEN txttipologiaimovel ~ '^T[0-5]'
            THEN substring(txttipologiaimovel FROM '^T[0-5]')
        WHEN tipologiaimovel ~ '^\{.*\}$'
             AND (tipologiaimovel::JSONB ->> 'PT') ~ '^T[0-5]'
            THEN substring(tipologiaimovel::JSONB ->> 'PT' FROM '^T[0-5]')
        ELSE NULL
    END                                                              AS typology,

    -- Energy + condition
    NULL::TEXT                                                       AS energy_class,
    txtcondicaoimovel                                                AS condition,
    NULL::INTEGER                                                    AS construction_year,

    -- Amenities (zome uses 0/1 integers; cast to bool)
    (attr_elevador = 1)                                              AS has_elevator,
    (attr_garagem = 1)                                               AS has_parking,
    NULL::BOOLEAN                                                    AS has_terrace,
    NULL::BOOLEAN                                                    AS has_garden,
    (attr_piscina = 1)                                               AS has_pool,

    -- Location: zome stores as text — cast carefully
    NULLIF(geocoordinateslat, '')::NUMERIC                           AS latitude,
    NULLIF(geocoordinateslong, '')::NUMERIC                          AS longitude,
    NULL::TEXT                                                       AS address_raw,
    COALESCE(localizacaolevel3, localizacaolevel4imovel)             AS location_name,

    -- Media + Floor Plans (filter aplantsgallery.hres[] by 'planta' filename)
    CASE WHEN jsonb_typeof(gallery) = 'array'
         THEN jsonb_array_length(gallery)
         ELSE 0 END                                                  AS image_count,
    COALESCE(
        (SELECT ARRAY_AGG(url ORDER BY url)
         FROM jsonb_array_elements_text(aplantsgallery->'hres') AS url
         WHERE aplantsgallery IS NOT NULL
           AND jsonb_typeof(aplantsgallery) = 'object'
           AND jsonb_typeof(aplantsgallery->'hres') = 'array'
           AND url ~* '/planta'),
        ARRAY[]::TEXT[]
    )                                                                AS floor_plan_urls,
    EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(aplantsgallery->'hres') AS url
        WHERE aplantsgallery IS NOT NULL
          AND jsonb_typeof(aplantsgallery) = 'object'
          AND jsonb_typeof(aplantsgallery->'hres') = 'array'
          AND url ~* '/planta'
    )                                                                AS has_floor_plan,
    COALESCE(
        (SELECT COUNT(*)::INTEGER
         FROM jsonb_array_elements_text(aplantsgallery->'hres') AS url
         WHERE aplantsgallery IS NOT NULL
           AND jsonb_typeof(aplantsgallery) = 'object'
           AND jsonb_typeof(aplantsgallery->'hres') = 'array'
           AND url ~* '/planta'),
        0
    )                                                                AS floor_plan_count,
    CASE WHEN EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(aplantsgallery->'hres') AS url
        WHERE aplantsgallery IS NOT NULL
          AND jsonb_typeof(aplantsgallery) = 'object'
          AND jsonb_typeof(aplantsgallery->'hres') = 'array'
          AND url ~* '/planta'
    ) THEN 'zome_aplants' END                                        AS floor_plan_source,

    -- Lifecycle
    _dlt_valid_from::DATE                                            AS last_seen_date,
    idestadoimovel::TEXT                                             AS listing_status_raw,

    -- Description (zome doesn't expose a description field in bronze)
    NULL::TEXT                                                       AS description_summary,
    NULL::TEXT                                                       AS listing_title,

    -- Agency
    NULL::TEXT                                                       AS agency_name

FROM latest
