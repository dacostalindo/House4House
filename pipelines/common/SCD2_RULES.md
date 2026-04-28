# SCD2 rules — cross-pipeline conventions

This document describes the **design principles** for SCD2 row versioning
that are uniform across the dlt-based bronze pipelines (`zome`, `remax`,
`idealista`). Each pipeline has its own version-column set (intrinsic —
different sources expose different fields) but the rules for what to
include vs exclude are identical.

For the field-naming policy (which leaf names land in bronze), see
[NAMING_CONVENTIONS.md](NAMING_CONVENTIONS.md).

## The principle

Every dlt source defines a `*_VERSION_COLUMNS` tuple per entity (listings,
developments, units). The columns in this tuple are hashed by `_stable_hash`
to produce `row_hash`, which dlt uses as the SCD2 row-version key. **A new
SCD2 version is opened iff `row_hash` changes between loads.**

The hard rule: **include columns that represent real business events; exclude
columns that are noisy proxies of those events.**

## Include vs exclude

| Category | Include in `*_VERSION_COLUMNS`? | Reason |
|---|---|---|
| **Asking price** + price-reduction flags | ✅ Yes | Core business event we want to time-version |
| **Status / availability flags** (`status`, `is_sold`, `is_active`, `last_deactivated_at`, `online_booking`) | ✅ Yes | Lifecycle transitions — needed for time-on-market analytics |
| **Inventory counts** on developments (`imoveisdisponiveis`, `listings_count`, `units_count`) | ✅ Yes | Sales-velocity signal |
| **Physical attributes** that may correct (`bedroom_count`, `lot_size`, `floor`, `energy_certificate`, `bathroom_count`) | ✅ Yes | Capture corrections; rare events |
| **Operation type** (`operation` sale/rent) | ✅ Yes | Real lifecycle event |
| **Agent/agency assignment** (`nomeconsultor`, `agency_name`) | ✅ Yes | Handoff cohort signal |
| **JSONB arrays** (`gallery`, `features`, `images`, `raw_json`) | ❌ No | Source-side reordering = phantom versions |
| **Snapshot-derived fields** (`market_days`, `previous_price`, `last_seen_date`, `modified_at`) | ❌ No | Change every run by definition; would open a version every load |
| **Immutable physical** (`address`, `latitude`, `longitude`, `construction_year`) | ❌ No | If they change, it's a data correction — keep as columns but don't version on |
| **Display-only** (`name`, `slug`, `og_title`) | ❌ No | Whitespace drift, semantic equivalence is noisy |
| **Ad-placement flags** (`is_featured`, `is_branded`, `is_special`) | ❌ No | Flip on cadences independent of any real estate event |

## Worked examples

### zome (`pipelines/api/zome/source.py`)

`LISTINGS_VERSION_COLUMNS` — 17 cols, including `idestadoimovel`,
`idcondicaoimovel`, `precosemformatacao`, `precoimovel`, `valorantigo`,
`areautilhab`, `areabrutaconst`, `totalquartossuite`, `attr_wcs`,
`attr_garagem`, `attr_garagem_num`, `attr_elevador`, `geocoordinateslat`,
`geocoordinateslong`, `reservadozomenow`, `showwebsite`, `showluxury`.

Excluded: JSONB arrays (`gallery`, `raw_json`, `geolocation`, `regiao`,
`gallerymainimages`), display-only (`titulo`).

`DEVELOPMENTS_VERSION_COLUMNS` — 15 cols, including price, typology groups,
inventory counts (available/reserved/sold), exclusivity flag, status,
consultant assignment, geo coords, web visibility flag.

### remax (`pipelines/api/remax/source.py`)

`LISTINGS_VERSION_COLUMNS` — 19 cols, including `listing_price`,
`listing_status_id`, `is_sold`, `sold_date`, `is_online`, `is_active`,
`total_area`, `living_area`, `num_bedrooms`, `num_bathrooms`, `floor_id`,
`floor_number`, `energy_efficiency_level`, `typology_id`, `garage_spots`,
`parking`, `is_exclusive`, `is_remax_collection`, `price_reduction_pct`.

Notably excluded: `market_days` and `previous_price` (snapshot-derived,
flip every run regardless of any real change), JSONB arrays, immutable
physical attrs (`address`, `apartment_number`, `construction_year`,
`latitude`, `longitude`), display-only (`slug`, `name`).

### idealista (`pipelines/api/idealista/source.py`)

`UNITS_VERSION_COLUMNS` — 12 cols (RE API verbatim names): `property_price`,
`property_subtype`, `bedroom_count`, `bathroom_count`, `lot_size`,
`lot_size_usable`, `floor`, `energy_certificate`, `status`,
`last_deactivated_at`, `operation`, `agency_name`.

Notably excluded: `modified_at` (server-side timestamp, flips on every
metadata edit even non-business changes), JSONB arrays, immutable physical
attrs (`address`, `latitude`, `longitude`), display-only (`property_title`,
`property_description`).

`DEVELOPMENTS_VERSION_COLUMNS` — 5 cols: `min_price_text`, `units_count`,
`is_completed`, `typology_summary`, `online_booking`. These come from
HTML parsing (Pass 1+2), not the RE API.

## Hash mechanics — duplicated across pipelines by design

`_stable_hash`, `_canonicalize`, `_HASH_SCALAR_TYPES`, and `SCHEMA_CONTRACT`
are duplicated in each pipeline's `source.py` (zome, remax, idealista) —
~30 lines each. This is intentional. A shared `pipelines/common/dlt_scd2.py`
module would be the worst of both worlds: pay the abstraction cost (new
import path, new place to look for the canonical version), get little
dedup benefit (small surface), and create migration debt if one consumer
adopts and others don't.

If a hash-mechanic change is required (e.g. handle a new scalar type), make
the same edit in all three files and verify with a unit test asserting
bytewise hash equality on a fixed sample row.

## Heartbeat sidecars — the "still in source?" answer

SCD2 alone cannot distinguish a stable unchanged row from a delisted row
(no new SCD2 version is opened in either case). Each pipeline therefore
emits a **heartbeat sidecar** table (`{source}_listings_state`,
`{source}_developments_state`, `{source}_development_units_state`) with
`UPSERT` write disposition and `last_seen_date` as the only payload.

**Silver-layer queries should treat a row as currently-active when:**

```sql
last_seen_date >= current_date - 21
```

The 21-day floor: weekly cadence (7 days) + one missed run (7 days) +
slack (7 days). **Do not lower below 14 days.** Document any change.

## Stub handling — when the source returns a degraded payload

idealista's RE API can return ≤6-field stub responses for deactivated /
wrong-tld listings. Writing a NULL-filled SCD2 row in this case would
churn versions on stub↔full oscillation (because the version cols all
go NULL → value → NULL).

**Convention**: when the source returns a stub, **skip the SCD2 row**
but **still emit the heartbeat sidecar entry**. The unit's last known
full SCD2 row stays current; the heartbeat ages out via the 21-day floor;
silver detects "currently inactive" via the heartbeat, not via row absence.

This is implemented in idealista (`source.development_units` resource skips
`detail.get("_re_api_stub")`). zome and remax don't currently observe
stub-like degraded payloads from their sources, but if one starts, apply
the same pattern.

## Schema contract

All pipelines use `SCHEMA_CONTRACT = {"data_type": "freeze", "columns": "evolve"}`:

- `data_type=freeze` — type drift on a known column (e.g. price was bigint,
  now string) **fails the load loudly** so it's caught the same week.
- `columns=evolve` — new columns from the source land silently as NULL;
  staging models must be updated to project them.

JSONB columns must be declared explicitly via `*_JSON_COLUMNS` tuples to
prevent dlt from auto-flattening into child tables (dlt issue #3811).
