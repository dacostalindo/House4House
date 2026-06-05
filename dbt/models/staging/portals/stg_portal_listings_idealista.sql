-- stg_portal_listings_idealista — canonical-schema staging for Idealista resale
-- listings (one row per active listing on the resale market).
-- Pattern mirrors stg_portal_developments_idealista (dev-grain); this is the
-- listing-grain analogue feeding unified_listings_residential.
--
-- bronze_listings.raw_idealista is append-only (not SCD2 dlt-managed), so we
-- dedupe via DISTINCT ON (property_id ORDER BY _carried_forward, _scrape_date DESC)
-- to take the latest non-carried-forward snapshot.
--
-- Floor plan extraction: property_image_tags[i] = 'plan' identifies plan
-- images via parallel-array indexing against property_images[i]. ~33% of
-- active listings have at least one plan tag.
--
-- Inline property_type mapping (Decision G·iii, 2026-06-05): full
-- dim_property_type expansion across 4 portals is >30 min; instead each
-- staging model emits a canonical property_type_canonical column via inline
-- CASE.
--
-- Areas: lot_size (gross) and lot_size_usable (useful) are TEXT in bronze
-- (idealista publishes "78 m²"); parsed to numeric here.

WITH latest AS (
    SELECT DISTINCT ON (property_id)
        property_id,
        property_url,
        property_type,
        property_subtype,
        property_price,
        lot_size,
        lot_size_usable,
        bedroom_count,
        bathroom_count,
        floor                   AS floor_raw,
        property_features,
        property_equipment,
        property_images,
        property_image_tags,
        property_condition,
        property_description,
        property_title,
        energy_certificate,
        address,
        location_name,
        location_hierarchy,
        latitude,
        longitude,
        agency_name,
        operation,
        status                  AS listing_status,
        last_deactivated_at,
        modified_at,
        _scrape_date            AS scrape_date,
        _carried_forward
    FROM {{ source('bronze_listings', 'raw_idealista') }}
    WHERE property_url IS NOT NULL
      AND _carried_forward = false
    ORDER BY property_id, _scrape_date DESC
),

plan_urls AS (
    -- Parallel-index join: property_images[i] is a plan iff property_image_tags[i] = 'plan'
    SELECT
        l.property_id,
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
    GROUP BY l.property_id
)

SELECT
    -- Identity
    'idealista'::TEXT                                                AS source,
    l.property_id::TEXT                                              AS source_listing_id,
    MD5('idealista|' || l.property_id)::TEXT                         AS listing_hash,
    l.property_url                                                   AS listing_url,

    -- Operation
    CASE LOWER(COALESCE(l.operation, ''))
        WHEN 'sale' THEN 'sale'
        WHEN 'rent' THEN 'rent'
        ELSE LOWER(COALESCE(l.operation, ''))
    END                                                              AS operation_type,

    -- Pricing
    NULLIF(l.property_price, '')::NUMERIC                            AS price_eur,

    -- Areas: lot_size = gross (ABC), lot_size_usable = useful
    NULLIF(l.lot_size, '')::NUMERIC                                  AS gross_area_m2,
    NULLIF(l.lot_size_usable, '')::NUMERIC                           AS useful_area_m2,
    NULL::NUMERIC                                                    AS implantation_area_m2,
    NULL::NUMERIC                                                    AS land_area_m2,
    NULL::BOOLEAN                                                    AS net_area_suspicious,

    -- Rooms (bedroom_count / bathroom_count are TEXT in bronze)
    LEAST(NULLIF(l.bedroom_count, '')::INTEGER, 15)                  AS num_rooms,
    LEAST(NULLIF(l.bathroom_count, '')::INTEGER, 10)                 AS num_bathrooms,

    -- Floor (raw text, e.g. "5", "ground", "5/8") — caller normalizes
    l.floor_raw                                                      AS floor_raw,

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

    -- Typology (T0..T5) derived from bedroom_count
    CASE
        WHEN NULLIF(l.bedroom_count, '')::INTEGER = 0 THEN 'T0'
        WHEN NULLIF(l.bedroom_count, '')::INTEGER BETWEEN 1 AND 5
            THEN 'T' || NULLIF(l.bedroom_count, '')::INTEGER::TEXT
        ELSE NULL
    END                                                              AS typology,

    -- Energy + condition
    l.energy_certificate                                             AS energy_class,
    l.property_condition                                             AS condition,
    -- construction_year is buried in property_features JSONB — extract via regex
    NULLIF(substring(l.property_features::TEXT FROM 'Constru.do em (\d{4})'), '')::INTEGER
                                                                     AS construction_year,

    -- Amenities (only universal ones in residential silver)
    (l.property_features::TEXT ~* '\melevador\M')                    AS has_elevator,
    (l.property_features::TEXT ~* '\m(garagem|estacionamento|parking)\M') AS has_parking,
    (l.property_features::TEXT ~* '\mterra')                         AS has_terrace,
    (l.property_features::TEXT ~* '\m(jardim|garden)\M')             AS has_garden,
    (l.property_features::TEXT ~* '\m(piscina|pool)\M')              AS has_pool,

    -- Location
    l.latitude::NUMERIC                                              AS latitude,
    l.longitude::NUMERIC                                             AS longitude,
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

    -- Lifecycle
    l.scrape_date                                                    AS last_seen_date,
    l.listing_status                                                 AS listing_status_raw,

    -- Description (truncated for storage hygiene)
    LEFT(l.property_description, 1000)                               AS description_summary,
    l.property_title                                                 AS listing_title,

    -- Agency
    l.agency_name                                                    AS agency_name

FROM latest l
LEFT JOIN plan_urls pu USING (property_id)
