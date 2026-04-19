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

~661 developments nationally with unit-level data.
Two-pass scraping: PaginatedSearch (all devs) + detail endpoint (online units only).
Unit detail includes: address, fraction letter, previousPrice, marketDays, room breakdown.
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
from pipelines.scraping.remax.remax_scraper import remax_scrape_fn


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
    trigger_dag_id="remax_bronze_load",
    tags=["remax", "developments", "portal", "s46"],
)

# ---------------------------------------------------------------------------
# Bronze config
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
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
        agent_name           TEXT,
        agent_phone          TEXT,
        description          TEXT,
        publish_date         TEXT,
        building_pictures    JSONB,
        listings             JSONB,
        _scrape_date         DATE NOT NULL,
        _batch_id            VARCHAR(50),
        _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
        _source              VARCHAR(50) DEFAULT 'remax_portal',
        _minio_path          TEXT,
        UNIQUE (development_id, _scrape_date)
    )
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_remax_dev_id ON bronze_listings.raw_remax_developments(development_id)",
    "CREATE INDEX IF NOT EXISTS idx_remax_dev_scrape ON bronze_listings.raw_remax_developments(_scrape_date)",
    "CREATE INDEX IF NOT EXISTS idx_remax_dev_region ON bronze_listings.raw_remax_developments(region_name2)",
]

INSERT_SQL = """
    INSERT INTO bronze_listings.raw_remax_developments (
        development_id, name, slug, latitude, longitude, minimum_price,
        region_name1, region_name2, region_name3, zip_code,
        listings_count, office_name, agent_name, agent_phone, description,
        publish_date, building_pictures, listings,
        _scrape_date, _batch_id, _minio_path
    ) VALUES (
        %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s
    )
    ON CONFLICT (development_id, _scrape_date) DO NOTHING
"""


def _extract_scrape_date(object_name: str) -> str:
    """Extract scrape date from MinIO path: remax_developments/{region}/{YYYYMMDD}/{timestamp}.jsonl"""
    match = re.search(r"/(\d{8})/", object_name)
    if match:
        d = match.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return date.today().isoformat()


def _flatten_remax_records(raw_records: list[dict], batch_id: str, minio_path: str) -> list[tuple]:
    """Convert JSONL records to INSERT tuples.

    Each record is a full development dict from PaginatedSearch,
    with listings[]._detail enriched by the detail endpoint for online units.
    The listings JSONB preserves the full unit array including enrichment.
    """
    scrape_date = _extract_scrape_date(minio_path)
    rows = []
    for r in raw_records:
        # Extract first description body if available
        desc_bodies = r.get("descriptionBodies") or []
        description = desc_bodies[0].get("description", "") if desc_bodies else ""

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
            r.get("userName", ""),
            r.get("userCellPhone", ""),
            description,
            r.get("publishDate", ""),
            json.dumps(r.get("buildingPictures", [])),
            json.dumps(r.get("listings", [])),
            scrape_date,
            batch_id,
            minio_path,
        ))
    return rows


REMAX_BRONZE_CONFIG = BronzeTableConfig(
    dag_id="remax_bronze_load",
    source_name="remax",
    description="Load RE/MAX development JSONL from MinIO into PostGIS bronze table",
    schema_name="bronze_listings",
    table_name="raw_remax_developments",
    create_table_sql=CREATE_TABLE_SQL,
    create_indexes_sql=CREATE_INDEXES_SQL,
    insert_sql=INSERT_SQL,
    minio_bucket="raw",
    minio_prefix="remax_developments",
    flatten_fn=_flatten_remax_records,
    file_format="jsonl",
    delete_before_insert=False,
    trigger_dag_id="dbt_remax_build",
    tags=["remax", "bronze", "developments", "s46"],
)
