-- Empty bronze_geo.raw_cos_national_ogc for CI's Tier-1 structural dbt build.
-- silver_geo.land_use is built from stg_cos2023 → which sources this bronze.
-- Stubbing it empty lets dbt build the silver model + tests/sql/silver_land_use_*
-- pgTAP test exercise the SQL contract against an empty table (count=0 passes
-- trivially). Schema mirrors the production loader (cos_ogc_bronze_dag.py).

CREATE SCHEMA IF NOT EXISTS bronze_geo;

CREATE TABLE IF NOT EXISTS bronze_geo.raw_cos_national_ogc (
    feature_id        INTEGER,
    municipio         TEXT,
    nutsii            TEXT,
    nutsiii           TEXT,
    cos23_n4_c        TEXT,
    cos23_n4_l        TEXT,
    area_ha           DOUBLE PRECISION,
    geom              GEOMETRY(GEOMETRY, 3763),
    _source_url       TEXT,
    _load_timestamp   TIMESTAMPTZ DEFAULT NOW()
);
