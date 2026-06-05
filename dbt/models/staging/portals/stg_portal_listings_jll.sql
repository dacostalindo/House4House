-- stg_portal_listings_jll — canonical-schema staging for JLL listings.
-- bronze_listings.jll_listings is dlt SCD2-managed: filter _dlt_valid_to IS NULL
-- to take the current version per id.
--
-- Geographic scope: JLL covers Lisboa, Porto, Faro, Setúbal — zero Aveiro
-- coverage. v1 Aveiro município wedge gets 0 rows from JLL; national rollout
-- unlocks ~7,400 listings + their 92.7% floor plan coverage.
--
-- Floor plans: blue_prints is a JSONB array of objects with .Original (PDF
-- URL on egorealestate CDN). 92.72% coverage — the strongest plan signal
-- across portals.
--
-- Areas: gross_area + net_area. CAVEAT — JLL frequently reports
-- net_area = gross_area as a fallback when only one is known (Decision C·i).
-- Flag and null out useful_area_m2 when they match exactly AND both > 0.

WITH latest AS (
    SELECT *
    FROM {{ source('bronze_listings', 'jll_listings') }}
    WHERE _dlt_valid_to IS NULL
      AND id IS NOT NULL
)

SELECT
    -- Identity
    'jll'::TEXT                                                      AS source,
    id::TEXT                                                         AS source_listing_id,
    MD5('jll|' || id::TEXT)::TEXT                                    AS listing_hash,
    'https://www.jll.pt/property/' || id::TEXT                       AS listing_url,

    -- Operation: property_business JSONB usually carries the business type
    CASE
        WHEN property_business::TEXT ~* 'venda|sale'         THEN 'sale'
        WHEN property_business::TEXT ~* 'arrendamento|rent'  THEN 'rent'
        ELSE NULL
    END                                                              AS operation_type,

    -- Pricing
    NULLIF(price_value, 0)::NUMERIC                                  AS price_eur,

    -- Areas — apply C·i: detect net_area==gross_area fallback, null out useful
    gross_area::NUMERIC                                              AS gross_area_m2,
    CASE
        WHEN gross_area > 0
         AND net_area > 0
         AND gross_area = net_area
            THEN NULL::NUMERIC
        ELSE net_area::NUMERIC
    END                                                              AS useful_area_m2,
    NULL::NUMERIC                                                    AS implantation_area_m2,
    land_area::NUMERIC                                               AS land_area_m2,
    (gross_area > 0 AND net_area > 0 AND gross_area = net_area)      AS net_area_suspicious,

    -- Rooms
    LEAST(rooms, 15)                                                 AS num_rooms,
    LEAST(bathrooms, 10)                                             AS num_bathrooms,
    floor::TEXT                                                      AS floor_raw,

    -- Property type — paired (type, type_id) at top of bronze; assume type is text
    type                                                             AS property_type,
    NULL::TEXT                                                       AS property_subtype,
    CASE LOWER(COALESCE(type, ''))
        WHEN 'apartment'      THEN 'Apartment'
        WHEN 'apartamento'    THEN 'Apartment'
        WHEN 'house'          THEN 'House'
        WHEN 'moradia'        THEN 'House'
        WHEN 'villa'          THEN 'Villa'
        WHEN 'studio'         THEN 'Studio'
        WHEN 'duplex'         THEN 'Duplex'
        WHEN 'townhouse'      THEN 'Townhouse'
        WHEN 'commercial'     THEN 'Commercial'
        ELSE 'Other'
    END                                                              AS property_type_canonical,

    -- Typology (T0..T5) from rooms (bedrooms equivalent)
    CASE
        WHEN rooms = 0 THEN 'T0'
        WHEN rooms BETWEEN 1 AND 5 THEN 'T' || rooms::TEXT
        ELSE NULL
    END                                                              AS typology,

    -- Energy + condition
    energy_certification                                             AS energy_class,
    condition                                                        AS condition,
    year::INTEGER                                                    AS construction_year,

    -- Amenities (in features JSONB — surface via text-search)
    (features::TEXT ~* '\melevador|elevator\M')                      AS has_elevator,
    (features::TEXT ~* '\m(garagem|garage|estacionamento|parking)\M') AS has_parking,
    (features::TEXT ~* '\mterra')                                    AS has_terrace,
    (features::TEXT ~* '\m(jardim|garden)\M')                        AS has_garden,
    (features::TEXT ~* '\m(piscina|pool)\M')                         AS has_pool,

    -- Location — gps_lat/lon are typed doubles with has_gps_location reliability flag
    CASE WHEN COALESCE(has_gps_location, FALSE) THEN gps_lat ELSE NULL END::NUMERIC
                                                                     AS latitude,
    CASE WHEN COALESCE(has_gps_location, FALSE) THEN gps_lon ELSE NULL END::NUMERIC
                                                                     AS longitude,
    address                                                          AS address_raw,
    parish                                                           AS location_name,

    -- Media + Floor Plans (blue_prints is array of {UID, Original, Thumbnail, ...})
    CASE WHEN jsonb_typeof(images) = 'array'
         THEN jsonb_array_length(images)
         ELSE 0 END                                                  AS image_count,
    COALESCE(
        (SELECT ARRAY_AGG(elem->>'Original')
         FROM jsonb_array_elements(blue_prints) elem
         WHERE blue_prints IS NOT NULL
           AND jsonb_typeof(blue_prints) = 'array'
           AND (elem->>'Original') IS NOT NULL),
        ARRAY[]::TEXT[]
    )                                                                AS floor_plan_urls,
    (blue_prints IS NOT NULL
     AND jsonb_typeof(blue_prints) = 'array'
     AND jsonb_array_length(blue_prints) > 0)                        AS has_floor_plan,
    CASE WHEN jsonb_typeof(blue_prints) = 'array'
         THEN jsonb_array_length(blue_prints)
         ELSE 0 END                                                  AS floor_plan_count,
    CASE WHEN blue_prints IS NOT NULL
              AND jsonb_typeof(blue_prints) = 'array'
              AND jsonb_array_length(blue_prints) > 0
         THEN 'jll_blueprints' END                                   AS floor_plan_source,

    -- Lifecycle
    _dlt_valid_from::DATE                                            AS last_seen_date,
    availability                                                     AS listing_status_raw,

    -- Description
    LEFT(description, 1000)                                          AS description_summary,
    NULL::TEXT                                                       AS listing_title,

    -- Agency
    NULL::TEXT                                                       AS agency_name

FROM latest
