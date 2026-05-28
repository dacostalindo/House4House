{{
    config(
        materialized='table',
        tags=['sce', 'silver', 'sce_buildings'],
        indexes=[
            {'columns': ['cluster_geom_3763'], 'type': 'gist'},
            {'columns': ['cluster_geom_4326'], 'type': 'gist'},
            {'columns': ['concelho']}
        ]
    )
}}

-- silver_sce_buildings — geocoded SCE certificates clustered into building-level rows.
--
-- Body-filled in sprint-09 Slice B (skeleton landed in sprint-08 Activity 8).
--
-- Pipeline:
--   1. Filter stg_sce_certificates to geocode_source='nominatim' (freguesia-centroid
--      rows share a single parish coordinate, which would collapse the entire parish
--      into one DBSCAN cluster).
--   2. ST_ClusterDBSCAN(eps=30m, minpoints=1) on geom_3763 → spatial cluster_id.
--   3. Fração grain: one physical unit can hold several certificates over time —
--      energy certificates expire (~10y) and are re-issued, also on sale. Collapse
--      to one row per fração, keyed by `fraction`, falling back to `doc_number` for
--      the ~52% of certs with no fração label (single houses) so they are never
--      wrongly merged. Keep the most recent certificate per fração.
--   4. Building grain: GROUP BY (cluster_id, normalized_address). The Appendix A
--      normalizer's 0% empirical leakage at 6k rows makes within-cluster GROUP BY
--      sufficient — Levenshtein-ratio fuzzy matching is deferred to v1.5 if dev
--      interviews surface false-splits.
--   5. Aggregates: frac_count (distinct frações), energy_class_dist (JSONB histogram
--      over each fração's latest cert), last_emission / dominant_state from the
--      latest cert per fração, first_emission over ALL certs (true history),
--      cluster_geocode_confidence (MIN — a fuzzy member drags the building's
--      confidence down honestly).
--
-- No parcel_id/cluster_split: empirical 97.7% NULL rate from ST_Within against
-- parcel_universe.geom_pt — Nominatim returns street-centerline points, cadastral
-- parcels are building plots set back from the street (typically 50-200m gap).
-- fn_assess_polygon / Atlas Inspector don't need parcel_id for v1; Inspector can
-- join parcel_universe at query time when it wants per-parcel context.
--
-- Consumed by sprint-09 gold.fn_assess_polygon via ST_DWithin against the input
-- polygon for the Atlas Site Inspector's "Nearby SCE Developments" surface.

WITH

nominatim_hits AS (
    SELECT
        doc_number,
        fraction,
        normalized_address,
        energy_class,
        issued_date,
        status,
        municipality,
        parish,
        geocode_confidence,
        geom_3763
    FROM {{ ref('stg_sce_certificates') }}
    WHERE geocode_source = 'nominatim'
      AND geom_3763 IS NOT NULL
      AND normalized_address IS NOT NULL
),

clustered AS (
    SELECT
        *,
        ST_ClusterDBSCAN(geom_3763, eps := 30, minpoints := 1) OVER () AS cluster_id
    FROM nominatim_hits
),

-- One row per fração: collapse a unit's renewal/re-issue certificates to its
-- most recent. Unlabelled certs (empty `fraction`) fall back to `doc_number`,
-- so each counts once and is never merged with another unlabelled unit.
fracao_grain AS (
    SELECT DISTINCT ON (
        cluster_id,
        normalized_address,
        COALESCE(NULLIF(TRIM(fraction), ''), doc_number)
    )
        *
    FROM clustered
    ORDER BY
        cluster_id,
        normalized_address,
        COALESCE(NULLIF(TRIM(fraction), ''), doc_number),
        issued_date DESC,
        doc_number DESC
),

energy_class_per_building AS (
    SELECT
        cluster_id,
        normalized_address,
        energy_class,
        COUNT(*)::int AS class_count
    FROM fracao_grain
    WHERE energy_class IS NOT NULL
    GROUP BY 1, 2, 3
),

energy_class_dist_per_building AS (
    SELECT
        cluster_id,
        normalized_address,
        jsonb_object_agg(energy_class, class_count) AS energy_class_dist
    FROM energy_class_per_building
    GROUP BY 1, 2
),

-- first_emission spans ALL certificates (a fração's superseded original cert is
-- still real history); every other aggregate uses the latest cert per fração.
emissions_per_building AS (
    SELECT
        cluster_id,
        normalized_address,
        MIN(issued_date) AS first_emission
    FROM clustered
    GROUP BY 1, 2
),

buildings AS (
    SELECT
        c.cluster_id,
        c.normalized_address,
        COUNT(*)::int                                                  AS frac_count,
        em.first_emission                                              AS first_emission,
        MAX(c.issued_date)                                             AS last_emission,
        MODE() WITHIN GROUP (ORDER BY c.status)                        AS dominant_state,
        MIN(c.geocode_confidence)::numeric(4, 3)                       AS cluster_geocode_confidence,
        ARRAY_AGG(c.doc_number ORDER BY c.issued_date, c.doc_number)   AS member_doc_numbers,
        ST_Centroid(ST_Collect(c.geom_3763))                           AS cluster_geom_3763,
        MODE() WITHIN GROUP (ORDER BY c.municipality)                  AS concelho,
        MODE() WITHIN GROUP (ORDER BY c.parish)                        AS parish
    FROM fracao_grain c
    JOIN emissions_per_building em
        ON  em.cluster_id         = c.cluster_id
        AND em.normalized_address = c.normalized_address
    GROUP BY c.cluster_id, c.normalized_address, em.first_emission
)

SELECT
    ROW_NUMBER() OVER (
        ORDER BY b.cluster_id, b.normalized_address
    )::bigint                                                          AS sce_building_id,
    b.cluster_geom_3763::geometry(Point, 3763)                         AS cluster_geom_3763,
    ST_Transform(b.cluster_geom_3763, 4326)::geometry(Point, 4326)     AS cluster_geom_4326,
    b.concelho,
    b.parish,
    b.frac_count,
    COALESCE(e.energy_class_dist, '{}'::jsonb)                         AS energy_class_dist,
    b.first_emission,
    b.last_emission,
    b.dominant_state,
    b.cluster_geocode_confidence,
    b.member_doc_numbers,
    NOW()::timestamptz                                                 AS _built_at
FROM buildings b
LEFT JOIN energy_class_dist_per_building e
    ON  b.cluster_id          = e.cluster_id
    AND b.normalized_address  = e.normalized_address
