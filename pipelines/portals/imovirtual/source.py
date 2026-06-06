"""dlt source for imovirtual PT bronze ingestion (SCD2 + per-entity heartbeat sidecars).

imovirtual runs on the OLX/Adevinta Nexus platform (Next.js + Apollo GraphQL).
We read the server-rendered JSON via the `_next/data` endpoint — NO scraping
vendor. Design + field maps locked in
wiki/decisions/2026-06-05-imovirtual-portal-onboarding.md (verified against the
live API + a DataDome canary on 2026-06-05).

Tables produced in `bronze_listings`:

  imovirtual_developments              SCD2,   primary_key=development_id
  imovirtual_developments_state        UPSERT, primary_key=development_id   (heartbeat)
  imovirtual_development_units         SCD2,   primary_key=unit_id          (FK development_id)
  imovirtual_development_units_state   UPSERT, primary_key=unit_id          (heartbeat)
  imovirtual_plots                     SCD2,   primary_key=listing_id
  imovirtual_plots_state               UPSERT, primary_key=listing_id       (heartbeat)

Two facts sources with DIFFERENT geographic scope (mixed-scope decision):
  - imovirtual_developments_facts_source → developments + units, NATIONAL
  - imovirtual_plots_facts_source        → terreno plots, AVEIRO only

Acquisition shape (no per-unit Pass 3 — the embedded `paginatedUnits` view's
`characteristics` are identical to the full /anuncio/ unit detail, verified):
  Developments: Pass 1 list (36/page) → Pass 2 dev detail (= dev row + its units).
  Plots:        list (36/page) → per-plot /anuncio/ detail (for coords +
                canonical classification, which the list lacks; affordable at
                Aveiro scope ~4.8k).

SCD2 row versioning is driven by an explicit `row_hash` over a curated column
subset — same policy as zome/remax/idealista (wiki/concepts/scd2-row-hash.md).
Heartbeat sidecars answer "is this entity still listed?" — silver treats a row
active when `last_seen_date >= current_date - 21` (per heartbeat-sidecar).

CONFIRM-AT-BUILD (two small unknowns flagged in the decision record):
  1. Unit pagination param for dev-detail pages with >10 listed units
     (`_iter_dev_units` uses `?page=N`; dedup-by-unit_id guards a wrong guess).
  2. Terreno `characteristics.type` enum values (agricultural/urban/rustico …)
     — captured raw; dbt staging maps to a canonical classification.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Iterable
from datetime import date
from typing import Any

import dlt
from dlt.sources.helpers import requests

log = logging.getLogger(__name__)

SITE_BASE = "https://www.imovirtual.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Geographic scope per grain (mixed by design — see the decision record).
DEV_SCOPE = "todo-o-pais"  # developments + units: national
PLOT_SCOPE = "aveiro"  # plots: Aveiro only (per-plot detail affordable here)

SEARCH_PAGE_SIZE = 36  # searchAds itemsPerPage
UNITS_PAGE_SIZE = 10  # paginatedUnits itemsPerPage
RATE_LIMIT_S = 1.0  # ~1 req/s + jitter; DataDome-friendly (canary clean at this rate)
REQUEST_TIMEOUT_S = 30
MAX_SEARCH_PAGES = 2000  # hard backstop (national plots ~1,188 pages)

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', re.DOTALL)


# ---------------------------------------------------------------------------
# Schema contract — same policy as the other portals.
#   data_type=freeze → type drift fails the load loudly
#   columns=evolve   → new columns land silently as NULL; staging must update
# ---------------------------------------------------------------------------
SCHEMA_CONTRACT = {"data_type": "freeze", "columns": "evolve"}


# ---------------------------------------------------------------------------
# SCD2 version columns (scalars only; no JSON, coords, names, descriptions).
# Verified field maps — see the decision record.
# ---------------------------------------------------------------------------
DEVELOPMENTS_VERSION_COLUMNS: tuple[str, ...] = (
    "total_units",
    "listed_units_count",
    "state",
    "price_per_m_from",
    "area_from",
    "area_to",
    "offered_estates_type",
)

UNITS_VERSION_COLUMNS: tuple[str, ...] = (
    "price",
    "price_per_m",
    "area_m",
    "rooms_num",
    "energy_certificate",
    "floor_no",
    "construction_status",
    "market",
)

PLOTS_VERSION_COLUMNS: tuple[str, ...] = (
    "price",
    "price_per_m",
    "area_m",
    "classification",
    "status",
)

# ---------------------------------------------------------------------------
# JSON columns to keep as `json`, NOT auto-flatten into child tables
# (dlt issue #3811 — nested-table nondeterminism on schema evolution).
# ---------------------------------------------------------------------------
DEVELOPMENTS_JSON_COLUMNS = (
    "images",
    "floor_plans",
    "characteristics",
    "target",
    "unit_groups",
    "promoter",
    "raw_json",
)
UNITS_JSON_COLUMNS = ("images", "characteristics", "raw_json")
PLOTS_JSON_COLUMNS = ("images", "characteristics", "raw_json")


# ---------------------------------------------------------------------------
# Hashing — canonicalize numerics so int↔float drift does not create spurious
# SCD2 versions. Whitelist scalars so a non-scalar in version_cols fails loudly.
# Duplicated across pipelines by design — see wiki/concepts/scd2-row-hash.md.
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
# HTTP — direct _next/data JSON. buildId rotates per deploy, so we bootstrap it
# fresh from any page's __NEXT_DATA__ once per process.
# ---------------------------------------------------------------------------
def _headers(json_data: bool = False) -> dict[str, str]:
    h = {"User-Agent": USER_AGENT}
    if json_data:
        h["x-nextjs-data"] = "1"
    return h


_BUILD_ID: str | None = None


def _get_build_id() -> str:
    """Scrape the current Next.js buildId from a known page (cached per process)."""
    global _BUILD_ID
    if _BUILD_ID:
        return _BUILD_ID
    resp = requests.get(
        f"{SITE_BASE}/pt/empreendimento/jc-barrocas-ID1hFvB",
        headers=_headers(),
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    m = _NEXT_DATA_RE.search(resp.text)
    if not m:
        raise RuntimeError("could not extract __NEXT_DATA__ buildId from imovirtual")
    _BUILD_ID = json.loads(m.group(1))["buildId"]
    return _BUILD_ID


_MAX_REQUEST_ATTEMPTS = 4
_RETRY_BACKOFF_S = 5  # 5/10/15s waits — bridges brief connectivity blips


def _next_data(path: str, params: list[tuple[str, str]] | None = None) -> dict:
    """GET /_next/data/{buildId}/{path}.json → pageProps.

    Retries transient network errors with linear backoff (bridges brief
    connectivity blips, e.g. a short host sleep) and refreshes the buildId on a
    404 (it rotates on deploys). Raises only after all attempts are exhausted —
    callers decide whether to skip the item or stop.
    """
    global _BUILD_ID
    last_exc: Exception | None = None
    for attempt in range(_MAX_REQUEST_ATTEMPTS):
        try:
            url = f"{SITE_BASE}/_next/data/{_get_build_id()}{path}.json"
            resp = requests.get(
                url, params=params, headers=_headers(json_data=True), timeout=REQUEST_TIMEOUT_S
            )
            if resp.status_code == 404:  # buildId likely rotated — refresh + retry
                _BUILD_ID = None
                continue
            resp.raise_for_status()
            return resp.json().get("pageProps", {})
        except Exception as exc:  # ConnectionError / Timeout / HTTPError / JSON
            last_exc = exc
            wait = _RETRY_BACKOFF_S * (attempt + 1)
            log.warning(
                "[imovirtual] _next_data attempt %d/%d for %s failed (%s) — retry in %ds",
                attempt + 1,
                _MAX_REQUEST_ATTEMPTS,
                path,
                exc,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(
        f"_next_data exhausted {_MAX_REQUEST_ATTEMPTS} attempts for {path}"
    ) from last_exc


def _search_params(category: str, loc: str, page: int) -> list[tuple[str, str]]:
    """Query params for the catch-all /pt/resultados/[[...searchingCriteria]] route."""
    return [
        ("page", str(page)),
        ("searchingCriteria", "comprar"),
        ("searchingCriteria", category),
        ("searchingCriteria", loc),
    ]


def _iter_search(category: str, loc: str) -> Iterable[dict]:
    """Paginate a searchAds result set (developments or plots), yielding list items.

    Logs each page for progress visibility. On a persistent page-fetch failure
    (after _next_data's retries) it stops pagination gracefully with what it has,
    rather than crashing the whole crawl — the warning shows exactly where.
    """
    path = f"/pt/resultados/comprar/{category}/{loc}"
    page = 1
    while page <= MAX_SEARCH_PAGES:
        try:
            pp = _next_data(path, params=_search_params(category, loc, page))
        except Exception as exc:
            log.warning(
                "[imovirtual] %s/%s: list page %d failed after retries — stopping "
                "pagination here (partial result): %s",
                category,
                loc,
                page,
                exc,
            )
            return
        sa = (pp.get("data") or {}).get("searchAds") or {}
        items = sa.get("items") or []
        if not items:
            return
        total_pages = (sa.get("pagination") or {}).get("totalPages") or page
        log.info(
            "[imovirtual] %s/%s: list page %d/%d (%d items)",
            category,
            loc,
            page,
            total_pages,
            len(items),
        )
        yield from items
        if page >= total_pages:
            return
        page += 1
        time.sleep(RATE_LIMIT_S)


# ---------------------------------------------------------------------------
# Normalization — pivot the Nexus `characteristics` array into columns, lift
# admin geography out of reverseGeocoding, attach raw_json. NO type casts here
# (deferred to dbt staging, per the leaf-name policy in portal-naming-conventions).
# ---------------------------------------------------------------------------
def _pivot_characteristics(chars: list[dict] | None) -> dict[str, Any]:
    return {c["key"]: c.get("value") for c in (chars or []) if "key" in c}


def _admin_from_reverse(location: dict) -> dict[str, Any]:
    out = {"distrito": None, "concelho": None, "parish": None}
    locs = (location.get("reverseGeocoding") or {}).get("locations") or []
    for x in locs:
        level, name = x.get("locationLevel"), x.get("name")
        if level == "district":
            out["distrito"] = name
        elif level == "council":
            out["concelho"] = name
        elif level == "parish":
            out["parish"] = name
    return out


def _coords(location: dict) -> tuple[Any, Any]:
    c = location.get("coordinates") or {}
    lat, lon = c.get("latitude"), c.get("longitude")
    # Units report (0, 0) — treat as "no own pin" (they inherit the development's).
    if not lat and not lon:
        return None, None
    return lat, lon


def _top_info(ad: dict, label: str) -> Any:
    for x in ad.get("topInformation") or []:
        if x.get("label") == label:
            vals = x.get("values") or []
            return vals[0] if vals else None
    return None


def _normalize_development(ad: dict) -> dict:
    """Development row from /pt/empreendimento/{slug} → pageProps.ad."""
    loc = ad.get("location") or {}
    lat, lon = _coords(loc)
    chars = _pivot_characteristics(ad.get("characteristics"))
    target = ad.get("target") or {}
    owner = ad.get("owner") or {}
    pagination = (ad.get("paginatedUnits") or {}).get("pagination") or {}
    rec: dict[str, Any] = {
        "development_id": ad.get("id"),
        "name": ad.get("title"),
        "slug": ad.get("slug"),
        "url": ad.get("url"),
        "status": ad.get("status"),
        "category_type": (ad.get("adCategory") or {}).get("type"),
        "created_at": ad.get("createdAt"),
        "modified_at": ad.get("modifiedAt"),
        "gps_lat": lat,
        "gps_lon": lon,
        "address_text": ((loc.get("address") or {}).get("street") or {}).get("name"),
        # TWO counts (imovirtual's data-quality edge over idealista): the true
        # project total AND the currently-listed subset.
        "total_units": _top_info(ad, "number_of_units_in_project"),
        "listed_units_count": pagination.get("totalResults"),
        # pivoted dev summary stats
        "price_per_m_from": chars.get("price_per_m_from"),
        "area_from": chars.get("area_from"),
        "area_to": chars.get("area_to"),
        "state": chars.get("state"),
        "offered_estates_type": chars.get("offered_estates_type"),
        # promoter (developer)
        "promoter_id": owner.get("id"),
        "promoter_name": owner.get("name"),
        "promoter_type": owner.get("type"),
        # JSON columns
        "images": ad.get("images"),
        "floor_plans": ad.get("floorPlans"),
        "characteristics": ad.get("characteristics"),
        "target": target,
        "unit_groups": ad.get("unitGroups"),
        "promoter": owner,
        "raw_json": ad,
    }
    _ = _admin_from_reverse(loc)
    rec.update(_)
    return rec


def _normalize_unit(item: dict, development_id: Any) -> dict:
    """Unit row from a development's paginatedUnits.items[]. FK minted from parent."""
    chars = _pivot_characteristics(item.get("characteristics"))
    rec: dict[str, Any] = {
        "unit_id": item.get("id"),
        "development_id": development_id,  # FK at parse time
        "unit_url": item.get("url"),
        "title": item.get("title") or None,
        "status": item.get("status") or None,
        "adcategory_type": (item.get("adCategory") or {}).get("type"),
        "created_at": item.get("createdAt"),
        "modified_at": item.get("modifiedAt"),
        # pivoted unit attributes (all present in the embedded view — no Pass 3)
        "price": chars.get("price"),
        "price_per_m": chars.get("price_per_m"),
        "area_m": chars.get("m"),
        "rooms_num": chars.get("rooms_num"),
        "energy_certificate": chars.get("energy_certificate"),
        "floor_no": chars.get("floor_no"),
        "building_floors_num": chars.get("building_floors_num"),
        "building_type": chars.get("building_type"),
        "construction_status": chars.get("construction_status"),
        "market": chars.get("market"),
        "heating": chars.get("heating"),
        "windows_type": chars.get("windows_type"),
        # JSON columns
        "images": item.get("images"),
        "characteristics": item.get("characteristics"),
        "raw_json": item,
    }
    return rec


def _normalize_plot(ad: dict) -> dict:
    """Plot row from a terreno /pt/anuncio/{slug} → pageProps.ad (detail fetch)."""
    loc = ad.get("location") or {}
    lat, lon = _coords(loc)
    chars = _pivot_characteristics(ad.get("characteristics"))
    rec: dict[str, Any] = {
        "listing_id": ad.get("id"),
        "title": ad.get("title"),
        "slug": ad.get("slug"),
        "url": ad.get("url"),
        "status": ad.get("status"),
        "created_at": ad.get("createdAt"),
        "modified_at": ad.get("modifiedAt"),
        "gps_lat": lat,
        "gps_lon": lon,
        "address_text": ((loc.get("address") or {}).get("street") or {}).get("name"),
        # pivoted plot attributes
        "price": chars.get("price"),
        "price_per_m": chars.get("price_per_m"),
        "area_m": chars.get("m"),
        # CONFIRM-AT-BUILD: terreno characteristics.type enum (agricultural/urban/…)
        "classification": chars.get("type"),
        "is_private_owner": (ad.get("owner") or {}).get("type") == "private",
        # JSON columns
        "images": ad.get("images"),
        "characteristics": ad.get("characteristics"),
        "raw_json": ad,
    }
    rec.update(_admin_from_reverse(loc))
    return rec


# ---------------------------------------------------------------------------
# Crawl — eager passes into module caches; the dlt resources are thin readers
# (mirrors idealista's _ensure_payload pattern, payload-cache-lifecycle).
# ---------------------------------------------------------------------------
_DEV_CACHE: dict[str, list[dict]] | None = None
_PLOT_CACHE: list[dict] | None = None


def _iter_dev_units(slug: str, ad: dict) -> Iterable[dict]:
    """Yield raw unit items for a development across all paginatedUnits pages.

    Page 1 arrives inside the dev-detail `ad`. For >10 listed units we fetch
    additional pages. CONFIRM-AT-BUILD: the unit-page param — `?page=N` on the
    empreendimento _next/data is the most likely; dedup-by-id guards a miss.
    """
    pu = ad.get("paginatedUnits") or {}
    seen: set[Any] = set()
    for item in pu.get("items") or []:
        if item.get("id") not in seen:
            seen.add(item.get("id"))
            yield item
    total_pages = (pu.get("pagination") or {}).get("totalPages") or 1
    for page in range(2, total_pages + 1):
        time.sleep(RATE_LIMIT_S)
        pp = _next_data(f"/pt/empreendimento/{slug}", params=[("page", str(page))])
        more = ((pp.get("ad") or {}).get("paginatedUnits") or {}).get("items") or []
        for item in more:
            if item.get("id") not in seen:
                seen.add(item.get("id"))
                yield item


def _ensure_dev_payload() -> dict[str, list[dict]]:
    """Pass 1 (national dev list) → Pass 2 (per-dev detail = dev row + its units)."""
    global _DEV_CACHE
    if _DEV_CACHE is not None:
        return _DEV_CACHE
    dev_rows: list[dict] = []
    unit_rows: list[dict] = []
    for card in _iter_search("empreendimento", DEV_SCOPE):
        slug = card.get("slug")
        if not slug:
            continue
        time.sleep(RATE_LIMIT_S)
        ad = _next_data(f"/pt/empreendimento/{slug}").get("ad") or {}
        if not ad.get("id"):
            continue
        dev_rows.append(_normalize_development(ad))
        for item in _iter_dev_units(slug, ad):
            unit_rows.append(_normalize_unit(item, development_id=ad.get("id")))
    _DEV_CACHE = {"developments": dev_rows, "units": unit_rows}
    return _DEV_CACHE


def _ensure_plot_payload() -> list[dict]:
    """Terreno list (Aveiro) → per-plot /anuncio/ detail (coords + classification)."""
    global _PLOT_CACHE
    if _PLOT_CACHE is not None:
        return _PLOT_CACHE
    rows: list[dict] = []
    seen = skipped = 0
    for card in _iter_search("terreno", PLOT_SCOPE):
        slug = card.get("slug")
        if not slug:
            continue
        seen += 1
        time.sleep(RATE_LIMIT_S)
        try:
            ad = _next_data(f"/pt/anuncio/{slug}").get("ad") or {}
        except Exception as exc:
            # A persistently-failing plot detail must not abort the whole crawl.
            skipped += 1
            log.warning("[imovirtual] plot detail skipped (slug=%s): %s", slug, exc)
            continue
        if ad.get("id"):
            rows.append(_normalize_plot(ad))
        if seen % 50 == 0:
            log.info(
                "[imovirtual] plots progress: seen=%d collected=%d skipped=%d",
                seen,
                len(rows),
                skipped,
            )
    log.info(
        "[imovirtual] plots crawl complete: seen=%d collected=%d skipped=%d",
        seen,
        len(rows),
        skipped,
    )
    _PLOT_CACHE = rows
    return _PLOT_CACHE


# ===========================================================================
# Source 1: Developments + units (NATIONAL). SCD2 + heartbeat sidecars.
# ===========================================================================
@dlt.source(name="imovirtual_developments_facts")
def imovirtual_developments_facts_source() -> Iterable[Any]:
    _ensure_dev_payload()
    yield developments
    yield developments_state
    yield development_units
    yield development_units_state


@dlt.resource(
    name="imovirtual_developments",
    write_disposition={
        "disposition": "merge",
        "strategy": "scd2",
        "row_version_column_name": "row_hash",
    },
    primary_key="development_id",
    columns={col: {"data_type": "json"} for col in DEVELOPMENTS_JSON_COLUMNS},
    schema_contract=SCHEMA_CONTRACT,
)
def developments() -> Iterable[dict]:
    for rec in _ensure_dev_payload()["developments"]:
        rec = dict(rec)
        rec["row_hash"] = _stable_hash(rec, DEVELOPMENTS_VERSION_COLUMNS)
        yield rec


@dlt.resource(
    name="imovirtual_developments_state",
    write_disposition="merge",
    primary_key="development_id",
)
def developments_state() -> Iterable[dict]:
    today = date.today()
    for rec in _ensure_dev_payload()["developments"]:
        yield {"development_id": rec["development_id"], "last_seen_date": today}


@dlt.resource(
    name="imovirtual_development_units",
    write_disposition={
        "disposition": "merge",
        "strategy": "scd2",
        "row_version_column_name": "row_hash",
    },
    primary_key="unit_id",
    columns={col: {"data_type": "json"} for col in UNITS_JSON_COLUMNS},
    schema_contract=SCHEMA_CONTRACT,
)
def development_units() -> Iterable[dict]:
    for rec in _ensure_dev_payload()["units"]:
        rec = dict(rec)
        rec["row_hash"] = _stable_hash(rec, UNITS_VERSION_COLUMNS)
        yield rec


@dlt.resource(
    name="imovirtual_development_units_state",
    write_disposition="merge",
    primary_key="unit_id",
)
def development_units_state() -> Iterable[dict]:
    today = date.today()
    for rec in _ensure_dev_payload()["units"]:
        yield {"unit_id": rec["unit_id"], "last_seen_date": today}


# ===========================================================================
# Source 2: Plots / terrenos (AVEIRO). Separate scope + separate dlt pipeline.
# ===========================================================================
@dlt.source(name="imovirtual_plots_facts")
def imovirtual_plots_facts_source() -> Iterable[Any]:
    _ensure_plot_payload()
    yield plots
    yield plots_state


@dlt.resource(
    name="imovirtual_plots",
    write_disposition={
        "disposition": "merge",
        "strategy": "scd2",
        "row_version_column_name": "row_hash",
    },
    primary_key="listing_id",
    columns={col: {"data_type": "json"} for col in PLOTS_JSON_COLUMNS},
    schema_contract=SCHEMA_CONTRACT,
)
def plots() -> Iterable[dict]:
    for rec in _ensure_plot_payload():
        rec = dict(rec)
        rec["row_hash"] = _stable_hash(rec, PLOTS_VERSION_COLUMNS)
        yield rec


@dlt.resource(
    name="imovirtual_plots_state",
    write_disposition="merge",
    primary_key="listing_id",
)
def plots_state() -> Iterable[dict]:
    today = date.today()
    for rec in _ensure_plot_payload():
        yield {"listing_id": rec["listing_id"], "last_seen_date": today}
