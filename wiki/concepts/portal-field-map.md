---
title: Portal field map (cross-portal correspondence matrix)
type: concept
last_verified: 2026-05-12
tags: [portals, fields, mapping, sprint-04.5, dedup, reference]
---

## For future Claude

This is a **descriptive (as-is)** cross-portal correspondence matrix for the three real-estate listing portals — [[remax]], [[idealista]], [[zome]]. It documents which portal columns mean the same thing today, and the data-quality differences between them. Input contract for [[sprint-04.5]]'s Portuguese normalization library and matching framework. Not prescriptive — the canonical column contract that silver staging models implement is produced by Sprint 4.5 Task 2.5. Read this when designing cross-portal dedup, building staging models, or asking "where does X live in portal Y?".

Per-column meanings live in [dbt sources YAML](../../dbt/models/staging/listings/_staging_listings__sources.yml).

## What it is

A reference table organized by canonical concept across three grains: development-level, listing/unit-level, and plot-level. Each row of the matrix names the column for each of [[remax]] / [[idealista]] / [[zome]] plus a "Notes" column explaining any cross-portal divergence.

**Sources documented:**

- `bronze_listings.remax_developments`, `remax_listings`, `remax_plots`
- `bronze_listings.idealista_developments`, `idealista_development_units`, `idealista_plots`
- `bronze_listings.zome_developments`, `zome_listings`, `zome_plots`

## Development-level fields

One row per real-world development across all three portals.

| Canonical concept | RE/MAX (`remax_developments`) | Idealista (`idealista_developments`) | Zome (`zome_developments`) | Notes |
|---|---|---|---|---|
| **Primary key** | `development_id` (bigint) | `development_id` (varchar — alphanumeric) | `venture_id` (bigint) | RE/MAX + Zome are integer; Idealista is string. Cast to varchar in silver. |
| **External display ID** | — | — | `emid` (varchar, e.g. `ZMPT123456`) | Zome only — its public-facing ID is distinct from the PK. |
| **Name** | `name` | `name` | `nome` | Zome retains Portuguese column names. |
| **Slug** | `slug` | (derived from `area_slug` + name) | `nameunaccent` | Idealista has area_slug; closest equivalent. |
| **GPS latitude** | `latitude` (double) | (in `raw_meta` only at dev level; available on units) | `geocoordinateslat` (**varchar!**) | Zome stores as string — needs `::numeric` cast. Idealista dev-level GPS comes from joining to first unit. |
| **GPS longitude** | `longitude` (double) | (see latitude) | `geocoordinateslong` (varchar) | Same caveats. |
| **Region level 1 (broadest)** | `region_name1` | (parsed from `area_slug`) | `localizacaolevel1` | Idealista flattens region into a single slug; needs splitting. |
| **Region level 2 (concelho)** | `region_name2` | (parsed from `area_slug`) | `localizacaolevel2` | All three ultimately resolve to a concelho name. |
| **Region level 3 (freguesia)** | `region_name3` | (parsed from `area_slug`) | `localizacaolevel3` | RE/MAX hierarchy is strict; Zome's is consistent; Idealista needs parsing. |
| **Postal code** | `zip_code` (NNNN-NNN) | (in `address_text`) | (not exposed at dev level) | Only RE/MAX exposes it as a typed column. |
| **Address (free text)** | (in agent free text only) | `address_text` | (in `regiao` JSONB) | All three need normalization. |
| **Min price** | `minimum_price` (double) | `min_price` (numeric) + `min_price_text` (str) | `precosemformatacao` (bigint) + `preco` (str) | Zome and Idealista both keep numeric + display-formatted. RE/MAX numeric only. |
| **Total unit count** | `listings_count` | `units_count` | `imoveisdisponiveis + imoveisreservados + imoveisvendidos` | Zome computes; others store directly. Sum gives Zome's total. |
| **Available unit count** | (compute via `listings.is_sold = false`) | (compute from unit-level statuses) | `imoveisdisponiveis` | Only Zome exposes the available count directly. |
| **Sold unit count** | (compute via `listings.is_sold = true`) | (compute from unit-level statuses) | `imoveisvendidos` | Same — Zome direct, others computed. |
| **Reserved unit count** | (not flagged at unit level) | (in unit `status`) | `imoveisreservados` | RE/MAX has no "reserved" flag at unit level. |
| **Typologies summary** | (from listings: `typology_id` aggregation) | `typology_summary` (str, e.g. "T1, T2, T3") | `tipologiagrupos` (str) | Idealista + Zome pre-aggregate; RE/MAX requires GROUP BY. |
| **Status** | (compute from `is_sold`/`is_active`) | `is_completed` (boolean) | `idestado` (encoded ID) | Zome's encoding needs decoding via business rules; RE/MAX has no native dev-level status. |
| **Description** | `description` | `description_full` (Pass 2) + `description_summary` (Pass 1) | `descricaocompleta` (JSONB, multi-language) | All three differ in shape. Zome's is JSONB. |
| **Cover image** | (first of `building_pictures`) | `cover_image` | (first of `gallery`) | |
| **Image gallery** | `building_pictures` (JSONB) | `gallery` (JSONB, Pass 2) | `gallery` (JSONB) | All three are JSONB arrays of URLs. |
| **Promoter / developer** | `office_name` (RE/MAX office) | `promoter_name` | `deschub` (Zome hub display name) | RE/MAX surfaces the SELLING office; Idealista the developer; Zome the hub. **NOT directly comparable.** |
| **Listing agent name** | `agent_name` | (none at dev level) | `nomeconsultor` | Idealista doesn't expose dev-level agents. |
| **Listing agent phone** | `agent_phone` | (none at dev level) | `contactoconsultor` (+`contactoconsultor351` with country code) | Zome stores 3 phone format variants. |
| **Publish date** | `publish_date` | (in `raw_meta`) | `dataentradarede` (consultant join date, NOT listing publish date) | RE/MAX is the only one with a true dev-publish timestamp. |

## Listing / unit-level fields

One row per individual unit. Note that Idealista uses `idealista_development_units` for new-construction units and `raw_idealista` for resale (legacy, slated for decommission post-[[sprint-04.5]]).

| Canonical concept | RE/MAX (`remax_listings`) | Idealista (`idealista_development_units`) | Zome (`zome_listings`) | Notes |
|---|---|---|---|---|
| **Primary key** | `listing_id` (bigint) | `unit_id` (varchar) | `listing_id` (bigint) | Idealista stringy. |
| **Parent development FK** | `development_id` | `development_id` | `idemp` | Zome's link is named `idemp` (empreendimento ID). |
| **Asking price** | `listing_price` (double) | `property_price` (numeric) | `precoimovel` (str) + `precosemformatacao` (bigint) | Zome's authoritative numeric is `precosemformatacao`. |
| **Previous price** | `previous_price` (Pass 2) | (not exposed) | `valorantigo` (str) | Zome surfaces it directly; RE/MAX only via Pass 2 detail fetch. |
| **Total area (m²)** | `total_area` (double) | `lot_size` (numeric) | `areabrutaconst` (bigint) | Idealista uses `lot_size` for both units (built area) and plots (land); naming overload. |
| **Useful / livable area (m²)** | `living_area` (double) | `lot_size_usable` (numeric) | `areautilhab` (bigint) | All three concepts roughly align but precise definitions vary. |
| **Bedroom count** | `num_bedrooms` (bigint) | `bedroom_count` (bigint) | `totalquartossuite` (bigint) | Zome counts rooms+suites combined. |
| **Bathroom count** | `num_bathrooms` (bigint) | `bathroom_count` (bigint) | `attr_wcs` (bigint) | |
| **Floor (numeric)** | `floor_number` (bigint, e.g. 0=ground, -1=basement) | `floor` (varchar — RE API gives strings like 'planta_baja', '3') | (not directly exposed) | RE/MAX is the cleanest; Idealista needs parsing; Zome doesn't expose. |
| **Floor description** | `floor_description` (Pass 2 only) | `floor_description` | (not exposed) | |
| **Typology label** | (derive from `typology_id`) | `property_subtype` | `tipologiaimovel` + `txttipologiaimovel` | Zome has both ID and free text. |
| **Energy class** | `energy_efficiency_level` (encoded ID) | `energy_certificate` (varchar, e.g. "A", "B-") | (not at unit level) | RE/MAX needs ID→letter mapping; Idealista is string-direct. |
| **Status — active** | `is_active` (boolean) | `status` (varchar) | `idestadoimovel` (encoded ID) | Each portal models lifecycle differently. Encoded IDs need decoding. |
| **Status — sold** | `is_sold` (boolean) + `sold_date` | `last_deactivated_at` (epoch) + `status` | `idestadoimovel` (encoded as one of several states) | RE/MAX has cleanest sold-flag semantics. |
| **Status — reserved** | (not exposed) | (in `status` enum) | `reservadozomenow` (boolean) + `idestadoimovel` | Zome has explicit boolean. |
| **Status — published online** | `is_online` (boolean) | (compute from `status`) | `showwebsite` (boolean) | Zome and RE/MAX have explicit booleans. |
| **GPS latitude** | `unit_latitude` (Pass 2 only, numeric) | `latitude` (numeric) | `geocoordinateslat` (varchar) | Zome's varchar GPS again — cast in silver. |
| **GPS longitude** | `unit_longitude` (Pass 2 only) | `longitude` | `geocoordinateslong` (varchar) | |
| **Address (street)** | `address` (Pass 2 only) | `address` | (not at unit level — only in `regiao` JSONB) | Zome doesn't surface unit-level street. |
| **Postal code** | (parse from address) | (parse from address) | (not exposed) | Needs parsing for all 3. |
| **Region — concelho** | `region_name2` | (in `location_hierarchy` JSONB) | `localizacaolevel2` | Idealista needs JSONB extraction. |
| **Region — freguesia** | `region_name3` | (in `location_hierarchy` JSONB) | `localizacaolevel3` | Same caveats. |
| **Garage spots** | `garage_spots` (bigint) | (in `property_features` JSONB) | `attr_garagem_num` (bigint) | Idealista buries it in features array. |
| **Has parking (boolean)** | `parking` | (in `property_features` JSONB) | `attr_garagem` (0/1, bigint) | Zome stores 0/1 instead of true/false. |
| **Pool (boolean)** | (in `listing_attributes_ids` JSONB) | (in `property_features` JSONB) | `attr_piscina` (bigint, 0/1) | RE/MAX + Idealista bury in arrays; Zome promotes to typed column. |
| **Elevator (boolean)** | (in `listing_attributes_ids` JSONB) | (in `property_features` JSONB) | `attr_elevador` (bigint, 0/1) | Same. |
| **Construction year** | `construction_year` (Pass 2 only) | (in `property_features` JSONB) | (not exposed) | Sparse for all 3. |
| **Days on market** | `market_days` (Pass 2) | `modified_at` (epoch — derive) | `lastdateupdate` (timestamp — derive) | All three require derivation; only RE/MAX surfaces it directly. |
| **Listing agent name** | (joined via dev's `agent_name`) | `agency_name` | `idconsultor` (FK — needs join) | Idealista names the agency, not the agent. |
| **Listing agent phone** | (in dev's `agent_phone`) | `agency_phone` | (in zome_developments via `idconsultor`) | |
| **Image gallery** | `gallery` (Pass 1) + `listing_pictures` (Pass 2) | `property_images` (JSONB) | `gallery` (JSONB) + `gallerymainimages` (JSONB) | RE/MAX has two separate fields; Zome separates hero from rest. |
| **Listing URL** | (compute from `slug` + agent_id) | `unit_url` | `url_detail_view_link` | All three are constructible. |
| **Currency** | (always EUR; not stored) | `price_currency_symbol` (always €) | `moedaimovel_descl` ("EUR") + `moedaimovel_descr` ("€") | Zome stores both forms. |

## Plot-level fields (terrenos)

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

| Field | RE/MAX | Idealista | Zome | Action in silver |
|---|---|---|---|---|
| GPS lat/lon | `double` | `numeric` | **`varchar`** | Cast Zome's `geocoordinateslat`/`long` via `NULLIF(col, '')::numeric`. |
| Boolean | `boolean` | `boolean` | mix of `boolean`, `bigint(0/1)`, `varchar('S'/'N')` | Coerce Zome's `bigint` flags via `(col = 1)::boolean`. |
| Price | `double` (RE/MAX) | `numeric` (Idealista) | `bigint` (`precosemformatacao`) + `varchar` (`precoimovel`, formatted) | Use Zome's `precosemformatacao::numeric` for math; ignore the formatted string. |

### JSON-buried fields (need extraction)

- **RE/MAX**: amenities/features live in `listing_attributes_ids` (JSONB array of integers). Need lookup table for `attribute_id` → label.
- **Idealista**: `property_features` (JSONB array of strings), `property_equipment` (same). Easier — strings already.
- **Zome**: features promoted to top-level `attr_*` columns (pool, elevator, garage, parking, accessibility). No extraction needed.

### Encoded IDs (need lookup tables)

- **RE/MAX**: `listing_status_id`, `typology_id`, `floor_id`, `energy_efficiency_level`, `business_type_id`, `country_id` — TODO source-of-truth mapping. (Currently no upstream lookup table exposed.)
- **Idealista**: very few encoded IDs (mostly string labels) — `property_subtype`, `status`, `operation` are already labels.
- **Zome**: `idcondicaoimovel`, `idtipoimovel`, `idtiponegocio`, `idestadoimovel`, `idtipologia` — decoded via `ref_zome_*` lookup tables (loaded by the Zome DAG in REPLACE mode).

### Pass 1 / Pass 2 / Pass 3 sparsity

- **RE/MAX**: Pass 2 enrichment only fires for `is_online = true` listings (~45% of total). Pass 2 fields are mostly NULL for offline listings: `address`, `apartment_number`, `market_days`, `previous_price`, `construction_year`, `floor_description`, `listing_rooms`, `listing_pictures`, `unit_latitude`, `unit_longitude`. Use `_has_detail` to filter.
- **Idealista**: Pass 2 (dev detail) fires for all developments. Pass 3 (RE API per unit) fires for all units but stub responses (≤6 fields) flagged via `_re_api_stub` upstream. Use `_has_detail` to filter.
- **Zome**: single-pass — no sparsity by enrichment phase.

### Region hierarchy variability

- **RE/MAX**: hierarchy is strict (`region_name1` always set, then `2`, then `3`).
- **Idealista**: flat — `area_slug` is a single token. `location_hierarchy` JSONB on units gives the chain.
- **Zome**: levels 1–3 always present; levels 4–5 sparse and inconsistent.

### What `row_hash` does NOT cover (across all 3 portals)

- All JSONB columns (galleries, descriptions, attribute arrays).
- Snapshot-derived fields that change every run (modified timestamps, market_days, anything Pass-2-fetched at run time).
- Immutable physical attributes (GPS, address, construction year — changes here are corrections, not events).

This means: matching by GPS or address is safe (those don't drift across SCD2 versions). Matching by price or status will surface real changes. See [[scd2-row-hash]] for the policy.

## Open questions for [[sprint-04.5]]

1. **Promoter resolution** — RE/MAX surfaces the selling office, Idealista the developer, Zome the hub. Cross-portal promoter dedup is a separate problem from listing dedup.
2. **Reserved units** — RE/MAX has no "reserved" status. Cross-portal absorption modeling (S5+) needs to handle this asymmetry.
3. **Floor parsing** — Idealista's `floor` is varchar (string codes mixed with integers). Needs a Portuguese-aware parser.
4. **Encoded ID dictionaries** — RE/MAX has 6+ encoded IDs with no upstream lookup. Sprint 4.5 either needs a CV-derived dictionary or a hand-curated reference table.

## See also

- [[scd2-row-hash]] — version-column include/exclude policy per portal
- [[portal-naming-conventions]] — structural-uniformity rules + leaf-name policy
- [[portal-plot-conventions]] — plot-table conventions
- [[heartbeat-sidecar]] — "is this entity still in the source?" mechanism
- [dbt sources YAML](../../dbt/models/staging/listings/_staging_listings__sources.yml) — per-column descriptions and source paths
- [[idealista]], [[remax]], [[zome]] — the three current portal pipelines
- [[sprint-04.5]] — the matching framework that consumes this map
