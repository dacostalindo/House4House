---
title: SCD2 row-hash policy
type: concept
last_verified: 2026-05-08
tags: [scd2, dlt, bronze, dedup, versioning]
---

## For future Claude

This is a concept page about the SCD2 row-hash policy that governs every dlt-based bronze pipeline ([[idealista]], [[jll]], [[remax]], [[zome]]). It explains the include/exclude rule for `*_VERSION_COLUMNS` (real business events vs noisy proxies), why the hash mechanics are deliberately duplicated across pipelines (rejecting a shared module), and the curated-hash escape valve for sources that reorder JSONB arrays. Read this when adding a new SCD2 sink, debugging spurious version churn, or being asked "should this column be in the row hash?"

## What it is

Every dlt-based portal pipeline in our stack writes to bronze using **SCD2 (Slowly Changing Dimension type 2)** semantics. Each row carries `_dlt_valid_from`, `_dlt_valid_to`, and a stable `row_hash` computed by `_stable_hash` over a curated column subset declared as `*_VERSION_COLUMNS`. **A new SCD2 version is opened iff `row_hash` changes between loads.**

The canonical policy lives at [pipelines/common/SCD2_RULES.md](../../pipelines/common/SCD2_RULES.md). This wiki page is the rule's destination per [[bronze-permissive]] no-content-duplication; the SQL-level mechanics live in code.

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

**Stub handling**: when a source returns a degraded payload (idealista's RE API ≤6-field stub for deactivated listings), skip the SCD2 row but still emit the [[heartbeat-sidecar]] entry. The unit's last full SCD2 row stays current; the heartbeat ages out via the 21-day floor; silver detects "currently inactive" via heartbeat absence, not row absence.

## See also

- [[heartbeat-sidecar]] — the companion mechanism that distinguishes stable-unchanged from delisted (SCD2 alone cannot)
- [[bronze-permissive]] — the broader bronze-layer policy this implements
- [[idealista]], [[jll]], [[remax]], [[zome]] — the four current SCD2 consumers
- [pipelines/common/SCD2_RULES.md](../../pipelines/common/SCD2_RULES.md) — the canonical rules document this page summarizes
