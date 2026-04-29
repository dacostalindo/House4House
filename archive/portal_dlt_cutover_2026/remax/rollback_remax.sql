-- Rollback DDL for the legacy RE/MAX bronze tables.
-- Run only if the dlt cutover (CUTOVER.md) needs to be reverted before
-- the new pipeline has produced trusted data.
--
-- Usage:
--   psql -h $WAREHOUSE_HOST -U $WAREHOUSE_USER -d $WAREHOUSE_DB -f rollback_remax.sql
--   # then re-enable the legacy DAGs (restored from git) and trigger
--   # remax_ingestion to repopulate from the source.
--
-- NOTE: unlike the Zome cutover, RE/MAX took NO data backup before cutover
-- (clean-slate strategy). A rollback means re-scraping from RE/MAX, which
-- takes ~5h sequential (legacy code) or ~15-20 min if you keep the new
-- parallel Pass 2 helpers and just point at the legacy bronze tables.

BEGIN;

-- ------------------------------------------------------------------
-- bronze_listings.raw_remax_developments
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze_listings.raw_remax_developments (
    id                   BIGSERIAL PRIMARY KEY,
    development_id       INTEGER NOT NULL,
    name                 TEXT,
    slug                 TEXT,
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    minimum_price        NUMERIC(12,2),
    region_name1         TEXT,
    region_name2         TEXT,
    region_name3         TEXT,
    zip_code             TEXT,
    listings_count       INTEGER,
    office_name          TEXT,
    office_id            INTEGER,
    agent_name           TEXT,
    agent_phone          TEXT,
    description          TEXT,
    publish_date         TEXT,
    is_special           BOOLEAN,
    is_special_exclusive BOOLEAN,
    building_pictures    JSONB,
    raw_json             JSONB,
    _scrape_date         DATE NOT NULL,
    _batch_id            VARCHAR(50),
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(50) DEFAULT 'remax_portal',
    _minio_path          TEXT,
    UNIQUE (development_id, _scrape_date)
);

CREATE INDEX IF NOT EXISTS idx_remax_dev_id     ON bronze_listings.raw_remax_developments(development_id);
CREATE INDEX IF NOT EXISTS idx_remax_dev_scrape ON bronze_listings.raw_remax_developments(_scrape_date);
CREATE INDEX IF NOT EXISTS idx_remax_dev_region ON bronze_listings.raw_remax_developments(region_name2);

-- ------------------------------------------------------------------
-- bronze_listings.raw_remax_listings
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze_listings.raw_remax_listings (
    id                        BIGSERIAL PRIMARY KEY,
    listing_id                INTEGER NOT NULL,
    development_id            INTEGER NOT NULL,
    listing_price             NUMERIC(12,2),
    total_area                NUMERIC(10,2),
    living_area               NUMERIC(10,2),
    num_bedrooms              SMALLINT,
    num_bathrooms             SMALLINT,
    floor_id                  SMALLINT,
    floor_number              SMALLINT,
    listing_status_id         SMALLINT,
    is_sold                   BOOLEAN,
    sold_date                 TEXT,
    is_online                 BOOLEAN,
    is_active                 BOOLEAN,
    energy_efficiency_level   SMALLINT,
    typology_id               SMALLINT,
    listing_type              TEXT,
    publish_date              TEXT,
    modified                  TEXT,
    region_name2              TEXT,
    region_name3              TEXT,
    garage_spots              SMALLINT,
    parking                   BOOLEAN,
    is_exclusive              BOOLEAN,
    is_remax_collection       BOOLEAN,
    price_reduction_pct       NUMERIC(5,2),
    -- Pass 2 enrichment (online units only)
    address                   TEXT,
    apartment_number          TEXT,
    market_days               INTEGER,
    previous_price            NUMERIC(12,2),
    construction_year         SMALLINT,
    contract_date             TEXT,
    floor_description         TEXT,
    listing_rooms             JSONB,
    unit_latitude             NUMERIC(10,7),
    unit_longitude            NUMERIC(10,7),
    -- metadata
    raw_json                  JSONB,
    _has_detail               BOOLEAN DEFAULT FALSE,
    _scrape_date              DATE NOT NULL,
    _batch_id                 VARCHAR(50),
    _ingested_at              TIMESTAMPTZ DEFAULT NOW(),
    _source                   VARCHAR(50) DEFAULT 'remax_portal',
    _minio_path               TEXT,
    UNIQUE (listing_id, development_id, _scrape_date)
);

CREATE INDEX IF NOT EXISTS idx_remax_list_id     ON bronze_listings.raw_remax_listings(listing_id);
CREATE INDEX IF NOT EXISTS idx_remax_list_dev    ON bronze_listings.raw_remax_listings(development_id);
CREATE INDEX IF NOT EXISTS idx_remax_list_scrape ON bronze_listings.raw_remax_listings(_scrape_date);
CREATE INDEX IF NOT EXISTS idx_remax_list_status ON bronze_listings.raw_remax_listings(listing_status_id);
CREATE INDEX IF NOT EXISTS idx_remax_list_sold   ON bronze_listings.raw_remax_listings(is_sold);

COMMIT;
