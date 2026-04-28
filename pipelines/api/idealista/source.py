"""dlt source for Idealista PT developments + their child units (new construction).

Tables produced in `bronze_listings`:

  idealista_developments               SCD2,   primary_key=development_id
  idealista_developments_state         UPSERT, primary_key=development_id   (heartbeat sidecar)
  idealista_development_units          SCD2,   primary_key=unit_id
  idealista_development_units_state    UPSERT, primary_key=unit_id          (heartbeat sidecar)

Distinct from the existing `bronze_listings.raw_idealista` (resale catalog via
ZenRows Real Estate API discovery+detail) — this source covers
`/comprar-empreendimentos/` (new-construction developments and their member
units), which has no equivalent ZenRows discovery endpoint. The two streams
will coexist; the resale table is slated for eventual decommissioning. To make
that decommission a drop-in replacement, this pipeline keeps RE API field
names verbatim in the bronze schema (matching `raw_idealista`'s shape).

Three-pass scrape strategy:

  Pass 1: GET /comprar-empreendimentos/{area}/pagina-{n}.htm   (Universal Scraper)
    Walks paginated discovery pages for each configured target area until an
    empty page is hit. Yields per-card "list-row" dicts (id, url, name,
    min_price, typology summary, cover image, branding flags).

  Pass 2: GET /empreendimento/{development_id}/   (Universal Scraper)
    For every development, fetch its detail page. Extracts og: meta tags,
    h1 status (e.g. "Nova construção concluída"), promoter name, full
    description, and the embedded list of child unit URLs.

  Pass 3: GET realestate.api.zenrows.com/.../properties/{unit_id}?tld=.pt
    For every child unit ID discovered in Pass 2, fetch structured JSON via
    the ZenRows Real Estate API (NOT Universal Scraper). RE API returns
    28-30 rich fields per active PT listing including
    property_condition='newdevelopment' for dev-rooted units. ~5× cheaper
    than Universal Scraper ($0.0015 vs $0.007) and no HTML parsing.

Pass 2 and Pass 3 are pre-fetched in parallel via ThreadPoolExecutor BEFORE
entering the dlt resource generators, then yielded as enriched rows. Module-
level cache so the four resources share one fetch.

LIFECYCLE: do NOT call pipeline.run() twice in the same process without
clearing _payload_cache between calls (Airflow tasks run in fresh processes;
this only matters in test harnesses or backfill scripts).

ZenRows: Pass 1+2 use Universal Scraper with js_render+premium_proxy+
proxy_country=pt — DataDome on idealista.pt rejects anything less. Pass 3
uses RE API with tld=.pt — required to scope to PT listings (without it,
the endpoint resolves to .es and returns deactivated stubs).

SCD2 row versioning is driven by an explicit `row_hash` over a curated column
subset. See pipelines/common/SCD2_RULES.md for the cross-pipeline policy.

Heartbeat sidecars distinguish "stable unchanged dev/unit" from "delisted".
Silver-layer queries should treat as active when:

    last_seen_date >= current_date - 21

The 21-day floor: weekly cadence (7) + one missed run (7) + slack (7).
Do not lower below 14 days.

INACTIVE UNITS: when RE API returns a stub response (≤6 fields — typically
because the unit was deactivated long ago), we skip writing an SCD2 row but
still emit a heartbeat. This avoids phantom SCD2 versions when a unit
oscillates stub→full→stub. Silver detects "currently inactive" via the
21-day heartbeat floor.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Iterable

import dlt
import requests as _requests
from bs4 import BeautifulSoup

from pipelines.api.idealista.idealista_config import (
    ZENROWS_DETAIL_URL,
    ZENROWS_DISCOVERY_URL,
)


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ZenRows endpoints + tuning constants
# ---------------------------------------------------------------------------
ZENROWS_ENDPOINT = "https://api.zenrows.com/v1/"
SITE_BASE = "https://www.idealista.pt"

# Universal Scraper params required for idealista (DataDome). Used for Pass 1+2.
# js_render+premium_proxy puts us in the 25× pricing tier (~$0.007/request).
ZENROWS_PARAMS_BASE: dict[str, str] = {
    "js_render": "true",
    "premium_proxy": "true",
    "proxy_country": "pt",
}

# Discovery: max pages per area before we bail. Idealista shows ~30 cards/page,
# so 50 pages × 30 = 1,500 — safely above any single-distrito expected count.
DISCOVERY_MAX_PAGES = 50
PASS1_DELAY_S = 1.0          # between discovery pages within an area
PASS2_PASS3_MAX_WORKERS = 8  # raised from 4 after Aveiro test showed 0 RE API errors;
                              # halves load_facts runtime. Drop back to 4 if 429s appear.
PASS_PER_WORKER_DELAY_S = 0.5
REQUEST_TIMEOUT_S = 180

# Universal Scraper retry policy (Pass 1+2)
ZENROWS_RETRIES = 3
ZENROWS_BACKOFF_S = 5

# RE API retry policy (Pass 3) — matches legacy idealista_ingestion's tenacity.
RE_API_RETRIES = 3
RE_API_BACKOFF_MIN_S = 5
RE_API_BACKOFF_MAX_S = 60
RE_API_TIMEOUT_S = 60

# Stub detection: RE API returns minimal 4-6 field payloads for deactivated /
# wrong-tld listings. We skip these from the SCD2 table; heartbeat still ticks.
RE_API_STUB_FIELD_THRESHOLD = 6

# ---------------------------------------------------------------------------
# Target geographic areas. Each entry is a list of idealista URL slugs to use
# as discovery roots. All distrito-level via the `-distrito` slug suffix
# verified in the Aveiro feasibility test. Lisbon and Setúbal distritos
# together cover the AML (Área Metropolitana de Lisboa) plus surrounding
# rural concelhos — the over-fetch is small relative to the AML core and
# avoids enumerating the 18 AML concelhos individually.
#
# This is the DEFAULT scope. The DAG can override per-run via the
# `target_areas_override` Param, which threads through `target_areas` arg
# all the way down to `_ensure_payload`. NEVER mutate this dict at runtime.
# ---------------------------------------------------------------------------
TARGET_AREAS: dict[str, list[str]] = {
    "aveiro":   ["aveiro-distrito"],
    "braga":    ["braga-distrito"],
    "coimbra":  ["coimbra-distrito"],
    "leiria":   ["leiria-distrito"],
    "lisboa":   ["lisboa-distrito"],
    "porto":    ["porto-distrito"],
    "setubal":  ["setubal-distrito"],
}


# ---------------------------------------------------------------------------
# Schema contract
#   data_type=freeze  → type drift fails the load loudly
#   columns=evolve    → new columns land silently as NULL; staging must update
# ---------------------------------------------------------------------------
SCHEMA_CONTRACT = {"data_type": "freeze", "columns": "evolve"}


# ---------------------------------------------------------------------------
# Version-relevant columns for SCD2 row_hash. See pipelines/common/SCD2_RULES.md
# for the cross-pipeline include/exclude policy.
# ---------------------------------------------------------------------------
DEVELOPMENTS_VERSION_COLUMNS: tuple[str, ...] = (
    "min_price_text",
    "units_count",
    "is_completed",
    "typology_summary",
    "online_booking",
)

# RE API verbatim names — see _normalize_unit. Includes lifecycle fields
# (last_deactivated_at, status, operation) so a unit going inactive opens a
# new SCD2 version when it's still returning a full payload (stubs are
# skipped from SCD2 entirely; see RE_API_STUB_FIELD_THRESHOLD).
# ---------------------------------------------------------------------------
# Plots — sourced via RE API (NOT Universal Scraper). Single grain — no
# developments↔units 1:N relationship for plots.
#   Pass 1: RE API discovery against /comprar-terrenos/{distrito}/ → list of
#           plot stubs (property_id, property_url, property_type='land',
#           property_price, etc. — ~20 per page).
#   Pass 2: RE API detail per property_id with tld=.pt → 28-30 rich fields
#           including lot_size, lot_size_usable, address, lat/long, etc.
#
# Cost: $0.0015/call × (~30 discovery pages + ~3000 plot details) ≈ $5/run.
# ---------------------------------------------------------------------------
PLOT_DISCOVERY_URL_TEMPLATE = "https://www.idealista.pt/comprar-terrenos/{slug}/"
PLOT_DISCOVERY_MAX_PAGES = 50

PLOTS_VERSION_COLUMNS: tuple[str, ...] = (
    "property_price",
    "property_subtype",
    "lot_size",
    "lot_size_usable",
    "status",
    "last_deactivated_at",
    "operation",
    "agency_name",
)
PLOTS_JSON_COLUMNS = (
    "property_features",
    "property_equipment",
    "property_images",
    "property_image_tags",
    "location_hierarchy",
    "raw_meta",
)


UNITS_VERSION_COLUMNS: tuple[str, ...] = (
    "property_price",
    "property_subtype",
    "bedroom_count",
    "bathroom_count",
    "lot_size",
    "lot_size_usable",
    "floor",
    "energy_certificate",
    "status",
    "last_deactivated_at",
    "operation",
    "agency_name",
)


# ---------------------------------------------------------------------------
# JSON columns to keep as `json` data_type, NOT auto-flatten into child tables.
# Addresses dlt issue #3811 (nested-table nondeterminism on schema evolution).
# ---------------------------------------------------------------------------
DEVELOPMENTS_JSON_COLUMNS = ("gallery", "unit_links", "raw_meta")
UNITS_JSON_COLUMNS = (
    "property_features",
    "property_equipment",
    "property_images",
    "property_image_tags",
    "location_hierarchy",
    "raw_meta",
)


# ---------------------------------------------------------------------------
# Hashing — canonicalize numerics so int↔float drift does not create spurious
# SCD2 versions. Whitelist scalar types so a non-scalar slipping into
# version_cols fails loudly instead of being str()-stringified.
#
# Kept in sync with zome/remax intentionally — see pipelines/common/SCD2_RULES.md
# for the conventions; the helpers below are duplicated across pipelines by
# design (small surface, zero shared deps preferred over an abstraction with
# one consumer migrated and others lagging).
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
# Counters surfaced to the DAG validation step (see idealista_dlt.py).
# Incremented by Pass 3 workers; reset in _ensure_payload.
# ---------------------------------------------------------------------------
_re_api_error_count = 0  # non-200/non-404 RE API responses across all retries
_stub_count = 0          # units whose RE API payload was a stub (skipped from SCD2)


# ---------------------------------------------------------------------------
# Universal Scraper HTTP wrapper with retry. Pre-flight rejections (REQS002)
# are free under pay-per-success; retried failures don't burn credits either.
# ---------------------------------------------------------------------------
def _zenrows_get(url: str, wait_for: str | None = None) -> str | None:
    """Fetch a target URL through ZenRows Universal Scraper. Returns HTML or None.

    `wait_for` is a CSS selector — when set, ZenRows waits for it to appear
    before snapshotting the rendered DOM. Critical for idealista: without it,
    ZenRows occasionally returns a 12 KB JS shell with no listing cards
    (intermittent — happens maybe 1 in 5 calls). Use the most-specific
    selector you'd extract from in the parser:
      Pass 1 (discovery): wait_for='article.item'
      Pass 2 (dev detail): wait_for='h1' (every dev page has one)
    """
    api_key = os.environ.get("ZENROWS_API_KEY", "")
    if not api_key:
        raise RuntimeError("ZENROWS_API_KEY not set in environment")

    params: dict[str, str] = {"apikey": api_key, "url": url, **ZENROWS_PARAMS_BASE}
    if wait_for:
        params["wait_for"] = wait_for
    last_err: Exception | None = None
    for attempt in range(1, ZENROWS_RETRIES + 1):
        try:
            r = _requests.get(ZENROWS_ENDPOINT, params=params, timeout=REQUEST_TIMEOUT_S)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                log.warning("[idealista_dev] 404 from origin for %s", url)
                return None
            last_err = RuntimeError(f"ZenRows HTTP {r.status_code}: {r.text[:200]}")
        except Exception as exc:
            last_err = exc
        if attempt < ZENROWS_RETRIES:
            time.sleep(ZENROWS_BACKOFF_S * attempt)

    log.warning("[idealista_dev] giving up on %s after %d tries: %s",
                url, ZENROWS_RETRIES, last_err)
    return None


# ---------------------------------------------------------------------------
# RE API HTTP wrapper with retry (Pass 3). Mirrors the legacy idealista
# pipeline's tenacity setup (max_retries=3, exponential backoff 5..60s) but
# uses a manual loop to keep this file dependency-free of tenacity, matching
# _zenrows_get's style.
# ---------------------------------------------------------------------------
def _zenrows_re_api_discovery(target_url: str, page: int) -> dict | list | None:
    """Fetch one page of RE API discovery for a target idealista search URL.
    Used by the plots Pass 1. tld=.pt scopes results to the PT site.
    Returns the parsed JSON (list or {property_list:[...]}) or None on failure.
    """
    global _re_api_error_count
    api_key = os.environ.get("ZENROWS_API_KEY", "")
    if not api_key:
        raise RuntimeError("ZENROWS_API_KEY not set in environment")

    params = {"apikey": api_key, "url": target_url, "page": page, "tld": ".pt"}
    last_err: Exception | None = None
    for attempt in range(1, RE_API_RETRIES + 1):
        try:
            r = _requests.get(ZENROWS_DISCOVERY_URL, params=params, timeout=RE_API_TIMEOUT_S)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
            last_err = RuntimeError(f"RE API discovery HTTP {r.status_code}: {r.text[:200]}")
        except Exception as exc:
            last_err = exc
        if attempt < RE_API_RETRIES:
            backoff = min(RE_API_BACKOFF_MAX_S, RE_API_BACKOFF_MIN_S * (2 ** (attempt - 1)))
            time.sleep(backoff)

    _re_api_error_count += 1
    log.warning("[idealista_plots] RE API discovery giving up on %s page %d after %d tries: %s",
                target_url, page, RE_API_RETRIES, last_err)
    return None


def _zenrows_re_api_get(property_id: str) -> dict | None:
    """Fetch a property via ZenRows Real Estate API with tld=.pt. Returns dict or None.

    Increments module-level `_re_api_error_count` for any non-200/non-404
    response (after retries exhausted) so the DAG validation can gate on
    a runaway error rate.
    """
    global _re_api_error_count

    api_key = os.environ.get("ZENROWS_API_KEY", "")
    if not api_key:
        raise RuntimeError("ZENROWS_API_KEY not set in environment")

    url = ZENROWS_DETAIL_URL.format(property_id=property_id)
    params = {"apikey": api_key, "tld": ".pt"}
    last_err: Exception | None = None
    for attempt in range(1, RE_API_RETRIES + 1):
        try:
            r = _requests.get(url, params=params, timeout=RE_API_TIMEOUT_S)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                # 404 = property doesn't exist in RE API namespace; do NOT retry.
                return None
            last_err = RuntimeError(f"RE API HTTP {r.status_code}: {r.text[:200]}")
        except Exception as exc:
            last_err = exc
        if attempt < RE_API_RETRIES:
            backoff = min(RE_API_BACKOFF_MAX_S, RE_API_BACKOFF_MIN_S * (2 ** (attempt - 1)))
            time.sleep(backoff)

    _re_api_error_count += 1
    log.warning("[idealista_dev] RE API giving up on property_id=%s after %d tries: %s",
                property_id, RE_API_RETRIES, last_err)
    return None


# ---------------------------------------------------------------------------
# Pass 1 — discovery pagination (Universal Scraper)
# ---------------------------------------------------------------------------
_PRICE_RE = re.compile(r"([\d\.\s]+)\s*€")


def _build_discovery_url(slug: str, page: int) -> str:
    base = f"{SITE_BASE}/comprar-empreendimentos/{slug}/"
    if page <= 1:
        return base
    # Idealista empreendimentos pagination URL pattern (verified by inspecting
    # the rendered page-1 HTML pagination block). NOT `pagina-N.htm` — that's
    # the listings-side convention and 404s/hangs here.
    return f"{base}pagina-{page}"


def _parse_discovery_card(art) -> dict | None:
    """Extract one development list-row dict from an <article class='item'> node."""
    dev_id = art.get("data-element-id")
    if not dev_id:
        return None

    link = art.select_one("a.item-link")
    rel_url = link.get("href") if link else None
    name = link.get_text(" ", strip=True) if link else None

    price_el = art.select_one(".item-price")
    price_text = price_el.get_text(" ", strip=True) if price_el else None
    price_label_el = art.select_one(".price-row")
    price_label = price_label_el.get_text(" ", strip=True) if price_label_el else None

    typology_el = art.select_one(".item-detail-char .item-detail")
    typology_summary = typology_el.get_text(" ", strip=True) if typology_el else None

    desc_el = art.select_one(".item-description p.ellipsis")
    description_summary = desc_el.get_text(" ", strip=True) if desc_el else None

    img = art.select_one("img")
    cover_image = (img.get("src") or img.get("data-src")) if img else None

    classes = art.get("class") or []
    is_featured = "item_hightop" in classes
    is_branded = "item_contains_branding" in classes
    online_booking = (art.get("data-online-booking") == "true")

    min_price = None
    if price_text:
        m = _PRICE_RE.search(price_text)
        if m:
            try:
                min_price = float(m.group(1).replace(".", "").replace(" ", "").replace(",", "."))
            except ValueError:
                min_price = None

    return {
        "development_id": str(dev_id),
        "development_url": (SITE_BASE + rel_url) if rel_url and rel_url.startswith("/") else rel_url,
        "name": name,
        "min_price": min_price,
        "min_price_text": price_text,
        "min_price_label": price_label,
        "typology_summary": typology_summary,
        "description_summary": description_summary,
        "cover_image": cover_image,
        "is_featured": is_featured,
        "is_branded": is_branded,
        "online_booking": online_booking,
    }


def _fetch_discovery_for_area(area_key: str, slug: str) -> list[dict]:
    """Walk paginated discovery for one slug. Returns list of card dicts."""
    rows: list[dict] = []
    seen_ids: set[str] = set()

    for page in range(1, DISCOVERY_MAX_PAGES + 1):
        url = _build_discovery_url(slug, page)
        html = _zenrows_get(url, wait_for="article.item")
        if html is None:
            break  # 404 or hard failure → assume end of pagination

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("article.item")
        if not cards:
            break

        page_added = 0
        for art in cards:
            row = _parse_discovery_card(art)
            if not row or row["development_id"] in seen_ids:
                continue
            seen_ids.add(row["development_id"])
            row["area_key"] = area_key
            row["area_slug"] = slug
            rows.append(row)
            page_added += 1

        log.info("[idealista_dev] Pass 1 %s page %d → %d cards (cumulative %d)",
                 slug, page, page_added, len(rows))
        if page_added == 0:
            break
        time.sleep(PASS1_DELAY_S)

    return rows


# ---------------------------------------------------------------------------
# Pass 2 — development detail page parsing (Universal Scraper)
# ---------------------------------------------------------------------------
_UNIT_HREF_RE = re.compile(r"/empreendimento/(\d+)/imovel/(\d+)/")


def _parse_development_detail(html: str) -> dict:
    """Extract structured fields + child unit links from a /empreendimento/{id}/ page."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, Any] = {}

    out["title"] = soup.title.string.strip() if soup.title and soup.title.string else None
    h1 = soup.find("h1")
    out["h1"] = h1.get_text(" ", strip=True) if h1 else None
    out["is_completed"] = bool(out["h1"] and "concluíd" in out["h1"].lower())

    for prop in ("og:title", "og:description", "og:image"):
        m = soup.find("meta", property=prop)
        out[prop.replace(":", "_")] = m.get("content") if m else None

    prom_el = (soup.select_one(".professional-name")
               or soup.select_one(".advertiser-name")
               or soup.select_one("[class*='advertiser']"))
    out["promoter_name"] = prom_el.get_text(" ", strip=True) if prom_el else None

    desc_el = soup.select_one(".comment, .item-description, [class*='description']")
    out["description_full"] = desc_el.get_text(" ", strip=True) if desc_el else None

    addr_el = soup.select_one(".main-info__title-minor, .ide-detail-address")
    out["address_text"] = addr_el.get_text(" ", strip=True) if addr_el else None

    gallery: list[str] = []
    seen: set[str] = set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src and "idealista" in src and src not in seen:
            seen.add(src)
            gallery.append(src)
    out["gallery"] = gallery

    unit_links: list[dict] = []
    seen_units: set[str] = set()
    for a in soup.find_all("a", href=True):
        m = _UNIT_HREF_RE.search(a["href"])
        if not m:
            continue
        dev_id, unit_id = m.group(1), m.group(2)
        if unit_id in seen_units:
            continue
        seen_units.add(unit_id)
        unit_links.append({
            "development_id": dev_id,
            "unit_id": unit_id,
            "unit_url": SITE_BASE + a["href"],
            "summary": a.get_text(" ", strip=True)[:300] or None,
        })
    out["unit_links"] = unit_links
    out["units_count"] = len(unit_links)
    return out


def _fetch_one_dev_detail(dev_id: str) -> dict:
    """Pass 2 worker. Returns enriched fields or {}."""
    url = f"{SITE_BASE}/empreendimento/{dev_id}/"
    try:
        html = _zenrows_get(url, wait_for="h1")
        if html is None:
            return {}
        return _parse_development_detail(html)
    except Exception as exc:
        log.warning("[idealista_dev] Pass 2 failed for dev=%s: %s", dev_id, exc)
        return {}
    finally:
        time.sleep(PASS_PER_WORKER_DELAY_S)


# ---------------------------------------------------------------------------
# Pass 3 — unit detail via RE API (replaces the previous Universal Scraper
# HTML-parsing path). Returns the RE API JSON dict directly with one surgical
# rename (drop redundant `bedrooms_count` — RE API exposes both
# `bedroom_count` and `bedrooms_count` for the same concept).
# ---------------------------------------------------------------------------
def _parse_unit_detail_re(payload: dict) -> dict:
    """Verbatim pass-through of RE API JSON, with stub detection and JSON-col defaults.

    Stub responses (≤6 fields, or missing all of property_price/address/
    property_features) signal a deactivated/wrong-tld listing — we mark them
    so the SCD2 resource skips writing a row. The heartbeat sidecar still
    ticks so silver can detect "re-listed after deactivation" via the 21-day
    floor.
    """
    if not isinstance(payload, dict):
        return {"_re_api_stub": True}

    is_stub = (
        len(payload) <= RE_API_STUB_FIELD_THRESHOLD
        or (
            payload.get("property_price") is None
            and payload.get("address") is None
            and not payload.get("property_features")
        )
    )
    if is_stub:
        return {"_re_api_stub": True}

    out = dict(payload)
    out.pop("bedrooms_count", None)  # surgical: keep `bedroom_count`, drop redundant duplicate

    # Coerce JSONB list/dict columns to defaults so dlt schema stays well-typed.
    for k in ("property_features", "property_equipment", "property_images",
              "property_image_tags", "location_hierarchy"):
        if k in out and out[k] is None:
            out[k] = [] if k != "location_hierarchy" else {}
    return out


def _fetch_one_unit_detail(unit: dict) -> dict:
    """Pass 3 worker. Returns RE API enrichment dict, {'_re_api_stub': True}, or {}."""
    try:
        payload = _zenrows_re_api_get(unit["unit_id"])
        if payload is None:
            return {}
        return _parse_unit_detail_re(payload)
    except Exception as exc:
        log.warning("[idealista_dev] Pass 3 failed for unit=%s: %s",
                    unit.get("unit_id"), exc)
        return {}
    finally:
        time.sleep(PASS_PER_WORKER_DELAY_S)


# ---------------------------------------------------------------------------
# Orchestration — Pass 1 → Pass 2 (parallel) → Pass 3 (parallel). Module-level
# cache so the four resources share a single fetch within a dlt load.
# ---------------------------------------------------------------------------
_payload_cache: dict[str, Any] = {}


def _ensure_payload(target_areas: dict | None = None) -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    """Returns (dev_rows, dev_details_by_id, unit_details_by_id).

    Populates the module-level cache on first call. Subsequent calls (from
    other resources within the same dlt load) return the cached payload.

    target_areas is honored only on the first call; subsequent calls return
    the cached payload regardless. Pass it via the source factory:
        idealista_developments_facts_source(target_areas={"aveiro": ["aveiro-distrito"]})
    """
    global _re_api_error_count, _stub_count

    if "devs" in _payload_cache:
        return _payload_cache["devs"], _payload_cache["dev_details"], _payload_cache["unit_details"]

    # Reset counters for this load.
    _re_api_error_count = 0
    _stub_count = 0

    areas = target_areas if target_areas is not None else TARGET_AREAS

    # ----- Pass 1 -----
    all_rows: list[dict] = []
    seen_global: set[str] = set()
    for area_key, slugs in areas.items():
        for slug in slugs:
            rows = _fetch_discovery_for_area(area_key, slug)
            for r in rows:
                if r["development_id"] in seen_global:
                    continue  # same dev surfaced from multiple areas; keep first
                seen_global.add(r["development_id"])
                all_rows.append(r)
    log.info("[idealista_dev] Pass 1 complete: %d unique developments across %d areas",
             len(all_rows), len(areas))

    # ----- Pass 2 (parallel) -----
    dev_details: dict[str, dict] = {}
    if all_rows:
        log.info("[idealista_dev] Pass 2 starting: %d dev detail pages, max_workers=%d",
                 len(all_rows), PASS2_PASS3_MAX_WORKERS)
        with ThreadPoolExecutor(max_workers=PASS2_PASS3_MAX_WORKERS) as ex:
            futures = {ex.submit(_fetch_one_dev_detail, r["development_id"]): r["development_id"]
                       for r in all_rows}
            done = 0
            for fut in as_completed(futures):
                dev_id = futures[fut]
                try:
                    dev_details[dev_id] = fut.result() or {}
                except Exception as exc:
                    log.warning("[idealista_dev] Pass 2 future failed for %s: %s", dev_id, exc)
                    dev_details[dev_id] = {}
                done += 1
                if done % 50 == 0:
                    log.info("[idealista_dev] Pass 2 progress: %d/%d", done, len(all_rows))

    # ----- Pass 3 (parallel) — RE API -----
    all_units: list[dict] = []
    for r in all_rows:
        for u in (dev_details.get(r["development_id"], {}).get("unit_links") or []):
            all_units.append(u)
    unit_details: dict[str, dict] = {}
    if all_units:
        log.info("[idealista_dev] Pass 3 starting (RE API): %d unit detail fetches, max_workers=%d",
                 len(all_units), PASS2_PASS3_MAX_WORKERS)
        with ThreadPoolExecutor(max_workers=PASS2_PASS3_MAX_WORKERS) as ex:
            futures = {ex.submit(_fetch_one_unit_detail, u): u["unit_id"] for u in all_units}
            done = 0
            for fut in as_completed(futures):
                unit_id = futures[fut]
                try:
                    result = fut.result() or {}
                except Exception as exc:
                    log.warning("[idealista_dev] Pass 3 future failed for %s: %s", unit_id, exc)
                    result = {}
                unit_details[unit_id] = result
                if result.get("_re_api_stub"):
                    _stub_count += 1
                done += 1
                if done % 100 == 0:
                    log.info("[idealista_dev] Pass 3 progress: %d/%d", done, len(all_units))

    enriched_d = sum(1 for v in dev_details.values() if v)
    enriched_u = sum(1 for v in unit_details.values()
                     if v and not v.get("_re_api_stub"))
    log.info(
        "[idealista_dev] Payload ready: %d devs (%d enriched), %d units "
        "(%d enriched, %d stubs, %d RE API errors)",
        len(all_rows), enriched_d, len(all_units), enriched_u,
        _stub_count, _re_api_error_count,
    )

    _payload_cache["devs"] = all_rows
    _payload_cache["dev_details"] = dev_details
    _payload_cache["unit_details"] = unit_details
    _payload_cache["pass3_total"] = len(all_units)
    _payload_cache["pass3_stubs"] = _stub_count
    _payload_cache["pass3_errors"] = _re_api_error_count
    return all_rows, dev_details, unit_details


def get_pass3_counters() -> dict[str, int]:
    """Expose Pass 3 metrics to the DAG validation step. Reads cached values
    populated during _ensure_payload (so calling this without a prior load
    returns zeros — caller should run the source first)."""
    return {
        "total": _payload_cache.get("pass3_total", 0),
        "stubs": _payload_cache.get("pass3_stubs", 0),
        "errors": _payload_cache.get("pass3_errors", 0),
    }


# ---------------------------------------------------------------------------
# Normalization — flatten Pass 1 + Pass 2 + Pass 3 into canonical bronze rows.
# Unit fields use RE API names verbatim (matches the legacy raw_idealista
# table for migration-friendly drop-in replacement).
# ---------------------------------------------------------------------------
def _normalize_development(card: dict, detail: dict) -> dict:
    return {
        "development_id": card["development_id"],
        "development_url": card.get("development_url"),
        "name": card.get("name"),
        "area_key": card.get("area_key"),
        "area_slug": card.get("area_slug"),
        "min_price": card.get("min_price"),
        "min_price_text": card.get("min_price_text"),
        "min_price_label": card.get("min_price_label"),
        "typology_summary": card.get("typology_summary"),
        "description_summary": card.get("description_summary"),
        "cover_image": card.get("cover_image"),
        "is_featured": bool(card.get("is_featured")),
        "is_branded": bool(card.get("is_branded")),
        "online_booking": bool(card.get("online_booking")),
        # Pass 2 enrichment
        "title": detail.get("title"),
        "h1": detail.get("h1"),
        "is_completed": bool(detail.get("is_completed")),
        "og_title": detail.get("og_title"),
        "og_description": detail.get("og_description"),
        "og_image": detail.get("og_image"),
        "promoter_name": detail.get("promoter_name"),
        "description_full": detail.get("description_full"),
        "address_text": detail.get("address_text"),
        "gallery": detail.get("gallery") or [],
        "unit_links": detail.get("unit_links") or [],
        "units_count": detail.get("units_count") or 0,
        "_has_detail": bool(detail),
        "raw_meta": {"card": card, "detail_keys": sorted(detail.keys()) if detail else []},
    }


def _normalize_unit(unit_link: dict, detail: dict) -> dict:
    """RE API verbatim names + identity columns from Pass 2.

    Caller must NOT pass a stub detail (`_re_api_stub=True`) here; stubs are
    skipped at the resource level so this function only sees full payloads
    or empty dicts (for fetch failures).
    """
    return {
        # Identity (our convention)
        "unit_id": unit_link["unit_id"],
        "development_id": unit_link["development_id"],
        "unit_url": unit_link.get("unit_url"),
        "summary_from_dev_page": unit_link.get("summary"),
        # RE API verbatim — all fields below mirror raw_idealista's shape
        "property_id": detail.get("property_id"),
        "property_url": detail.get("property_url"),
        "property_type": detail.get("property_type"),
        "property_subtype": detail.get("property_subtype"),
        "property_price": detail.get("property_price"),
        "price_currency_symbol": detail.get("price_currency_symbol"),
        "lot_size": detail.get("lot_size"),
        "lot_size_usable": detail.get("lot_size_usable"),
        "property_dimensions": detail.get("property_dimensions"),
        "bedroom_count": detail.get("bedroom_count"),
        # bedrooms_count (redundant duplicate) intentionally dropped in _parse_unit_detail_re
        "bathroom_count": detail.get("bathroom_count"),
        "floor": detail.get("floor"),
        "floor_description": detail.get("floor_description"),
        "property_features": detail.get("property_features") or [],
        "property_equipment": detail.get("property_equipment") or [],
        "property_images": detail.get("property_images") or [],
        "property_image_tags": detail.get("property_image_tags") or [],
        "property_condition": detail.get("property_condition"),
        "property_description": detail.get("property_description"),
        "property_title": detail.get("property_title"),
        "energy_certificate": detail.get("energy_certificate"),
        "address": detail.get("address"),
        "location_name": detail.get("location_name"),
        "location_hierarchy": detail.get("location_hierarchy") or {},
        "latitude": detail.get("latitude"),
        "longitude": detail.get("longitude"),
        "country": detail.get("country"),
        "agency_name": detail.get("agency_name"),
        "agency_phone": detail.get("agency_phone"),
        "agency_logo": detail.get("agency_logo"),
        "modified_at": detail.get("modified_at"),
        "status": detail.get("status"),
        "last_deactivated_at": detail.get("last_deactivated_at"),
        "operation": detail.get("operation"),
        # dlt structural
        "_has_detail": bool(detail),
        "raw_meta": {
            "unit_link": unit_link,
            "re_api_keys": sorted(detail.keys()) if detail else [],
        },
    }


# ===========================================================================
# Source: Facts (SCD2 + sidecars). Failure here blocks bronze refresh.
# Accepts target_areas to allow per-run scope overrides (e.g. the Aveiro test
# from the DAG); when None, falls back to the module-level TARGET_AREAS.
# ===========================================================================
@dlt.source(name="idealista_developments_facts")
def idealista_developments_facts_source(target_areas: dict | None = None) -> Iterable[Any]:
    # Eagerly populate the cache with the chosen scope BEFORE yielding resources.
    # Each resource then reads from the cache via _ensure_payload() with no args.
    _ensure_payload(target_areas)
    yield developments
    yield developments_state
    yield development_units
    yield development_units_state


@dlt.resource(
    name="idealista_developments",
    write_disposition={
        "disposition": "merge",
        "strategy": "scd2",
        "row_version_column_name": "row_hash",
    },
    primary_key="development_id",
    columns={
        **{col: {"data_type": "json"} for col in DEVELOPMENTS_JSON_COLUMNS},
        "min_price": {"data_type": "decimal"},
    },
    schema_contract=SCHEMA_CONTRACT,
)
def developments() -> Iterable[dict]:
    rows, dev_details, _units = _ensure_payload()
    for card in rows:
        rec = _normalize_development(card, dev_details.get(card["development_id"], {}))
        rec["row_hash"] = _stable_hash(rec, DEVELOPMENTS_VERSION_COLUMNS)
        yield rec


@dlt.resource(
    name="idealista_developments_state",
    write_disposition="merge",
    primary_key="development_id",
)
def developments_state() -> Iterable[dict]:
    rows, _devd, _units = _ensure_payload()
    today = date.today()
    for card in rows:
        yield {
            "development_id": card["development_id"],
            "last_seen_date": today,
        }


@dlt.resource(
    name="idealista_development_units",
    write_disposition={
        "disposition": "merge",
        "strategy": "scd2",
        "row_version_column_name": "row_hash",
    },
    primary_key="unit_id",
    columns={
        **{col: {"data_type": "json"} for col in UNITS_JSON_COLUMNS},
        "property_price": {"data_type": "decimal"},
        "latitude": {"data_type": "decimal"},
        "longitude": {"data_type": "decimal"},
        "lot_size": {"data_type": "decimal"},
        "lot_size_usable": {"data_type": "decimal"},
        "bedroom_count": {"data_type": "bigint"},
        "bathroom_count": {"data_type": "bigint"},
        "modified_at": {"data_type": "bigint"},
        "last_deactivated_at": {"data_type": "bigint"},
    },
    schema_contract=SCHEMA_CONTRACT,
)
def development_units() -> Iterable[dict]:
    _rows, dev_details, unit_details = _ensure_payload()
    for _dev_id, dev_detail in dev_details.items():
        for unit_link in (dev_detail.get("unit_links") or []):
            detail = unit_details.get(unit_link["unit_id"], {})
            # Skip stubs entirely — heartbeat sidecar still ticks below.
            # Avoids phantom SCD2 versions on stub↔full oscillation.
            if detail.get("_re_api_stub"):
                continue
            rec = _normalize_unit(unit_link, detail)
            rec["row_hash"] = _stable_hash(rec, UNITS_VERSION_COLUMNS)
            yield rec


@dlt.resource(
    name="idealista_development_units_state",
    write_disposition="merge",
    primary_key="unit_id",
)
def development_units_state() -> Iterable[dict]:
    """Heartbeat sidecar — emitted for EVERY unit_link discovered in Pass 2,
    including stubs that were skipped from the SCD2 table. This is the
    contract that lets silver detect "unit re-listed after deactivation"
    via the 21-day floor."""
    _rows, dev_details, _unit_details = _ensure_payload()
    today = date.today()
    for _dev_id, dev_detail in dev_details.items():
        for unit_link in (dev_detail.get("unit_links") or []):
            yield {
                "unit_id": unit_link["unit_id"],
                "last_seen_date": today,
            }


# ===========================================================================
# Plots — separate facts source. Independent of the developments+units load
# (different cache, different orchestration). Uses RE API for both passes.
# ===========================================================================
_plots_cache: dict[str, Any] = {}


def _fetch_plot_discovery(area_slug: str) -> list[dict]:
    """Pass 1 for plots: paginate RE API discovery for /comprar-terrenos/{slug}/."""
    target_url = PLOT_DISCOVERY_URL_TEMPLATE.format(slug=area_slug)
    rows: list[dict] = []
    seen_ids: set[str] = set()
    for page in range(1, PLOT_DISCOVERY_MAX_PAGES + 1):
        data = _zenrows_re_api_discovery(target_url, page)
        if data is None:
            break
        items = data if isinstance(data, list) else (
            data.get("property_list") or data.get("data") or []
        )
        if not items:
            break
        page_added = 0
        for it in items:
            pid = str(it.get("property_id") or "")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            it["_area_slug"] = area_slug
            rows.append(it)
            page_added += 1
        log.info("[idealista_plots] Pass 1 %s page %d → %d items (cumulative %d)",
                 area_slug, page, page_added, len(rows))
        if page_added == 0:
            break
        time.sleep(PASS1_DELAY_S)
    return rows


def _ensure_plots_payload(target_areas: dict | None = None) -> tuple[list[dict], dict[str, dict]]:
    """Returns (plot_stubs_from_discovery, plot_details_by_id).

    Populates _plots_cache on first call. target_areas honored only on first call.
    """
    global _re_api_error_count, _stub_count
    if "stubs" in _plots_cache:
        return _plots_cache["stubs"], _plots_cache["details"]

    areas = target_areas if target_areas is not None else TARGET_AREAS

    # Pass 1: discovery per area
    all_stubs: list[dict] = []
    seen_global: set[str] = set()
    for area_key, slugs in areas.items():
        for slug in slugs:
            for it in _fetch_plot_discovery(slug):
                pid = str(it.get("property_id") or "")
                if not pid or pid in seen_global:
                    continue
                seen_global.add(pid)
                it["_area_key"] = area_key
                all_stubs.append(it)
    log.info("[idealista_plots] Pass 1 complete: %d unique plots across %d areas",
             len(all_stubs), len(areas))

    # Pass 2: detail per plot via RE API (parallel)
    details: dict[str, dict] = {}
    plot_stub_count = 0
    if all_stubs:
        log.info("[idealista_plots] Pass 2 starting (RE API): %d plot detail fetches, max_workers=%d",
                 len(all_stubs), PASS2_PASS3_MAX_WORKERS)
        with ThreadPoolExecutor(max_workers=PASS2_PASS3_MAX_WORKERS) as ex:
            futures = {ex.submit(_zenrows_re_api_get, str(s["property_id"])): str(s["property_id"])
                       for s in all_stubs}
            done = 0
            for fut in as_completed(futures):
                pid = futures[fut]
                try:
                    payload = fut.result()
                except Exception as exc:
                    log.warning("[idealista_plots] Pass 2 future failed for %s: %s", pid, exc)
                    payload = None
                if payload is None:
                    details[pid] = {}
                else:
                    parsed = _parse_unit_detail_re(payload)
                    if parsed.get("_re_api_stub"):
                        plot_stub_count += 1
                        details[pid] = {"_re_api_stub": True}
                    else:
                        details[pid] = parsed
                done += 1
                if done % 200 == 0:
                    log.info("[idealista_plots] Pass 2 progress: %d/%d", done, len(all_stubs))

    enriched = sum(1 for v in details.values() if v and not v.get("_re_api_stub"))
    log.info(
        "[idealista_plots] Plots payload ready: %d stubs (%d enriched, %d RE-API-stubs)",
        len(all_stubs), enriched, plot_stub_count,
    )
    _plots_cache["stubs"] = all_stubs
    _plots_cache["details"] = details
    _plots_cache["pass2_total"] = len(all_stubs)
    _plots_cache["pass2_stubs"] = plot_stub_count
    return all_stubs, details


def _normalize_plot(stub: dict, detail: dict) -> dict:
    """RE API verbatim names + identity from Pass 1 stub. Caller must NOT pass
    a stub-flagged detail (`_re_api_stub=True`) here; stubs are skipped at the
    resource level."""
    return {
        # Identity
        "external_listing_id": str(stub.get("property_id")),
        "area_key": stub.get("_area_key"),
        "area_slug": stub.get("_area_slug"),
        "discovery_url": stub.get("property_url"),
        # RE API verbatim — same shape as raw_idealista
        "property_id": detail.get("property_id"),
        "property_url": detail.get("property_url"),
        "property_type": detail.get("property_type"),
        "property_subtype": detail.get("property_subtype"),
        "property_price": detail.get("property_price"),
        "price_currency_symbol": detail.get("price_currency_symbol"),
        "lot_size": detail.get("lot_size"),
        "lot_size_usable": detail.get("lot_size_usable"),
        "property_dimensions": detail.get("property_dimensions"),
        "property_features": detail.get("property_features") or [],
        "property_equipment": detail.get("property_equipment") or [],
        "property_images": detail.get("property_images") or [],
        "property_image_tags": detail.get("property_image_tags") or [],
        "property_condition": detail.get("property_condition"),
        "property_description": detail.get("property_description"),
        "property_title": detail.get("property_title"),
        "energy_certificate": detail.get("energy_certificate"),
        "address": detail.get("address"),
        "location_name": detail.get("location_name"),
        "location_hierarchy": detail.get("location_hierarchy") or {},
        "latitude": detail.get("latitude"),
        "longitude": detail.get("longitude"),
        "country": detail.get("country"),
        "agency_name": detail.get("agency_name"),
        "agency_phone": detail.get("agency_phone"),
        "agency_logo": detail.get("agency_logo"),
        "modified_at": detail.get("modified_at"),
        "status": detail.get("status"),
        "last_deactivated_at": detail.get("last_deactivated_at"),
        "operation": detail.get("operation"),
        "_has_detail": bool(detail),
        "raw_meta": {"discovery_stub": stub, "re_api_keys": sorted(detail.keys()) if detail else []},
    }


@dlt.source(name="idealista_plots_facts")
def idealista_plots_facts_source(target_areas: dict | None = None) -> Iterable[Any]:
    _ensure_plots_payload(target_areas)
    yield plots
    yield plots_state


@dlt.resource(
    name="idealista_plots",
    write_disposition={
        "disposition": "merge",
        "strategy": "scd2",
        "row_version_column_name": "row_hash",
    },
    primary_key="external_listing_id",
    columns={
        **{col: {"data_type": "json"} for col in PLOTS_JSON_COLUMNS},
        "property_price": {"data_type": "decimal"},
        "latitude": {"data_type": "decimal"},
        "longitude": {"data_type": "decimal"},
        "lot_size": {"data_type": "decimal"},
        "lot_size_usable": {"data_type": "decimal"},
        "modified_at": {"data_type": "bigint"},
        "last_deactivated_at": {"data_type": "bigint"},
    },
    schema_contract=SCHEMA_CONTRACT,
)
def plots() -> Iterable[dict]:
    stubs, details = _ensure_plots_payload()
    for stub in stubs:
        pid = str(stub.get("property_id"))
        detail = details.get(pid, {})
        if detail.get("_re_api_stub"):
            continue  # skip SCD2 row; heartbeat below still ticks
        rec = _normalize_plot(stub, detail)
        rec["row_hash"] = _stable_hash(rec, PLOTS_VERSION_COLUMNS)
        yield rec


@dlt.resource(
    name="idealista_plots_state",
    write_disposition="merge",
    primary_key="external_listing_id",
)
def plots_state() -> Iterable[dict]:
    """Heartbeat for every Pass 1 discovery hit, including stubs."""
    stubs, _details = _ensure_plots_payload()
    today = date.today()
    for stub in stubs:
        yield {
            "external_listing_id": str(stub.get("property_id")),
            "last_seen_date": today,
        }


def get_plots_pass2_counters() -> dict[str, int]:
    """Expose plot Pass 2 metrics to the DAG validation step."""
    return {
        "total": _plots_cache.get("pass2_total", 0),
        "stubs": _plots_cache.get("pass2_stubs", 0),
    }
