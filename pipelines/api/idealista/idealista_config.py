"""
Idealista — Ingestion Configuration

ZenRows Real Estate API endpoints:
  Discovery: https://realestate.api.zenrows.com/v1/targets/idealista/discovery/
  Detail:    https://realestate.api.zenrows.com/v1/targets/idealista/properties/{id}

Crawl strategy: Split by Portugal's 18 continental distritos × 2 operations (sale/rent).
Each segment stays within Idealista's ~1,800 listing cap per search URL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

ZENROWS_DISCOVERY_URL = (
    "https://realestate.api.zenrows.com/v1/targets/idealista/discovery/"
)
ZENROWS_DETAIL_URL = (
    "https://realestate.api.zenrows.com/v1/targets/idealista/properties/{property_id}"
)

OPERATIONS = ["sale", "rent"]

# Active distritos for scheduled runs.
# Set to None to crawl all 18 distritos, or list specific ones.
# Manual triggers can still override via the "distrito" param.
ACTIVE_DISTRITOS: list[str] | None = ["aveiro"]

# 18 continental distritos mapped to their Idealista search base URLs.
# Each district has a sale and rent URL following Idealista's URL structure.
DISTRITO_SEARCH_URLS: dict[str, dict[str, str]] = {
    "aveiro": {
        "sale": "https://www.idealista.pt/comprar-casas/aveiro/",
        "rent": "https://www.idealista.pt/arrendar-casas/aveiro/",
    },
    "beja": {
        "sale": "https://www.idealista.pt/comprar-casas/beja/",
        "rent": "https://www.idealista.pt/arrendar-casas/beja/",
    },
    "braga": {
        "sale": "https://www.idealista.pt/comprar-casas/braga/",
        "rent": "https://www.idealista.pt/arrendar-casas/braga/",
    },
    "braganca": {
        "sale": "https://www.idealista.pt/comprar-casas/braganca/",
        "rent": "https://www.idealista.pt/arrendar-casas/braganca/",
    },
    "castelo_branco": {
        "sale": "https://www.idealista.pt/comprar-casas/castelo-branco/",
        "rent": "https://www.idealista.pt/arrendar-casas/castelo-branco/",
    },
    "coimbra": {
        "sale": "https://www.idealista.pt/comprar-casas/coimbra/",
        "rent": "https://www.idealista.pt/arrendar-casas/coimbra/",
    },
    "evora": {
        "sale": "https://www.idealista.pt/comprar-casas/evora/",
        "rent": "https://www.idealista.pt/arrendar-casas/evora/",
    },
    "faro": {
        "sale": "https://www.idealista.pt/comprar-casas/faro/",
        "rent": "https://www.idealista.pt/arrendar-casas/faro/",
    },
    "guarda": {
        "sale": "https://www.idealista.pt/comprar-casas/guarda/",
        "rent": "https://www.idealista.pt/arrendar-casas/guarda/",
    },
    "leiria": {
        "sale": "https://www.idealista.pt/comprar-casas/leiria/",
        "rent": "https://www.idealista.pt/arrendar-casas/leiria/",
    },
    "lisboa": {
        "sale": "https://www.idealista.pt/comprar-casas/lisboa/",
        "rent": "https://www.idealista.pt/arrendar-casas/lisboa/",
    },
    "portalegre": {
        "sale": "https://www.idealista.pt/comprar-casas/portalegre/",
        "rent": "https://www.idealista.pt/arrendar-casas/portalegre/",
    },
    "porto": {
        "sale": "https://www.idealista.pt/comprar-casas/porto/",
        "rent": "https://www.idealista.pt/arrendar-casas/porto/",
    },
    "santarem": {
        "sale": "https://www.idealista.pt/comprar-casas/santarem/",
        "rent": "https://www.idealista.pt/arrendar-casas/santarem/",
    },
    "setubal": {
        "sale": "https://www.idealista.pt/comprar-casas/setubal/",
        "rent": "https://www.idealista.pt/arrendar-casas/setubal/",
    },
    "viana_do_castelo": {
        "sale": "https://www.idealista.pt/comprar-casas/viana-do-castelo/",
        "rent": "https://www.idealista.pt/arrendar-casas/viana-do-castelo/",
    },
    "vila_real": {
        "sale": "https://www.idealista.pt/comprar-casas/vila-real/",
        "rent": "https://www.idealista.pt/arrendar-casas/vila-real/",
    },
    "viseu": {
        "sale": "https://www.idealista.pt/comprar-casas/viseu/",
        "rent": "https://www.idealista.pt/arrendar-casas/viseu/",
    },
}

# Rate limiting (seconds between requests)
DISCOVERY_RATE_LIMIT_SECONDS: float = 2.0
DETAIL_RATE_LIMIT_SECONDS: float = 1.5
REQUEST_TIMEOUT_SECONDS: int = 60

# Incremental detail fetching
# Skip detail fetch for listings already in bronze within this window.
# After DETAIL_REFRESH_DAYS, re-fetch to capture price/description changes.
DETAIL_REFRESH_DAYS: int = 30

# MinIO storage
MINIO_BUCKET = "raw"
MINIO_PREFIX = "idealista"
# Paths: raw/idealista/discovery/{operation}/{distrito}/{YYYYMMDD}.jsonl
#        raw/idealista/detail/{operation}/{distrito}/{YYYYMMDD}.jsonl

# Bronze table
BRONZE_SCHEMA_TABLE = "bronze_listings.raw_idealista"


# ---------------------------------------------------------------------------
# Config dataclass (mirrors template's APIIngestionConfig pattern)
# ---------------------------------------------------------------------------


@dataclass
class IdealistaIngestionConfig:
    """
    All parameters needed to run the Idealista ingestion DAG.

    Mirrors the template's APIIngestionConfig style but adds fields
    for two-phase crawling (discovery → detail) and incremental logic.
    """

    # --- DAG identity ---
    dag_id: str = "idealista_ingestion"
    source_name: str = "idealista"
    description: str = (
        "Idealista listing ingestion via ZenRows API. "
        "Crawls Portuguese distritos for sale and rent. "
        "Stores discovery + detail JSONL in MinIO raw layer."
    )

    # --- API connection ---
    discovery_url: str = ZENROWS_DISCOVERY_URL
    detail_url: str = ZENROWS_DETAIL_URL
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS

    # --- Retry (tenacity) ---
    max_retries: int = 3
    retry_backoff_seconds: int = 5

    # --- Rate limiting ---
    discovery_rate_limit_seconds: float = DISCOVERY_RATE_LIMIT_SECONDS
    detail_rate_limit_seconds: float = DETAIL_RATE_LIMIT_SECONDS

    # --- Crawl dimensions ---
    operations: list[str] = field(default_factory=lambda: OPERATIONS)
    active_distritos: list[str] | None = field(
        default_factory=lambda: ACTIVE_DISTRITOS
    )
    distrito_search_urls: dict[str, dict[str, str]] = field(
        default_factory=lambda: DISTRITO_SEARCH_URLS
    )

    # --- Incremental ---
    detail_refresh_days: int = DETAIL_REFRESH_DAYS

    # --- MinIO storage ---
    minio_bucket: str = MINIO_BUCKET
    minio_prefix: str = MINIO_PREFIX

    # --- Bronze ---
    bronze_schema_table: str = BRONZE_SCHEMA_TABLE

    # --- Scheduling ---
    schedule: str = "0 3 * * *"
    start_date: datetime = field(default_factory=lambda: datetime(2025, 1, 1))
    max_active_runs: int = 1
    max_active_tasks: int = 4

    # --- Orchestration ---
    trigger_dag_id: str | None = "idealista_bronze_load"

    # --- DAG settings ---
    tags: list[str] = field(default_factory=lambda: ["idealista"])
    retries: int = 2
    retry_delay_minutes: int = 5

    # --- Discovery limits ---
    max_discovery_pages: int = 90  # 90 × 20 = 1,800 cap


IDEALISTA_CONFIG = IdealistaIngestionConfig()
