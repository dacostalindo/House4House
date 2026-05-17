-- Empty SCE bronze tables for CI's Tier-1 structural dbt build.
-- Schemas mirror the live warehouse exactly so dbt build catches type
-- mismatches against the real upstream. No data inserted.
--
-- Used by .github/workflows/ci.yml step "Bootstrap bronze schemas".
-- Adds the surface needed by stg_sce_certificates → silver_sce_buildings
-- (sprint-09 Slice B path).

CREATE SCHEMA IF NOT EXISTS bronze_regulatory;
CREATE SCHEMA IF NOT EXISTS bronze_enrichment;

CREATE TABLE IF NOT EXISTS bronze_regulatory.raw_sce_certificates (
    id                BIGSERIAL                NOT NULL,
    doc_number        VARCHAR(50)              NOT NULL,
    morada            TEXT,
    fracao            VARCHAR(50),
    localidade        VARCHAR(200),
    concelho          VARCHAR(100),
    estado            VARCHAR(50),
    doc_substituto    VARCHAR(50),
    tipo_documento    VARCHAR(50),
    classe_energetica VARCHAR(10),
    data_emissao      VARCHAR(20),
    data_validade     VARCHAR(20),
    freguesia_detail  VARCHAR(200),
    perito_num        VARCHAR(50),
    conservatoria     VARCHAR(200),
    sob_o_num         VARCHAR(50),
    artigo_matricial  VARCHAR(100),
    fracao_autonoma   VARCHAR(50),
    query_distrito    VARCHAR(10),
    query_concelho    VARCHAR(10),
    query_freguesia   VARCHAR(10),
    _scrape_date      DATE                     NOT NULL,
    _batch_id         VARCHAR(50),
    _ingested_at      TIMESTAMPTZ DEFAULT NOW(),
    _source           VARCHAR(50) DEFAULT 'sce_portal',
    _minio_path       TEXT
);

CREATE TABLE IF NOT EXISTS bronze_enrichment.raw_sce_geocoded (
    doc_number         TEXT          NOT NULL PRIMARY KEY,
    address_lat        NUMERIC(10, 7),
    address_lng        NUMERIC(10, 7),
    geocode_source     TEXT          NOT NULL,
    geocode_confidence NUMERIC(4, 3) NOT NULL,
    normalized_address TEXT,
    nominatim_display  TEXT,
    _geocoded_at       TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
