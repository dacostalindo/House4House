---
title: Portal field map (cross-portal correspondence matrix)
type: concept
last_verified: 2026-05-18
tags: [portals, fields, mapping, sprint-04.5, dedup, cross-portal-dev-dedup, jll, reference]
---

## For future Claude

This is a **descriptive (as-is)** cross-portal correspondence matrix for the four real-estate listing portals — [[remax]], [[idealista]], [[jll]], [[zome]]. It documents which portal columns mean the same thing today, and the data-quality differences between them. Input contract for [[sprint-04.5]]'s Portuguese normalization library and matching framework, and load-bearing reference for sprint-09 Slice B-prime's `silver_unified_developments` cross-portal dedup. Not prescriptive — the canonical column contract that silver staging models implement is produced by Sprint 4.5 Task 2.5. Read this when designing cross-portal dedup, building staging models, or asking "where does X live in portal Y?".

JLL was added as the fourth portal 2026-05-18 alongside two audit corrections to existing rows ([[idealista]]'s project-name field discovery + [[remax]]'s parish-centroid GPS finding). See per-row Notes for details.

Per-column meanings live in [dbt sources YAML](../../dbt/models/staging/listings/_staging_listings__sources.yml).

## What it is

A reference table organized by canonical concept across three grains: development-level, listing/unit-level, and plot-level. Each row of the matrix names the column for each of [[remax]] / [[idealista]] / [[jll]] / [[zome]] plus a "Notes" column explaining any cross-portal divergence. Exception: JLL plots are out of scope (the `vui`-protected `/v1/Properties` endpoint requires per-visitor cookies — see [[jll]] Quirks), so the plot-level matrix stays 3-portal.

**Sources documented:**

- `bronze_listings.remax_developments`, `remax_listings`, `remax_plots`
- `bronze_listings.idealista_developments`, `idealista_development_units`, `idealista_plots`
- `bronze_listings.jll_developments`, `jll_listings` (no plot table — out of scope)
- `bronze_listings.zome_developments`, `zome_listings`, `zome_plots`

## Development-level fields

One row per real-world development across all four portals.

| Canonical concept | RE/MAX (`remax_developments`) | Idealista (`idealista_developments`) | JLL (`jll_developments`) | Zome (`zome_developments`) | Notes |
|---|---|---|---|---|---|
| **Primary key** | `development_id` (bigint) | `development_id` (varchar — alphanumeric) | `development_id` (bigint) | `venture_id` (bigint) | RE/MAX + JLL + Zome are integer; Idealista is string. Cast to varchar in silver. |
| **External display ID** | — | — | `uid` (varchar) | `emid` (varchar, e.g. `ZMPT123456`) | Zome and JLL expose stable external IDs distinct from the PK. |
| **Name** | `name` | `(regexp_match(title, '^Empreendimento (.+?) anuncia '))[1]` | `name` (also `title` for longer descriptive text) | `nome` | **Idealista correction 2026-05-18**: the project name lives in `title` (pattern `Empreendimento <NAME> anuncia <agency>, <area> — idealista`), NOT `name` (which is the address). 100% extraction rate on the Aveiro sample (95/95). Zome retains Portuguese column names. |
| **Slug** | `slug` | (derived from `area_slug` + name) | (none) | `nameunaccent` | Idealista has area_slug; closest equivalent. JLL doesn't expose a slug. |
| **GPS latitude** | `latitude` (double) | (in `raw_meta` only at dev level; available on units) | `gps_lat` (double) | `geocoordinateslat` (**varchar!**) | **RE/MAX correction 2026-05-18**: coordinates are parish-centroid-level, NOT development-precise. 51% of RE/MAX devs have NULL coords; the 49% with coords often share lat/lng with neighbouring devs in the same parish (4 distinct Coimbra developments share `(40.20674, -8.44083)`). Downstream dedup must use name-similarity to disambiguate. Zome stores as string — needs `::numeric` cast. Idealista dev-level GPS comes from joining to first unit. JLL is cleanest: typed `double` + `has_gps_location` boolean flag for explicit reliability signal. |
| **GPS longitude** | `longitude` (double) | (see latitude) | `gps_lon` (double) | `geocoordinateslong` (varchar) | Same caveats. JLL pairs with `has_gps_location` boolean. |
| **Region level 1 (broadest)** | `region_name1` | (parsed from `area_slug`) | `district` (varchar) + `district_id` (bigint) | `localizacaolevel1` | JLL has the cleanest typed columns + paired IDs. Idealista flattens region into a single slug; needs splitting. |
| **Region level 2 (concelho)** | `region_name2` | (parsed from `area_slug`) | `municipality` (varchar) + `municipality_id` (bigint) | `localizacaolevel2` | All four resolve to a concelho name. |
| **Region level 3 (freguesia)** | `region_name3` | (parsed from `area_slug`) | `parish` (varchar) + `parish_id` (bigint) | `localizacaolevel3` | RE/MAX hierarchy is strict; JLL + Zome are consistent; Idealista needs parsing. |
| **Postal code** | `zip_code` (NNNN-NNN) | (in `address_text`) | `zip_code` (varchar) | (not exposed at dev level) | RE/MAX + JLL expose it as typed columns. |
| **Address (free text)** | (in agent free text only) | `address_text` | `address` (varchar) | (in `regiao` JSONB) | All four need normalization. JLL has a clean typed column. |
| **Min price** | `minimum_price` (double) | `min_price` (numeric) + `min_price_text` (str) | `min_property_formatted_price` (varchar — formatted only, no numeric column) | `precosemformatacao` (bigint) + `preco` (str) | JLL surfaces only formatted-string prices at dev level — silver staging must parse. Zome and Idealista both keep numeric + display-formatted. RE/MAX numeric only. |
| **Max price** | (not exposed) | `max_price` (numeric) | `max_property_formatted_price` (varchar) | (not exposed) | JLL also exposes `min_available_property_formatted_price` + `max_available_property_formatted_price` for the "currently available" subset. |
| **Total unit count** | `listings_count` | `units_count` | `total_fractions` (bigint) | `imoveisdisponiveis + imoveisreservados + imoveisvendidos` | Zome computes; the others store directly. Sum gives Zome's total. |
| **Available unit count** | (compute via `listings.is_sold = false`) | (compute from unit-level statuses) | `total_available_fractions` (bigint) | `imoveisdisponiveis` | **JLL is cleanest of the 4** — direct typed column. Zome also exposes the count directly; RE/MAX + Idealista require computation. |
| **Sold unit count** | (compute via `listings.is_sold = true`) | (compute from unit-level statuses) | (derive: `total_fractions - total_available_fractions`) | `imoveisvendidos` | Zome direct; the others computed. JLL has no separate "reserved" semantics, so this derivation conflates sold + reserved. |
| **Reserved unit count** | (not flagged at unit level) | (in unit `status`) | (not exposed separately) | `imoveisreservados` | RE/MAX + JLL have no "reserved" flag. |
| **Typologies summary** | (from listings: `typology_id` aggregation) | `typology_summary` (str, e.g. "T1, T2, T3") | `available_rooms_fomated_range` (jsonb — note column-name typo "fomated") | `tipologiagrupos` (str) | Idealista + Zome pre-aggregate as strings; JLL gives JSONB; RE/MAX requires GROUP BY. |
| **Status** | (compute from `is_sold`/`is_active`) | `is_completed` (boolean) | `status` (varchar) + `status_id` (bigint) + `availability` (varchar) + `availability_id` (bigint) | `idestado` (encoded ID) | JLL exposes both status (lifecycle state) and availability (sellable inventory) as paired typed columns + IDs. Zome's encoding needs decoding via business rules; RE/MAX has no native dev-level status. |
| **Condition** | (not exposed) | (in description) | `condition` (varchar) + `condition_id` (bigint) | (not exposed) | JLL unique — surfaces dev-level condition (new build / refurbished / etc.). |
| **Description** | `description` | `description_full` (Pass 2) + `description_summary` (Pass 1) | `description` (varchar) | `descricaocompleta` (JSONB, multi-language) | All differ in shape. Zome's is JSONB. |
| **Cover image** | (first of `building_pictures`) | `cover_image` | `thumbnail` (varchar) | (first of `gallery`) | |
| **Image gallery** | `building_pictures` (JSONB) | `gallery` (JSONB, Pass 2) | `images` (JSONB) | `gallery` (JSONB) | All four are JSONB arrays of URLs. |
| **Promoter / developer** | `office_name` (RE/MAX office) | `promoter_name` | (in `agency` JSONB) | `deschub` (Zome hub display name) | RE/MAX surfaces the SELLING office; Idealista the developer; JLL the agency (JSONB); Zome the hub. **NOT directly comparable.** |
| **Listing agent name** | `agent_name` | (none at dev level) | (in `development_agents` JSONB) | `nomeconsultor` | Idealista doesn't expose dev-level agents. JLL stores agent details in a JSONB array. |
| **Listing agent phone** | `agent_phone` | (none at dev level) | (in `development_agents` JSONB) | `contactoconsultor` (+`contactoconsultor351` with country code) | Zome stores 3 phone format variants. |
| **Construction year** | (not at dev level) | (in `raw_meta`) | `year` (bigint) | (not exposed) | JLL surfaces dev-level construction year directly. |
| **Publish date** | `publish_date` | (in `raw_meta`) | `created_date` (timestamptz) | `dataentradarede` (consultant join date, NOT listing publish date) | RE/MAX + JLL both expose a true publish timestamp. JLL also has `last_modified` (timestamptz) for SCD2 change tracking. |

## Listing / unit-level fields

One row per individual unit. Note that Idealista uses `idealista_development_units` for new-construction units and `raw_idealista` for resale (legacy, slated for decommission post-[[sprint-04.5]]).

| Canonical concept | RE/MAX (`remax_listings`) | Idealista (`idealista_development_units`) | JLL (`jll_listings`) | Zome (`zome_listings`) | Notes |
|---|---|---|---|---|---|
| **Primary key** | `listing_id` (bigint) | `unit_id` (varchar) | `id` (bigint) | `listing_id` (bigint) | Idealista stringy. |
| **Parent development FK** | `development_id` | `development_id` | `development_id` (bigint) | `idemp` | Zome's link is named `idemp` (empreendimento ID). |
| **Parent development NAME** | (join via FK) | (join via FK) | `development_name` (varchar, **100% populated** — 7755/7755 listings) | (join via FK) | **JLL UNIQUE** — denormalized parent project name at listing grain. Useful for cross-portal matching without a back-join to developments. |
| **Asking price** | `listing_price` (double) | `property_price` (numeric) | `price_value` (double) | `precoimovel` (str) + `precosemformatacao` (bigint) | Zome's authoritative numeric is `precosemformatacao`. |
| **Previous price** | `previous_price` (Pass 2) | (not exposed) | (not exposed) | `valorantigo` (str) | Zome surfaces it directly; RE/MAX only via Pass 2 detail fetch. |
| **Total area (m²)** | `total_area` (double) | `lot_size` (numeric) | `gross_area` (double) | `areabrutaconst` (bigint) | Idealista uses `lot_size` for both units (built area) and plots (land); naming overload. |
| **Useful / livable area (m²)** | `living_area` (double) | `lot_size_usable` (numeric) | `net_area` (double) | `areautilhab` (bigint) | All four concepts roughly align but precise definitions vary. |
| **Land area (for unit listings with a plot)** | (not exposed) | (not exposed) | `land_area` (bigint) | (not exposed) | JLL unique — useful for villa listings. |
| **Bedroom count** | `num_bedrooms` (bigint) | `bedroom_count` (bigint) | `rooms` (bigint) | `totalquartossuite` (bigint) | Zome counts rooms+suites combined. |
| **Bathroom count** | `num_bathrooms` (bigint) | `bathroom_count` (bigint) | `bathrooms` (bigint) | `attr_wcs` (bigint) | |
| **Floor (numeric)** | `floor_number` (bigint, e.g. 0=ground, -1=basement) | `floor` (varchar — RE API gives strings like 'planta_baja', '3') | `floor` (bigint) + `floors` (bigint, total in building) | (not directly exposed) | RE/MAX + JLL are clean; Idealista needs parsing; Zome doesn't expose. JLL also exposes the building's total floor count. |
| **Floor description** | `floor_description` (Pass 2 only) | `floor_description` | (not exposed) | (not exposed) | |
| **Fraction code** | (not exposed) | `fracao` | `fraction` (varchar) | (not exposed) | JLL + Idealista expose the fração letter/code (e.g. "A", "B-2"). |
| **Typology label** | (derive from `typology_id`) | `property_subtype` | `type` (varchar) + `type_id` (bigint) | `tipologiaimovel` + `txttipologiaimovel` | Zome and JLL have both ID and free text. |
| **Energy class** | `energy_efficiency_level` (encoded ID) | `energy_certificate` (varchar, e.g. "A", "B-") | `energy_certification` (varchar) | (not at unit level) | RE/MAX needs ID→letter mapping; Idealista + JLL are string-direct. |
| **Energy cert consumption (kWh/m²·yr)** | (not exposed) | (not exposed) | `energy_certification_consumption` (double) | (not exposed) | **JLL UNIQUE** — richer than the other 3. |
| **Energy cert emission (kgCO2/m²·yr)** | (not exposed) | (not exposed) | `energy_certification_emission` (double) | (not exposed) | **JLL UNIQUE.** |
| **Energy cert validity date** | (not exposed) | (not exposed) | `energy_certification_validity` (timestamptz) | (not exposed) | **JLL UNIQUE** — when the cert expires. |
| **Energy cert number** | (not exposed) | (not exposed) | `energy_certification_number` (varchar) | (not exposed) | **JLL UNIQUE** — registry number. |
| **Status — active** | `is_active` (boolean) | `status` (varchar) | `availability` (varchar) + `availability_id` (bigint) | `idestadoimovel` (encoded ID) | Each portal models lifecycle differently. Encoded IDs need decoding. |
| **Status — sold** | `is_sold` (boolean) + `sold_date` | `last_deactivated_at` (epoch) + `status` | `status` (varchar) + `status_id` | `idestadoimovel` (encoded as one of several states) | RE/MAX has cleanest sold-flag semantics. |
| **Status — reserved** | (not exposed) | (in `status` enum) | (in `status`/`availability` enums) | `reservadozomenow` (boolean) + `idestadoimovel` | Zome has explicit boolean. |
| **Status — published online** | `is_online` (boolean) | (compute from `status`) | (compute from `availability`) | `showwebsite` (boolean) | Zome and RE/MAX have explicit booleans. |
| **GPS latitude** | `unit_latitude` (Pass 2 only, numeric) | `latitude` (numeric) | `gps_lat` (double) + `has_gps_location` (boolean) | `geocoordinateslat` (varchar) | Zome's varchar GPS again — cast in silver. JLL adds an explicit reliability boolean none of the others have. |
| **GPS longitude** | `unit_longitude` (Pass 2 only) | `longitude` | `gps_lon` (double) | `geocoordinateslong` (varchar) | |
| **Address (street)** | `address` (Pass 2 only) | `address` | `address` (varchar) | (not at unit level — only in `regiao` JSONB) | Zome doesn't surface unit-level street. |
| **Postal code** | (parse from address) | (parse from address) | (parse from address) | (not exposed) | Needs parsing for all four. |
| **Region — concelho** | `region_name2` | (in `location_hierarchy` JSONB) | `municipality` (varchar) | `localizacaolevel2` | JLL has the cleanest typed column. Idealista needs JSONB extraction. |
| **Region — freguesia** | `region_name3` | (in `location_hierarchy` JSONB) | `parish` (varchar) | `localizacaolevel3` | Same caveats. |
| **Garage spots** | `garage_spots` (bigint) | (in `property_features` JSONB) | (in `features` JSONB) | `attr_garagem_num` (bigint) | Idealista + JLL bury it in features. |
| **Has parking (boolean)** | `parking` | (in `property_features` JSONB) | (in `features` JSONB) | `attr_garagem` (0/1, bigint) | Zome stores 0/1 instead of true/false. |
| **Pool (boolean)** | (in `listing_attributes_ids` JSONB) | (in `property_features` JSONB) | (in `features` JSONB) | `attr_piscina` (bigint, 0/1) | RE/MAX + Idealista + JLL bury in arrays; Zome promotes to typed column. |
| **Elevator (boolean)** | (in `listing_attributes_ids` JSONB) | (in `property_features` JSONB) | (in `features` JSONB) | `attr_elevador` (bigint, 0/1) | Same. |
| **Construction year** | `construction_year` (Pass 2 only) | (in `property_features` JSONB) | (not exposed at listing — see dev `year`) | (not exposed) | JLL exposes it at dev grain only. |
| **Days on market** | `market_days` (Pass 2) | `modified_at` (epoch — derive) | `created_date` + `last_modified` (timestamptz — derive) | `lastdateupdate` (timestamp — derive) | All four require derivation; only RE/MAX surfaces it directly. |
| **Listing agent name** | (joined via dev's `agent_name`) | `agency_name` | (in `property_agents` JSONB) | `idconsultor` (FK — needs join) | Idealista names the agency, not the agent. JLL stores agent details in a JSONB array. |
| **Listing agent phone** | (in dev's `agent_phone`) | `agency_phone` | (in `property_agents` JSONB) | (in zome_developments via `idconsultor`) | |
| **Listing agency** | `office_name` | `agency_name` | (in `property_agency` JSONB) | (in development) | |
| **Image gallery** | `gallery` (Pass 1) + `listing_pictures` (Pass 2) | `property_images` (JSONB) | `images` (JSONB) + `blue_prints` (JSONB) + `videos` (JSONB) | `gallery` (JSONB) + `gallerymainimages` (JSONB) | RE/MAX has two separate fields; JLL separates images, blueprints, and videos; Zome separates hero from rest. |
| **Listing URL** | (compute from `slug` + agent_id) | `unit_url` | (compute from `reference` or `id`) | `url_detail_view_link` | All four are constructible. |
| **Currency** | (always EUR; not stored) | `price_currency_symbol` (always €) | `currency_format` (varchar) | `moedaimovel_descl` ("EUR") + `moedaimovel_descr` ("€") | Zome and JLL store explicit currency strings. |

## Plot-level fields (terrenos)

JLL does NOT have a plot table — its `/v1/Properties` endpoint is `vui`-protected (per-visitor cookies required for headless extraction) and the per-listing detail endpoint that would expose plot-specific fields isn't fetched. Plot coverage already exists in Idealista/RE/MAX/Zome. See [[jll]] Quirks.

| Canonical concept | RE/MAX (`remax_plots`) | Idealista (`idealista_plots`) | Zome (`zome_plots`) | Notes |
|---|---|---|---|---|
| **Primary key** | `listing_id` (bigint) | `external_listing_id` (varchar) | `listing_id` (bigint, filtered from listings by `idtipoimovel=3`) | |
| **Plot area (m²)** | `lot_size` (numeric) | `lot_size` (numeric) | `areaterreno` (bigint) | Same concept, different column names. Authoritative plot metric. |
| **Buildable / usable area** | (not exposed) | `lot_size_usable` (numeric) | `areaimplement` (bigint) | RE/MAX doesn't distinguish. |
| **Existing built area** | `built_area` (numeric) | (in `property_features`) | (sparse) | Mostly absent. |
| **Plot subtype** | (in `listing_type`) | `property_subtype` ("rural", "urban") | `tipologiaimovel` ("Urbanizável", "Rústico", "Urbano") | Each portal has its own classification system. |
| **Asking price** | `listing_price` | `property_price` | `precoimovel` (str) + `precosemformatacao` (bigint) | |
| **GPS lat/lon** | (not in plot table directly — in raw_json) | `latitude` / `longitude` | `geocoordinateslat` / `geocoordinateslong` (varchar) | RE/MAX plots may need extraction from `raw_json`. |
| **Region 2 / 3** | `region_name2` / `region_name3` | (in `location_hierarchy` JSONB) | `localizacaolevel2` / `localizacaolevel3` | |
| **Energy class** | `energy_efficiency_level` (mostly null for plots) | `energy_certificate` (mostly null) | (not exposed) | Energy certs are rare for raw plots. |

## Cross-cutting data-quality notes

These came up across multiple tables and are worth surfacing in one place for the matching framework to handle.

### Type-cast mismatches

| Field | RE/MAX | Idealista | JLL | Zome | Action in silver |
|---|---|---|---|---|---|
| GPS lat/lon | `double` | `numeric` | `double` (+ `has_gps_location` boolean for reliability) | **`varchar`** | Cast Zome's `geocoordinateslat`/`long` via `NULLIF(col, '')::numeric`. JLL is cleanest — typed + explicit reliability flag. |
| Boolean | `boolean` | `boolean` | `boolean` | mix of `boolean`, `bigint(0/1)`, `varchar('S'/'N')` | Coerce Zome's `bigint` flags via `(col = 1)::boolean`. |
| Price | `double` (RE/MAX) | `numeric` (Idealista) | `double` (`price_value` at listing); **varchar formatted-only at dev level** (`min_property_formatted_price` etc.) | `bigint` (`precosemformatacao`) + `varchar` (`precoimovel`, formatted) | Use Zome's `precosemformatacao::numeric` for math; ignore the formatted string. JLL listings have clean numeric `price_value`; JLL dev-level prices need string-parsing or aggregation from listings. |
| Date/timestamp | `date` for `publish_date`; `timestamp` for `created_date` | epoch (numeric) for `modified_at` | typed `timestamptz` for `created_date`, `last_modified`, `last_reserved_date`, `energy_certification_validity` | typed `timestamp` for `lastdateupdate` | JLL is cleanest — all timestamps are typed `timestamptz`. |

### JSON-buried fields (need extraction)

- **RE/MAX**: amenities/features live in `listing_attributes_ids` (JSONB array of integers). Need lookup table for `attribute_id` → label.
- **Idealista**: `property_features` (JSONB array of strings), `property_equipment` (same). Easier — strings already.
- **JLL**: JSONB fields at dev level: `images`, `feature_tags`, `tags`, `development_business`, `available_rooms_list`, `available_rooms_range`, `available_rooms_fomated_range`, `area_util_range`, `agency`, `development_agents`, `raw_json`. JSONB at listing level: `images`, `features`, `feature_tags`, `tags`, `property_business`, `blue_prints`, `videos`, `property_agency`, `property_agents`, `raw_json`. Promoter/agency data is consistently JSONB across all listings.
- **Zome**: features promoted to top-level `attr_*` columns (pool, elevator, garage, parking, accessibility). No extraction needed.

### Encoded IDs (need lookup tables)

- **RE/MAX**: `listing_status_id`, `typology_id`, `floor_id`, `energy_efficiency_level`, `business_type_id`, `country_id` — TODO source-of-truth mapping. (Currently no upstream lookup table exposed.)
- **Idealista**: very few encoded IDs (mostly string labels) — `property_subtype`, `status`, `operation` are already labels.
- **JLL**: every `*_id` column has a paired text column at the source: `district_id` + `district`, `municipality_id` + `municipality`, `parish_id` + `parish`, `status_id` + `status`, `availability_id` + `availability`, `condition_id` + `condition`, `type_id` + `type`, `master_type_id` (no paired text), `country_id` + `country` (+ `country_iso`), `agency_id`, `master_type_id`. **No lookup table needed for the typed columns** — JLL denormalizes at source. The `_id` columns are useful as stable cross-snapshot keys.
- **Zome**: `idcondicaoimovel`, `idtipoimovel`, `idtiponegocio`, `idestadoimovel`, `idtipologia` — decoded via `ref_zome_*` lookup tables (loaded by the Zome DAG in REPLACE mode).

### Pass 1 / Pass 2 / Pass 3 sparsity

- **RE/MAX**: Pass 2 enrichment only fires for `is_online = true` listings (~45% of total). Pass 2 fields are mostly NULL for offline listings: `address`, `apartment_number`, `market_days`, `previous_price`, `construction_year`, `floor_description`, `listing_rooms`, `listing_pictures`, `unit_latitude`, `unit_longitude`. Use `_has_detail` to filter.
- **Idealista**: Pass 2 (dev detail) fires for all developments. Pass 3 (RE API per unit) fires for all units but stub responses (≤6 fields) flagged via `_re_api_stub` upstream. Use `_has_detail` to filter.
- **JLL**: single-pass — dlt fetches everything in one request per development. No sparsity by enrichment phase.
- **Zome**: single-pass — no sparsity by enrichment phase.

### Region hierarchy variability

- **RE/MAX**: hierarchy is strict (`region_name1` always set, then `2`, then `3`).
- **Idealista**: flat — `area_slug` is a single token. `location_hierarchy` JSONB on units gives the chain.
- **JLL**: **cleanest of the 4** — typed `district` (L1) + `municipality` (L2) + `parish` (L3) columns, each with a paired `_id`. Coverage geographic-restricted to Lisboa / Porto / Faro / Setúbal distritos.
- **Zome**: levels 1–3 always present; levels 4–5 sparse and inconsistent.

### Geographic coverage asymmetry (added 2026-05-18)

- **RE/MAX, Idealista, Zome**: nationwide coverage.
- **JLL**: Lisboa, Porto, Faro, Setúbal distritos only. **Zero Aveiro coverage** as of 2026-05-17 audit (0 of 215 dev rows). Relevant for sprint-10 portal expansion but adds zero rows to the Aveiro v1 wedge demo's `silver_unified_developments`. JLL staging models still ship in sprint-09 Slice B-prime PR-B for future-proofing.

### What `row_hash` does NOT cover (across all 4 portals)

- All JSONB columns (galleries, descriptions, attribute arrays).
- Snapshot-derived fields that change every run (modified timestamps, market_days, anything Pass-2-fetched at run time).
- Immutable physical attributes (GPS, address, construction year — changes here are corrections, not events).

This means: matching by GPS or address is safe (those don't drift across SCD2 versions). Matching by price or status will surface real changes. See [[scd2-row-hash]] for the policy.

## Open questions for [[sprint-04.5]] / [[sprint-09]]

1. **Promoter resolution** — RE/MAX surfaces the selling office, Idealista the developer, JLL the agency (JSONB), Zome the hub. Cross-portal promoter dedup is a separate problem from listing dedup.
2. **Reserved units** — RE/MAX + JLL have no "reserved" status. Cross-portal absorption modeling (S5+) needs to handle this asymmetry.
3. **Floor parsing** — Idealista's `floor` is varchar (string codes mixed with integers). Needs a Portuguese-aware parser.
4. **Encoded ID dictionaries** — RE/MAX has 6+ encoded IDs with no upstream lookup. Sprint 4.5 either needs a CV-derived dictionary or a hand-curated reference table. JLL avoids this problem via denormalized paired text columns.
5. **RE/MAX coord precision** (sprint-09 Slice B-prime PR-B / sprint-10 portal expansion) — RE/MAX devs are geocoded to parish centroid. Decide whether to Nominatim-enrich addresses upstream or rely on `name_similarity` to disambiguate downstream. Currently the latter, per Decision 8 of the Slice B-prime plan.

## See also

- [[scd2-row-hash]] — version-column include/exclude policy per portal
- [[portal-naming-conventions]] — structural-uniformity rules + leaf-name policy
- [[portal-plot-conventions]] — plot-table conventions
- [[heartbeat-sidecar]] — "is this entity still in the source?" mechanism
- [dbt sources YAML](../../dbt/models/staging/listings/_staging_listings__sources.yml) — per-column descriptions and source paths
- [[idealista]], [[remax]], [[jll]], [[zome]] — the four current portal pipelines
- [[sprint-04.5]] — the matching framework that consumes this map
- [[sprint-09]] — Slice B-prime's `silver_unified_developments` uses this map as its canonical-name extraction reference
