"""
RE/MAX PT Developments — Scraping + Bronze Configuration

Source:  https://remax.pt/api/Development/PaginatedSearch
Format:  JSON (open REST API, no auth)
Method:  requests (no browser needed)
Refresh: Weekly

--- HOW TO TRIGGER ---

Trigger manually from Airflow UI:
    Airflow UI → remax_ingestion → Trigger DAG

--- DATA ---

~661 developments nationally with ~8,700 unit-level listings.
Two-pass scraping: PaginatedSearch (all devs) + detail endpoint (online units only).
Unit detail includes: address, fraction letter, previousPrice, marketDays, room breakdown.

--- BRONZE TABLES ---

Two bronze tables under bronze_listings:
  raw_remax_developments  ← development-level fields (no JSONB bloat)
  raw_remax_listings      ← one row per unit, typed columns + Pass 2 enrichment
"""

from __future__ import annotations

from datetime import date
import json
import re

from pipelines.scraping.template.scraping_ingestion_template import (
    ScrapingRegion,
    ScrapingIngestionConfig,
)
from pipelines.scraping.template.scraping_bronze_template import BronzeTableConfig
from pipelines.api.remax.remax_scraper import remax_scrape_fn


# ---------------------------------------------------------------------------
# Regions — single region for full country scrape
# ---------------------------------------------------------------------------

REMAX_REGIONS = [
    ScrapingRegion(code="pt", name="PORTUGAL", params={"pageSize": 50}),
]

# ---------------------------------------------------------------------------
# Ingestion config
# ---------------------------------------------------------------------------

REMAX_CONFIG = ScrapingIngestionConfig(
    dag_id="remax_ingestion",
    source_name="remax",
    description=(
        "Scrape new development listings from RE/MAX PT API. "
        "~661 developments with unit-level data (two-pass: search + detail)."
    ),
    target_url="https://remax.pt/api/Development/PaginatedSearch",
    landing_url="https://remax.pt",
    regions=REMAX_REGIONS,
    scrape_fn=remax_scrape_fn,
    backend="requests",
    request_delay=1.0,
    request_timeout=30,
    minio_bucket="raw",
    minio_prefix="remax_developments",
    trigger_dag_id=["remax_bronze_load_developments", "remax_bronze_load_listings"],
    tags=["remax", "developments", "portal", "s46"],
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _extract_scrape_date(object_name: str) -> str:
    """Extract scrape date from MinIO path: remax_developments/{region}/{YYYYMMDD}/{timestamp}.jsonl"""
    match = re.search(r"/(\d{8})/", object_name)
    if match:
        d = match.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Bronze: Developments
# ---------------------------------------------------------------------------

CREATE_DEVELOPMENTS_SQL = """
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
    )
"""

CREATE_DEVELOPMENTS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_remax_dev_id ON bronze_listings.raw_remax_developments(development_id)",
    "CREATE INDEX IF NOT EXISTS idx_remax_dev_scrape ON bronze_listings.raw_remax_developments(_scrape_date)",
    "CREATE INDEX IF NOT EXISTS idx_remax_dev_region ON bronze_listings.raw_remax_developments(region_name2)",
]

INSERT_DEVELOPMENTS_SQL = """
    INSERT INTO bronze_listings.raw_remax_developments (
        development_id, name, slug, latitude, longitude, minimum_price,
        region_name1, region_name2, region_name3, zip_code,
        listings_count, office_name, office_id, agent_name, agent_phone,
        description, publish_date, is_special, is_special_exclusive,
        building_pictures, raw_json,
        _scrape_date, _batch_id, _minio_path
    ) VALUES (
        %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s,
        %s, %s, %s
    )
    ON CONFLICT (development_id, _scrape_date) DO NOTHING
"""


def _flatten_remax_developments(raw_records: list[dict], batch_id: str, minio_path: str) -> list[tuple]:
    """Convert JSONL records to development INSERT tuples (no listings JSONB)."""
    scrape_date = _extract_scrape_date(minio_path)
    rows = []
    for r in raw_records:
        desc_bodies = r.get("descriptionBodies") or []
        description = desc_bodies[0].get("description", "") if desc_bodies else ""

        # Store raw_json without the heavy listings array
        raw = {k: v for k, v in r.items() if k not in ("listings", "listingTitleList")}

        rows.append((
            r.get("id", 0),
            r.get("name", ""),
            r.get("nameToSort", ""),
            r.get("latitude"),
            r.get("longitude"),
            r.get("minimumPrice"),
            r.get("regionName1", ""),
            r.get("regionName2", ""),
            r.get("regionName3", ""),
            r.get("zipCode", ""),
            r.get("listingsCount", 0),
            r.get("officeName", ""),
            r.get("officeID"),
            r.get("userName", ""),
            r.get("userCellPhone", ""),
            description,
            r.get("publishDate", ""),
            r.get("isSpecial"),
            r.get("isSpecialExclusive"),
            json.dumps(r.get("buildingPictures", [])),
            json.dumps(raw),
            scrape_date,
            batch_id,
            minio_path,
        ))
    return rows


# ---------------------------------------------------------------------------
# Bronze: Listings (units)
# ---------------------------------------------------------------------------

CREATE_LISTINGS_SQL = """
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
    )
"""

CREATE_LISTINGS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_remax_list_id ON bronze_listings.raw_remax_listings(listing_id)",
    "CREATE INDEX IF NOT EXISTS idx_remax_list_dev ON bronze_listings.raw_remax_listings(development_id)",
    "CREATE INDEX IF NOT EXISTS idx_remax_list_scrape ON bronze_listings.raw_remax_listings(_scrape_date)",
    "CREATE INDEX IF NOT EXISTS idx_remax_list_status ON bronze_listings.raw_remax_listings(listing_status_id)",
    "CREATE INDEX IF NOT EXISTS idx_remax_list_sold ON bronze_listings.raw_remax_listings(is_sold)",
]

INSERT_LISTINGS_SQL = """
    INSERT INTO bronze_listings.raw_remax_listings (
        listing_id, development_id,
        listing_price, total_area, living_area,
        num_bedrooms, num_bathrooms, floor_id, floor_number,
        listing_status_id, is_sold, sold_date, is_online, is_active,
        energy_efficiency_level, typology_id, listing_type,
        publish_date, modified, region_name2, region_name3,
        garage_spots, parking, is_exclusive, is_remax_collection,
        price_reduction_pct,
        address, apartment_number, market_days, previous_price,
        construction_year, contract_date, floor_description,
        listing_rooms, unit_latitude, unit_longitude,
        raw_json, _has_detail,
        _scrape_date, _batch_id, _minio_path
    ) VALUES (
        %s, %s,
        %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s,
        %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s,
        %s, %s, %s
    )
    ON CONFLICT (listing_id, development_id, _scrape_date) DO NOTHING
"""


def _flatten_remax_listings(raw_records: list[dict], batch_id: str, minio_path: str) -> list[tuple]:
    """Explode listings[] from each development into per-unit INSERT tuples."""
    scrape_date = _extract_scrape_date(minio_path)
    rows = []
    for dev in raw_records:
        dev_id = dev.get("id", 0)
        for u in dev.get("listings", []):
            detail = u.get("_detail") or {}
            has_detail = bool(detail)

            rows.append((
                u.get("id", 0),
                dev_id,
                u.get("listingPrice") or None,
                u.get("totalArea"),
                u.get("livingArea"),
                u.get("numberOfBedrooms"),
                u.get("numberOfBathrooms"),
                u.get("floorID"),
                u.get("floorAsNumber"),
                u.get("listingStatusID"),
                u.get("isSold"),
                u.get("soldDate"),
                u.get("isOnline"),
                u.get("isActive"),
                u.get("energyEfficiencyLevelID"),
                u.get("typologyID"),
                u.get("listingType"),
                u.get("publishDate"),
                u.get("modified"),
                u.get("regionName2"),
                u.get("regionName3"),
                u.get("garageSpots"),
                u.get("parking"),
                u.get("isExclusive"),
                u.get("isRemaxCollection"),
                u.get("priceReductionPercentageValue"),
                # Pass 2
                detail.get("address"),
                detail.get("apartmentNumber"),
                detail.get("marketDays"),
                detail.get("previousPrice"),
                detail.get("constructionYear"),
                detail.get("contractDate"),
                detail.get("floorDescription"),
                json.dumps(detail.get("listingRooms")) if detail.get("listingRooms") else None,
                detail.get("latitude"),
                detail.get("longitude"),
                # metadata
                json.dumps(u),
                has_detail,
                scrape_date,
                batch_id,
                minio_path,
            ))
    return rows


# ---------------------------------------------------------------------------
# Bronze configs
# ---------------------------------------------------------------------------

REMAX_BRONZE_DEVELOPMENTS_CONFIG = BronzeTableConfig(
    dag_id="remax_bronze_load_developments",
    source_name="remax",
    description="Load RE/MAX developments from MinIO into PostGIS bronze table",
    schema_name="bronze_listings",
    table_name="raw_remax_developments",
    create_table_sql=CREATE_DEVELOPMENTS_SQL,
    create_indexes_sql=CREATE_DEVELOPMENTS_INDEXES,
    insert_sql=INSERT_DEVELOPMENTS_SQL,
    minio_bucket="raw",
    minio_prefix="remax_developments",
    flatten_fn=_flatten_remax_developments,
    file_format="jsonl",
    delete_before_insert=False,
    trigger_dag_id=None,
    tags=["remax", "bronze", "developments", "s46"],
)

REMAX_BRONZE_LISTINGS_CONFIG = BronzeTableConfig(
    dag_id="remax_bronze_load_listings",
    source_name="remax",
    description="Load RE/MAX unit listings from MinIO into PostGIS bronze table",
    schema_name="bronze_listings",
    table_name="raw_remax_listings",
    create_table_sql=CREATE_LISTINGS_SQL,
    create_indexes_sql=CREATE_LISTINGS_INDEXES,
    insert_sql=INSERT_LISTINGS_SQL,
    minio_bucket="raw",
    minio_prefix="remax_developments",
    flatten_fn=_flatten_remax_listings,
    file_format="jsonl",
    delete_before_insert=False,
    trigger_dag_id=None,
    tags=["remax", "bronze", "listings", "s46"],
)
