-- stg_portal_listings_imovirtual — canonical-schema staging for imovirtual
-- development units. 5th UNION arm of unified_listings_residential.
--
-- Bronze grain: imovirtual_development_units (national, ~4,440 rows).
-- Plots (Aveiro terreno, non-residential) and developments-as-listings are out
-- of scope. imovirtual has no resale-listing table — coverage is dev-units only.
--
-- Coords: units have (0,0) in bronze (mapped to NULL). We JOIN the active SCD2
-- version of imovirtual_developments by development_id to inherit gps_lat/lon
-- and address_text. dim_geography spatial resolution happens later inside
-- unified_listings_residential.with_geom (same path as the other 4 portals).
--
-- Floor plans: TWO disjoint per-unit feeds, UNION'd into floor_plan_urls.
--   (a) floor_plans (native JSONB array, lifted from raw_json->'floorPlans'
--       in the bronze normalizer 2026-06-09): olxcdn JPGs, 29.62% coverage.
--   (b) raw_json->'links'->>'localPlanUrl' (scalar URL string,
--       NOT pivoted to a column): egorealestate PDFs/JPGs + agency hosts,
--       44.82% coverage. Distinct upstream feed; only 5.6% overlap with (a).
-- Combined unit-level coverage: 68.83% (3,056/4,440). Verified zero URL
-- overlap with dev-level floor_plans (master/site plans on the dev row —
-- those belong on unified_developments, NOT here).
-- floor_plan_source = 'imovirtual_units'. Sits between jll (92.72%) and
-- idealista (32.59%) in the cross-portal coverage table.
--
-- Amenities: extras_types is a structured JSONB enum array
-- (extras_types::garage, ::lift, ::balcony, ::terrace, ::garden, ::pool, etc.).
-- Use JSONB containment (?|), NOT regex over description text.
--
-- Areas: imovirtual exposes a single area_m → useful_area_m2. gross_area is
-- NULL (no outdoor-area aggregator like jll's exterior_sum). terrain_area_m
-- → land_area_m2 (4.6% coverage, populates a column that was idealista+remax
-- NULL-only before).
--
-- Operation type: 4,421 SELL units + 19 RENT units in bronze. Map honestly
-- via adcategory_type CASE; the unified silver filter on price_eur>0 keeps
-- both arms.
--
-- DISTINCT ON guard: consistent with the other 4 staging models — defensive
-- against SCD2 close-row misses across runs.

WITH latest AS (
    SELECT DISTINCT ON (unit_id) *
    FROM {{ source('bronze_listings', 'imovirtual_development_units') }}
    WHERE _dlt_valid_to IS NULL
      AND unit_id IS NOT NULL
    ORDER BY unit_id, _dlt_valid_from DESC
),

dev AS (
    SELECT DISTINCT ON (development_id)
        development_id,
        gps_lat,
        gps_lon,
        address_text
    FROM {{ source('bronze_listings', 'imovirtual_developments') }}
    WHERE _dlt_valid_to IS NULL
      AND development_id IS NOT NULL
    ORDER BY development_id, _dlt_valid_from DESC
)

SELECT
    -- Identity
    'imovirtual'::TEXT                                               AS source,
    l.unit_id::TEXT                                                  AS source_listing_id,
    MD5('imovirtual|' || l.unit_id::TEXT)::TEXT                      AS listing_hash,
    l.development_id::TEXT                                           AS portal_dev_id,
    l.unit_url                                                       AS listing_url,

    -- Operation: SELL/RENT enum on adcategory_type. 19 RENT rows exist.
    CASE l.adcategory_type
        WHEN 'SELL' THEN 'sale'
        WHEN 'RENT' THEN 'rent'
        ELSE NULL
    END                                                              AS operation_type,

    -- Pricing
    NULLIF(l.price, '')::NUMERIC                                     AS price_eur,

    -- Areas: imovirtual exposes a single area → useful. gross NULL.
    -- terrain_area_m → land_area_m2 (~4.6% pop; villas+terrenos within devs).
    NULL::NUMERIC                                                    AS gross_area_m2,
    NULLIF(l.area_m, '')::NUMERIC                                    AS useful_area_m2,
    NULL::NUMERIC                                                    AS implantation_area_m2,
    NULLIF(l.terrain_area_m, '')::NUMERIC                            AS land_area_m2,
    NULL::BOOLEAN                                                    AS net_area_suspicious,

    -- Rooms — bathrooms_num + rooms_num + floor_no lifted in the bronze normalizer.
    NULLIF(l.rooms_num, '')::INTEGER                                 AS num_rooms,
    -- bathrooms_num is mixed: "1"/"2"/"3" plain digits + "bathrooms_num::4_or_more"
    -- enum (725 rows = ~16%). Floor 4+ at literal 4 — closest honest INTEGER.
    CASE
        WHEN l.bathrooms_num ~ '^[0-9]+$'        THEN l.bathrooms_num::INTEGER
        WHEN l.bathrooms_num LIKE '%4_or_more%'  THEN 4
        ELSE NULL
    END                                                              AS num_bathrooms,
    l.floor_no                                                       AS floor_raw,

    -- Property type
    l.adcategory_type                                                AS property_type,
    l.construction_status                                            AS property_subtype,  -- to_completion / ready_to_use
    CASE LOWER(COALESCE(l.adcategory_type, ''))
        WHEN 'sell'  THEN 'Apartment'   -- empreendimento units are apartment-dominated
        WHEN 'rent'  THEN 'Apartment'
        WHEN 'flat'  THEN 'Apartment'
        WHEN 'house' THEN 'House'
        ELSE 'Other'
    END                                                              AS property_type_canonical,
    CASE
        WHEN NULLIF(l.rooms_num,'')::INTEGER = 0 THEN 'T0'
        WHEN NULLIF(l.rooms_num,'')::INTEGER BETWEEN 1 AND 5
             THEN 'T' || NULLIF(l.rooms_num,'')::INTEGER::TEXT
        ELSE NULL
    END                                                              AS typology,

    -- Energy + condition + build year (build_year lifted in bronze 2026-06-09)
    l.energy_certificate                                             AS energy_class,
    NULL::TEXT                                                       AS condition,  -- construction_status is build-status, not condition; lives in property_subtype
    NULLIF(l.build_year, '')::INTEGER                                AS construction_year,

    -- Amenities — extras_types is structured JSONB enum array. JSONB containment.
    (l.extras_types ?| ARRAY[
        'extras_types::lift', 'extras_types::elevator'
     ])                                                              AS has_elevator,
    (l.extras_types ?| ARRAY[
        'extras_types::garage', 'extras_types::parking'
     ])                                                              AS has_parking,
    (l.extras_types ?| ARRAY[
        'extras_types::terrace', 'extras_types::balcony'
     ])                                                              AS has_terrace,
    (l.extras_types ?  'extras_types::garden')                       AS has_garden,
    (l.extras_types ?  'extras_types::pool')                         AS has_pool,

    -- Location — inherit from parent dev (units have (0,0) own pin)
    d.gps_lat::NUMERIC                                               AS latitude,
    d.gps_lon::NUMERIC                                               AS longitude,
    d.address_text                                                   AS address_raw,
    NULL::TEXT                                                       AS location_name,  -- no per-unit parish

    -- Media + Floor Plans. UNION of two disjoint per-unit feeds:
    --   (a) l.floor_plans array (olxcdn JPGs, 29.62% coverage)
    --   (b) l.raw_json->'links'->>'localPlanUrl' scalar (egorealestate PDFs +
    --       agency hosts, 44.82% coverage)
    -- Combined: 68.83% coverage, source = 'imovirtual_units'.
    CASE WHEN jsonb_typeof(l.images) = 'array'
         THEN jsonb_array_length(l.images)
         ELSE 0 END                                                  AS image_count,
    (
        COALESCE(
            (SELECT ARRAY_AGG(elem #>> '{}')
             FROM jsonb_array_elements(l.floor_plans) elem
             WHERE jsonb_typeof(l.floor_plans) = 'array'),
            ARRAY[]::TEXT[]
        )
        || CASE
             WHEN NULLIF(l.raw_json->'links'->>'localPlanUrl','') IS NOT NULL
                  THEN ARRAY[l.raw_json->'links'->>'localPlanUrl']
             ELSE ARRAY[]::TEXT[]
           END
    )                                                                AS floor_plan_urls,
    (
        (jsonb_typeof(l.floor_plans) = 'array' AND jsonb_array_length(l.floor_plans) > 0)
        OR NULLIF(l.raw_json->'links'->>'localPlanUrl','') IS NOT NULL
    )                                                                AS has_floor_plan,
    (
        CASE WHEN jsonb_typeof(l.floor_plans) = 'array'
             THEN jsonb_array_length(l.floor_plans)
             ELSE 0 END
        + CASE WHEN NULLIF(l.raw_json->'links'->>'localPlanUrl','') IS NOT NULL
               THEN 1 ELSE 0 END
    )                                                                AS floor_plan_count,
    CASE
        WHEN (jsonb_typeof(l.floor_plans) = 'array' AND jsonb_array_length(l.floor_plans) > 0)
             OR NULLIF(l.raw_json->'links'->>'localPlanUrl','') IS NOT NULL
        THEN 'imovirtual_units'
    END                                                              AS floor_plan_source,

    -- Lifecycle. listing_status_raw: bronze `status` column was dropped by
    -- dlt (all-NULL across the corpus, same as `title`). Set NULL.
    l._dlt_valid_from::DATE                                          AS last_seen_date,
    NULL::TEXT                                                       AS listing_status_raw,

    -- Description (raw_json carries the full Nexus item incl. description text)
    LEFT(l.raw_json->>'description', 1000)                           AS description_summary,

    -- Title: bronze column does not exist (dlt evolved away — likely all-NULL)
    NULL::TEXT                                                       AS listing_title,

    -- Agency: imovirtual promoter (developer) is dev-level + unreliable.
    -- Per-unit agency not exposed.
    NULL::TEXT                                                       AS agency_name

FROM latest l
LEFT JOIN dev d ON d.development_id = l.development_id
