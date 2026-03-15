{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_pls_listing ON {{ this }} (listing_key)",
            "CREATE INDEX IF NOT EXISTS idx_pls_geo ON {{ this }} (geo_key)"
        ]
    )
}}

-- Transport proximity scores per listing.
-- For each mode, finds the nearest stop via LATERAL + KNN index scan
-- on EPSG:3763 (meters). Applies exponential decay with variable
-- decay constant per mode. Composite score is a weighted sum.
--
-- Decay constants: rail 800m, bus 350m, tram 500m, air 5000m, ferry 500m
-- Weights: rail 0.30, bus 0.35, tram 0.15, air 0.10, ferry 0.10
--
-- Full table rebuild (~16K listings × 5 LATERAL joins).
-- Convert to incremental when volume exceeds 100K listings.

WITH listings AS (
    SELECT listing_key, geo_key, geom_pt
    FROM {{ ref('unified_listings') }}
    WHERE geom_pt IS NOT NULL
)

SELECT
    l.listing_key,
    l.geo_key,

    -- Raw distances (meters, crow-flies EPSG:3763)
    rail.distance_m::NUMERIC(12,1)      AS nearest_rail_m,
    rail.stop_name                      AS nearest_rail_name,
    bus.distance_m::NUMERIC(12,1)       AS nearest_bus_m,
    bus.stop_name                       AS nearest_bus_name,
    tram.distance_m::NUMERIC(12,1)      AS nearest_tram_m,
    tram.stop_name                      AS nearest_tram_name,
    air.distance_m::NUMERIC(12,1)       AS nearest_air_m,
    air.stop_name                       AS nearest_air_name,
    ferry.distance_m::NUMERIC(12,1)     AS nearest_ferry_m,
    ferry.stop_name                     AS nearest_ferry_name,

    -- Individual mode scores (exponential decay, variable constant)
    EXP(-COALESCE(rail.distance_m, 99999) / 800.0)::NUMERIC(6,4)   AS rail_score,
    EXP(-COALESCE(bus.distance_m, 99999) / 350.0)::NUMERIC(6,4)    AS bus_score,
    EXP(-COALESCE(tram.distance_m, 99999) / 500.0)::NUMERIC(6,4)   AS tram_score,
    EXP(-COALESCE(air.distance_m, 99999) / 5000.0)::NUMERIC(6,4)   AS air_score,
    EXP(-COALESCE(ferry.distance_m, 99999) / 500.0)::NUMERIC(6,4)  AS ferry_score,

    -- Composite transport score (weighted sum)
    (
        0.30 * EXP(-COALESCE(rail.distance_m, 99999) / 800.0)
      + 0.35 * EXP(-COALESCE(bus.distance_m, 99999) / 350.0)
      + 0.15 * EXP(-COALESCE(tram.distance_m, 99999) / 500.0)
      + 0.10 * EXP(-COALESCE(air.distance_m, 99999) / 5000.0)
      + 0.10 * EXP(-COALESCE(ferry.distance_m, 99999) / 500.0)
    )::NUMERIC(6,4)                     AS transport_score,

    NOW()                               AS _updated_at

FROM listings l

LEFT JOIN LATERAL (
    SELECT s.stop_name, ST_Distance(l.geom_pt, s.geom_pt) AS distance_m
    FROM {{ ref('transport_stops') }} s
    WHERE s.stop_type = 'rail'
    ORDER BY l.geom_pt <-> s.geom_pt
    LIMIT 1
) rail ON TRUE

LEFT JOIN LATERAL (
    SELECT s.stop_name, ST_Distance(l.geom_pt, s.geom_pt) AS distance_m
    FROM {{ ref('transport_stops') }} s
    WHERE s.stop_type = 'bus'
    ORDER BY l.geom_pt <-> s.geom_pt
    LIMIT 1
) bus ON TRUE

LEFT JOIN LATERAL (
    SELECT s.stop_name, ST_Distance(l.geom_pt, s.geom_pt) AS distance_m
    FROM {{ ref('transport_stops') }} s
    WHERE s.stop_type = 'tram'
    ORDER BY l.geom_pt <-> s.geom_pt
    LIMIT 1
) tram ON TRUE

LEFT JOIN LATERAL (
    SELECT s.stop_name, ST_Distance(l.geom_pt, s.geom_pt) AS distance_m
    FROM {{ ref('transport_stops') }} s
    WHERE s.stop_type = 'air'
    ORDER BY l.geom_pt <-> s.geom_pt
    LIMIT 1
) air ON TRUE

LEFT JOIN LATERAL (
    SELECT s.stop_name, ST_Distance(l.geom_pt, s.geom_pt) AS distance_m
    FROM {{ ref('transport_stops') }} s
    WHERE s.stop_type = 'ferry'
    ORDER BY l.geom_pt <-> s.geom_pt
    LIMIT 1
) ferry ON TRUE
