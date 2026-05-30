-- Empty bronze_enrichment tables for CI's Tier-1 structural dbt build.
-- Mirrors the live warehouse exactly so `dbt build` catches type mismatches
-- against upstream. No data inserted.
--
-- bronze_enrichment.raw_sce_geocoded is already created live by
-- pipelines/enrichment/sce_geocode_dag.py; mirroring the DDL here for CI.
-- bronze_enrichment.raw_plot_listing_extractions added by Sprint-09 Slice C
-- (plot_listing_extraction_dag.py).

CREATE SCHEMA IF NOT EXISTS bronze_enrichment;

-- ── SCE geocoded (sprint-08 Activity 7 — Phase 3) ──────────────────────
CREATE TABLE IF NOT EXISTS bronze_enrichment.raw_sce_geocoded (
    doc_number          TEXT PRIMARY KEY,
    address_lat         NUMERIC(10, 7),
    address_lng         NUMERIC(10, 7),
    geocode_source      TEXT NOT NULL,
    geocode_confidence  NUMERIC(4, 3) NOT NULL,
    normalized_address  TEXT,
    nominatim_display   TEXT,
    _geocoded_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Plot listing extractions (sprint-09 Slice C) ───────────────────────
CREATE TABLE IF NOT EXISTS bronze_enrichment.raw_plot_listing_extractions (
    idempotency_hash                  TEXT PRIMARY KEY,
    listing_id                        TEXT NOT NULL,
    listing_url                       TEXT NOT NULL,
    implantation_area_m2              FLOAT,
    construction_area_m2_above_ground FLOAT,
    construction_area_m2_total        FLOAT,
    area_loteamento_m2                FLOAT,
    num_dwellings_allowed             INTEGER,
    max_floors_allowed                INTEGER,
    num_caves                         INTEGER,
    permit_status                     TEXT,
    is_loteamento                     BOOLEAN,
    source_spans                      JSONB NOT NULL DEFAULT '{}'::jsonb,
    extraction_confidence             NUMERIC(4, 3),
    extraction_status                 TEXT NOT NULL DEFAULT 'success',
    error_message                     TEXT,
    raw_response                      TEXT,
    model_id                          TEXT NOT NULL,
    input_tokens                      INTEGER,
    output_tokens                     INTEGER,
    cost_usd                          NUMERIC(8, 5),
    extracted_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
