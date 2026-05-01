"""dlt source for JLL Residential PT bronze ingestion (SCD2 + per-entity heartbeat sidecars).

Tables produced in `bronze_listings`:

  jll_developments              SCD2,   primary_key=development_id
  jll_developments_state        UPSERT, primary_key=development_id   (heartbeat sidecar)
  jll_listings                  SCD2,   primary_key=listing_id
  jll_listings_state            UPSERT, primary_key=listing_id       (heartbeat sidecar)

Data source: eGO Real Estate API (https://websiteapi.egorealestate.com/v1)
used by residential.jll.pt. Public token embedded in page JS; no credentials needed.

Two-pass fetch strategy:

  Pass 1: GET /v1/Developments?lng=en-GB&nre=50&pag={n}
    Paginate all developments (171 as of 2026-05). Yields development-level data
    including price ranges, unit counts, GPS, condition, and status.

  Pass 2: GET /v1/Developments/{id}/Fractions?lng=en-GB&nre=200
    For each development discovered in Pass 1, fetch all child units (fractions).
    Yields unit-level data including price, area, rooms, floor, energy cert, etc.

Pass 2 is pre-fetched sequentially with rate-limit delays before entering the
dlt resource generators, then yielded as enriched rows. Module-level cache so
the four resources (devs, devs_state, listings, listings_state) share one fetch.

Plots: not ingested. The /v1/Properties endpoint requires a per-visitor session
identifier (`vui`) sourced from a separate vcs.imoguia.com bootstrap that is
infeasible to reproduce server-side without a real browser. Plot inventory in
PT is already captured by the idealista/remax/zome pipelines.

SCD2 row versioning is driven by an explicit `row_hash` over a curated column
subset. See pipelines/common/SCD2_RULES.md for the cross-pipeline policy.

Heartbeat sidecars distinguish "stable unchanged" from "delisted".
Silver-layer queries should treat as active when:

    last_seen_date >= current_date - 21

The 21-day floor: weekly cadence (7) + one missed run (7) + slack (7).

Rate limiting: eGO returns HTTP 430 when hit too fast. Sequential fetching
with 1.0s delay between requests. Retry on 430 with exponential backoff.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import date
from typing import Any, Iterable

import dlt
import requests as _requests


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# API configuration
# ---------------------------------------------------------------------------
API_BASE = "https://websiteapi.egorealestate.com/v1"
API_TOKEN = "dtGETeo4+XhLexRIjmy3gYZ04bqZq7Xl1et++oPh3HY="

DEV_PAGE_SIZE = 50
FRACTIONS_PAGE_SIZE = 200
RATE_LIMIT_S = 1.0
REQUEST_TIMEOUT_S = 30
MAX_RETRIES = 3
RETRY_BACKOFF_S = 30


# ---------------------------------------------------------------------------
# Schema contract
# ---------------------------------------------------------------------------
SCHEMA_CONTRACT = {"data_type": "freeze", "columns": "evolve"}


# ---------------------------------------------------------------------------
# Version-relevant columns for SCD2 row_hash.
# ---------------------------------------------------------------------------
DEVELOPMENTS_VERSION_COLUMNS: tuple[str, ...] = (
    "min_property_formatted_price",
    "max_property_formatted_price",
    "total_fractions",
    "total_available_fractions",
    "availability_id",
    "condition_id",
    "status_id",
    "gps_lat",
    "gps_lon",
)

LISTINGS_VERSION_COLUMNS: tuple[str, ...] = (
    "price_value",
    "formatted_price",
    "availability_id",
    "condition_id",
    "status_id",
    "gross_area",
    "net_area",
    "rooms",
    "bathrooms",
    "floor",
    "energy_certification_type",
    "gps_lat",
    "gps_lon",
)

# ---------------------------------------------------------------------------
# Numeric columns explicitly typed as `double` — eGO returns these as int
# OR float across rows (e.g. net_area=75 vs net_area=74.5). With
# data_type=freeze, dlt would otherwise infer the type from the first row
# and reject a variant column for the other shape. Pre-declaring locks
# them to float-compatible storage from row #1.
# ---------------------------------------------------------------------------
DEVELOPMENTS_FLOAT_COLUMNS = ("gps_lat", "gps_lon")
LISTINGS_FLOAT_COLUMNS = (
    "price_value", "gross_area", "net_area", "gps_lat", "gps_lon",
)


# ---------------------------------------------------------------------------
# JSON columns — keep as `json` data_type, NOT auto-flatten into child tables.
# ---------------------------------------------------------------------------
DEVELOPMENTS_JSON_COLUMNS = (
    "images",
    "feature_tags",
    "tags",
    "development_business",
    "available_rooms_list",
    "available_rooms_range",
    "area_util_range",
    "raw_json",
)

LISTINGS_JSON_COLUMNS = (
    "images",
    "features",
    "feature_tags",
    "tags",
    "property_business",
    "blue_prints",
    "videos",
    "raw_json",
)



# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _api_headers() -> dict[str, str]:
    return {
        "AuthorizationToken": API_TOKEN,
        "UserInfoToken": "0",
        "x-async": "true",
        "X-Served-By": "JanelaDigital",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Referer": "https://residential.jll.pt/",
        "Origin": "https://residential.jll.pt",
    }


def _fetch_json(path: str, params: dict | None = None) -> dict:
    """GET request to the eGO API with retry on 430 (rate limit)."""
    url = f"{API_BASE}{path}"
    for attempt in range(MAX_RETRIES):
        resp = _requests.get(
            url, params=params, headers=_api_headers(), timeout=REQUEST_TIMEOUT_S,
        )
        if resp.status_code == 430:
            wait = RETRY_BACKOFF_S * (attempt + 1)
            log.warning(
                "[jll] 430 rate limit on %s (attempt %d/%d), waiting %ds",
                path, attempt + 1, MAX_RETRIES, wait,
            )
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# CamelCase → snake_case normalization
# ---------------------------------------------------------------------------
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _to_snake(name: str) -> str:
    return _CAMEL_RE.sub("_", name).lower()


def _snake_case_keys(d: dict) -> dict:
    return {_to_snake(k): v for k, v in d.items()}


# ---------------------------------------------------------------------------
# Hashing — canonicalize numerics so int↔float drift does not create
# spurious SCD2 versions. Kept in sync with zome/remax/idealista by design.
# See pipelines/common/SCD2_RULES.md.
# ---------------------------------------------------------------------------
_HASH_SCALAR_TYPES = (int, float, str, bool, type(None))


def _canonicalize(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return value


def _stable_hash(row: dict, version_cols: Iterable[str]) -> str:
    payload: dict[str, Any] = {}
    for k in version_cols:
        v = row.get(k)
        if not isinstance(v, _HASH_SCALAR_TYPES):
            raise TypeError(
                f"_stable_hash got non-scalar for column {k!r}: {type(v).__name__}. "
                f"Add canonicalization or remove from version_cols."
            )
        payload[k] = _canonicalize(v)
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
def _normalize_development(raw: dict) -> dict:
    """CamelCase → snake_case, preserve raw_json."""
    out = _snake_case_keys(raw)
    out["development_id"] = out.pop("i_d", raw.get("ID"))
    out["raw_json"] = raw
    return out


def _normalize_listing(raw: dict) -> dict:
    """CamelCase → snake_case, flatten price from PropertyBusiness, preserve raw_json."""
    out = _snake_case_keys(raw)
    out["listing_id"] = out.pop("i_d", raw.get("ID"))

    # Flatten price from PropertyBusiness[0].Prices[0]
    biz = raw.get("PropertyBusiness", [{}])
    biz_entry = biz[0] if biz else {}
    prices = biz_entry.get("Prices", [{}])
    price_entry = prices[0] if prices else {}
    out["price_value"] = price_entry.get("PriceValue", 0)
    out["formatted_price"] = price_entry.get("FormattedPrice", "")
    out["currency_iso"] = price_entry.get("CurrencyISO", "")
    out["market_value"] = price_entry.get("MarketValue", 0)
    out["business_name"] = biz_entry.get("BusinessName", "")

    out["raw_json"] = raw
    return out


# ---------------------------------------------------------------------------
# Payload cache — fetched once, shared across all resources in the same run.
# ---------------------------------------------------------------------------
_payload_cache: dict[str, Any] = {}


def _ensure_payload() -> tuple[list[dict], list[dict]]:
    """Fetch all developments (Pass 1) and their fractions (Pass 2).

    Returns (developments, all_listings).
    """
    if "developments" in _payload_cache:
        return _payload_cache["developments"], _payload_cache["listings"]

    # Pass 1: paginate developments
    all_devs: list[dict] = []
    page = 1
    while True:
        data = _fetch_json(
            "/Developments",
            params={"lng": "en-GB", "nre": str(DEV_PAGE_SIZE), "pag": str(page)},
        )
        devs = data.get("Developments", [])
        if not devs:
            break
        all_devs.extend(devs)
        log.info("[jll] Pass 1: page %d → %d developments (total %d)", page, len(devs), len(all_devs))
        if len(devs) < DEV_PAGE_SIZE:
            break
        page += 1
        time.sleep(RATE_LIMIT_S)

    # Pass 2: fetch fractions for each development (paginate if >200)
    all_listings: list[dict] = []
    for i, dev in enumerate(all_devs):
        dev_id = dev["ID"]
        page = 1
        while True:
            time.sleep(RATE_LIMIT_S)
            data = _fetch_json(
                f"/Developments/{dev_id}/Fractions",
                params={
                    "lng": "en-GB",
                    "nre": str(FRACTIONS_PAGE_SIZE),
                    "pag": str(page),
                },
            )
            fractions = data.get("Properties", [])
            all_listings.extend(fractions)
            if len(fractions) < FRACTIONS_PAGE_SIZE:
                break
            page += 1
        if (i + 1) % 20 == 0 or i == len(all_devs) - 1:
            log.info(
                "[jll] Pass 2: %d/%d developments fetched (%d listings total)",
                i + 1, len(all_devs), len(all_listings),
            )

    _payload_cache["developments"] = all_devs
    _payload_cache["listings"] = all_listings
    log.info(
        "[jll] payload ready: %d developments, %d listings",
        len(all_devs), len(all_listings),
    )
    return all_devs, all_listings


def clear_cache() -> None:
    """Clear module-level cache. Call between pipeline.run() calls in tests."""
    _payload_cache.clear()


# ===========================================================================
# Source 1: Facts (SCD2 + sidecars) — developments + listings
# ===========================================================================
@dlt.source(name="jll_facts")
def jll_facts_source() -> Iterable[Any]:
    yield jll_developments
    yield jll_developments_state
    yield jll_listings
    yield jll_listings_state


@dlt.resource(
    name="jll_developments",
    write_disposition={
        "disposition": "merge",
        "strategy": "scd2",
        "row_version_column_name": "row_hash",
    },
    primary_key="development_id",
    columns={
        **{col: {"data_type": "json"} for col in DEVELOPMENTS_JSON_COLUMNS},
        **{col: {"data_type": "double"} for col in DEVELOPMENTS_FLOAT_COLUMNS},
    },
    schema_contract=SCHEMA_CONTRACT,
)
def jll_developments() -> Iterable[dict]:
    devs, _ = _ensure_payload()
    for raw in devs:
        rec = _normalize_development(raw)
        rec["row_hash"] = _stable_hash(rec, DEVELOPMENTS_VERSION_COLUMNS)
        yield rec


@dlt.resource(
    name="jll_developments_state",
    write_disposition="merge",
    primary_key="development_id",
)
def jll_developments_state() -> Iterable[dict]:
    today = date.today()
    devs, _ = _ensure_payload()
    for raw in devs:
        yield {"development_id": raw.get("ID"), "last_seen_date": today}


@dlt.resource(
    name="jll_listings",
    write_disposition={
        "disposition": "merge",
        "strategy": "scd2",
        "row_version_column_name": "row_hash",
    },
    primary_key="listing_id",
    columns={
        **{col: {"data_type": "json"} for col in LISTINGS_JSON_COLUMNS},
        **{col: {"data_type": "double"} for col in LISTINGS_FLOAT_COLUMNS},
    },
    schema_contract=SCHEMA_CONTRACT,
)
def jll_listings() -> Iterable[dict]:
    _, listings = _ensure_payload()
    for raw in listings:
        rec = _normalize_listing(raw)
        rec["row_hash"] = _stable_hash(rec, LISTINGS_VERSION_COLUMNS)
        yield rec


@dlt.resource(
    name="jll_listings_state",
    write_disposition="merge",
    primary_key="listing_id",
)
def jll_listings_state() -> Iterable[dict]:
    today = date.today()
    _, listings = _ensure_payload()
    for raw in listings:
        yield {"listing_id": raw.get("ID"), "last_seen_date": today}


