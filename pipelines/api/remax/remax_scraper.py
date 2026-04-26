"""
RE/MAX PT Development Scraper — two-pass requests edition
=========================================================
Scrapes new development data from the RE/MAX Portugal API to track
competitive supply for UC-2 pricing strategy.

Two-pass strategy:
  Pass 1: POST /api/Development/PaginatedSearch
    → All ~661 developments with basic unit data (area, rooms, energy, isSold)
    → ~14 pages × 50 developments

  Pass 2: GET /_next/data/{buildId}/en/imoveis/{slug}/{listingTitle}.json
    → Full detail for online units only (~17% = ~700 units)
    → Gets: address, fraction letter, previousPrice, marketDays, room breakdown, GPS
    → Offline units return notFound (sold/delisted) — skip them

Usage (Airflow):
  Called by the ingestion template via remax_config.scrape_fn.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEARCH_URL = "https://remax.pt/api/Development/PaginatedSearch"
SITE_URL = "https://remax.pt/en/comprar-empreendimentos"
DETAIL_URL_TEMPLATE = "https://remax.pt/_next/data/{build_id}/en/imoveis/{slug}/{title}.json"

PAGE_SIZE = 50
MAX_PAGES = 15  # 661 / 50 ≈ 14 pages


# ---------------------------------------------------------------------------
# Pass 2 helpers
# ---------------------------------------------------------------------------

def _get_build_id(session) -> str:
    """Extract Next.js buildId from any RE/MAX page."""
    resp = session.get(SITE_URL, timeout=30)
    match = re.search(r'"buildId":"([^"]+)"', resp.text)
    if not match:
        raise RuntimeError("Could not extract buildId from RE/MAX page")
    build_id = match.group(1)
    log.info("[remax] Extracted buildId: %s", build_id)
    return build_id


def _fetch_unit_detail(session, build_id: str, unit: dict, delay: float) -> dict | None:
    """Fetch full detail for a single online unit. Returns enriched fields or None."""
    slug = unit.get("descriptionTags", "")
    title = unit.get("listingTitle", "")
    if not slug or not title:
        return None

    url = DETAIL_URL_TEMPLATE.format(build_id=build_id, slug=slug, title=title)
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("notFound"):
            return None

        encoded = data.get("pageProps", {}).get("listingEncoded")
        if not encoded:
            return None

        detail = json.loads(base64.b64decode(encoded))
        time.sleep(delay)

        return {
            "address": detail.get("address"),
            "apartmentNumber": detail.get("apartmentNumber"),
            "zipCode": detail.get("zipCode"),
            "marketDays": detail.get("marketDays"),
            "previousPrice": detail.get("previousPrice"),
            "constructionYear": detail.get("constructionYear"),
            "contractDate": detail.get("contractDate"),
            "floorDescription": detail.get("floorDescription"),
            "floorAsNumber": detail.get("floorAsNumber"),
            "listingRooms": detail.get("listingRooms"),
            "listingPictures": detail.get("listingPictures"),
            "latitude": detail.get("latitude"),
            "longitude": detail.get("longitude"),
        }
    except Exception as e:
        log.warning("[remax] Detail fetch failed for %s: %s", title, e)
        return None


# ---------------------------------------------------------------------------
# Main scrape function (used by ingestion template)
# ---------------------------------------------------------------------------

def remax_scrape_fn(session, region, config) -> list[dict]:
    """
    Two-pass scrape conforming to ScrapingIngestionConfig.scrape_fn contract.

    Pass 1: PaginatedSearch → all developments with basic unit data
    Pass 2: Detail endpoint → enrich online units with address, fraction, price history
    """
    # --- Pass 1: PaginatedSearch ---
    all_developments = []
    seen_ids = set()

    for page in range(1, MAX_PAGES + 1):
        log.info("[remax] Pass 1: Fetching page %d (pageSize=%d)...", page, PAGE_SIZE)

        resp = session.post(
            SEARCH_URL,
            json={"pageNumber": page, "pageSize": PAGE_SIZE},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        total = data.get("total", 0)

        if not results:
            log.info("[remax] Pass 1: No more results at page %d. Done.", page)
            break

        for dev in results:
            dev_id = dev.get("id")
            if dev_id and dev_id not in seen_ids:
                seen_ids.add(dev_id)
                all_developments.append(dev)

        log.info("[remax] Pass 1: page %d → %d results (total: %d / %d)",
                 page, len(results), len(all_developments), total)

        if len(all_developments) >= total:
            break

        time.sleep(config.request_delay)

    log.info("[remax] Pass 1 complete: %d unique developments, %d total units",
             len(all_developments),
             sum(len(d.get("listings", [])) for d in all_developments))

    # --- Pass 2: Detail endpoint for online units ---
    build_id = _get_build_id(session)
    online_count = 0
    enriched_count = 0

    for dev in all_developments:
        for unit in dev.get("listings", []):
            if not unit.get("isOnline"):
                continue
            online_count += 1

            detail = _fetch_unit_detail(session, build_id, unit, config.request_delay)
            if detail:
                unit["_detail"] = detail
                enriched_count += 1

            if online_count % 50 == 0:
                log.info("[remax] Pass 2: %d/%d online units enriched so far",
                         enriched_count, online_count)

    log.info("[remax] Pass 2 complete: %d online units found, %d enriched with detail",
             online_count, enriched_count)
    log.info("[remax] Scrape complete: %d developments, %d total units (%d online, %d enriched)",
             len(all_developments),
             sum(len(d.get("listings", [])) for d in all_developments),
             online_count, enriched_count)

    return all_developments
