---
title: imovirtual portal onboarding — acquisition + scope design
type: decision
last_verified: 2026-06-06
tags: [imovirtual, portals, dlt, bronze, scd2, next-data, datadome, scope]
confidence: high
---

## Addendum 2026-06-06 — silver wiring landed + geometry-priority demotion

The remaining follow-up listed in the preamble — `stg_portal_developments_imovirtual` + 5th UNION arm in [[cross-portal-dev-dedup|unified_developments]] — shipped. Two notes on what diverged from the original record:

1. **Geometry-priority slot demoted from 2 to 4.** Original ladder: `JLL > imovirtual > Zome > RE/MAX > idealista`. Shipped ladder: `JLL > Zome > RE/MAX > imovirtual > idealista`. imovirtual's typed dev-level pin + `reverseGeocoding` are cleaner than RE/MAX in principle, but coordinate coverage was unverified at silver-build time — the conservative slot (just above idealista) wins for v1 until a coverage spot-check (% non-null gps_lat, distribution within a known concelho) clears a promotion. Reversibility cost is 4 lines in the priority CASE.
2. **Unit-count semantics held** — `total_units` carries `number_of_units_in_project` (TRUE project size, not the listed subset). `listed_units_count` lives in `raw_meta` of the staging model for consumers that want both. This is the data-quality edge over idealista the decision called out, kept intact through silver.

Units/plots staging remain deferred (no cross-portal consumer needs them yet; `unified_listings_residential` stays at 4 portals).

## For future Claude

This is a decision record about adding **imovirtual** as the 5th listing portal, alongside [[idealista]], [[remax]], [[zome]], [[jll]]. It locks the acquisition method (direct Next.js `_next/data` JSON, no scraping vendor), the three-grain table design (developments + development_units + plots), the per-grain geographic scope (devs/units national, plots Aveiro), and the silver participation (5th arm of [[cross-portal-dev-dedup|unified_developments]]). Designed from live-API recon + a DataDome canary 2026-06-05, then **built, run, and verified 2026-06-06**: the national dev+unit load (801 devs / 4,465 units) + Aveiro plots (4,894) landed in `bronze_listings` and passed the validation bands. The dbt staging + 5th UNION arm shipped 2026-06-06 — see the addendum above for the rank-change rationale. Read this before extending the imovirtual pipeline or revisiting its scope.

## Decision

Onboard **imovirtual** (OLX/Adevinta Nexus platform, Next.js + Apollo GraphQL) as a dlt-based portal mirroring the existing pattern. Specifics:

- **Acquisition: direct `GET /_next/data/{buildId}/{path}.json`** (header `x-nextjs-data: 1`). No ZenRows. `buildId` rotates per deploy — scrape it fresh each run from any page's `__NEXT_DATA__`. ZenRows Universal Scraper is the documented fallback if DataDome ever challenges at volume.
- **Three grains → 6 bronze tables** in `bronze_listings` (per [[portal-naming-conventions]]):
  - `imovirtual_developments` (PK `development_id` = numeric `ad.id`) + `_state`
  - `imovirtual_development_units` (PK `unit_id`, FK `development_id`) + `_state`
  - `imovirtual_plots` (PK `listing_id`) + `_state`
- **Scope (mixed, deliberate):** developments + units **national** (~810 devs); plots **Aveiro-only** (~4.8k terreno). Rationale in Options.
- **No per-unit fetch.** A development's `_next/data` returns `ad.paginatedUnits` whose embedded `characteristics` are **identical to the full `/anuncio/` unit detail** (verified). Units come fully from the dev crawl — the [[idealista]] Pass 3 is unnecessary here.
- **Plots use list + per-plot detail** (Aveiro scope makes this affordable): the terreno list lacks `coordinates` (null) and canonical classification, both of which the `/anuncio/` detail supplies.
- **Silver:** add imovirtual as the 5th `UNION ALL` arm of [[cross-portal-dev-dedup|unified_developments]], ranked **JLL > imovirtual > Zome > RE/MAX > idealista** in the geometry-priority ladder (imovirtual carries a true dev-level pin + official `reverseGeocoding` to freguesia, second only to JLL's flagged GPS).

## Why

imovirtual is a large PT portal not yet covered. Its `_next/data` JSON is cleaner and more stable than [[idealista]]'s HTML+RE-API split — structured, typed-ish, no vendor cost. It also exposes a data-quality win the other portals lack (see unit-count note below).

**Acquisition — why direct, not ZenRows.** A 2026-06-05 DataDome canary (national dev lists across Lisboa/Porto/Faro + deep pagination, Aveiro terreno deep pages, and **20 rapid `_next/data` JSON calls with zero delay**) returned **real data on every request, 0 blocks**. DataDome ships a script on every HTML page but does not challenge this traffic. `_next/data` JSON responses carry no DataDome markers at all. So direct is free and works; ZenRows is held as a fallback, not a dependency. Full national run is ~2,400 requests (~40 min @ 1 req/s).

**Unit counts — the data-quality win.** A development exposes TWO counts: `number_of_units_in_project` (the true project size, e.g. 20) and `number_of_adverts` / `paginatedUnits.totalResults` (currently-listed subset, e.g. 11). Per [[cross-portal-dev-dedup]], [[idealista]] only ever reports the *listed subset*, never the development total — which is why `portal_unit_counts` avoids a laundered "authoritative" number. imovirtual gives both, so its `total_units` maps to `number_of_units_in_project` and a separate `listed_units_count` holds the advertised count. Strictly more than idealista.

**Data shape.** Both developments and units store attributes as a `characteristics: [{key, value, currency, localizedValue}]` array (the Nexus pattern). Normalization pivots known keys into columns; the rest goes to `raw_json`. Geography is free: `location.reverseGeocoding` yields district/council(concelho)/parish directly — no parsing, unlike [[idealista]] and [[remax]] (see [[portal-field-map]]).

### Verified field maps (live, 2026-06-05)

**Developments** (`/pt/empreendimento/{slug}` → `pageProps.ad`): `development_id`←`id`; `name`←`title`; `slug`; `gps_lat/lon`←`location.coordinates`; `distrito/concelho/parish`←`location.reverseGeocoding`; `address_text`←`location.address.street.name`; `total_units`←`topInformation.number_of_units_in_project`; `listed_units_count`←`paginatedUnits.pagination.totalResults`; `promoter_*`←`owner`/`agency` (type=developer); `status`; `created_at`/`modified_at`; pivoted from `characteristics`/`target`: `price_per_m_from`, `area_from`, `area_to`, `state`, `offered_estates_type`, `project_amenities`, `extra_spaces`; typology from `unitGroups` (groupBy ROOMS_NUMBER). JSON cols: `images`, `floorPlans`, `characteristics`, `target`, `raw_json`. The `*UnitsCount` top-level fields are always null — do NOT use them.

**Units** (`ad.paginatedUnits.items[]`, embedded = complete): `unit_id`←`id`; `development_id`←parent (parse-time); `unit_url`←`url`; from `characteristics` (12 keys): `price`, `price_per_m`, `area_m`, `rooms_num`, `energy_certificate`, `floor_no`, `building_floors_num`, `building_type`, `construction_status`, `market`, `heating`, `windows_type`. Units carry no own pin (`coordinates` = 0,0) — they inherit the dev's. `title`/`status`/`slug` are empty in the embedded view (cosmetic; status covered by the [[heartbeat-sidecar]]).

**Plots** (terreno list + `/anuncio/` detail): `listing_id`←`id`; `price`←`totalPrice`/`characteristics.price`; `price_per_m`←`pricePerSquareMeter`; `area_m`←`areaInSquareMeters`/`characteristics.m`; `classification`←`characteristics.type` (agricultural/urban/rústico; the list only has it in the title); `distrito/concelho/parish`←`reverseGeocoding`; `coordinates`←detail only (list is null); `date_created`; `is_private_owner`. JSON: `images`, `raw_json`.

### SCD2 version columns (per [[scd2-row-hash]])

- Devs: `total_units`, `listed_units_count`, `state`, `price_per_m_from`, `area_from`, `area_to`, `offered_estates_type`
- Units: `price`, `price_per_m`, `area_m`, `rooms_num`, `energy_certificate`, `floor_no`, `construction_status`, `market`
- Plots: `price`, `price_per_m`, `area_m`, `classification`, `status`

## Options considered

1. **Scope — devs/units national + plots Aveiro** (chosen). National devs/units is cheap (~2,400 req) and the canary shows no blocking. National plots-with-detail would be ~42.7k fetches (~12h) for precise coords, which is prohibitive; Aveiro plots-with-detail is ~4.8k and affordable. Mixed scope buys national development coverage without paying the national-plots tax.
2. **All-national, plots list-only (no coords)** — rejected by user: gives up precise plot coordinates and canonical classification. Acceptable only because no silver consumer needs plot coords yet, but the user preferred real plot geo for Aveiro.
3. **All-Aveiro** — rejected: undersells imovirtual's value (810 national devs vs 17 Aveiro).
4. **Acquisition via ZenRows** (mirroring [[idealista]]) — rejected as default: the canary shows direct works at zero cost. ZenRows retained as fallback only.
5. **Per-unit detail fetch (idealista-style Pass 3)** — rejected: embedded `paginatedUnits` characteristics are identical to unit detail, so a third pass adds ~9k national fetches for nothing.

## Consequences

- New pipeline dir `pipelines/portals/imovirtual/` (source.py + DAG + tests + README), mirroring [[zome]]'s single-file dlt skeleton with [[idealista]]'s dev→units 1:N FK-at-parse-time loop. Copy `_stable_hash`/`_canonicalize` verbatim per the duplication-by-design policy in [[scd2-row-hash]].
- Acquisition crawl: Pass 1 (dev list, paginate 36/page) → Pass 2 (dev detail = dev row + units, paginate units 10/page). Plots: terreno-list (Aveiro) → per-plot `/anuncio/` detail. `buildId` refreshed per run; 404 → refetch buildId.
- dbt: new `stg_portal_developments_imovirtual.sql` (13 canonical cols, dev-level geom, concelho/parish straight from reverseGeocoding); source blocks in `_staging_listings__sources.yml`; test block in `_staging_portals__models.yml`; 5th UNION arm + geo-priority rank in `unified_developments.sql`. Plots/units staging deferred (no cross-portal unified consumer for those grains yet — [[cross-portal-dev-dedup]] is developments-only; unified_listings is idealista-legacy-only).
- Validation gate: national row-count bands (devs `[500,1500]`, units `[2000,30000]`), Aveiro plots band (`[1000,8000]`), `_dlt_loads.status == 0`, heartbeat 21-day floor.
- Risk: `buildId` rotation mid-run (rare; handled by refetch). Risk: DataDome at sustained national volume (mitigated by ~1 req/s throttle + 403/429 backoff + ZenRows fallback). Risk: imovirtual unit pagination param + terreno `characteristics.type` enum need a one-shot confirmation at build time.
- Reversibility: dropping imovirtual = remove the dlt source + the 5th UNION arm + 1 line in the geo-priority CASE. No other portal depends on it.

## Status

`accepted` — bronze pipeline built, run & verified (2026-06-06). First full load: **801 developments + 4,465 units (national), 4,894 plots (Aveiro)** in `bronze_listings`, all within the validation bands; 0 orphan units, 100% plot coords. Two operational findings, both now handled in the code/infra:

- **Airflow zombie-kill on long crawls.** The load task is a single 30+ min synchronous crawl; the default 300s `scheduler_zombie_task_threshold` killed the *live* task when its heartbeat lapsed under CPU contention. Fixed: threshold → 3600s in `docker-compose.yml`, and the two loads serialized (`audit → load_facts → load_plots → validate`).
- **DataDome 403 bursts under sustained load** (~every few hundred plots). The crawl's per-request retry/backoff + per-item skip rides them out — first full run logged 19 retries with **0 plots dropped**. (Host-sleep DNS drops were the other killer; mitigated by `caffeinate` during manual runs.)

Confirm-at-build items resolved by the real run: unit `?page=N` pagination works; terreno `characteristics.type` enum = {building, habitat, agricultural, other, commercial, agricultural_building, woodland} + nullable. Remaining follow-up: dbt staging + the 5th `unified_developments` arm (this PR is bronze + wiki only).

## See also

- [[idealista]] — the dev→units 1:N analog (Pass-2/3 fused here); [[zome]] — the single-file dlt skeleton template
- [[portal-field-map]] — cross-portal correspondence matrix (add imovirtual columns post-build)
- [[portal-plot-conventions]] — `_plots` table conventions
- [[cross-portal-dev-dedup]] — `unified_developments`; imovirtual is the 5th arm + new geo-priority rank
- [[scd2-row-hash]] — version-column policy; [[heartbeat-sidecar]] — delisted-active mechanism
- [[portal-naming-conventions]] — PK / `_state` / schema-contract rules
- [[remax]], [[jll]] — the other two contributing portals
