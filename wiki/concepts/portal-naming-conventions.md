---
title: Portal pipeline naming conventions
type: concept
last_verified: 2026-05-12
tags: [naming, conventions, portals, dlt, bronze, scd2]
---

## For future Claude

This is a concept page about the naming conventions that govern the dlt-based portal pipelines ([[idealista]], [[jll]], [[remax]], [[zome]]). It explains what MUST be uniform across pipelines (PKs, heartbeat shape, SCD2 columns, schema contracts) and why leaf field names follow the source rather than a global canonical scheme. Read this before adding a new portal bronze pipeline or proposing a "rename for consistency" PR.

## What it is

A cross-pipeline policy distinguishing **structural uniformity** (required across all dlt portal pipelines) from **leaf-field naming** (intentionally heterogeneous — follows each source's natural names). The rules are enforced by code review, not lint; the cost of a wrong choice is downstream dbt refactor.

## Why

Three failure modes the policy prevents:

1. **Rewrite cascades from premature canonicalization.** Forcing every pipeline onto English snake_case would mean rewriting at least two of the three stable pipelines (zome's Portuguese Supabase columns, remax's camelCase JSON) plus their downstream dbt models. The cost is high; the benefit is cosmetic.
2. **Hidden drift over time.** A "rename discipline" requires every contributor to know the policy and apply it to every new field. Mixed conventions in the same table are worse than verbatim throughout. The wiki rule states the principle so the next contributor doesn't reinvent it.
3. **Lost business naming opportunity.** Silver dbt models apply business names with cheap `AS` aliases. Burying the rename in bronze locks future analytics into one naming choice; the dbt layer is where naming should be debated and changed.

Structural uniformity is non-negotiable because downstream code (heartbeat checks, SCD2 mechanics, the silver "currently active" filter) keys off these column names.

## How

### Required structural uniformity

| Convention | Implementation |
|---|---|
| PK column | `{entity}_id` — e.g. `listing_id`, `development_id`, `unit_id`, `venture_id` |
| Heartbeat sidecar shape | exactly `{entity}_id`, `last_seen_date` |
| SCD2 columns (managed by dlt) | `_dlt_valid_from`, `_dlt_valid_to`, `row_hash` |
| Schema contract | `{"data_type": "freeze", "columns": "evolve"}` |
| JSONB column declaration | explicit `*_JSON_COLUMNS` tuple + `columns={col: {"data_type": "json"}}` per resource |
| Raw payload column | `raw_json` ([[zome]]) or `raw_meta` ([[remax]] / [[idealista]]) — pick one going forward; keep current for backwards-compat |
| Pass-2 enrichment flag | `_has_detail` boolean column |
| Delisted-active threshold | `last_seen_date >= current_date - 21` (silver-layer convention; see [[heartbeat-sidecar]]) |
| Pipeline name in dlt | `{source}_facts` (e.g. `zome_facts`, `remax_facts`, `idealista_developments_facts`) |
| Bronze schema | `bronze_listings` |
| Module-level cache for parallel pre-fetch | `_payload_cache: dict[str, Any] = {}`, populated lazily; do NOT call `pipeline.run()` twice in one process without `_payload_cache.clear()` (see [[payload-cache-lifecycle]]) |

Adding a new portal pipeline? Pattern-match these from `zome` or `remax` first.

### Leaf field names — follow the source

Each source exposes its own field names; bronze preserves them.

| Pipeline | Source field convention | What we do |
|---|---|---|
| [[zome]] | Portuguese snake_case-ish from Supabase REST | **Keep verbatim.** 4 surgical renames in `LISTINGS_RENAMES` (e.g. `localizacaolevel1imovel` → `localizacaolevel1`). |
| [[remax]] | camelCase JSON from `/api/Development/PaginatedSearch` | **Canonicalize**, because camelCase isn't valid as Postgres column names. ~30 renames in `_normalize_listing` and `_normalize_development` (e.g. `numberOfBedrooms` → `num_bedrooms`). |
| [[idealista]] | snake_case English from RE API; HTML elements from Universal Scraper | **Keep RE API names verbatim.** One surgical rename: drop redundant `bedrooms_count` (RE API exposes both `bedroom_count` and `bedrooms_count`). HTML-derived fields use our own snake_case names (`is_completed`, `units_count`, `unit_links`). |

### Surgical renames ARE allowed for

- **Redundant duplicates** — drop one.
- **Ambiguously-named display-only fields** where the source name actively misleads (rare; document in the rename map comment).
- **Conversion to a syntactically-valid Postgres identifier** when the source uses casing/punctuation Postgres can't handle (camelCase, hyphens).

### Surgical renames are NOT allowed for

- Cosmetic English/snake_case rewrites of already-snake_case source fields.
- Aligning one pipeline's leaf names with another's.
- Inserting business naming (`listing_price` for `property_price`) — that belongs in silver dbt models with `AS` aliases.

### No retroactive cosmetic rewrites

If a refactor of a stable pipeline IS required for a future feature, it earns its own PR with:

- A unit test that asserts `_stable_hash` produces bytewise-identical output before and after the rename, on a fixed sample row.
- A dbt staging update that maps old column names → new in the same PR.
- A migration script for the bronze table (rename via `ALTER TABLE`, preserving data).

Do NOT bundle leaf-name renames as a side-effect of unrelated work.

### How to add a new bronze portal pipeline

1. Pattern-match the structural conventions (table above) from `remax/source.py` (closer to a typical scraping source) or `zome/source.py` (closer to a typical structured API source).
2. Use the source's natural field names. Apply surgical renames sparingly and document each in a `*_RENAMES` constant.
3. Define `*_VERSION_COLUMNS` per the rules in [[scd2-row-hash]].
4. Define `*_JSON_COLUMNS` for any nested arrays/dicts.
5. Add a [[heartbeat-sidecar]] resource per primary entity.
6. Add a `CUTOVER.md` per the existing template.
7. Add a `rollback_{source}.sql` per the existing template.

## See also

- [[scd2-row-hash]] — which fields go in `*_VERSION_COLUMNS`
- [[heartbeat-sidecar]] — the companion "is this entity still in the source?" mechanism
- [[portal-plot-conventions]] — how plot/terreno tables differ from housing
- [[portal-field-map]] — cross-portal column correspondence matrix (as-is, descriptive)
- [[bronze-permissive]] — the broader bronze policy this implements
- [[payload-cache-lifecycle]] — module-level `_payload_cache` discipline
- [[idealista]], [[jll]], [[remax]], [[zome]] — the four current portal pipelines
