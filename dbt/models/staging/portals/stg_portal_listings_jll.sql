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
-- Areas — corrected semantics 2026-06-05:
--   bronze.gross_area  = "Área Bruta Privativa" (interior with walls, NO outdoor)
--                      → canonical useful_area_m2
--   bronze.net_area    = unused (ambiguous: also interior, different measure)
--   canonical gross    = bronze.gross_area + sum of exterior areas extracted from
--                        features.Areas children with tags AREA_BALCONY,
--                        AREA_TERRACE, AREA_GARDEN, PATIO_AREA
--   area_exterior_m2   = sum of those exterior tags (new column)
-- This matches the JLL UI semantic where "AREA BRUTA" is interior and
-- "AREA EXTERIOR" is a separate column for outdoor areas.

WITH latest AS (
    -- DISTINCT ON guards against dlt SCD2 close-row duplicates (~0.01% rate
    -- on jll — wiki/sprints/sprint-09 status 2026-05-19). Pick newest version
    -- when bronze accidentally retains >1 _dlt_valid_to IS NULL row per id.
    SELECT DISTINCT ON (id) *
    FROM {{ source('bronze_listings', 'jll_listings') }}
    WHERE _dlt_valid_to IS NULL
      AND id IS NOT NULL
    ORDER BY id, _dlt_valid_from DESC
),

exterior_sum AS (
    -- Sum the outdoor area tags per listing from features.Areas.Childs
    SELECT
        l.id,
        COALESCE(SUM((child->>'Value')::NUMERIC), 0) AS area_exterior_m2
    FROM latest l,
         LATERAL jsonb_array_elements(l.features) AS feat,
         LATERAL jsonb_array_elements(feat->'Childs') AS child
    WHERE jsonb_typeof(l.features) = 'array'
      AND jsonb_typeof(feat->'Childs') = 'array'
      AND (child->>'Tag') IN (
          ';AREAS;AREA_BALCONY;',
          ';AREAS;AREA_TERRACE;',
          ';AREAS;AREA_GARDEN;',
          ';AREAS;PATIO_AREA;'
      )
      AND (child->>'Value') ~ '^[0-9]+\.?[0-9]*$'
      AND (child->>'Unit') = 'm²'
    GROUP BY l.id
)

SELECT
    -- Identity
    'jll'::TEXT                                                      AS source,
    latest.id::TEXT                                                  AS source_listing_id,
    MD5('jll|' || latest.id::TEXT)::TEXT                             AS listing_hash,
    'https://www.jll.pt/property/' || latest.id::TEXT                AS listing_url,

    -- Operation: property_business JSONB usually carries the business type
    CASE
        WHEN property_business::TEXT ~* 'venda|sale'         THEN 'sale'
        WHEN property_business::TEXT ~* 'arrendamento|rent'  THEN 'rent'
        ELSE NULL
    END                                                              AS operation_type,

    -- Pricing
    NULLIF(price_value, 0)::NUMERIC                                  AS price_eur,

    -- Areas — corrected semantics:
    --   useful_area_m2 = JLL bronze gross_area (= Área Bruta Privativa, interior)
    --   gross_area_m2  = useful + extracted exterior (balcony + terrace + garden + patio)
    --   area_exterior_m2 = the extracted exterior sum (NEW column)
    -- net_area dropped (ambiguous; consumers can read directly from bronze)
    -- net_area_suspicious dropped (no longer relevant — we use gross as useful directly)
    (latest.gross_area + COALESCE(es.area_exterior_m2, 0))::NUMERIC  AS gross_area_m2,
    latest.gross_area::NUMERIC                                       AS useful_area_m2,
    NULL::NUMERIC                                                    AS implantation_area_m2,
    latest.land_area::NUMERIC                                        AS land_area_m2,
    NULL::BOOLEAN                                                    AS net_area_suspicious,

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
LEFT JOIN exterior_sum es ON es.id = latest.id
