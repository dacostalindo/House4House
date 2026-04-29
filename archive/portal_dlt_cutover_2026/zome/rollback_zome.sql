-- Rollback DDL for the legacy zome bronze tables.
-- Run only if the dlt cutover (CUTOVER.md) needs to be reverted before
-- the new pipeline has produced trusted data.
--
-- Usage:
--   psql -h $WAREHOUSE_HOST -U $WAREHOUSE_USER -d $WAREHOUSE_DB -f rollback_zome.sql
--   psql ... -c "\\copy bronze_listings.raw_zome_developments FROM '...'"  -- restore data
--   psql ... -c "\\copy bronze_listings.raw_zome_listings     FROM '...'"
--
-- Companion data dump from CUTOVER.md step 1:
--   pg_dump --data-only --table=bronze_listings.raw_zome_* > zome_pre_cutover.sql

BEGIN;

-- ------------------------------------------------------------------
-- bronze_listings.raw_zome_developments
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze_listings.raw_zome_developments (
    id                   BIGSERIAL PRIMARY KEY,
    venture_id           INTEGER NOT NULL,
    emid                 TEXT,
    nome                 TEXT,
    geocoordinateslat    TEXT,
    geocoordinateslong   TEXT,
    preco                TEXT,
    precosemformatacao   NUMERIC(12,2),
    tipologiagrupos      TEXT,
    imoveisdisponiveis   INTEGER,
    imoveisreservados    INTEGER,
    imoveisvendidos      INTEGER,
    acabamento           TEXT,
    exclusividade        BOOLEAN,
    idestado             INTEGER,
    localizacaolevel1    TEXT,
    localizacaolevel2    TEXT,
    localizacaolevel3    TEXT,
    nomeconsultor        TEXT,
    emailconsultor       TEXT,
    contactoconsultor    TEXT,
    deschub              TEXT,
    dataentradarede      TEXT,
    mostrarprecowebsite  BOOLEAN,
    descricaocompleta    JSONB,
    gallery              JSONB,
    video                JSONB,
    virtualreality       JSONB,
    raw_json             JSONB,
    _scrape_date         DATE NOT NULL,
    _batch_id            VARCHAR(50),
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(50) DEFAULT 'zome_supabase',
    _minio_path          TEXT,
    UNIQUE (venture_id, _scrape_date)
);

CREATE INDEX IF NOT EXISTS idx_zome_dev_id     ON bronze_listings.raw_zome_developments(venture_id);
CREATE INDEX IF NOT EXISTS idx_zome_dev_scrape ON bronze_listings.raw_zome_developments(_scrape_date);
CREATE INDEX IF NOT EXISTS idx_zome_dev_loc    ON bronze_listings.raw_zome_developments(localizacaolevel2);

-- ------------------------------------------------------------------
-- bronze_listings.raw_zome_listings
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze_listings.raw_zome_listings (
    id                   BIGSERIAL PRIMARY KEY,
    listing_id           BIGINT NOT NULL,
    pid                  TEXT,
    idemp                INTEGER,
    emid                 TEXT,
    nome_emp             TEXT,
    idestadoimovel       INTEGER,
    idcondicaoimovel     INTEGER,
    idtipologia          INTEGER,
    idtiponegocio        INTEGER,
    precoimovel          TEXT,
    precosemformatacao   NUMERIC(12,2),
    valorantigo          TEXT,
    areautilhab          NUMERIC(10,2),
    areabrutaconst       NUMERIC(10,2),
    totalquartossuite    INTEGER,
    attr_wcs             INTEGER,
    attr_garagem         TEXT,
    attr_garagem_num     INTEGER,
    attr_elevador        INTEGER,
    geocoordinateslat    TEXT,
    geocoordinateslong   TEXT,
    localizacaolevel1    TEXT,
    localizacaolevel2    TEXT,
    localizacaolevel3    TEXT,
    url_detail           TEXT,
    dataentradarede      TEXT,
    reservadozomenow     BOOLEAN,
    showwebsite          BOOLEAN,
    showluxury           BOOLEAN,
    rating               INTEGER,
    gallery              JSONB,
    raw_json             JSONB,
    _scrape_date         DATE NOT NULL,
    _batch_id            VARCHAR(50),
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(50) DEFAULT 'zome_supabase',
    _minio_path          TEXT,
    UNIQUE (listing_id, _scrape_date)
);

CREATE INDEX IF NOT EXISTS idx_zome_list_id     ON bronze_listings.raw_zome_listings(listing_id);
CREATE INDEX IF NOT EXISTS idx_zome_list_pid    ON bronze_listings.raw_zome_listings(pid);
CREATE INDEX IF NOT EXISTS idx_zome_list_idemp  ON bronze_listings.raw_zome_listings(idemp);
CREATE INDEX IF NOT EXISTS idx_zome_list_scrape ON bronze_listings.raw_zome_listings(_scrape_date);
CREATE INDEX IF NOT EXISTS idx_zome_list_state  ON bronze_listings.raw_zome_listings(idestadoimovel);

COMMIT;
