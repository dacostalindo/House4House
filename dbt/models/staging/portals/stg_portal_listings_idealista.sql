-- stg_portal_listings_idealista — canonical-schema staging for Idealista
-- DEVELOPMENT UNITS (new-construction units in marketed projects).
--
-- Source: bronze_listings.idealista_development_units (dlt SCD2) — Pass 3 RE
-- API enrichment per unit, discovered via Pass 1+2 of the developments DAG
-- (/comprar-empreendimentos/). Each row carries a development_id linking back
-- to the parent project; this table is dev-linked BY DESIGN.
--
-- 2026-06-06 refactor: previously this staging consumed bronze_listings.raw_idealista
-- (LEGACY append-only resale catalog), which mixed dev-linked + arbitrary
-- resale listings — NOT the correct scope for unified_listings_residential.
-- Switched to idealista_development_units to match the cross-portal contract:
-- residential silver holds only development-marketed listings.
--
-- Pass 3 stubs filtered out (_has_detail = FALSE) — these are placeholder
-- rows for units discovered via Pass 2 dev-page parse but where the RE API
-- detail call failed (e.g. ZenRows outage, deactivated listing). They have
-- unit_id + summary_from_dev_page only, no typed price/area/rooms. Silver
-- waits for the next clean Pass 3 to populate; no synthetic data.
--
-- Floor plans: idealista_development_units has the same property_image_tags
-- parallel-array convention as raw_idealista — tag='plan' identifies plan
-- images via index against property_images.

WITH latest AS (
    -- dlt SCD2 close-row dedup defensive guard (~0.01% rate on idealista_dev_units).
    -- Filter to enriched rows only (_has_detail = TRUE); stubs land back here
    -- automatically when Pass 3 RE API recovers.
    SELECT DISTINCT ON (unit_id) *
    FROM {{ source('bronze_listings', 'idealista_development_units') }}
    WHERE _dlt_valid_to IS NULL
      AND unit_id IS NOT NULL
      AND _has_detail IS TRUE
    ORDER BY unit_id, _dlt_valid_from DESC
),

plan_urls AS (
    -- Parallel-index join: property_images[i] is a plan iff property_image_tags[i] = 'plan'.
    SELECT
        l.unit_id,
        ARRAY_AGG(img.url ORDER BY img.ord)
            FILTER (WHERE tag.tag = 'plan')                          AS floor_plan_urls
    FROM latest l,
         LATERAL jsonb_array_elements_text(l.property_images)
             WITH ORDINALITY AS img(url, ord),
         LATERAL jsonb_array_elements_text(l.property_image_tags)
             WITH ORDINALITY AS tag(tag, t_ord)
    WHERE l.property_images IS NOT NULL
      AND l.property_image_tags IS NOT NULL
      AND jsonb_typeof(l.property_images) = 'array'
      AND jsonb_typeof(l.property_image_tags) = 'array'
      AND img.ord = tag.t_ord
    GROUP BY l.unit_id
)

SELECT
    -- Identity
    'idealista'::TEXT                                                AS source,
    l.unit_id::TEXT                                                  AS source_listing_id,
    MD5('idealista|' || l.unit_id)::TEXT                             AS listing_hash,
    l.development_id::TEXT                                           AS portal_dev_id,
    l.property_url                                                   AS listing_url,

    -- Operation
    CASE LOWER(COALESCE(l.operation, ''))
        WHEN 'sale' THEN 'sale'
        WHEN 'rent' THEN 'rent'
        ELSE LOWER(COALESCE(l.operation, ''))
    END                                                              AS operation_type,

    -- Pricing (typed numeric in development_units, unlike raw_idealista)
    l.property_price                                                 AS price_eur,

    -- Areas: lot_size = gross (ABC), lot_size_usable = useful (typed numeric)
    l.lot_size                                                       AS gross_area_m2,
    l.lot_size_usable                                                AS useful_area_m2,
    NULL::NUMERIC                                                    AS implantation_area_m2,
    NULL::NUMERIC                                                    AS land_area_m2,
    NULL::BOOLEAN                                                    AS net_area_suspicious,

    -- Rooms (typed bigint in development_units)
    LEAST(l.bedroom_count, 15)::INTEGER                              AS num_rooms,
    LEAST(l.bathroom_count, 10)::INTEGER                             AS num_bathrooms,
    l.floor                                                          AS floor_raw,

    -- Property type (portal-native + canonical)
    l.property_type                                                  AS property_type,
    l.property_subtype                                               AS property_subtype,
    CASE l.property_type
        WHEN 'flat'         THEN 'Apartment'
        WHEN 'chalet'       THEN
            CASE l.property_subtype
                WHEN 'semidetachedHouse' THEN 'Townhouse'
                WHEN 'terracedHouse'     THEN 'Townhouse'
                ELSE 'House'
            END
        WHEN 'countryHouse' THEN 'House'
        WHEN 'homes'        THEN 'House'
        ELSE 'Other'
    END                                                              AS property_type_canonical,

    -- Typology (T0..T5) from bedroom_count
    CASE
        WHEN l.bedroom_count = 0 THEN 'T0'
        WHEN l.bedroom_count BETWEEN 1 AND 5 THEN 'T' || l.bedroom_count::TEXT
        ELSE NULL
    END                                                              AS typology,

    -- Energy + condition
    l.energy_certificate                                             AS energy_class,
    l.property_condition                                             AS condition,
    NULLIF(substring(l.property_features::TEXT FROM 'Constru.do em (\d{4})'), '')::INTEGER
                                                                     AS construction_year,

    -- Amenities (extracted from property_features JSONB array)
    (l.property_features::TEXT ~* '\melevador\M')                    AS has_elevator,
    (l.property_features::TEXT ~* '\m(garagem|estacionamento|parking)\M') AS has_parking,
    (l.property_features::TEXT ~* '\mterra')                         AS has_terrace,
    (l.property_features::TEXT ~* '\m(jardim|garden)\M')             AS has_garden,
    (l.property_features::TEXT ~* '\m(piscina|pool)\M')              AS has_pool,

    -- Location (typed numeric)
    l.latitude,
    l.longitude,
    l.address                                                        AS address_raw,
    l.location_name                                                  AS location_name,

    -- Media + Floor Plans
    CASE WHEN jsonb_typeof(l.property_images) = 'array'
         THEN jsonb_array_length(l.property_images)
         ELSE 0 END                                                  AS image_count,
    COALESCE(pu.floor_plan_urls, ARRAY[]::TEXT[])                    AS floor_plan_urls,
    COALESCE(pu.floor_plan_urls, ARRAY[]::TEXT[]) <> ARRAY[]::TEXT[] AS has_floor_plan,
    COALESCE(array_length(pu.floor_plan_urls, 1), 0)                 AS floor_plan_count,
    CASE WHEN pu.floor_plan_urls IS NOT NULL THEN 'idealista_tagged' END
                                                                     AS floor_plan_source,

    -- Lifecycle (SCD2 timestamps from dlt)
    l._dlt_valid_from::DATE                                          AS last_seen_date,
    l.status                                                         AS listing_status_raw,

    -- Description
    LEFT(l.property_description, 1000)                               AS description_summary,
    l.property_title                                                 AS listing_title,

    -- Agency
    l.agency_name                                                    AS agency_name

FROM latest l
LEFT JOIN plan_urls pu USING (unit_id)
