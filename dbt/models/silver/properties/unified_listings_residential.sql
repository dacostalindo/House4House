{{
    config(
        materialized='incremental',
        unique_key='listing_hash',
        incremental_strategy='merge',
        merge_update_columns=[
            'listing_url', 'operation_type',
            'price_eur', 'price_per_sqm_useful', 'price_per_sqm_gross',
            'useful_area_m2', 'gross_area_m2', 'implantation_area_m2', 'land_area_m2',
            'net_area_suspicious',
            'num_rooms', 'num_bathrooms', 'floor_raw',
            'property_type', 'property_subtype', 'property_type_canonical', 'typology',
            'energy_class', 'condition', 'construction_year',
            'has_elevator', 'has_parking', 'has_terrace', 'has_garden', 'has_pool',
            'geo_key', 'freguesia_code', 'concelho_code', 'distrito_code',
            'freguesia_name', 'concelho_name', 'distrito_name',
            'latitude', 'longitude', 'geom', 'geom_pt',
            'address_raw', 'location_name',
            'image_count', 'floor_plan_urls', 'has_floor_plan',
            'floor_plan_count', 'floor_plan_source',
            'last_seen_date', 'listing_age_days', 'is_active', 'listing_status_raw',
            'price_change_count',
            'description_summary', 'listing_title', 'agency_name',
            '_updated_at'
        ],
        tags=['unified_listings', 'silver', 'cross_portal'],
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_unified_listings_residential_geom ON {{ this }} USING GIST(geom)",
            "CREATE INDEX IF NOT EXISTS idx_unified_listings_residential_geom_pt ON {{ this }} USING GIST(geom_pt)",
            "CREATE INDEX IF NOT EXISTS idx_unified_listings_residential_geo_key ON {{ this }} (geo_key)",
            "CREATE INDEX IF NOT EXISTS idx_unified_listings_residential_source ON {{ this }} (source)",
            "CREATE INDEX IF NOT EXISTS idx_unified_listings_residential_active ON {{ this }} (is_active) WHERE is_active",
            "CREATE INDEX IF NOT EXISTS idx_unified_listings_residential_operation ON {{ this }} (operation_type)",
            "CREATE INDEX IF NOT EXISTS idx_unified_listings_residential_listing_hash ON {{ this }} (listing_hash)",
            "UPDATE {{ this }} SET is_active = FALSE WHERE last_seen_date < CURRENT_DATE - INTERVAL '3 days' AND is_active"
        ]
    )
}}

-- unified_listings_residential — cross-portal LISTING-grain silver for
-- residential properties (apartments + houses, both resale and dev units).
--
-- Sprint-09 follow-on, 2026-06-05. Companion to unified_developments
-- (DEV-grain, shipped 2026-05-22) and unified_listings_idealista_legacy
-- (the prior Idealista-only listing silver, renamed alongside this commit).
--
-- Portal scope: idealista (resale), RE/MAX, Zome, JLL. UNION ALL across the
-- 4 portal-listing staging models. NO cross-portal listing-level dedup in v1
-- (decision 2026-06-05 D2: a single physical property listed on 3 portals
-- yields 3 rows — consumers see the per-portal price variance which is itself
-- a signal). Listing-level dedup deferred to v1.5.
--
-- Grain: 1 row per (source, source_listing_id). listing_hash is the deterministic
-- merge key = MD5(source || '|' || source_listing_id) — same portal+id always
-- produces same hash, different portals never collide.
--
-- Floor plans (decision L7): floor_plan_urls TEXT[] + has_floor_plan +
-- floor_plan_count + floor_plan_source. Coverage by source:
--   jll_blueprints   = 92.72% (PDF on egorealestate CDN — best quality)
--   idealista_tagged = 32.59% (JPG/WEBP on idealista CDN — tag='plan' index)
--   zome_aplants     = 26.76% (JPG on zome.pt — filename 'planta' match)
--   remax_path       =  8.18% (PDF on i.maxwork.pt/bb — may 404 if session-gated)
--
-- Incremental merge by listing_hash: every portal pipeline run safely re-merges
-- without duplicates. Same hash + same row_hash → UPDATE no-op. New SCD2 version
-- in bronze → UPDATE in place. Brand new listing → INSERT. first_seen_date and
-- initial_price_eur preserved via COALESCE with existing row.
--
-- 3-day deactivation post-hook: is_active flips to FALSE when last_seen_date
-- falls outside the 3-day grace window.

WITH unioned AS (
    SELECT * FROM {{ ref('stg_portal_listings_idealista') }}
    UNION ALL
    SELECT * FROM {{ ref('stg_portal_listings_remax') }}
    UNION ALL
    SELECT * FROM {{ ref('stg_portal_listings_zome') }}
    UNION ALL
    SELECT * FROM {{ ref('stg_portal_listings_jll') }}
),

with_geom AS (
    SELECT
        u.*,
        CASE WHEN u.latitude IS NOT NULL AND u.longitude IS NOT NULL
             THEN ST_SetSRID(ST_MakePoint(u.longitude, u.latitude), 4326)
        END                                                          AS geom,
        CASE WHEN u.latitude IS NOT NULL AND u.longitude IS NOT NULL
             THEN ST_Transform(ST_SetSRID(ST_MakePoint(u.longitude, u.latitude), 4326), 3763)
        END                                                          AS geom_pt
    FROM unioned u
),

geo_joined AS (
    SELECT g.*, dg.geo_key, dg.freguesia_code, dg.freguesia_name,
                dg.concelho_code, dg.concelho_name,
                dg.distrito_code, dg.distrito_name
    FROM with_geom g
    LEFT JOIN LATERAL (
        SELECT geo_key, freguesia_code, freguesia_name,
               concelho_code, concelho_name, distrito_code, distrito_name
        FROM {{ ref('dim_geography') }} d
        WHERE d.is_current
          AND g.geom_pt IS NOT NULL
          AND ST_Contains(d.freguesia_geom_pt, g.geom_pt)
        LIMIT 1
    ) dg ON TRUE
)

SELECT
    -- Identity
    j.listing_hash,
    j.source,
    j.source_listing_id,
    j.listing_url,
    j.operation_type,

    -- Pricing (computed price-per-sqm where possible)
    j.price_eur,
    CASE WHEN j.useful_area_m2 > 0 THEN ROUND(j.price_eur / j.useful_area_m2, 2) END
                                                                     AS price_per_sqm_useful,
    CASE WHEN j.gross_area_m2 > 0 THEN ROUND(j.price_eur / j.gross_area_m2, 2) END
                                                                     AS price_per_sqm_gross,
    {% if is_incremental() %}
        COALESCE(t.initial_price_eur, j.price_eur)                   AS initial_price_eur,
        COALESCE(t.price_change_count, 0)
            + CASE WHEN t.price_eur IS NOT NULL AND t.price_eur <> j.price_eur THEN 1 ELSE 0 END
                                                                     AS price_change_count,
    {% else %}
        j.price_eur                                                  AS initial_price_eur,
        0                                                            AS price_change_count,
    {% endif %}

    -- Areas
    j.useful_area_m2, j.gross_area_m2, j.implantation_area_m2, j.land_area_m2,
    j.net_area_suspicious,

    -- Rooms + floor
    j.num_rooms, j.num_bathrooms, j.floor_raw,

    -- Property type
    j.property_type, j.property_subtype, j.property_type_canonical, j.typology,

    -- Energy + condition
    j.energy_class, j.condition, j.construction_year,

    -- Amenities
    j.has_elevator, j.has_parking, j.has_terrace, j.has_garden, j.has_pool,

    -- Location
    j.geo_key,
    j.freguesia_code, j.freguesia_name,
    j.concelho_code,  j.concelho_name,
    j.distrito_code,  j.distrito_name,
    j.latitude, j.longitude,
    j.geom::geometry(Point, 4326)                                    AS geom,
    j.geom_pt::geometry(Point, 3763)                                 AS geom_pt,
    j.address_raw, j.location_name,

    -- Media + Floor Plans
    j.image_count, j.floor_plan_urls, j.has_floor_plan,
    j.floor_plan_count, j.floor_plan_source,

    -- Lifecycle (SCD)
    {% if is_incremental() %}
        COALESCE(t.first_seen_date, j.last_seen_date)                AS first_seen_date,
    {% else %}
        j.last_seen_date                                             AS first_seen_date,
    {% endif %}
    j.last_seen_date,
    GREATEST(0,
        (j.last_seen_date -
         {% if is_incremental() %}COALESCE(t.first_seen_date, j.last_seen_date)
         {% else %}j.last_seen_date{% endif %}
        )::INTEGER
    )                                                                AS listing_age_days,
    -- is_active: true if last seen in 3-day grace; the post-hook later flips
    -- rows that age past the window.
    (j.last_seen_date >= CURRENT_DATE - INTERVAL '3 days')            AS is_active,
    j.listing_status_raw,

    -- Description
    j.description_summary, j.listing_title, j.agency_name,

    -- Audit
    {% if is_incremental() %}
        COALESCE(t._created_at, NOW())                               AS _created_at,
    {% else %}
        NOW()                                                        AS _created_at,
    {% endif %}
    NOW()                                                            AS _updated_at

FROM geo_joined j
{% if is_incremental() %}
LEFT JOIN {{ this }} t ON t.listing_hash = j.listing_hash
{% endif %}
WHERE j.price_eur IS NOT NULL AND j.price_eur > 0
