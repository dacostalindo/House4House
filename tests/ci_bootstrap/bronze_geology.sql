-- Empty bronze_geology table for CI's Tier-1 structural dbt build.
-- Schema mirrors live warehouse exactly so dbt build catches type mismatches
-- against the real upstream. No data inserted.
--
-- Used by .github/workflows/ci.yml step "Bootstrap bronze schemas".
-- Adds the surface needed by stg_lneg_geology → silver_geo.geology
-- (sprint-09 WS4 quick-wins batch).

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS bronze_geology;

-- LNEG geology 1:500k — generic JSONB schema per lneg_bronze_dag.py
CREATE TABLE IF NOT EXISTS bronze_geology.raw_lneg_geology_500k (
    feature_id      INTEGER,
    layer_name      VARCHAR(64),
    properties      JSONB,
    geom            GEOMETRY(GEOMETRY, 3763),
    _source_url     TEXT,
    _load_timestamp TIMESTAMPTZ DEFAULT NOW()
);
