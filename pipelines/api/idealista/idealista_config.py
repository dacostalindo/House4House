"""
Idealista — Ingestion Configuration

ZenRows Real Estate API endpoints:
  Discovery: https://realestate.api.zenrows.com/v1/targets/idealista/discovery/
  Detail:    https://realestate.api.zenrows.com/v1/targets/idealista/properties/{id}

Crawl strategy: Split by Portugal's 18 continental distritos × 2 operations (sale/rent).
Each segment stays within Idealista's ~1,800 listing cap per search URL.
"""

ZENROWS_DISCOVERY_URL = (
    "https://realestate.api.zenrows.com/v1/targets/idealista/discovery/"
)
ZENROWS_DETAIL_URL = (
    "https://realestate.api.zenrows.com/v1/targets/idealista/properties/{property_id}"
)

OPERATIONS = ["sale", "rent"]

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
