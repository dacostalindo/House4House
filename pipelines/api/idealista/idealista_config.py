"""
Idealista — Ingestion Configuration

ZenRows Real Estate API endpoints:
  Discovery: https://realestate.api.zenrows.com/v1/targets/idealista/discovery/
  Detail:    https://realestate.api.zenrows.com/v1/targets/idealista/properties/{id}

Crawl strategy: Split by concelho (municipality) × 2 operations (sale/rent).
ACTIVE_DISTRITOS selects which distritos to crawl; dim_geography provides
the distrito→concelho mapping at runtime.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------------------
# URL slug utilities
# ---------------------------------------------------------------------------


def to_idealista_slug(name: str) -> str:
    """Convert a Portuguese geographic name to an Idealista URL slug.

    "Águeda"              → "agueda"
    "São João da Madeira" → "sao-joao-da-madeira"
    "Oliveira de Azeméis" → "oliveira-de-azemeis"
    """
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    slug = ascii_text.lower().strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


IDEALISTA_OP_SLUGS: dict[str, str] = {
    "sale": "comprar-casas",
    "rent": "arrendar-casas",
}


def build_idealista_url(
    operation: str, distrito_name: str, concelho_name: str | None = None
) -> str:
    """Build an Idealista search URL dynamically.

    Distrito:  https://www.idealista.pt/comprar-casas/aveiro/
    Concelho:  https://www.idealista.pt/comprar-casas/agueda/
    (Idealista uses concelho slug directly, not nested under distrito.)
    """
    op_slug = IDEALISTA_OP_SLUGS[operation]
    if concelho_name:
        return f"https://www.idealista.pt/{op_slug}/{to_idealista_slug(concelho_name)}/"
    return f"https://www.idealista.pt/{op_slug}/{to_idealista_slug(distrito_name)}/"


def fetch_concelho_mapping(active_distritos: list[str] | None = None) -> list[dict]:
    """Query dim_geography for distinct distrito/concelho pairs.

    Must be called inside an Airflow task (uses Variable.get).
    """
    import psycopg2
    from airflow.models import Variable

    conn = psycopg2.connect(
        host=Variable.get("WAREHOUSE_HOST"),
        port=int(Variable.get("WAREHOUSE_PORT")),
        dbname=Variable.get("WAREHOUSE_DB"),
        user=Variable.get("WAREHOUSE_USER"),
        password=Variable.get("WAREHOUSE_PASSWORD"),
    )
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT distrito_name, concelho_name
            FROM gold_analytics.dim_geography
            ORDER BY distrito_name, concelho_name
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    mapping = [{"distrito_name": r[0], "concelho_name": r[1]} for r in rows]

    if active_distritos:
        active_slugs = {to_idealista_slug(d) for d in active_distritos}
        mapping = [
            m
            for m in mapping
            if to_idealista_slug(m["distrito_name"]) in active_slugs
        ]

    return mapping


# ---------------------------------------------------------------------------
# ZenRows API endpoints
# ---------------------------------------------------------------------------

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
ACTIVE_DISTRITOS: list[str] | None = ["aveiro", "coimbra", "leiria"]

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

# Price-range splitting for large concelhos.
# ZenRows/Idealista caps discovery at ~1,000 unique results.
# When a segment hits UNIQUE_CAP_THRESHOLD, we re-crawl with price-range
# sub-splits to capture all listings.
UNIQUE_CAP_THRESHOLD: int = 950
PRICE_RANGE_BOUNDARIES: list[int] = [150_000, 300_000, 500_000]


def build_price_filtered_url(
    base_url: str, price_min: int | None = None, price_max: int | None = None
) -> str:
    """Append Idealista price filter path to a search URL.

    >>> build_price_filtered_url("https://www.idealista.pt/comprar-casas/aveiro/", 300_000, 500_000)
    'https://www.idealista.pt/comprar-casas/aveiro/com-preco-min_300000,preco-max_500000/'
    """
    parts = []
    if price_min is not None:
        parts.append(f"preco-min_{price_min}")
    if price_max is not None:
        parts.append(f"preco-max_{price_max}")
    if not parts:
        return base_url
    filter_seg = "com-" + ",".join(parts) + "/"
    return base_url.rstrip("/") + "/" + filter_seg


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
# Paths: raw/idealista/discovery/{operation}/{distrito}/{concelho}/{YYYYMMDD}.jsonl
#        raw/idealista/detail/{operation}/{distrito}/{concelho}/{YYYYMMDD}.jsonl

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
    crawl_level: str = "concelho"  # "concelho" (new) or "distrito" (legacy)
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
    schedule: str | None = None
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
