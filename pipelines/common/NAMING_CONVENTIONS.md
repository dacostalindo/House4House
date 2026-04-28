# Naming conventions — cross-pipeline policy

This document codifies what's uniform vs source-specific across the
dlt-based bronze pipelines (`zome`, `remax`, `idealista`).

For SCD2 row-versioning rules (which fields to hash on), see
[SCD2_RULES.md](SCD2_RULES.md).

## TL;DR

- **Structural columns** (PKs, heartbeat shape, SCD2 cols, contracts)
  MUST be uniform across pipelines.
- **Leaf field names** follow the source of truth — snake_case where the
  source provides it, source's natural casing otherwise.
- **No retroactive cosmetic rewrites** of stable pipelines.

## Required structural uniformity

These conventions MUST match across pipelines. Adding a new pipeline?
Pattern-match on these from `zome` or `remax` first.

| Convention | Implementation |
|---|---|
| PK column | `{entity}_id` — e.g. `listing_id`, `development_id`, `unit_id`, `venture_id` |
| Heartbeat sidecar shape | exactly `{entity}_id`, `last_seen_date` |
| SCD2 columns (managed by dlt) | `_dlt_valid_from`, `_dlt_valid_to`, `row_hash` |
| Schema contract | `{"data_type": "freeze", "columns": "evolve"}` |
| JSONB column declaration | explicit `*_JSON_COLUMNS` tuple + `columns={col: {"data_type": "json"}}` per resource |
| Raw payload column | `raw_json` (zome) or `raw_meta` (remax/idealista) — pick one going forward; keep current for backwards-compat |
| Pass-2 enrichment flag | `_has_detail` boolean column |
| Delisted-active threshold | `last_seen_date >= current_date - 21` (silver-layer convention) |
| Pipeline name in dlt | `{source}_facts` (e.g. `zome_facts`, `remax_facts`, `idealista_developments_facts`) |
| Bronze schema | `bronze_listings` |
| Module-level cache for parallel pre-fetch | `_payload_cache: dict[str, Any] = {}`, populated lazily; do NOT call `pipeline.run()` twice in one process without `_payload_cache.clear()` |

## Leaf field names — follow the source

Each source exposes its own field names; bronze preserves them.

### Why we don't force leaf-name uniformity

We considered enforcing canonical English snake_case names across all
pipelines. Reasons we didn't:

1. **Stable pipelines would need rewrites.** zome's source returns
   Portuguese Supabase columns (`precoimovel`, `areautilhab`). remax's
   source returns camelCase JSON. idealista RE API is already snake_case
   English. Forcing one canonical scheme means rewriting at least two
   stable pipelines plus their downstream dbt models.

2. **The "future-proof to new fields" argument is weak.**
   `columns=evolve` already handles new fields (they land as NULL until
   staging maps them). A canonical-renames map adds a maintenance burden
   per new field with no benefit.

3. **Drift over time is worse than initial inconsistency.** A "rename
   discipline" requires every contributor to know the policy and apply it
   to every new field. Mixed conventions in the same table are worse than
   verbatim throughout.

4. **The cost is paid once, in dbt staging.** Silver models can apply
   business naming with `AS` aliases; the rename is in SQL where it's
   cheap to change.

### What each pipeline actually does

| Pipeline | Source field convention | What we do |
|---|---|---|
| zome | Portuguese snake_case-ish from Supabase REST | **Keep verbatim.** 4 surgical renames in `LISTINGS_RENAMES` (e.g. `localizacaolevel1imovel` → `localizacaolevel1`). |
| remax | camelCase JSON from `/api/Development/PaginatedSearch` | **Canonicalize**, because camelCase isn't acceptable as Postgres column names. ~30 renames in `_normalize_listing` and `_normalize_development` (e.g. `numberOfBedrooms` → `num_bedrooms`). |
| idealista | snake_case English from RE API; HTML elements from Universal Scraper | **Keep RE API names verbatim.** One surgical rename: drop redundant `bedrooms_count` (RE API exposes both `bedroom_count` and `bedrooms_count`). HTML-derived fields use our own snake_case names (`is_completed`, `units_count`, `unit_links`). |

### Surgical renames are allowed for

- **Redundant duplicates** — drop one.
- **Ambiguously-named display-only fields** where the source name actively
  misleads (rare; document the rationale in the rename map comment).
- **Conversion to a syntactically-valid Postgres identifier** when the
  source uses casing/punctuation Postgres can't handle (camelCase,
  hyphens).

### Surgical renames are NOT allowed for

- Cosmetic English/snake_case rewrites of already-snake_case source fields.
- Aligning one pipeline's leaf names with another's.
- Inserting business naming (`listing_price` for `property_price`) — that
  belongs in silver dbt models with `AS` aliases.

## No retroactive rewrites

If a refactor of a stable pipeline is required for a future feature, it
earns its own PR with:

- A unit test that asserts `_stable_hash` produces bytewise-identical output
  before and after the rename, on a fixed sample row.
- A dbt staging update that maps old column names → new in the same PR.
- A migration script for the bronze table (rename via `ALTER TABLE`,
  preserving data).

Do NOT bundle leaf-name renames as a side-effect of unrelated work.

## How to add a new bronze pipeline

1. Pattern-match the structural conventions (table above) from `remax/source.py`
   (closer to a typical scraping source) or `zome/source.py` (closer to a
   typical structured API source).
2. Use the source's natural field names. Apply surgical renames sparingly
   and document each in a `*_RENAMES` constant.
3. Define `*_VERSION_COLUMNS` per the rules in `SCD2_RULES.md`.
4. Define `*_JSON_COLUMNS` for any nested arrays/dicts.
5. Add a heartbeat sidecar resource per primary entity.
6. Add a `CUTOVER.md` per the existing template.
7. Add a `rollback_{source}.sql` per the existing template.
