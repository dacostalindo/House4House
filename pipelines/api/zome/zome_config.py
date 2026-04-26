"""
Zome PT — API Ingestion + Bronze Configuration

Source:  Supabase REST API at luvskhnljpxllkxpeasu.supabase.co
Auth:    Public anon key via ZOME_SUPABASE_KEY env var
Schema:  pt_prod (via Accept-Profile header)
Refresh: Weekly

Two tables:
  tab_ventures     (296 developments) — aggregate unit counts, GPS, pricing, finishing maps
  tab_listing_list (8,972 listings)   — per-unit price, area, rooms, status, GPS

--- HOW TO TRIGGER ---

Trigger manually from Airflow UI:
    Airflow UI → zome_api_ingestion → Trigger DAG

--- BRONZE LOADING ---

Two bronze tables under bronze_listings:
  raw_zome_developments  ← tab_ventures (296 rows)
  raw_zome_listings      ← tab_listing_list (8,972 rows)
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime

from pipelines.api.template.api_ingestion_template import (
    APIIndicator,
    APIIngestionConfig,
)
from pipelines.scraping.template.scraping_bronze_template import BronzeTableConfig


# ---------------------------------------------------------------------------
# Supabase connection
# ---------------------------------------------------------------------------

SUPABASE_URL = "https://luvskhnljpxllkxpeasu.supabase.co"


def _supabase_headers() -> dict[str, str]:
    """Build Supabase auth headers from environment variable."""
    key = os.environ.get("ZOME_SUPABASE_KEY", "")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept-Profile": "pt_prod",
    }


# ---------------------------------------------------------------------------
# Indicators (one per Supabase table)
# ---------------------------------------------------------------------------

# Supabase caps at 1,000 rows per request. Ventures (296) fits in one request.
# Listings (8,975) needs 9 paginated requests via offset indicators.

ZOME_INDICATORS = [
    APIIndicator(
        code="tab_ventures",
        name="developments",
        description="Zome developments — aggregate unit counts, GPS, pricing, finishing maps",
        category="developments",
        endpoint_params={"select": "*", "limit": "1000"},
    ),
] + [
    APIIndicator(
        code="tab_listing_list",
        name=f"listings_p{i}",
        description=f"Zome listings page {i} (offset {i * 1000})",
        category="listings",
        endpoint_params={"select": "*", "limit": "1000", "offset": str(i * 1000)},
        storage_key=f"tab_listing_list/p{i}",
    )
    for i in range(10)  # 10 pages × 1,000 = covers up to 10,000 listings
]

DATASET_CODES = [ind.code for ind in ZOME_INDICATORS]

# ---------------------------------------------------------------------------
# Ingestion config
# ---------------------------------------------------------------------------

ZOME_CONFIG = APIIngestionConfig(
    dag_id="zome_api_ingestion",
    source_name="zome",
    description=(
        "Fetch developments (296) + listings (8,972) from Zome PT Supabase API. "
        "Two indicators: tab_ventures and tab_listing_list."
    ),
    base_url=SUPABASE_URL,
    api_path="/rest/v1/",
    code_in_path=True,
    code_param_name=None,
    default_params={},
    extra_headers=_supabase_headers(),
    request_timeout_seconds=60,
    rate_limit_delay_seconds=0.5,
    indicators=ZOME_INDICATORS,
    minio_bucket="raw",
    minio_prefix="zome",

    # --- Schedule: daily refresh (every day at 06:00 UTC) ---
    schedule="0 6 * * *",
    start_date=datetime(2026, 1, 1),

    trigger_dag_id=["zome_bronze_load_developments", "zome_bronze_load_listings"],
    tags=["zome", "developments", "listings", "portal", "supabase"],
)


# ---------------------------------------------------------------------------
# Bronze: Developments (tab_ventures)
# ---------------------------------------------------------------------------

CREATE_DEVELOPMENTS_SQL = """
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
    )
"""

CREATE_DEVELOPMENTS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_zome_dev_id ON bronze_listings.raw_zome_developments(venture_id)",
    "CREATE INDEX IF NOT EXISTS idx_zome_dev_scrape ON bronze_listings.raw_zome_developments(_scrape_date)",
    "CREATE INDEX IF NOT EXISTS idx_zome_dev_loc ON bronze_listings.raw_zome_developments(localizacaolevel2)",
]

INSERT_DEVELOPMENTS_SQL = """
    INSERT INTO bronze_listings.raw_zome_developments (
        venture_id, emid, nome, geocoordinateslat, geocoordinateslong,
        preco, precosemformatacao, tipologiagrupos,
        imoveisdisponiveis, imoveisreservados, imoveisvendidos,
        acabamento, exclusividade, idestado,
        localizacaolevel1, localizacaolevel2, localizacaolevel3,
        nomeconsultor, emailconsultor, contactoconsultor, deschub,
        dataentradarede, mostrarprecowebsite, descricaocompleta,
        gallery, video, virtualreality, raw_json,
        _scrape_date, _batch_id, _minio_path
    ) VALUES (
        %s, %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s
    )
    ON CONFLICT (venture_id, _scrape_date) DO NOTHING
"""


# ---------------------------------------------------------------------------
# Bronze: Listings (tab_listing_list)
# ---------------------------------------------------------------------------

CREATE_LISTINGS_SQL = """
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
    )
"""

CREATE_LISTINGS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_zome_list_id ON bronze_listings.raw_zome_listings(listing_id)",
    "CREATE INDEX IF NOT EXISTS idx_zome_list_pid ON bronze_listings.raw_zome_listings(pid)",
    "CREATE INDEX IF NOT EXISTS idx_zome_list_idemp ON bronze_listings.raw_zome_listings(idemp)",
    "CREATE INDEX IF NOT EXISTS idx_zome_list_scrape ON bronze_listings.raw_zome_listings(_scrape_date)",
    "CREATE INDEX IF NOT EXISTS idx_zome_list_state ON bronze_listings.raw_zome_listings(idestadoimovel)",
]

INSERT_LISTINGS_SQL = """
    INSERT INTO bronze_listings.raw_zome_listings (
        listing_id, pid, idemp, emid, nome_emp,
        idestadoimovel, idcondicaoimovel, idtipologia, idtiponegocio,
        precoimovel, precosemformatacao, valorantigo,
        areautilhab, areabrutaconst, totalquartossuite, attr_wcs,
        attr_garagem, attr_garagem_num, attr_elevador,
        geocoordinateslat, geocoordinateslong,
        localizacaolevel1, localizacaolevel2, localizacaolevel3,
        url_detail, dataentradarede, reservadozomenow, showwebsite, showluxury,
        rating, gallery, raw_json,
        _scrape_date, _batch_id, _minio_path
    ) VALUES (
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s,
        %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s
    )
    ON CONFLICT (listing_id, _scrape_date) DO NOTHING
"""


# ---------------------------------------------------------------------------
# Flatten functions
# ---------------------------------------------------------------------------

def _extract_scrape_date(object_name: str) -> str:
    """Extract scrape date from MinIO path: zome/{code}/{YYYYMMDD}T*.json"""
    match = re.search(r"/(\d{8})T", object_name)
    if match:
        d = match.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return date.today().isoformat()


def _flatten_developments(raw_records: list[dict], batch_id: str, minio_path: str) -> list[tuple]:
    """Convert tab_ventures records to INSERT tuples."""
    scrape_date = _extract_scrape_date(minio_path)
    rows = []
    for r in raw_records:
        rows.append((
            r.get("id", 0),
            r.get("emid", ""),
            r.get("nome", ""),
            r.get("geocoordinateslat", ""),
            r.get("geocoordinateslong", ""),
            r.get("preco", ""),
            r.get("precosemformatacao"),
            r.get("tipologiagrupos", ""),
            r.get("imoveisdisponiveis"),
            r.get("imoveisreservados"),
            r.get("imoveisvendidos"),
            r.get("acabamento", ""),
            r.get("exclusividade"),
            r.get("idestado"),
            r.get("localizacaolevel1", ""),
            r.get("localizacaolevel2", ""),
            r.get("localizacaolevel3", ""),
            r.get("nomeconsultor", ""),
            r.get("emailconsultor", ""),
            r.get("contactoconsultor", ""),
            r.get("deschub", ""),
            r.get("dataentradarede", ""),
            r.get("mostrarprecowebsite"),
            json.dumps(r.get("descricaocompleta")) if r.get("descricaocompleta") else None,
            json.dumps(r.get("gallery")) if r.get("gallery") else None,
            json.dumps(r.get("video")) if r.get("video") else None,
            json.dumps(r.get("virtualreality")) if r.get("virtualreality") else None,
            json.dumps(r),
            scrape_date,
            batch_id,
            minio_path,
        ))
    return rows


def _flatten_listings(raw_records: list[dict], batch_id: str, minio_path: str) -> list[tuple]:
    """Convert tab_listing_list records to INSERT tuples."""
    scrape_date = _extract_scrape_date(minio_path)
    rows = []
    for r in raw_records:
        rows.append((
            r.get("id", 0),
            r.get("pid", ""),
            r.get("idemp"),
            r.get("emid", ""),
            r.get("nome_emp", ""),
            r.get("idestadoimovel"),
            r.get("idcondicaoimovel"),
            r.get("idtipologia"),
            r.get("idtiponegocio"),
            r.get("precoimovel", ""),
            r.get("precosemformatacao"),
            r.get("valorantigo", ""),
            r.get("areautilhab"),
            r.get("areabrutaconst"),
            r.get("totalquartossuite"),
            r.get("attr_wcs"),
            r.get("attr_garagem", ""),
            r.get("attr_garagem_num"),
            r.get("attr_elevador"),
            r.get("geocoordinateslat", ""),
            r.get("geocoordinateslong", ""),
            r.get("localizacaolevel1imovel", ""),
            r.get("localizacaolevel2imovel", ""),
            r.get("localizacaolevel3imovel", ""),
            r.get("url_detail_view_website", ""),
            r.get("dataentradarede", ""),
            r.get("reservadozomenow"),
            r.get("showwebsite"),
            r.get("showluxury"),
            r.get("rating"),
            json.dumps(r.get("gallery")) if r.get("gallery") else None,
            json.dumps(r),
            scrape_date,
            batch_id,
            minio_path,
        ))
    return rows


# ---------------------------------------------------------------------------
# Bronze configs
# ---------------------------------------------------------------------------

ZOME_BRONZE_DEVELOPMENTS_CONFIG = BronzeTableConfig(
    dag_id="zome_bronze_load_developments",
    source_name="zome",
    description="Load Zome developments from MinIO into PostGIS bronze table",
    schema_name="bronze_listings",
    table_name="raw_zome_developments",
    create_table_sql=CREATE_DEVELOPMENTS_SQL,
    create_indexes_sql=CREATE_DEVELOPMENTS_INDEXES,
    insert_sql=INSERT_DEVELOPMENTS_SQL,
    minio_bucket="raw",
    minio_prefix="zome/tab_ventures",
    flatten_fn=_flatten_developments,
    file_format="json",
    delete_before_insert=False,
    trigger_dag_id=None,
    tags=["zome", "bronze", "developments"],
)

ZOME_BRONZE_LISTINGS_CONFIG = BronzeTableConfig(
    dag_id="zome_bronze_load_listings",
    source_name="zome",
    description="Load Zome listings from MinIO into PostGIS bronze table",
    schema_name="bronze_listings",
    table_name="raw_zome_listings",
    create_table_sql=CREATE_LISTINGS_SQL,
    create_indexes_sql=CREATE_LISTINGS_INDEXES,
    insert_sql=INSERT_LISTINGS_SQL,
    minio_bucket="raw",
    minio_prefix="zome/tab_listing_list",
    flatten_fn=_flatten_listings,
    file_format="json",
    delete_before_insert=False,
    trigger_dag_id=None,
    tags=["zome", "bronze", "listings"],
)
