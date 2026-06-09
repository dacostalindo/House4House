---
title: imovirtual listings silver — dev_units only, 5th UNION arm
type: decision
last_verified: 2026-06-09
tags: [imovirtual, silver, unified-listings, portals]
confidence: high
---

## For future Claude

This is a decision record about adding [[imovirtual]] as the 5th `UNION ALL` arm of `unified_listings_residential` via `stg_portal_listings_imovirtual`. It locks the scope (dev_units only — no plots, no synthetic dev-as-listing rows, no resale), the field map (which bronze column maps to which canonical column), the empirical floor-plan finding (unit-level plans are unit-specific and have zero URL overlap with dev-level master plans, so dev plans stay on `unified_developments` and don't bleed into the listings silver), and the post-hoc verification numbers from the first end-to-end run.

## Decision

Add `dbt/models/staging/portals/stg_portal_listings_imovirtual.sql` and union it into `unified_listings_residential` as the 5th portal arm. Grain: imovirtual_development_units (national, ~4,440 rows). Plots (Aveiro terreno) and a synthetic dev-as-listing variant are explicitly out of scope. Resale doesn't exist for imovirtual by construction — the ingest scope is `/comprar/empreendimento`.

Unit floor plans are the **UNION of two disjoint per-unit feeds**:
- (a) the native `floor_plans` JSONB array (lifted into bronze 2026-06-09 alongside `bathrooms_num`, `build_year`, `terrain_area_m`, `extras_types`, `security_types`, `advertiser_type`, `building_material`, `building_ownership`, `remote_services`) — olxcdn JPGs, 29.62% coverage
- (b) the `raw_json->'links'->>'localPlanUrl'` scalar (still inside raw_json, NOT pivoted to a typed column) — egorealestate PDFs + agency hosts (povoa.imob.properties, luximos.imob.properties, …), 44.82% coverage

`floor_plan_source = 'imovirtual_units'`, **combined coverage 68.83%** (3,056/4,440 units). Only 5.6% URL overlap between the two feeds (`both = 249`, `only_floorPlans = 1,066`, `only_localPlanUrl = 1,741`) — they're substantially independent. This jumps imovirtual to the **second-best floor-plan source after [[jll]]** in the cross-portal coverage table, ahead of [[idealista]] (32.59%).

Amenities derived via JSONB containment on `extras_types` (structured enum: `extras_types::lift`, `::garage`, `::balcony`, `::terrace`, `::garden`, `::pool`, etc.) — NOT regex over description text. Two-key OR groups: lift+elevator → `has_elevator`, garage+parking → `has_parking`, terrace+balcony → `has_terrace`.

Coordinates inherited from the parent dev via JOIN on `development_id` against the active SCD2 version of `imovirtual_developments` (unit `location.coordinates` is `(0,0)` in bronze, mapped to NULL by the normalizer). `dim_geography` spatial resolution happens later inside `unified_listings_residential.with_geom` — staging stays flat.

## Why

**Why dev_units only.** imovirtual has three bronze grains: developments, development_units, plots. Plots are terreno (non-residential) and Aveiro-scoped — they violate `unified_listings_residential`'s residential semantic and would mix scopes. Developments are dev-grain, already represented in [[cross-portal-dev-dedup|unified_developments]]; injecting them as synthetic listings would double-count against per-unit rows. dev_units is the only grain that fits the listing-grain contract.

**Why unit-level plans, not dev-level.** Empirical analysis 2026-06-09 (on the `floor_plans` array — feed (a) above):
- Dev-level coverage: **19.3%** (154/798 devs)
- Unit-level coverage: **29.6%** (1,315/4,440 units) — higher than dev
- **URL overlap: 0.00%** (2,141 distinct unit URLs, zero appear in any dev's `floor_plans` array)
- Of 154 devs with plans, 112 have all-units-with-plans, 10 have some, 32 have NO units with plans

The 0% URL overlap proves the two arrays are semantically distinct artifacts: dev-level plans are master/site plans (dev-grain), unit-level plans are per-unit layouts (listing-grain). Mixing them via COALESCE would pollute the per-listing signal. Dev-level plans remain a deferred concern for the dev-grain silver.

**Why BOTH `floor_plans` array AND `localPlanUrl` scalar.** A second unit-grain plan feed was found at `raw_json->'links'->'localPlanUrl'` (alongside `videoUrl`, `view3dUrl`, `walkaroundUrl`). NOT pivoted to a typed column in the bronze normalizer — read in-place from raw_json. Coverage 44.82%, only 5.6% URL overlap with the `floor_plans` array (the two feeds are substantially independent — different upstream CDNs entirely: olxcdn vs egorealestate/agency hosts). Lifting only the `floor_plans` array would silently drop 1,741 unit plans that exist exclusively in `localPlanUrl`. UNION'ing both pushes imovirtual from a middling 29.6% plan source to a **strong 68.83% — second only to jll** (92.72%).

**Why `extras_types` containment beats description regex.** `extras_types` is a typed JSONB array of 18 canonical enum values across the corpus. Containment (`?|`) is a clean equality match against the enum dictionary; description regex would have to handle Portuguese morphology + free-text mistakes. The jll model uses regex because jll's `features` is unstructured; imovirtual gives us the structured signal natively.

**Why bathrooms gets a CASE not a straight cast.** 16% of `bathrooms_num` values are the enum literal `bathrooms_num::4_or_more` (725 rows). Floor at 4 — closest honest INTEGER representation. Pure cast crashes; NULL'ing loses 725 rows of real signal.

**Why `condition = NULL`.** `construction_status` carries `to_completion` / `ready_to_use` — that's a **build-status** signal (under-construction vs finished), not a condition signal (used/new/needs-work) as the other portals populate `condition`. Mapping it to `condition` lies semantically. It lands on `property_subtype` instead, preserving the signal without polluting `condition`.

**Why `agency_name` and `listing_title = NULL`.** imovirtual `promoter` is dev-level and unreliable (per user feedback 2026-06-09). The per-unit `title` bronze column was dropped by dlt as all-NULL — same fate as `status` (`listing_status_raw` is also NULL).

**Why `operation_type` is mapped, not hardcoded.** Empirical: 4,421 SELL + 19 RENT in bronze. Hardcoding `'sale'` would silently mislabel the 19 rentals.

## Consequences

- `unified_listings_residential` total rows: ~7,500 → **11,967** (5 portals).
- imovirtual is now the **largest single contributor** at 4,413 silver rows (the price/area filters drop 27 of the 4,440 raw units).
- **100% `unified_development_id` linkage** for imovirtual rows — the dual-signal dedup that shipped in #54 already captured every imovirtual dev into `unified_developments.portal_refs`, so the lateral lookup hits on every row.
- Cross-portal floor-plan coverage table grows from 4 to 5 sources; imovirtual_units (combined feeds) sits between jll_blueprints (92.72%) and idealista_tagged (32.59%) — the new second-best plan signal.
- `terrain_area_m` is populated for 204 imovirtual units (4.6%) — that gives the silver `land_area_m2` column its third populating source (after jll's `land_area` and zome's `areaterreno`); strengthens the villa+terreno consumer story.
- The bronze normalizer changes (new columns) don't need a re-load — the SCD2 path adds the columns silently and the next dlt run backfills.
- Wiki Propagation Rule discharged: [[imovirtual]] source page Silver section + Last verified updated; this decision record created; `wiki/log.md` and `wiki/index.md` entries added.

## Status

accepted
