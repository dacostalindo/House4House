---
title: Portal plot (terreno) ingestion conventions
type: concept
last_verified: 2026-05-12
tags: [plots, terreno, portals, dlt, bronze, scd2]
---

## For future Claude

This is a concept page about how plots/terrenos (land listings without a building) are modelled across the dlt-based portal pipelines ([[idealista]], [[remax]], [[zome]]). It explains why plots live in separate `*_plots` tables rather than being filtered out of a housing table, the plot-specific SCD2 columns, and the per-pipeline ingestion strategies. Read this before extending plot ingestion or considering a "unify housing and plots" refactor.

## What it is

Each portal bronze pipeline has a separate `{source}_plots` SCD2 table + `{source}_plots_state` heartbeat sidecar. Plots are NOT merged into the housing `{source}_listings` table — they have different field sets, different SCD2 versioning drivers, and different downstream analytics.

## Why

Plots and housing diverge in three structural ways:

| Aspect | Housing | Plots |
|---|---|---|
| **Has** | `num_bedrooms`, `num_bathrooms`, `floor`, `energy_certificate`, `living_area` | `lot_size` (terrain m²), `tipologiaimovel ∈ {Urbanizável, Rústico, Urbano, Edifício...}` |
| **Lacks** | (no equivalent) | bedrooms, bathrooms, floor, energy_certificate are NULL or meaningless |
| **SCD2 versioning drivers** | price + bedrooms + status + lifecycle | price + lot_size + classification + lifecycle |
| **Analytics domain** | livability scoring, time-on-market | development potential, buildable area, zoning fit |

Forcing them into one table produces:

- ~70% NULL columns when housing and plot rows coexist
- Wrong SCD2 hashing (`num_bedrooms` would always be NULL on plots → never opens a plot version)
- Silver/gold downstream models would need branchy logic per row type

Separate tables resolve all three.

## How

### Per-pipeline implementations

#### [[zome]] (`pipelines/portals/zome/source.py`)

- **Source**: same Supabase REST endpoint `tab_listing_list`, filtered by `idtipoimovel = 3` (Terreno).
- **Volume**: ~1,780 plots (verified 2026-04-28).
- **Pre-existing reuse**: `_normalize_listing` works as-is — the same 4 surgical renames apply (`localizacaolevelN imovel` → `localizacaolevelN`).
- **Plot-specific field**: `areaterreno` (m² of the terrain).
- **Tables**: `zome_plots` (SCD2, pk=`listing_id`), `zome_plots_state` (heartbeat).
- **Resources**: yielded from `zome_facts_source` alongside dev/listing resources.
- **Cost**: $0 (Supabase REST is free at our usage).

#### [[remax]] (`pipelines/portals/remax/source.py`)

- **Source**: NOT `/api/Development/PaginatedSearch` (HOUSING-only — its `listingTypeIDs` filter is silently ignored). Uses **sitemap → Next.js**:
  - **Pass 1** (`_fetch_all_plots`): walk `https://remax.pt/sitemap.xml` → 4 PT listing detail sitemaps → filter URLs matching `PLOT_URL_PATTERN` (substring `terreno`).
  - **Pass 2** (`_prefetch_plots`): for each plot URL, GET `_next/data/{build}/en/imoveis/{slug}/{title}.json`, decode `pageProps.listingEncoded`, **filter to `listingTypeID == 21`** (the real Terreno code at unit level — NOT 39, which is the search-page business code that doesn't push down to listings).
- **Volume**: ~12,400 plots (matches website `/comprar/imoveis/terreno/` total).
- **Tables**: `remax_plots` (SCD2, pk=`listing_id`), `remax_plots_state`.
- **Resources**: yielded from `remax_facts_source` alongside dev/listing.
- **Cost**: $0 (no scraping API needed; sitemap + Next.js are public).
- **Throughput**: with `PASS2_MAX_WORKERS=4` and `1s` per-worker delay, ~1 hour for full ~12.4k plot fetches.

#### [[idealista]] (`pipelines/portals/idealista/source.py`)

- **Source**: ZenRows **Real Estate API** (NOT Universal Scraper):
  - **Pass 1** (`_fetch_plot_discovery`): RE API discovery against `/comprar-terrenos/{distrito}/` paginated until empty. `tld=.pt` scopes to PT site.
  - **Pass 2** (`_ensure_plots_payload`): for each `property_id`, RE API detail with `tld=.pt` → 28-30 fields.
- **Volume**: ~3,000 plots estimated (refine after first run).
- **Single grain**: no developments↔units 1:N relationship for plots.
- **Tables**: `idealista_plots` (SCD2, pk=`external_listing_id`), `idealista_plots_state`.
- **Source factory**: separate `idealista_plots_facts_source` (independent of `idealista_developments_facts_source`). Loaded by a parallel `load_plots` task in the DAG, not folded into `load_facts`.
- **Cost**: ~$5/run (~3,000 RE API calls × $0.0015).

### Plots-specific SCD2 version columns

Per-pipeline tuples — see `source.py` for each. Common pattern:

| Category | Include? |
|---|---|
| Asking price + reductions | ✅ |
| Status / activity flags (`status`, `is_sold`, `is_active`, `last_deactivated_at`) | ✅ |
| Operation type (sale/rent) | ✅ |
| **Lot size** (m² of terrain) | ✅ |
| **Total area** / **lot_size_usable** if exposed | ✅ |
| Property subtype / classification (Urbanizável / Rústico / Urbano) | ✅ |
| Agency / handoff signal | ✅ |
| Energy efficiency level (when surfaced for plots) | ✅ |
| JSONB images / features arrays | ❌ (CDN reorder noise) |
| Snapshot-derived (market_days, previous_price, modified_at) | ❌ |
| Immutable physical (latitude, longitude, address) | ❌ |
| Display-only (description_tags, slug) | ❌ |

Excluded for plots specifically:

- `num_bedrooms`, `num_bathrooms`, `floor`, `floor_id` — meaningless for land.
- `built_area`, `living_area` — typically NULL for plots; rare exceptions (a building permit attached to a plot) shouldn't drive SCD2 versions.

### Heartbeat sidecars — same 21-day floor

Plots use the same delisted-active threshold as housing (see [[heartbeat-sidecar]]):

```sql
last_seen_date >= current_date - 21
```

For idealista plots, the heartbeat is emitted for **every Pass 1 discovery hit**, including stub responses skipped from the SCD2 table. This mirrors the developments-units pattern.

### Required structural conventions

Per [[portal-naming-conventions]]:

- PK: `listing_id` ([[zome]], [[remax]]) or `external_listing_id` ([[idealista]], mirroring the dev-units pattern)
- Heartbeat: `{pk}, last_seen_date`
- SCD2 columns: `_dlt_valid_from`, `_dlt_valid_to`, `row_hash`
- Schema contract: `freeze/evolve`
- JSON columns declared explicitly via `PLOTS_JSON_COLUMNS`
- Raw payload: `raw_json` ([[zome]], [[remax]]) or `raw_meta` ([[idealista]])

### Validation gates (DAG-level)

| Pipeline | Plots row count band | Stub-rate ceiling |
|---|---|---|
| [[zome]] | [500, 5000] | n/a (Supabase doesn't return stubs) |
| [[remax]] | [5000, 25000] | n/a (Next.js returns full payload or notFound) |
| [[idealista]] | [500, 10000] | <10% (cross-country tld leakage check) |

When the Aveiro-test override Param is in use ([[idealista]]), row-count bands are skipped — the override is for development testing.

### Cost summary (weekly cadence)

| Pipeline | Plots cost/run | Plots cost/month |
|---|---|---|
| [[zome]] | $0 | $0 |
| [[remax]] | $0 | $0 |
| [[idealista]] | ~$5 | ~$20 |
| **Total marginal** | **~$5/week** | **~$20/month** |

### Decommission paths

- **[[zome]]**: `tab_listing_list` is the source of truth; plot ingestion is forever-coupled to that endpoint. No deprecation path.
- **[[remax]]**: `sitemap.xml` is the discovery primitive. The same sitemap could also serve housing listings (~47k vs current ~3.9k from PaginatedSearch), giving a 12× coverage win — see backlog item "remax housing sitemap refactor".
- **[[idealista]]**: plots use RE API directly; will continue working after the legacy `raw_idealista` resale table is decommissioned.

## See also

- [[scd2-row-hash]] — SCD2 version-column include/exclude policy
- [[heartbeat-sidecar]] — companion "is this entity still in the source?" mechanism
- [[portal-naming-conventions]] — structural uniformity requirements
- [[portal-field-map]] — cross-portal field correspondence matrix
- [[zenrows-universal-vs-re-api]] — [[idealista]]'s RE-API-vs-Universal-Scraper split
- [[idealista]], [[remax]], [[zome]] — the three current plot pipelines
