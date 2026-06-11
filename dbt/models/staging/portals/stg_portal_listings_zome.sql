-- stg_portal_listings_zome — canonical-schema staging for Zome listings.
-- bronze_listings.zome_listings is dlt SCD2-managed: filter _dlt_valid_to IS NULL
-- to take the current version per pid.
--
-- Floor plans: zome stores in aplantsgallery JSONB OBJECT (not array) with
-- 3-resolution keys {hres, lres, mres}. Column literally means "a plantas
-- gallery" — its sole purpose is floor plans. Any non-empty hres entry is
-- treated as a plan (filenames like 'planta_...', 'planta1', 'piso1', or
-- bare 'N' are all unit/floor-numbered plans). 2026-06-06 correction —
-- earlier filter on '/planta' basename was over-strict and dropped legitimate
-- multi-unit numbered plans. zome URLs are direct public links to
-- images.zome.pt — no CDN prefix needed.
--
-- Areas: areabrutaconst = gross (ABC), areautilhab = useful, areaimplement =
-- footprint, areaterreno = land/lot.

WITH latest AS (
    -- DISTINCT ON guards against dlt SCD2 close-row duplicates (~6% rate on
    -- zome — wiki/sprints/sprint-09 status 2026-05-19, worst across portals).
    --
    -- Scope filter (2026-06-06): only listings associated with an
    -- empreendimento (development) are in scope for unified_listings_residential.
    -- Filter on typed idemp (bigint) — the numeric empreendimento id, same
    -- field unified_developments uses as portal_dev_id (sourced there from
    -- zome_developments.venture_id, also bigint). emid (text code like
    -- EMPT194625) is co-populated and has identical coverage (1,140 / 9,335
    -- active = 12.2%), but using idemp keeps the FK join uniform with
    -- unified_developments.
    SELECT DISTINCT ON (pid) *
    FROM {{ source('bronze_listings', 'zome_listings') }}
    WHERE _dlt_valid_to IS NULL
      AND pid IS NOT NULL
      AND idemp IS NOT NULL AND idemp > 0
    ORDER BY pid, _dlt_valid_from DESC
)

SELECT
    -- Identity
    'zome'::TEXT                                                     AS source,
    pid::TEXT                                                        AS source_listing_id,
    MD5('zome|' || pid::TEXT)::TEXT                                  AS listing_hash,
    -- portal_dev_id = idemp::TEXT (the numeric empreendimento id).
    -- Matches unified_developments which uses venture_id::TEXT for Zome's
    -- portal_dev_id (same underlying numeric id, different column name).
    idemp::TEXT                                                      AS portal_dev_id,
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

    -- Media + Floor Plans — aplantsgallery is the dedicated floor-plan column;
    -- any non-empty entry in hres is a plan.
    CASE WHEN jsonb_typeof(gallery) = 'array'
         THEN jsonb_array_length(gallery)
         ELSE 0 END                                                  AS image_count,
    COALESCE(
        (SELECT ARRAY_AGG(url ORDER BY url)
         FROM jsonb_array_elements_text(aplantsgallery->'hres') AS url
         WHERE jsonb_typeof(aplantsgallery) = 'object'
           AND jsonb_typeof(aplantsgallery->'hres') = 'array'),
        ARRAY[]::TEXT[]
    )                                                                AS floor_plan_urls,
    (jsonb_typeof(aplantsgallery) = 'object'
     AND jsonb_typeof(aplantsgallery->'hres') = 'array'
     AND jsonb_array_length(aplantsgallery->'hres') > 0)             AS has_floor_plan,
    CASE WHEN jsonb_typeof(aplantsgallery) = 'object'
              AND jsonb_typeof(aplantsgallery->'hres') = 'array'
         THEN jsonb_array_length(aplantsgallery->'hres')
         ELSE 0 END                                                  AS floor_plan_count,
    CASE WHEN jsonb_typeof(aplantsgallery) = 'object'
              AND jsonb_typeof(aplantsgallery->'hres') = 'array'
              AND jsonb_array_length(aplantsgallery->'hres') > 0
         THEN 'zome_aplants' END                                     AS floor_plan_source,

    -- Lifecycle
    _dlt_valid_from::DATE                                            AS last_seen_date,
    idestadoimovel::TEXT                                             AS listing_status_raw,

    -- Description (zome doesn't expose a description field in bronze)
    NULL::TEXT                                                       AS description_summary,
    NULL::TEXT                                                       AS listing_title,

    -- Agency
    NULL::TEXT                                                       AS agency_name

FROM latest
