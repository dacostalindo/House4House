---
title: Idealista
type: source
last_verified: 2026-05-08
tags: [portal, real-estate, scraper, zenrows]
---

## For future Claude

This is a source page about Idealista, the largest real-estate portal active in Portugal. It documents the two-pass ZenRows-RE-API ingest strategy (discovery + incremental detail), the auto-split logic when a concelho exceeds 950 listings, and the SCD2-style bronze layout. Read this page before editing [pipelines/portals/idealista/source.py](../../pipelines/portals/idealista/source.py) or any DAG/config in that directory.

## Source

- **Official name**: Idealista (Portugal vertical)
- **Owner**: Idealista S.A. (private company; market-leading real-estate portal across Iberia)
- **Protocol**: ZenRows Real Estate API (REST JSON) — two-phase: discovery then incremental detail
- **Base endpoint**: `https://realestate.api.zenrows.com/v1/targets/idealista/{discovery,properties}`
- **License**: proprietary; ZenRows handles upstream ToS via its scraping infrastructure
- **Active crawl level**: `concelho` (per [[2026-05-08-idealista-enrichment-architecture]] direction; was `distrito` historically)
- **Active distritos**: subset of 18 distritos via `ACTIVE_DISTRITOS`; `dim_geography` (sourced from [[caop]]) provides the distrito → concelho mapping at runtime
- **Schedule**: daily 03:00 UTC (`catchup=False`)

## Schema

Bronze table: `bronze_listings.raw_idealista` — discovery + detail merged per listing.

- **Discovery rows**: `property_id`, `address`, `price`, `bathrooms`, `size_m2`, `description`, `images` (URL list), `type` (sale | rent), location metadata (concelho, distrito, geocoords)
- **Detail rows**: full listing enrichment with additional attributes; injected via `_property_id`, `_scrape_date`, `_carried_forward` (true when reused from a prior bronze row inside the `DETAIL_REFRESH_DAYS` window)
- **Bronze policy**: permissive ingest per [[bronze-permissive]] — no Pydantic validation inside the dlt resource (per [[pydantic-not-in-dlt]]); type coercion happens in dbt staging.

## Quirks

- **Three coexisting streams in flight**: resale (legacy `raw_idealista` table), developments + units (new dlt 2026-04 path), plots. The legacy `raw_idealista` table is scheduled for retirement in Sprint 4.5 once a `unified_listings` canonical model lands, gated on hand-labeled-sample precision ≥ 0.9.
- **Two-pass validation gates** (quantitative bars, not just band checks): Pass 2 dev-detail enrichment ≥ 80%, Pass 3 unit-detail ≥ 95%, stub-rate ceiling < 10%. Outside any of those → DAG fails.
- **Mixed APIs by stream** (per [[zenrows-universal-vs-re-api]]): developments use Universal Scraper for Pass 1 + 2 (no RE API equivalent for `/comprar-empreendimentos`); Pass 3 (units) uses RE API. The mix reflects endpoint availability, not preference.
- **Auto-split by price-range**: if a discovery segment returns ≥ 950 unique listings (effectively the API's hard ceiling), the source auto-splits the segment along three price boundaries (€150k, €300k, €500k) and re-fetches each sub-segment. Without this, the tail above the ceiling is silently truncated.
- **Detail incrementality**: pass 1 = discovery, pass 2 = detail fetch for property_ids NOT seen in bronze within `DETAIL_REFRESH_DAYS` (default 30). Inside that window, prior detail is carried forward via `_carried_forward=True` instead of re-fetched. Saves ~80% of detail-call cost.
- **Stub handling**: stub rows (incomplete details) are skipped from SCD2 to avoid phantom-version oscillation; the [[heartbeat-sidecar]] still ticks for them, enabling 21-day-floor "have we seen this listing recently?" detection.
- **Field-name compatibility gambit**: the new dlt-driven tables use RE API verbatim names matching `raw_idealista` so silver models can be drop-in replaced when the legacy table retires.
- **Cost band**: ~$26-38 / run for the full 7-distrito scope. Validates budget before scaling nationally.
- **Payload caching**: discovery + detail responses are cached to MinIO via the `_payload_cache` mechanism (see [[payload-cache-lifecycle]]). Re-runs against an unchanged crawl reuse cached payloads.
- **macOS host-sleep gotcha**: when triggering from a laptop, run under `caffeinate` — `_payload_cache` is process-local, and macOS Idle Sleep kills the heartbeat → forces a full re-run from scratch.
- **Rate limits**: 2.0s discovery delay, 1.5s detail delay; 60s request timeout; max 90 discovery pages per segment (hard cap to prevent runaway loops).
- **Crawl-level switch**: at runtime, the source reads `config.crawl_level` and dispatches either distrito-level or concelho-level segments. Currently locked to `concelho` (finer-grained, more parallelizable, fewer auto-splits). Switching back is one-line revert if needed.
- **Description language**: predominantly Portuguese; downstream Phase 5 enrichment (Pydantic AI) will parse for structured fields like construction year, bedrooms, energy certificate references.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config + DAG re-read against current code).
