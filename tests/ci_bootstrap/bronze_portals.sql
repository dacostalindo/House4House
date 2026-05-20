-- Empty portal bronze tables for CI's Tier-1 structural dbt build.
-- One CREATE TABLE per portal-developments source consumed by
-- `dbt/models/staging/portals/stg_portal_developments_<portal>.sql`.
-- Schemas mirror live warehouse exactly so `dbt build` catches type
-- mismatches against the real upstream. No data inserted.
--
-- Per-PR-additive convention (continuing the pattern from sprint-09 Slice B's
-- bronze_sce.sql): PR-B1 lands RE/MAX. PR-B2/B3/B4 append Zome / Idealista
-- (developments + dev units) / JLL to this file.

CREATE SCHEMA IF NOT EXISTS bronze_listings;

-- ── RE/MAX (PR-B1) ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bronze_listings.remax_developments (
    development_id   BIGINT,
    name             TEXT,
    slug             TEXT,
    region_name1     TEXT,
    region_name2     TEXT,
    region_name3     TEXT,
    zip_code         VARCHAR(10),
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    listings_count   BIGINT,
    minimum_price    DOUBLE PRECISION,
    agent_name       TEXT,
    office_name      TEXT,
    publish_date     TIMESTAMPTZ,
    _dlt_valid_from  TIMESTAMPTZ,
    _dlt_valid_to    TIMESTAMPTZ,
    row_hash         TEXT
);

-- ── Zome (PR-B2) ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bronze_listings.zome_developments (
    venture_id          BIGINT,
    nome                VARCHAR,
    emid                VARCHAR,
    deschub             VARCHAR,
    localizacaolevel2   VARCHAR,
    localizacaolevel3   VARCHAR,
    geocoordinateslat   VARCHAR,
    geocoordinateslong  VARCHAR,
    imoveisdisponiveis  BIGINT,
    imoveisreservados   BIGINT,
    imoveisvendidos     BIGINT,
    idestado            BIGINT,
    tipologiagrupos     VARCHAR,
    precosemformatacao  BIGINT,
    url_user_link       VARCHAR,
    _dlt_valid_from     TIMESTAMPTZ,
    _dlt_valid_to       TIMESTAMPTZ,
    row_hash            VARCHAR
);
