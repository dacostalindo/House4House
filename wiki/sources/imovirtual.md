---
title: imovirtual PT
type: source
last_verified: 2026-06-05
tags: [portal, real-estate, dlt, scd2, next-data]
priority: P1
---

## For future Claude

This is a source page about imovirtual.com, the 5th listing portal (after [[idealista]] / [[remax]] / [[jll]] / [[zome]]). It documents the dlt-driven SCD2 ingest via the site's Next.js `_next/data` JSON endpoint (no scraping vendor), the three-grain table set, and the mixed per-grain scope (developments + units national, plots Aveiro). The full design + verified field maps live in [[2026-06-05-imovirtual-portal-onboarding]]. Read this page before editing [pipelines/portals/imovirtual/imovirtual_dlt_dag.py](../../pipelines/portals/imovirtual/imovirtual_dlt_dag.py).

## Source

- **Official name**: imovirtual (imovirtual.com)
- **Owner**: OLX / Adevinta (Nexus platform; Next.js + Apollo GraphQL frontend)
- **Protocol**: dlt + direct Next.js `_next/data` JSON (`GET /_next/data/{buildId}/{path}.json`, header `x-nextjs-data: 1`). No ZenRows.
- **Base endpoint**: `https://www.imovirtual.com` — dev list `/pt/resultados/comprar/empreendimento/{loc}`, dev detail `/pt/empreendimento/{slug}`, plots `/pt/resultados/comprar/terreno/{loc}` + `/pt/anuncio/{slug}`
- **License**: proprietary; public site. robots.txt disallows `/ajax/`, `/adminpanel/`, ad-slot paths — NOT the listing pages we read. Direct `_next/data` reads of public listings; no auth, no PII collected beyond public agent/developer contacts.
- **Schedule**: weekly Thursdays 06:00 UTC (`0 6 * * 4`) — staggered off [[idealista]] (Wed)
- **Source pattern**: dlt with SCD2 write-disposition, per [[scd2-row-hash]]

## Schema

Three SCD2 fact tables + per-entity heartbeat sidecars (per [[heartbeat-sidecar]]), in `bronze_listings`:

- `imovirtual_developments` — SCD2, PK `development_id` (numeric `ad.id`). National. Dev-level GPS + `reverseGeocoding` → distrito/concelho/parish (no parsing, unlike [[idealista]]/[[remax]] — see [[portal-field-map]]). Carries BOTH `total_units` (true project size, from `number_of_units_in_project`) and `listed_units_count` (advertised subset) — a data-quality edge over [[idealista]] (listed-subset only).
- `imovirtual_development_units` — SCD2, PK `unit_id`, FK `development_id` (minted at parse time from the parent dev). National. Sourced fully from the dev's embedded `paginatedUnits` (no per-unit Pass 3 — the embedded `characteristics` are identical to the `/anuncio/` detail).
- `imovirtual_plots` — SCD2, PK `listing_id`. **Aveiro only** (one of four portal plot sources; see [[portal-plot-conventions]]). List + per-plot detail (the list lacks coordinates + canonical classification).

No ref/lookup tables (the Nexus payload is self-describing via `localizedValue`), so there is no `load_refs` task. Two facts sources with different scope: `imovirtual_developments_facts_source` (national) and `imovirtual_plots_facts_source` (Aveiro), loaded by parallel `load_facts` / `load_plots` DAG tasks into separate dlt pipelines.

Silver: imovirtual is the 5th `UNION ALL` arm of [[cross-portal-dev-dedup|unified_developments]], geometry-priority rank **JLL > imovirtual > Zome > RE/MAX > idealista** (genuine dev-level pin + official reverse-geocode).

## Quirks

- **`buildId` rotation**: the `_next/data` path embeds a Next.js build hash that changes on every deploy. The pipeline scrapes it fresh per run from a page's `__NEXT_DATA__` and refreshes it once on a 404 mid-run. Never hardcode it.
- **DataDome 403 bursts under sustained load**: a seconds-long canary was clean, but the full ~1h plots crawl provoked short 403 bursts roughly every few hundred requests. The crawl's per-request retry/backoff (4 attempts, 5/10/15s waits) + per-item skip ride them out — first full run logged **19 retries, 0 plots dropped**. Otherwise `_next/data` JSON carries no DataDome markers. Keep ~1 req/s; [[idealista]]-style ZenRows Universal Scraper is the documented fallback if a burst ever outlasts the backoff window.
- **`characteristics` pivot**: both developments and units store attributes as a `characteristics: [{key, value, currency, localizedValue}]` array (the Nexus pattern). Normalizers pivot known keys into columns; everything else is in `raw_json`. NO type casts in bronze (deferred to dbt staging, per [[portal-naming-conventions]]).
- **`*UnitsCount` fields are always null**: the development `ad` has `totalUnitsCount` / `activeUnitsCount` / etc. that are deceptively named and always null. The real count is `topInformation.number_of_units_in_project` (project total) and `paginatedUnits.pagination.totalResults` (listed). Do NOT use the `*UnitsCount` fields.
- **Units have no own pin**: unit `location.coordinates` is `(0, 0)`; units inherit the development's coordinates. `_coords` maps `(0,0)` → NULL.
- **Mixed scope**: developments/units are national (~810 devs); plots are Aveiro-only (~4.8k terreno) because national plots-with-detail would be ~42.7k fetches (~12h). National plots without coords (list-only) was the rejected alternative.
- **Validation bands** (current-state, widen after first national run): `developments` ∈ [500, 1500]; `development_units` ∈ [2000, 30000]; `plots` ∈ [1000, 8000]. Outside → fail.
- **No backfill yet**: dlt SCD2 `boundary_timestamp` not wired (day 0 = today), same as the other portals.
- **Long single-task fragility (Airflow)**: each load is a 30+ min synchronous crawl. Airflow's default 300s `scheduler_zombie_task_threshold` killed the *live* task on a heartbeat lapse under CPU contention → raised to 3600s in `docker-compose.yml` and the two loads serialized (`audit → load_facts → load_plots → validate`). Host sleep (lid close) drops the container network mid-crawl (DNS failure) — use `caffeinate` for long manual runs.
- **Resolved at first run**: unit `?page=N` pagination works (dedup-by-id guards overlap); terreno `characteristics.type` enum = {building, habitat, agricultural, other, commercial, agricultural_building, woodland} + nullable (~54% empty). **Pagination overlap**: a plot can recur across list pages during a long crawl (first run: 4,894 rows / 4,759 distinct listing_ids); the heartbeat (UPSERT by PK) dedups and staging carries `DISTINCT ON (listing_id)`.

## Last verified

2026-06-06 — built, run & verified end-to-end. First full load in `bronze_listings`: **801 developments + 4,465 units** (national, 64 concelhos, 0 orphans) and **4,894 plots** (Aveiro, 100% coords; 4,759 distinct listing_ids). 33 offline tests + ruff green; all grains within the validation bands. dbt staging + the 5th `unified_developments` arm are the remaining follow-up.
