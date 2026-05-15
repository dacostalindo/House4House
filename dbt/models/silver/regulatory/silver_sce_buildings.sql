{{
    config(
        materialized='table',
        tags=['sce', 'silver', 'sce_buildings'],
        indexes=[
            {'columns': ['cluster_geom_3763'], 'type': 'gist'},
            {'columns': ['cluster_geom_4326'], 'type': 'gist'},
            {'columns': ['parcel_id']},
            {'columns': ['concelho']}
        ]
    )
}}

-- silver_sce_buildings — clustered SCE certificates rolled up to per-building rows.
--
-- ┌─ Sprint-08 Activity 8 (THIS COMMIT): empty skeleton only ─┐
-- │  Schema declared with the locked column types, indexes,    │
-- │  and tests. WHERE FALSE produces zero rows — dbt creates    │
-- │  the empty silver_regulatory.silver_sce_buildings table     │
-- │  + GIST/btree indexes so sprint-09 only fills the body.     │
-- └────────────────────────────────────────────────────────────┘
--
-- Sprint-09 Slice B fills this body with the actual clustering logic:
--   1. ST_ClusterDBSCAN(stg_sce_certificates.geom_3763, eps=30m, minpoints=1)
--      on geocoded SCE certificates (Aveiro distrito).
--   2. Within each spatial cluster, dedup rows with Levenshtein-ratio <= 0.15
--      on normalized_address (fuzzystrmatch.levenshtein, installed in
--      dbt_project.yml on-run-start as part of this Activity).
--   3. Tiebreak when a cluster spans 2+ cadastral parcels (parcel_universe):
--      pick parcel with most member rows → smaller area → still-tied →
--      cluster_split=TRUE on BOTH parcels (per Appendix A).
--   4. Aggregates per building: frac_count (≈ units), energy_class_dist (JSONB
--      histogram across A+ / A / B / B- / C / D / E / F), first_emission,
--      last_emission, dominant_state, cluster_geocode_confidence (MIN of
--      member geocode_confidence — so a fuzzy member drags the building's
--      confidence down to be honest in the UI).
--
-- Consumed by sprint-09's gold.fn_assess_polygon via ST_DWithin against the
-- input polygon for the "nearby SCE developments" surface in the Atlas
-- Site Inspector.

SELECT
    NULL::BIGINT                                  AS sce_building_id,
    CAST(NULL AS geometry(Point, 3763))           AS cluster_geom_3763,
    CAST(NULL AS geometry(Point, 4326))           AS cluster_geom_4326,
    NULL::TEXT                                    AS concelho,
    NULL::TEXT                                    AS parish,
    NULL::TEXT                                    AS parcel_id,
    NULL::BOOLEAN                                 AS cluster_split,
    NULL::INTEGER                                 AS frac_count,
    NULL::JSONB                                   AS energy_class_dist,
    NULL::DATE                                    AS first_emission,
    NULL::DATE                                    AS last_emission,
    NULL::TEXT                                    AS dominant_state,
    NULL::NUMERIC(4, 3)                           AS cluster_geocode_confidence,
    ARRAY[]::TEXT[]                               AS member_doc_numbers,
    NOW()::TIMESTAMPTZ                            AS _built_at
FROM {{ ref('stg_sce_certificates') }}
WHERE FALSE
