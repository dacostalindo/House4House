---
title: SCD2 row-hash policy
type: concept
last_verified: 2026-05-12
tags: [scd2, dlt, bronze, dedup, versioning]
---

## For future Claude

This is a concept page about the SCD2 row-hash policy that governs every dlt-based bronze pipeline ([[idealista]], [[jll]], [[remax]], [[zome]]). It explains the include/exclude rule for `*_VERSION_COLUMNS` (real business events vs noisy proxies), why the hash mechanics are deliberately duplicated across pipelines (rejecting a shared module), and the curated-hash escape valve for sources that reorder JSONB arrays. Read this when adding a new SCD2 sink, debugging spurious version churn, or being asked "should this column be in the row hash?"

## What it is

Every dlt-based portal pipeline in our stack writes to bronze using **SCD2 (Slowly Changing Dimension type 2)** semantics. Each row carries `_dlt_valid_from`, `_dlt_valid_to`, and a stable `row_hash` computed by `_stable_hash` over a curated column subset declared as `*_VERSION_COLUMNS`. **A new SCD2 version is opened iff `row_hash` changes between loads.**

This page is the canonical source of truth for the policy. The mechanics (`_stable_hash`, `_canonicalize`, `SCHEMA_CONTRACT`) live in code, intentionally duplicated across each portal `source.py` — see the "Hash mechanics duplicated by design" section below.

## Why

Without a curated row-hash, two failure modes emerge:

1. **Phantom version churn**: hashing the full row produces spurious SCD2 versions on every load when the source reorders JSONB arrays (e.g., [[zome]]'s Supabase reorders `gallery`, `video`, `raw_json` between calls). Storage inflates and "what changed for this listing?" queries return noise.
2. **Missed business events**: the opposite extreme — hashing only price misses status transitions (sold/delisted/reactivated), inventory shifts on developments, agent reassignments, energy-certificate corrections. Time-on-market analytics depend on these.

The curated subset is the **business signal**, separated from upstream serialization noise.

## How

**The hard rule**: include columns that represent real business events; exclude columns that are noisy proxies of those events.

| Category | Include? | Reason |
|---|---|---|
| Asking price + price-reduction flags | ✅ Yes | Core business event — time-versioning is the point |
| Status / availability flags (`status`, `is_sold`, `is_active`, `last_deactivated_at`, `online_booking`) | ✅ Yes | Lifecycle transitions feed time-on-market analytics |
| Inventory counts on developments (`imoveisdisponiveis`, `units_count`) | ✅ Yes | Sales-velocity signal |
| Physical attributes that may correct (`bedroom_count`, `lot_size`, `floor`, `energy_certificate`) | ✅ Yes | Capture corrections; rare events |
| Operation type (`operation` sale/rent) | ✅ Yes | Real lifecycle event |
| Agent/agency assignment (`nomeconsultor`, `agency_name`) | ✅ Yes | Handoff cohort signal |
| **JSONB arrays** (`gallery`, `features`, `images`, `raw_json`) | ❌ No | Source-side reordering = phantom versions |
| **Snapshot-derived fields** (`market_days`, `previous_price`, `last_seen_date`, `modified_at`) | ❌ No | Change every run by definition; would version every load |
| **Immutable physical** (`address`, `latitude`, `longitude`, `construction_year`) | ❌ No | If they change, it's a data correction — keep the column, don't version on it |
| **Display-only** (`name`, `slug`, `og_title`) | ❌ No | Whitespace drift, semantic equivalence is noisy |
| **Ad-placement flags** (`is_featured`, `is_branded`, `is_special`) | ❌ No | Flip on cadences independent of any real-estate event |

**Hash mechanics duplicated by design**: `_stable_hash`, `_canonicalize`, `_HASH_SCALAR_TYPES`, `SCHEMA_CONTRACT` are duplicated in each pipeline's `source.py` (~30 lines each). A shared `pipelines/common/dlt_scd2.py` would cost the abstraction (new import path, canonical-version question) and produce minimal dedup benefit. If a hash-mechanic change is required, edit all three files and verify with a unit test asserting bytewise hash equality on a fixed sample row.

**Schema contract**: `SCHEMA_CONTRACT = {"data_type": "freeze", "columns": "evolve"}`:
- `data_type=freeze` — type drift on a known column (price was bigint, now string) **fails the load loudly**, caught the same week.
- `columns=evolve` — new columns from the source land silently as NULL; staging models update to project them.

**Stub handling**: when a source returns a degraded payload ([[idealista]]'s RE API ≤6-field stub for deactivated listings), skip the SCD2 row but still emit the [[heartbeat-sidecar]] entry. The unit's last full SCD2 row stays current; the heartbeat ages out via the 21-day floor; silver detects "currently inactive" via heartbeat absence, not row absence.

**21-day floor (silver "currently active" threshold)**:

```sql
last_seen_date >= current_date - 21
```

Rationale: weekly cadence (7 days) + one missed run (7 days) + slack (7 days). **Do not lower below 14 days.** Document any change.

## Worked examples — per-pipeline `*_VERSION_COLUMNS`

### [[zome]] (`pipelines/portals/zome/source.py`)

`LISTINGS_VERSION_COLUMNS` — 17 cols, including `idestadoimovel`, `idcondicaoimovel`, `precosemformatacao`, `precoimovel`, `valorantigo`, `areautilhab`, `areabrutaconst`, `totalquartossuite`, `attr_wcs`, `attr_garagem`, `attr_garagem_num`, `attr_elevador`, `geocoordinateslat`, `geocoordinateslong`, `reservadozomenow`, `showwebsite`, `showluxury`.

Excluded: JSONB arrays (`gallery`, `raw_json`, `geolocation`, `regiao`, `gallerymainimages`), display-only (`titulo`).

`DEVELOPMENTS_VERSION_COLUMNS` — 15 cols, including price, typology groups, inventory counts (available/reserved/sold), exclusivity flag, status, consultant assignment, geo coords, web visibility flag.

### [[remax]] (`pipelines/portals/remax/source.py`)

`LISTINGS_VERSION_COLUMNS` — 19 cols, including `listing_price`, `listing_status_id`, `is_sold`, `sold_date`, `is_online`, `is_active`, `total_area`, `living_area`, `num_bedrooms`, `num_bathrooms`, `floor_id`, `floor_number`, `energy_efficiency_level`, `typology_id`, `garage_spots`, `parking`, `is_exclusive`, `is_remax_collection`, `price_reduction_pct`.

Notably excluded: `market_days` and `previous_price` (snapshot-derived, flip every run regardless of any real change), JSONB arrays, immutable physical attrs (`address`, `apartment_number`, `construction_year`, `latitude`, `longitude`), display-only (`slug`, `name`).

### [[idealista]] (`pipelines/portals/idealista/source.py`)

`UNITS_VERSION_COLUMNS` — 12 cols (RE API verbatim names): `property_price`, `property_subtype`, `bedroom_count`, `bathroom_count`, `lot_size`, `lot_size_usable`, `floor`, `energy_certificate`, `status`, `last_deactivated_at`, `operation`, `agency_name`.

Notably excluded: `modified_at` (server-side timestamp, flips on every metadata edit even non-business changes), JSONB arrays, immutable physical attrs (`address`, `latitude`, `longitude`), display-only (`property_title`, `property_description`).

`DEVELOPMENTS_VERSION_COLUMNS` — 5 cols: `min_price_text`, `units_count`, `is_completed`, `typology_summary`, `online_booking`. These come from HTML parsing (Pass 1+2), not the RE API.

### For plots specifically

See [[portal-plot-conventions]] for the plot-table SCD2 column choices — same include/exclude rules above, with bedroom/bathroom/floor/energy explicitly excluded (meaningless for land).

## See also

- [[heartbeat-sidecar]] — the companion mechanism that distinguishes stable-unchanged from delisted (SCD2 alone cannot)
- [[bronze-permissive]] — the broader bronze-layer policy this implements
- [[portal-naming-conventions]] — structural-uniformity requirements across the dlt portal pipelines
- [[portal-plot-conventions]] — plot-table SCD2 column choices
- [[portal-field-map]] — cross-portal field correspondence matrix
- [[idealista]], [[jll]], [[remax]], [[zome]] — the four current SCD2 consumers
