-- Empty bronze_ine.raw_indicators for CI's Tier-1 structural dbt build.
-- Schema mirrors live warehouse exactly (post sprint-09 WS4 migration that
-- added indicator_category). No data inserted.
--
-- NOTE: bronze_ine schema is also referenced by bronze_geography.sql for the
-- raw_bgri table — using IF NOT EXISTS so both files compose.
--
-- Used by .github/workflows/ci.yml step "Bootstrap bronze schemas".

CREATE SCHEMA IF NOT EXISTS bronze_ine;

CREATE TABLE IF NOT EXISTS bronze_ine.raw_indicators (
    id                   BIGSERIAL PRIMARY KEY,
    indicator_code       VARCHAR(20) NOT NULL,
    indicator_name       TEXT,
    indicator_category   VARCHAR(20),
    last_updated         DATE,
    time_period          VARCHAR(50) NOT NULL,
    geocod               VARCHAR(20),
    geodsg               VARCHAR(200),
    dim_3                VARCHAR(20),
    dim_3_t              VARCHAR(200),
    dim_4                VARCHAR(20),
    dim_4_t              VARCHAR(200),
    dim_5                VARCHAR(20),
    dim_5_t              VARCHAR(200),
    valor                NUMERIC(15,4),
    ind_string           VARCHAR(50),
    sinal_conv           VARCHAR(10),
    sinal_conv_desc      VARCHAR(100),
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(50) DEFAULT 'ine_api',
    _batch_id            VARCHAR(50),
    _api_extraction_ts   TIMESTAMPTZ
);
