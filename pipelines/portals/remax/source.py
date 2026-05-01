"""dlt source for RE/MAX PT bronze ingestion (SCD2 + per-entity heartbeat sidecars).

Tables produced in `bronze_listings`:

  remax_developments              SCD2,   primary_key=development_id
  remax_listings                  SCD2,   primary_key=listing_id
  remax_developments_state        UPSERT, primary_key=development_id   (heartbeat sidecar)
  remax_listings_state            UPSERT, primary_key=listing_id       (heartbeat sidecar)

Two-pass scrape strategy (preserved from the legacy pipeline):

  Pass 1: POST /api/Development/PaginatedSearch
    All ~661 developments with embedded listings[] (basic per-unit fields).

  Pass 2: GET /_next/data/{buildId}/en/imoveis/{slug}/{title}.json
    For online listings only (~45% of total). Adds: address, fraction letter,
    market_days, previous_price, construction_year, contract_date, room
    breakdown, unit-level GPS.

Pass 2 fields are exclusive to the Next.js endpoint — they cannot be obtained
from any REST API call. We pre-fetch them in parallel via ThreadPoolExecutor
BEFORE entering the dlt resource generator, then yield enriched rows.

SCD2 row versioning is driven by an explicit `row_hash` over a curated column
subset. We exclude:
  - Pass 2 snapshot-derived fields (`market_days`, `previous_price`) which
    change every run regardless of business state.
  - JSONB arrays (`gallery`, `building_pictures`, `listing_rooms`,
    `listing_pictures`, `raw_json`) which Next.js may reorder between calls.
  - Immutable physical attributes (`address`, `apartment_number`,
    `construction_year`, `latitude`, `longitude`).

The heartbeat sidecars distinguish "stable unchanged listing" from "delisted".
Silver-layer queries should treat a listing as active when:

    last_seen_date >= current_date - 21

The 21-day floor: weekly cadence (7) + one missed run (7) + slack (7).
Do not lower below 14 days.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Iterable

import dlt
import requests as _requests
from dlt.sources.helpers import requests


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Endpoints + tuning constants
# ---------------------------------------------------------------------------
SEARCH_URL = "https://remax.pt/api/Development/PaginatedSearch"
SITE_URL = "https://remax.pt/en/comprar-empreendimentos"
DETAIL_URL_TEMPLATE = "https://remax.pt/_next/data/{build_id}/en/imoveis/{slug}/{title}.json"

# Plots ingestion uses sitemap → Next.js detail (no PaginatedSearch equivalent).
# `/api/Development/PaginatedSearch` is HOUSING-only; its `listingTypeIDs` filter
# is silently ignored. Plots live as standalone listings, enumerable only via
# the public sitemap. Verified 2026-04-28: 4 PT detail sitemaps total ~12,400
# plots (matches the website's `/comprar/imoveis/terreno/` total of 12,403).
SITEMAP_INDEX_URL = "https://remax.pt/sitemap.xml"
PLOT_LISTING_TYPE_ID = 21  # `listingType="Terreno"` at the unit level (NOT 39)
PLOT_URL_PATTERN = re.compile(r"/imoveis/[^/]*terreno[^/]*/(\d+-\d+)$")

PAGE_SIZE = 50
MAX_PAGES = 20  # safety upper bound; pagination stops on empty page or hasNextPage=False
PASS1_DELAY_S = 1.0  # rate limit between Pass 1 page requests
REQUEST_TIMEOUT_S = 30
DETAIL_TIMEOUT_S = 15

# Pass 2 parallelism: each worker enforces a 1s delay locally, so 8 workers ~= 8 req/s.
# Start conservative (4 workers) — raise to 8 once stability is observed in production.
PASS2_MAX_WORKERS = 4
PASS2_PER_WORKER_DELAY_S = 1.0


# ---------------------------------------------------------------------------
# Schema contract
#   data_type=freeze  → type drift fails the load loudly (caught the same week)
#   columns=evolve    → new columns land silently as NULL; staging must update
# ---------------------------------------------------------------------------
SCHEMA_CONTRACT = {"data_type": "freeze", "columns": "evolve"}


# ---------------------------------------------------------------------------
# Version-relevant columns for SCD2 row_hash.
#
# Excluded by design:
#   - JSONB arrays (gallery, building_pictures, listing_rooms, listing_pictures, raw_json)
#   - Pass 2 snapshot-derived fields (market_days, previous_price) — these
#     change on every run regardless of any real change
#   - Immutable physical attributes (address, apartment_number, construction_year,
#     latitude, longitude) — if they change, it's data correction, not a real event
#   - Display-only (slug, name) — semantic name changes are rare and noisy
# ---------------------------------------------------------------------------
DEVELOPMENTS_VERSION_COLUMNS: tuple[str, ...] = (
    "minimum_price",
    "listings_count",
    "is_special",
    "is_special_exclusive",
)

LISTINGS_VERSION_COLUMNS: tuple[str, ...] = (
    "listing_price",
    "listing_status_id",
    "is_sold",
    "sold_date",
    "is_online",
    "is_active",
    "total_area",
    "living_area",
    "num_bedrooms",
    "num_bathrooms",
    "floor_id",
    "floor_number",
    "energy_efficiency_level",
    "typology_id",
    "garage_spots",
    "parking",
    "is_exclusive",
    "is_remax_collection",
    "price_reduction_pct",
)


# ---------------------------------------------------------------------------
# JSON columns to keep as `json` data_type, NOT auto-flatten into child tables.
# Addresses dlt issue #3811 (nested-table nondeterminism on schema evolution).
# ---------------------------------------------------------------------------
DEVELOPMENTS_JSON_COLUMNS = ("building_pictures", "raw_json")
LISTINGS_JSON_COLUMNS = ("gallery", "listing_rooms", "listing_pictures", "raw_json")


# ---------------------------------------------------------------------------
# Plots — version cols and JSON cols. Plots are sourced from a different
# entry point (sitemap → Next.js detail; see _fetch_all_plots), so the field
# names mirror the Next.js detail payload directly (camelCase → snake_case
# canonical, same convention as _normalize_listing for housing).
#
# Excluded from version_cols by design (per pipelines/common/SCD2_RULES.md):
#   - market_days, previous_price, last_price_reduction_date — snapshot-derived
#   - JSONB arrays (listing_pictures, listing_attributes_ids, near_regions, raw_json)
#   - Display-only (description_tags), immutable (latitude, longitude, address)
# ---------------------------------------------------------------------------
PLOTS_VERSION_COLUMNS: tuple[str, ...] = (
    "listing_price",
    "listing_status_id",
    "is_sold",
    "sold_date",
    "is_online",
    "is_active",
    "lot_size",
    "total_area",
    "energy_efficiency_level",
    "price_reduction_pct",
    "is_special",
    "is_special_exclusive",
    "market_status_id",
)
PLOTS_JSON_COLUMNS = (
    "descriptions",
    "listing_pictures",
    "listing_attributes_ids",
    "near_regions",
    "raw_json",
)


# ---------------------------------------------------------------------------
# Hashing — canonicalize numerics so int↔float drift does not create spurious
# SCD2 versions. Whitelist scalar types so a non-scalar slipping into
# version_cols fails loudly instead of being str()-stringified.
#
# Kept in sync with zome/idealista intentionally — see
# pipelines/common/SCD2_RULES.md for the conventions; the helpers below are
# duplicated across pipelines by design (small surface, zero shared deps
# preferred over an abstraction with one consumer migrated and others lagging).
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
# HTTP — Pass 1: paginated search
# ---------------------------------------------------------------------------
def _fetch_all_developments() -> list[dict]:
    """POST PaginatedSearch repeatedly until pagination is exhausted.

    Returns a deduped list of full development dicts (with embedded listings[]).
    """
    all_devs: list[dict] = []
    seen_ids: set[int] = set()

    for page in range(1, MAX_PAGES + 1):
        resp = requests.post(
            SEARCH_URL,
            json={"pageNumber": page, "pageSize": PAGE_SIZE},
            timeout=REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        total = data.get("total", 0)
        if not results:
            break
        for dev in results:
            dev_id = dev.get("id")
            if dev_id and dev_id not in seen_ids:
                seen_ids.add(dev_id)
                all_devs.append(dev)
        log.info(
            "[remax] Pass 1: page %d → %d results (cumulative %d / %d)",
            page, len(results), len(all_devs), total,
        )
        if not data.get("hasNextPage") or len(all_devs) >= total:
            break
        time.sleep(PASS1_DELAY_S)

    return all_devs


# ---------------------------------------------------------------------------
# HTTP — Pass 2: parallel detail prefetch
# ---------------------------------------------------------------------------
def _get_build_id() -> str:
    """Extract Next.js buildId from the RE/MAX comprar-empreendimentos page."""
    resp = requests.get(SITE_URL, timeout=REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    match = re.search(r'"buildId":"([^"]+)"', resp.text)
    if not match:
        raise RuntimeError("Could not extract buildId from RE/MAX page")
    build_id = match.group(1)
    log.info("[remax] Extracted buildId: %s", build_id)
    return build_id


def _fetch_one_detail(build_id: str, unit: dict) -> dict:
    """Fetch a single unit's Pass 2 detail. Returns enriched fields or {}.

    Failures are caught here and return {}; the caller treats this as
    "no enrichment available" rather than aborting the whole batch.
    Each call sleeps PASS2_PER_WORKER_DELAY_S after the request to enforce
    a per-worker rate limit.
    """
    slug = unit.get("descriptionTags") or ""
    title = unit.get("listingTitle") or ""
    if not slug or not title:
        return {}

    url = DETAIL_URL_TEMPLATE.format(build_id=build_id, slug=slug, title=title)
    try:
        resp = _requests.get(url, timeout=DETAIL_TIMEOUT_S)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        if data.get("notFound"):
            return {}
        encoded = (data.get("pageProps") or {}).get("listingEncoded")
        if not encoded:
            return {}
        detail = json.loads(base64.b64decode(encoded))
    except Exception as exc:
        log.warning("[remax] Pass 2 fetch failed for listingTitle=%s: %s", title, exc)
        return {}
    finally:
        time.sleep(PASS2_PER_WORKER_DELAY_S)

    return {
        "address": detail.get("address"),
        "apartment_number": detail.get("apartmentNumber"),
        "zip_code": detail.get("zipCode"),
        "market_days": detail.get("marketDays"),
        "previous_price": detail.get("previousPrice"),
        "construction_year": detail.get("constructionYear"),
        "contract_date": detail.get("contractDate"),
        "floor_description": detail.get("floorDescription"),
        "listing_rooms": detail.get("listingRooms"),
        "listing_pictures": detail.get("listingPictures"),
        "unit_latitude": detail.get("latitude"),
        "unit_longitude": detail.get("longitude"),
    }


def _prefetch_pass2(devs: list[dict]) -> dict[int, dict]:
    """Concurrently fetch Pass 2 details for all online listings across all devs.

    Returns dict[listing_id → detail_dict]. Failed/missing fetches yield an
    empty dict entry so the dlt resource still emits the listing with NULL
    Pass 2 fields. Memory: <50MB for ~3,900 detail dicts.
    """
    online_units: list[dict] = []
    for dev in devs:
        for unit in dev.get("listings") or []:
            if unit.get("isOnline") and unit.get("id") is not None:
                online_units.append(unit)

    if not online_units:
        log.info("[remax] Pass 2: no online units to enrich.")
        return {}

    build_id = _get_build_id()
    log.info(
        "[remax] Pass 2: prefetching %d online units in parallel "
        "(max_workers=%d, per-worker delay=%.1fs)",
        len(online_units), PASS2_MAX_WORKERS, PASS2_PER_WORKER_DELAY_S,
    )

    results: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=PASS2_MAX_WORKERS) as ex:
        futures = {
            ex.submit(_fetch_one_detail, build_id, u): u["id"]
            for u in online_units
        }
        completed = 0
        for fut in as_completed(futures):
            listing_id = futures[fut]
            try:
                results[listing_id] = fut.result() or {}
            except Exception as exc:  # defensive — _fetch_one_detail catches its own
                log.warning("[remax] Pass 2 future failed for %s: %s", listing_id, exc)
                results[listing_id] = {}
            completed += 1
            if completed % 200 == 0:
                log.info("[remax] Pass 2: %d/%d enriched", completed, len(online_units))

    enriched_count = sum(1 for v in results.values() if v)
    log.info(
        "[remax] Pass 2 complete: %d/%d enriched (%d returned empty due to "
        "fetch failure or missing slug/title).",
        enriched_count, len(online_units), len(online_units) - enriched_count,
    )
    return results


# ---------------------------------------------------------------------------
# Plots — sitemap enumeration + Next.js detail per plot URL.
# Two-pass strategy distinct from housing (which uses PaginatedSearch):
#   Pass 1: walk sitemap.xml index → 4 PT detail sitemaps → ~12.4k plot URLs
#   Pass 2: per URL, GET _next/data/{build}/en/imoveis/{slug}/{title}.json
#           → decode listingEncoded → keep if listingTypeID == 21 (Terreno)
# ---------------------------------------------------------------------------
def _fetch_all_plots() -> list[dict]:
    """Pass 1 for plots: sitemap walk → list of {slug, title, plot_url} dicts.

    Returns a deduped list. Sitemap URLs are filtered to those matching
    PLOT_URL_PATTERN. The actual listingTypeID==21 check happens in Pass 2,
    after we have the structured payload — sitemap URL substring is a
    heuristic only.
    """
    resp = requests.get(SITEMAP_INDEX_URL, timeout=REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    child_sitemaps = re.findall(r"<loc>([^<]+)</loc>", resp.text)
    listing_sitemaps = [u for u in child_sitemaps if "listings_details_pt" in u]
    log.info("[remax] Plots Pass 1: %d PT listing sitemaps", len(listing_sitemaps))

    plots: list[dict] = []
    seen_titles: set[str] = set()
    for sm_url in listing_sitemaps:
        rs = requests.get(sm_url, timeout=REQUEST_TIMEOUT_S)
        rs.raise_for_status()
        urls = re.findall(r"<loc>([^<]+)</loc>", rs.text)
        added = 0
        for u in urls:
            m = PLOT_URL_PATTERN.search(u)
            if not m:
                continue
            title = m.group(1)
            if title in seen_titles:
                continue
            seen_titles.add(title)
            slug = u.rstrip("/").rsplit("/", 2)[-2]
            plots.append({"slug": slug, "title": title, "plot_url": u})
            added += 1
        log.info("[remax] Plots Pass 1: %s → %d plot URLs (cumulative %d)",
                 sm_url.rsplit("/", 1)[-1], added, len(plots))
        time.sleep(PASS1_DELAY_S)
    return plots


def _fetch_one_plot_detail(build_id: str, plot_ref: dict) -> dict:
    """Pass 2 worker for plots. Returns the full Next.js detail payload (decoded)
    or {} on failure. Filters to listingTypeID == 21 (Terreno) — non-plot
    URLs that matched the sitemap heuristic are returned as {} so the caller
    skips them.
    """
    slug, title = plot_ref["slug"], plot_ref["title"]
    url = DETAIL_URL_TEMPLATE.format(build_id=build_id, slug=slug, title=title)
    try:
        resp = _requests.get(url, timeout=DETAIL_TIMEOUT_S)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        if data.get("notFound"):
            return {}
        encoded = (data.get("pageProps") or {}).get("listingEncoded")
        if not encoded:
            return {}
        detail = json.loads(base64.b64decode(encoded))
    except Exception as exc:
        log.warning("[remax] Plot Pass 2 failed for %s/%s: %s", slug, title, exc)
        return {}
    finally:
        time.sleep(PASS2_PER_WORKER_DELAY_S)

    if detail.get("listingTypeID") != PLOT_LISTING_TYPE_ID:
        return {}  # sitemap URL matched 'terreno' heuristic but payload says otherwise
    return detail


def _prefetch_plots(plot_refs: list[dict]) -> dict[int, dict]:
    """Concurrently fetch Pass 2 details for all sitemap-discovered plot URLs.

    Returns dict[listing_id → detail_dict]. URLs that turn out to be non-plots
    (listingTypeID != 21) are filtered out — their dict entry is omitted, so
    the SCD2 resource simply yields fewer rows than there were sitemap URLs.
    """
    if not plot_refs:
        log.info("[remax] Plots Pass 2: no plot URLs to enrich.")
        return {}

    build_id = _get_build_id()
    log.info(
        "[remax] Plots Pass 2: prefetching %d plot URLs in parallel "
        "(max_workers=%d, per-worker delay=%.1fs)",
        len(plot_refs), PASS2_MAX_WORKERS, PASS2_PER_WORKER_DELAY_S,
    )

    results: dict[int, dict] = {}
    skipped_non_plot = 0
    with ThreadPoolExecutor(max_workers=PASS2_MAX_WORKERS) as ex:
        futures = {ex.submit(_fetch_one_plot_detail, build_id, p): p for p in plot_refs}
        completed = 0
        for fut in as_completed(futures):
            try:
                detail = fut.result() or {}
            except Exception as exc:
                ref = futures[fut]
                log.warning("[remax] Plot Pass 2 future failed for %s/%s: %s",
                            ref["slug"], ref["title"], exc)
                detail = {}
            if detail and detail.get("id") is not None:
                results[detail["id"]] = detail
            elif not detail:
                # Either a true fetch failure OR a non-plot URL we filtered.
                # Distinguishing requires re-fetching; not worth it.
                skipped_non_plot += 1
            completed += 1
            if completed % 500 == 0:
                log.info("[remax] Plots Pass 2: %d/%d processed", completed, len(plot_refs))

    log.info(
        "[remax] Plots Pass 2 complete: %d enriched, %d skipped (fetch failed or non-plot)",
        len(results), skipped_non_plot,
    )
    return results


def _normalize_plot(detail: dict) -> dict:
    """Flatten a Next.js plot detail into a canonical bronze row.

    Mirrors _normalize_listing's camelCase→snake_case convention. Plot-specific
    fields kept: lot_size (the m² of the terrain), local_zone, near_regions.
    Housing-only fields (num_bedrooms, num_bathrooms, floor_id, etc.) are
    excluded — they're meaningless for plots.
    """
    return {
        "listing_id": detail.get("id"),
        "agent_id": detail.get("agentID"),
        "office_id": detail.get("officeID"),
        "team_id": detail.get("teamID"),
        "user_id": detail.get("userID"),
        "owner_page_id": detail.get("ownerPageId"),
        "listing_class_id": detail.get("listingClassID"),
        "listing_type": detail.get("listingType"),
        "listing_type_id": detail.get("listingTypeID"),
        "business_type": detail.get("businessType"),
        "business_type_id": detail.get("businessTypeID"),
        "listing_status_id": detail.get("listingStatusID"),
        "market_status_id": detail.get("marketStatusID"),
        "is_sold": bool(detail.get("isSold")),
        "sold_date": detail.get("soldDate"),
        "is_online": bool(detail.get("isOnline")),
        "is_active": bool(detail.get("isActive")),
        "is_special": bool(detail.get("isSpecial")),
        "is_special_exclusive": bool(detail.get("isSpecialExclusive")),
        # Price
        "listing_price": detail.get("listingPrice") or None,
        "previous_price": detail.get("previousPrice"),
        "price_reduction_pct": detail.get("priceReductionPercentageValue"),
        "last_price_reduction_date": detail.get("lastPriceReductionDate"),
        # Areas (plot-relevant)
        "lot_size": detail.get("lotSize"),
        "lot_size_display": detail.get("lotSizeDisplay"),
        "total_area": detail.get("totalArea"),
        "built_area": detail.get("builtArea"),
        "living_area": detail.get("livingArea"),
        # Address / location
        "address": detail.get("address"),
        "local_zone": detail.get("localZone"),
        "zip_code": detail.get("zipCode"),
        "is_exact_address": bool(detail.get("isExactAddress")),
        "has_private_address": bool(detail.get("hasPrivateAddress")),
        "public_address": bool(detail.get("publicAddress")),
        "country_id": detail.get("countryID"),
        "region1_id": detail.get("region1ID"),
        "region2_id": detail.get("region2ID"),
        "region3_id": detail.get("region3ID"),
        "region_name1": detail.get("regionName1"),
        "region_name2": detail.get("regionName2"),
        "region_name3": detail.get("regionName3"),
        "region_name4": detail.get("regionName4"),
        "region_search2": detail.get("regionSearch2"),
        "region_search3": detail.get("regionSearch3"),
        # Energy / features
        "energy_efficiency_level": detail.get("energyEfficiencyLevelID"),
        "emission_efficiency_level": detail.get("emissionEfficiencyLevelID"),
        "construction_year": detail.get("constructionYear"),
        # Lifecycle
        "market_days": detail.get("marketDays"),
        "language_id": detail.get("languageID"),
        "master_id": detail.get("masterID"),
        # Slug / agent_id_in_url
        "description_tags": detail.get("descriptionTags"),
        # JSONB
        "descriptions": detail.get("descriptions") or [],
        "listing_pictures": detail.get("listingPictures") or [],
        "listing_attributes_ids": detail.get("listingAttributesIds") or [],
        "near_regions": detail.get("nearRegions") or [],
        "raw_json": detail,
    }


# ---------------------------------------------------------------------------
# Normalization — flatten Pass 1 + Pass 2 records into canonical bronze rows.
# Column names follow the existing raw_remax_* schema for continuity.
# ---------------------------------------------------------------------------
def _normalize_development(dev: dict) -> dict:
    """Strip listings[] from raw_json (kept separately in remax_listings)."""
    raw = {k: v for k, v in dev.items() if k not in ("listings", "listingTitleList")}
    desc_bodies = dev.get("descriptionBodies") or []
    description = (desc_bodies[0] or {}).get("description", "") if desc_bodies else ""

    return {
        "development_id": dev.get("id"),
        "name": dev.get("name"),
        "slug": dev.get("nameToSort"),
        "latitude": dev.get("latitude"),
        "longitude": dev.get("longitude"),
        "minimum_price": dev.get("minimumPrice"),
        "region_name1": dev.get("regionName1"),
        "region_name2": dev.get("regionName2"),
        "region_name3": dev.get("regionName3"),
        "zip_code": dev.get("zipCode"),
        "listings_count": dev.get("listingsCount") or 0,
        "office_name": dev.get("officeName"),
        "office_id": dev.get("officeID"),
        "agent_name": dev.get("userName"),
        "agent_phone": dev.get("userCellPhone"),
        "description": description,
        "publish_date": dev.get("publishDate"),
        "is_special": bool(dev.get("isSpecial")),
        "is_special_exclusive": bool(dev.get("isSpecialExclusive")),
        "building_pictures": dev.get("buildingPictures") or [],
        "raw_json": raw,
    }


def _normalize_listing(unit: dict, dev_id: int, detail: dict) -> dict:
    """Combine Pass 1 unit fields with Pass 2 enrichment (when available)."""
    return {
        "listing_id": unit.get("id"),
        "development_id": dev_id,
        "listing_price": unit.get("listingPrice") or None,
        "total_area": unit.get("totalArea"),
        "living_area": unit.get("livingArea"),
        "num_bedrooms": unit.get("numberOfBedrooms"),
        "num_bathrooms": unit.get("numberOfBathrooms"),
        "floor_id": unit.get("floorID"),
        "floor_number": unit.get("floorAsNumber"),
        "listing_status_id": unit.get("listingStatusID"),
        "is_sold": bool(unit.get("isSold")),
        "sold_date": unit.get("soldDate"),
        "is_online": bool(unit.get("isOnline")),
        "is_active": bool(unit.get("isActive")),
        "energy_efficiency_level": unit.get("energyEfficiencyLevelID"),
        "typology_id": unit.get("typologyID"),
        "listing_type": unit.get("listingType"),
        "publish_date": unit.get("publishDate"),
        "modified": unit.get("modified"),
        "region_name2": unit.get("regionName2"),
        "region_name3": unit.get("regionName3"),
        "garage_spots": unit.get("garageSpots"),
        "parking": bool(unit.get("parking")),
        "is_exclusive": bool(unit.get("isExclusive")),
        "is_remax_collection": bool(unit.get("isRemaxCollection")),
        "price_reduction_pct": unit.get("priceReductionPercentageValue"),
        # Pass 2 enrichment (NULL when no detail or fetch failed)
        "address": detail.get("address"),
        "apartment_number": detail.get("apartment_number"),
        "market_days": detail.get("market_days"),
        "previous_price": detail.get("previous_price"),
        "construction_year": detail.get("construction_year"),
        "contract_date": detail.get("contract_date"),
        "floor_description": detail.get("floor_description"),
        "listing_rooms": detail.get("listing_rooms"),
        "listing_pictures": detail.get("listing_pictures"),
        "unit_latitude": detail.get("unit_latitude"),
        "unit_longitude": detail.get("unit_longitude"),
        "_has_detail": bool(detail),
        "gallery": unit.get("listingPictures") or [],  # Pass 1 picture URLs (separate from Pass 2 listing_pictures detail)
        "raw_json": unit,
    }


# ===========================================================================
# Source: Facts (SCD2 + sidecars). Failure here blocks bronze refresh.
# ===========================================================================
@dlt.source(name="remax_facts")
def remax_facts_source() -> Iterable[Any]:
    """All resources share a single fetch via module-level cached state.

    Housing path: PaginatedSearch (Pass 1) → Next.js detail (Pass 2).
    Plots path: sitemap.xml walk (Pass 1) → Next.js detail (Pass 2).
    The two paths are independent — caches are stored under separate keys.
    """
    yield developments
    yield developments_state
    yield listings
    yield listings_state
    yield plots
    yield plots_state


# Module-level cache — populated lazily on first resource call within a load.
# Cleared by deleting the module from sys.modules between loads (dlt creates
# a fresh process per pipeline.run()). Keys: "devs"/"pass2" for housing,
# "plots"/"plot_details" for plots.
_payload_cache: dict[str, Any] = {}


def _ensure_payload() -> tuple[list[dict], dict[int, dict]]:
    """Fetch housing Pass 1 + Pass 2 once per load, cache for subsequent resources."""
    if "devs" not in _payload_cache:
        _payload_cache["devs"] = _fetch_all_developments()
        _payload_cache["pass2"] = _prefetch_pass2(_payload_cache["devs"])
        log.info(
            "[remax] Payload ready: %d developments, %d listings, %d Pass 2 details",
            len(_payload_cache["devs"]),
            sum(len(d.get("listings") or []) for d in _payload_cache["devs"]),
            sum(1 for v in _payload_cache["pass2"].values() if v),
        )
    return _payload_cache["devs"], _payload_cache["pass2"]


def _ensure_plots_payload() -> dict[int, dict]:
    """Fetch plot sitemap + Pass 2 once per load, cache for plots + heartbeat."""
    if "plot_details" not in _payload_cache:
        plot_refs = _fetch_all_plots()
        _payload_cache["plot_refs"] = plot_refs
        _payload_cache["plot_details"] = _prefetch_plots(plot_refs)
        log.info(
            "[remax] Plots payload ready: %d sitemap URLs, %d Pass 2 details",
            len(plot_refs), len(_payload_cache["plot_details"]),
        )
    return _payload_cache["plot_details"]


@dlt.resource(
    name="remax_developments",
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
    devs, _pass2 = _ensure_payload()
    for raw in devs:
        rec = _normalize_development(raw)
        rec["row_hash"] = _stable_hash(rec, DEVELOPMENTS_VERSION_COLUMNS)
        yield rec


@dlt.resource(
    name="remax_developments_state",
    write_disposition="merge",
    primary_key="development_id",
)
def developments_state() -> Iterable[dict]:
    devs, _pass2 = _ensure_payload()
    today = date.today()
    for raw in devs:
        yield {
            "development_id": raw.get("id"),
            "last_seen_date": today,
        }


@dlt.resource(
    name="remax_listings",
    write_disposition={
        "disposition": "merge",
        "strategy": "scd2",
        "row_version_column_name": "row_hash",
    },
    primary_key="listing_id",
    columns={
        **{col: {"data_type": "json"} for col in LISTINGS_JSON_COLUMNS},
        # Type hints for columns that may be NULL in early loads — without them
        # dlt's freeze schema would reject them on the first non-NULL value.
        "price_reduction_pct": {"data_type": "decimal"},
        "previous_price": {"data_type": "decimal"},
        "market_days": {"data_type": "bigint"},
        "construction_year": {"data_type": "bigint"},
        "unit_latitude": {"data_type": "decimal"},
        "unit_longitude": {"data_type": "decimal"},
        "address": {"data_type": "text"},
        "apartment_number": {"data_type": "text"},
        "contract_date": {"data_type": "text"},
        "floor_description": {"data_type": "text"},
        "sold_date": {"data_type": "text"},
    },
    schema_contract=SCHEMA_CONTRACT,
)
def listings() -> Iterable[dict]:
    devs, pass2 = _ensure_payload()
    for dev in devs:
        dev_id = dev.get("id")
        for unit in dev.get("listings") or []:
            unit_id = unit.get("id")
            if unit_id is None:
                continue
            detail = pass2.get(unit_id, {})
            rec = _normalize_listing(unit, dev_id, detail)
            rec["row_hash"] = _stable_hash(rec, LISTINGS_VERSION_COLUMNS)
            yield rec


@dlt.resource(
    name="remax_listings_state",
    write_disposition="merge",
    primary_key="listing_id",
)
def listings_state() -> Iterable[dict]:
    devs, _pass2 = _ensure_payload()
    today = date.today()
    for dev in devs:
        for unit in dev.get("listings") or []:
            unit_id = unit.get("id")
            if unit_id is None:
                continue
            yield {
                "listing_id": unit_id,
                "last_seen_date": today,
            }


# ---------------------------------------------------------------------------
# Plots — sourced via sitemap.xml + Next.js detail (NOT PaginatedSearch).
# See _fetch_all_plots / _prefetch_plots above.
# ---------------------------------------------------------------------------
@dlt.resource(
    name="remax_plots",
    write_disposition={
        "disposition": "merge",
        "strategy": "scd2",
        "row_version_column_name": "row_hash",
    },
    primary_key="listing_id",
    columns={
        **{col: {"data_type": "json"} for col in PLOTS_JSON_COLUMNS},
        "listing_price": {"data_type": "decimal"},
        "previous_price": {"data_type": "decimal"},
        "price_reduction_pct": {"data_type": "decimal"},
        "lot_size": {"data_type": "decimal"},
        "total_area": {"data_type": "decimal"},
        "built_area": {"data_type": "decimal"},
        "living_area": {"data_type": "decimal"},
        "market_days": {"data_type": "bigint"},
        "construction_year": {"data_type": "bigint"},
        "address": {"data_type": "text"},
        "sold_date": {"data_type": "text"},
        "last_price_reduction_date": {"data_type": "text"},
    },
    schema_contract=SCHEMA_CONTRACT,
)
def plots() -> Iterable[dict]:
    plot_details = _ensure_plots_payload()
    for detail in plot_details.values():
        rec = _normalize_plot(detail)
        rec["row_hash"] = _stable_hash(rec, PLOTS_VERSION_COLUMNS)
        yield rec


@dlt.resource(
    name="remax_plots_state",
    write_disposition="merge",
    primary_key="listing_id",
)
def plots_state() -> Iterable[dict]:
    plot_details = _ensure_plots_payload()
    today = date.today()
    for listing_id in plot_details.keys():
        yield {
            "listing_id": listing_id,
            "last_seen_date": today,
        }
