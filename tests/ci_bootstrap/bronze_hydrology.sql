-- Empty bronze_hydrology tables for CI's Tier-1 structural dbt build.
-- Schemas mirror live warehouse exactly so dbt build catches type mismatches
-- against the real upstream. No data inserted.
--
-- Used by .github/workflows/ci.yml step "Bootstrap bronze schemas".
-- Adds the surface needed by stg_apa_arpsi + stg_lneg_aquiferos
-- → silver_geo.floodplains + silver_geo.aquifers (sprint-09 WS4 quick-wins batch).

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS bronze_hydrology;

-- APA ARPSI floodplain — typed schema per apa_bronze_dag.py CREATE_TABLE_SQL
CREATE TABLE IF NOT EXISTS bronze_hydrology.raw_apa_arpsi_floodplain (
    feature_id            INTEGER,
    river_basin           TEXT,
    location              TEXT,
    designation           TEXT,
    source                TEXT,
    publication_date      TIMESTAMPTZ,
    return_period_years   INTEGER,
    geocode               INTEGER,
    geom                  GEOMETRY(GEOMETRY, 3763),
    _source_url           TEXT,
    _load_timestamp       TIMESTAMPTZ DEFAULT NOW()
);

-- LNEG aquifers — generic JSONB schema per lneg_bronze_dag.py _create_table_sql
CREATE TABLE IF NOT EXISTS bronze_hydrology.raw_lneg_aquiferos (
    feature_id      INTEGER,
    layer_name      VARCHAR(64),
    properties      JSONB,
    geom            GEOMETRY(GEOMETRY, 3763),
    _source_url     TEXT,
    _load_timestamp TIMESTAMPTZ DEFAULT NOW()
);
