-- stg_portal_listings_remax — canonical-schema staging for RE/MAX listings.
-- bronze_listings.remax_listings is dlt SCD2-managed: filter _dlt_valid_to IS NULL
-- to take the current version per listing_id.
--
-- Floor plan: RE/MAX bronze has has_floor_plan (bool) + floor_plan_path (varchar,
-- single relative path like /documents/listing/2025/{id}/{hash}.pdf). CDN base
-- is https://i.maxwork.pt/bb (verified via curl probe on listing images
-- 2026-06-05). Floor-plan PDFs may 404 on direct fetch — likely session-gated;
-- URL is constructed deterministically and consumers handle 4xx.
--
-- Areas: total_area = gross (ABC), living_area = useful. Dead columns:
-- built_area + lot_size are 100% empty in active bronze — dropped from
-- canonical mapping. The "listings/" prefix on listing_pictures is a separate
-- relative-path namespace — gallery URLs constructed as
-- https://i.maxwork.pt/bb/{listing_pictures[i]}.

WITH latest AS (
    -- DISTINCT ON guards against dlt SCD2 close-row duplicates (~0.03% rate
    -- on remax — wiki/sprints/sprint-09 status 2026-05-19).
    SELECT DISTINCT ON (listing_id) *
    FROM {{ source('bronze_listings', 'remax_listings') }}
    WHERE _dlt_valid_to IS NULL
      AND listing_id IS NOT NULL
    ORDER BY listing_id, _dlt_valid_from DESC
)

SELECT
    -- Identity
    'remax'::TEXT                                                    AS source,
    listing_id::TEXT                                                 AS source_listing_id,
    MD5('remax|' || listing_id::TEXT)::TEXT                          AS listing_hash,
    development_id::TEXT                                             AS portal_dev_id,
    -- Public detail URL — construct from listing_id and listing_type
    'https://remax.pt/listing/' || listing_id::TEXT                  AS listing_url,

    -- Operation: business_type 'Venda' = sale, 'Arrendamento' = rent
    CASE LOWER(COALESCE(business_type, ''))
        WHEN 'venda'         THEN 'sale'
        WHEN 'arrendamento'  THEN 'rent'
        WHEN 'sale'          THEN 'sale'
        WHEN 'rent'          THEN 'rent'
        ELSE LOWER(COALESCE(business_type, ''))
    END                                                              AS operation_type,

    -- Pricing
    NULLIF(listing_price, 0)::NUMERIC                                AS price_eur,

    -- Areas
    total_area                                                       AS gross_area_m2,
    living_area                                                      AS useful_area_m2,
    NULL::NUMERIC                                                    AS implantation_area_m2,
    NULL::NUMERIC                                                    AS land_area_m2,
    NULL::BOOLEAN                                                    AS net_area_suspicious,

    -- Rooms
    LEAST(num_bedrooms, 15)                                          AS num_rooms,
    LEAST(num_bathrooms, 10)                                         AS num_bathrooms,
    floor_number::TEXT                                               AS floor_raw,

    -- Property type
    listing_type                                                     AS property_type,
    NULL::TEXT                                                       AS property_subtype,
    CASE LOWER(COALESCE(listing_type, ''))
        WHEN 'apartamento'   THEN 'Apartment'
        WHEN 'apartment'     THEN 'Apartment'
        WHEN 'moradia'       THEN 'House'
        WHEN 'house'         THEN 'House'
        WHEN 'villa'         THEN 'Villa'
        WHEN 'estudio'       THEN 'Studio'
        WHEN 'studio'        THEN 'Studio'
        WHEN 'duplex'        THEN 'Duplex'
        WHEN 'penthouse'     THEN 'Apartment'
        WHEN 'comercial'     THEN 'Commercial'
        WHEN 'escritorio'    THEN 'Commercial'
        ELSE 'Other'
    END                                                              AS property_type_canonical,

    -- Typology (T0..T5) from num_bedrooms
    CASE
        WHEN num_bedrooms = 0 THEN 'T0'
        WHEN num_bedrooms BETWEEN 1 AND 5 THEN 'T' || num_bedrooms::TEXT
        ELSE NULL
    END                                                              AS typology,

    -- Energy + condition
    energy_efficiency_level::TEXT                                    AS energy_class,
    conservation_status_id::TEXT                                     AS condition,
    construction_year::INTEGER                                       AS construction_year,

    -- Amenities (typed boolean columns in bronze)
    elevator                                                         AS has_elevator,
    parking                                                          AS has_parking,
    NULL::BOOLEAN                                                    AS has_terrace,
    NULL::BOOLEAN                                                    AS has_garden,
    NULL::BOOLEAN                                                    AS has_pool,

    -- Location (lat/lon not directly exposed in bronze — derived via coordinates JSONB later)
    NULL::NUMERIC                                                    AS latitude,
    NULL::NUMERIC                                                    AS longitude,
    address                                                          AS address_raw,
    region_name3                                                     AS location_name,

    -- Media + Floor Plans
    CASE WHEN jsonb_typeof(listing_pictures) = 'array'
         THEN jsonb_array_length(listing_pictures)
         ELSE 0 END                                                  AS image_count,
    CASE
        WHEN has_floor_plan IS TRUE AND floor_plan_path IS NOT NULL AND floor_plan_path <> ''
            THEN ARRAY['https://i.maxwork.pt/bb' || floor_plan_path]::TEXT[]
        ELSE ARRAY[]::TEXT[]
    END                                                              AS floor_plan_urls,
    COALESCE(has_floor_plan, FALSE) AND floor_plan_path IS NOT NULL  AS has_floor_plan,
    CASE
        WHEN has_floor_plan IS TRUE AND floor_plan_path IS NOT NULL AND floor_plan_path <> ''
            THEN 1
        ELSE 0
    END                                                              AS floor_plan_count,
    CASE WHEN has_floor_plan IS TRUE AND floor_plan_path IS NOT NULL
         THEN 'remax_path'
    END                                                              AS floor_plan_source,

    -- Lifecycle
    _dlt_valid_from::DATE                                            AS last_seen_date,
    CASE
        WHEN is_sold THEN 'sold'
        WHEN is_active THEN 'active'
        WHEN is_online THEN 'online'
        ELSE 'inactive'
    END                                                              AS listing_status_raw,

    -- Description (no rich description in remax bronze — use listing_type as fallback)
    NULL::TEXT                                                       AS description_summary,
    NULL::TEXT                                                       AS listing_title,

    -- Agency
    NULL::TEXT                                                       AS agency_name

FROM latest
