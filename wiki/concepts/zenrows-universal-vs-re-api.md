---
title: ZenRows — Universal Scraper vs Real Estate API
type: concept
last_verified: 2026-05-08
tags: [zenrows, scraping, idealista, ingest-pattern]
---

## For future Claude

This is a concept page about [[idealista]]'s mixed-API scrape strategy: Universal Scraper for HTML pages (Pass 1 + 2 of the developments stream) and the Real Estate API for structured listing JSON (Pass 3 + the resale pipeline). It explains the cost asymmetry (~5× cheaper RE API), the DataDome / `tld=.pt` constraints that force the mix, and why other portals ([[jll]], [[remax]], [[zome]]) don't use ZenRows at all. Read this when adding a new portal scraper, debugging an "endpoint resolves to .es" symptom, or scoping the cost of a new crawl.

## What it is

ZenRows offers two products we use, with different price/capability profiles:

| Product | What it does | Cost per request | When we use it |
|---|---|---|---|
| **Universal Scraper** | Generic anti-bot HTML fetcher (`js_render` + `premium_proxy` + `proxy_country`) | ~$0.007 | When we need raw HTML and there's no structured-data endpoint, or when the structured endpoint doesn't cover the page type |
| **Real Estate API (RE API)** | Domain-specific structured-data endpoint (returns 28-30 typed fields per listing) | ~$0.0015 | When the listing exists in RE API's coverage and we want structured data |

[[idealista]] uses BOTH in the same DAG; [[jll]], [[remax]], [[zome]] use neither (their portals' own JSON APIs are open enough that direct fetches work).

## Why

**RE API is ~5× cheaper for the same data shape**, so it's the default when it covers the case. But RE API has gaps:

- **Developments-page coverage**: `/comprar-empreendimentos/` (new-construction developments) has no RE API endpoint. Only the resale catalog (`/comprar-X/lista/`) and individual property details are exposed via RE API. Developments + their child units must be discovered via HTML — Universal Scraper for Pass 1 (development list pages) and Pass 2 (development detail pages).
- **DataDome on idealista.pt**: idealista.pt rejects anything less than `js_render=true + premium_proxy + proxy_country=pt`. Cheaper proxy modes get blocked. Pass 1 + 2 explicitly request the maximum-protection profile despite the cost.
- **TLD-locked listings**: the RE API endpoint defaults to `.es` (Spanish portal). Without `tld=.pt` in the request, the same property ID may resolve to a Spanish listing that's been deactivated → returns a ≤6-field stub. Always pass `tld=.pt` when fetching PT properties via RE API.

The mix isn't aesthetic — it reflects which endpoint actually returns the data we need at each pass.

## How

[[idealista]]'s three-pass scrape:

1. **Pass 1 (Universal Scraper)**: `GET /comprar-empreendimentos/{area}/pagina-{n}.htm` — paginated discovery pages for each configured target area until an empty page. Yields per-card "list-row" dicts (id, url, name, min_price, typology summary, cover image, branding flags). Uses `js_render+premium_proxy+proxy_country=pt`.

2. **Pass 2 (Universal Scraper)**: `GET /empreendimento/{development_id}/` — for every development found in Pass 1, fetch its detail page. Extracts og: meta tags, h1 status (e.g. "Nova construção concluída"), promoter name, full description, and the embedded list of child unit URLs.

3. **Pass 3 (RE API)**: `GET realestate.api.zenrows.com/.../properties/{unit_id}?tld=.pt` — for every child unit ID discovered in Pass 2, fetch structured JSON. RE API returns 28-30 rich fields per active PT listing including `property_condition='newdevelopment'` for dev-rooted units. ~5× cheaper than Universal Scraper, no HTML parsing.

**Pre-fetching to amortize cost**: Pass 2 + Pass 3 are pre-fetched in parallel via `ThreadPoolExecutor` BEFORE entering the dlt resource generators. The shared module-level cache ([[payload-cache-lifecycle]]) ensures the four resources (developments / developments-state / units / units-state) share one fetch. Without this, each resource's separate fetch would 4× the API spend.

**Stub detection on Pass 3**: when RE API returns ≤6 fields, treat as a stub (deactivated / wrong-tld). Skip the SCD2 row write per [[scd2-row-hash]] stub-handling rule; emit the [[heartbeat-sidecar]] anyway so silver detects "currently inactive" via heartbeat absence.

**Cost band for the full crawl** (per [[2026-05-08-idealista-enrichment-architecture]]): ~$26-38 per run for the 7-distrito scope. Validates budget assumptions before scaling nationally.

## See also

- [[idealista]] — the only consumer of this pattern in the stack
- [[payload-cache-lifecycle]] — the cache that makes the three-pass strategy economical
- [[scd2-row-hash]] — the stub-handling rule that protects bronze from oscillation
- [[heartbeat-sidecar]] — the staleness signal for stubs
- [[2026-05-08-idealista-enrichment-architecture]] — the decision record framing this pattern
