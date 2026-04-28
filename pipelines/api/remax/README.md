# RE/MAX Portugal — New Developments

**RE/MAX Portugal** — ~609 developments / ~8,630 unit listings fetched from the open REST API + the Next.js detail endpoint for enrichment. Bronze is dlt-managed (SCD2) with parallel Pass 2.

> **Pipeline status (2026-04-28):** dlt cutover complete. Legacy DAGs and
> `raw_remax_*` tables are gone. The single `remax_dlt` DAG runs weekly
> (Tuesdays 06:00 UTC) and writes SCD2 bronze tables (`remax_developments`,
> `remax_listings`) plus heartbeat sidecars. Pass 2 enrichment is parallelized
> via `ThreadPoolExecutor` — runtime dropped from ~5h sequential to ~37 min.
> See [CUTOVER.md](CUTOVER.md) for the migration runbook.

RE/MAX Collection (remaxcollection.pt) is the same API with 100% ID overlap —
no separate scrape needed. The `is_special` flag identifies Collection properties.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | RE/MAX Portugal |
| Pass 1 API | `POST https://remax.pt/api/Development/PaginatedSearch` |
| Pass 2 endpoint | `GET https://remax.pt/_next/data/{buildId}/en/imoveis/{slug}/{title}.json` (Next.js SSR; `pageProps.listingEncoded` is base64) |
| Auth | None required |
| Format | JSON |
| Coverage | Portugal (national) |
| Refresh | Weekly (Tuesdays 06:00 UTC) |

---

## What it fetches

### Pass 1 — Paginated Search (all ~609 developments, ~8,630 units)

| Field | Level | Coverage | Notes |
|-------|-------|----------|-------|
| Development name, GPS, region | Dev | 100% | |
| Min price | Dev | 62% | `minimumPrice` |
| Office/Agent | Dev | 100% | Name, phone, ID |
| `is_special` (Collection) | Dev | 100% | Identifies Collection properties |
| Unit price | Unit | ~65% non-zero | `listingPrice` |
| Unit area (total + living) | Unit | ~95% | m² |
| Bedrooms, bathrooms | Unit | ~97% | |
| Floor (`floor_id`, `floor_number`) | Unit | ~90% | See floor encoding below |
| Energy class | Unit | 100% | `energyEfficiencyLevelID` |
| Status (`listing_status_id`) | Unit | 100% | See status encoding below |
| `is_sold`, `is_online`, `is_active` | Unit | 100% | Booleans (also encoded in `listing_status_id`) |

### Pass 2 — Unit Detail (online units only, ~45%)

Pass 2 fields are exclusive to the Next.js endpoint — they cannot be obtained
from any REST API call. We pre-fetch them in parallel via `ThreadPoolExecutor`
inside `source._prefetch_pass2()` BEFORE entering the dlt resource generator.

| Field | Coverage | Notes |
|-------|----------|-------|
| `address` | ~45% | Street-level (e.g. "Rua António da Rocha Madail") |
| `apartment_number` (fraction) | ~10% | SCE cross-ref key (e.g. "1A", "3.7") |
| `market_days` | ~45% | Days on market (demand signal) |
| `previous_price` | ~20% | Price change history |
| `construction_year` | ~30% | |
| `contract_date` | ~45% | Listing contract signing date |
| `floor_description` | ~45% | Text label (e.g. "R/C", "1º Andar") |
| `listing_rooms` | ~45% | Room-by-room breakdown with m² areas |
| Unit GPS (`unit_latitude`, `unit_longitude`) | ~45% | Unit-level lat/lng |

---

## Field encoding reference

These are RE/MAX-side codes whose meanings are **inferred from the data** —
RE/MAX does not publish a code dictionary. Validate before relying on them
in silver. Joining `listing_status_id` against the `is_sold` / `is_online` /
`is_active` booleans (which are also returned per listing) is the safest way
to decode status; the table below was derived from that join.

### `listing_status_id`

Observed values + decoding (one row per `(listing_status_id, is_sold, is_online, is_active)` combination, from current SCD2 state):

| `listing_status_id` | `is_sold` | `is_online` | `is_active` | Count | Inferred meaning |
|---|---|---|---|---|---|
| 1 | F | T | T | 3,722 | **Available, online** — actively marketed unit |
| 1 | F | F | F | 1 | Available but offline (data anomaly, likely transient) |
| 2 | F | T | F | 54 | **Reserved, online** — visible but not buyable |
| 2 | F | F | F | 232 | **Reserved, offline** — held but no longer publicly listed |
| 4 | T | T | F | 64 | **Sold, still visible** — pending takedown from site |
| 4 | T | F | F | 897 | **Sold, removed from site** — historic sales record |
| 5 | F | F | F | 3,660 | **Withdrawn / inactive** — neither sold nor available; off-market |

**Decoded constants** (use for silver layer joins — keep in sync with [source.py](source.py) if RE/MAX adds new states):

| Code | Label |
|---|---|
| 1 | `available` |
| 2 | `reserved` |
| 4 | `sold` |
| 5 | `withdrawn` |

### `floor_id` and `floor_number`

These are **two different floor representations** that come from RE/MAX's listing form. Both are present because RE/MAX models a floor as a categorical dropdown (`floor_id`) plus a free-form integer (`floor_number`).

- **`floor_id`** — the dropdown choice. Maps to a textual label (returned in Pass 2 as `floor_description`). Includes special categories like "C/V" (cave/sub-cave) and "R/C" (rés-do-chão / ground floor) which don't have a clean numeric equivalent.
- **`floor_number`** — the numeric floor (0 = ground, 1 = first, etc.). Used for display and sorting. Often agrees with `floor_id` but not always — agents sometimes type a different number than the category they picked, so treat the two fields as **independent observations of the same physical floor**.

Inferred mapping from observed data (modal `floor_number` and joined `floor_description` per `floor_id`):

| `floor_id` | Modal `floor_number` | `floor_description` | Inferred label |
|---|---|---|---|
| 1 | 0 | C/V | Cave / sub-cave (basement) |
| 2 | 0 | R/C | Rés-do-chão (ground floor) |
| 3 | 1 | 1º Andar | 1st floor |
| 4 | 2 | 2º Andar | 2nd floor |
| 5 | 3 | 3º Andar | 3rd floor |
| 6 | 4 | 4º Andar | 4th floor |
| 7 | 5 | 5º Andar | 5th floor |
| ... | n−2 | nº Andar | nth floor (`floor_id = floor_number + 2`) |

The `floor_id = floor_number + 2` relationship holds for the modal case
above ground floor, but ~5% of rows show mismatches (agent picked one
dropdown but typed a different number). Silver should:
1. Prefer `floor_description` (Pass 2) when available — it's the
   user-facing label.
2. Fall back to `floor_id` decoded via the table above.
3. Use `floor_number` only as a tiebreaker / sortable scalar.

---

## How it works (post-cutover)

```
audit_to_minio        # Pass 1 raw JSON → s3://raw/remax/PaginatedSearch/p{0..N}/
      |               # (audit copy only; load_facts re-fetches independently)
      v
load_facts            # Pass 1 paginated search → Pass 2 parallel prefetch (4 workers, 1s/worker delay)
      |               # → dlt SCD2 merge: developments + listings + sidecars
      v
validate_facts        # _dlt_loads.status='loaded_data' + count bands + Pass 2 enrichment count
```

Why 4 workers + 1s per-worker delay = ~4 req/s effective. Conservative starting
point — RE/MAX has not rate-limited us in testing. If 3 consecutive runs succeed,
raise `PASS2_MAX_WORKERS` in [source.py](source.py) to 8 (~7 min total runtime).

---

## How to run

### 1. Trigger the DAG

Runs on a **weekly** schedule (Tuesdays 06:00 UTC, cron `0 6 * * 2`).
Tuesday avoids the Monday clash with `zome_dlt`.

To run an out-of-cycle refresh: Airflow UI → **`remax_dlt`** → **Trigger DAG**.

No configuration needed (RE/MAX has no auth).

### 2. Where it lands

**MinIO** (audit copy of Pass 1 only):
```
s3://raw/remax/PaginatedSearch/p0/{timestamp}.json
s3://raw/remax/PaginatedSearch/p1/{timestamp}.json
...
```

Pass 2 details are NOT mirrored to MinIO (~3,800 tiny files would be too
granular for audit). If we ever need Pass 2 audit, dump to a single
concatenated JSONL.

**PostgreSQL** (`bronze_listings` schema, dlt-managed):
- `remax_developments` — SCD2 (versioned by `row_hash` over curated columns)
- `remax_listings` — SCD2
- `remax_developments_state` — UPSERT sidecar (`development_id`, `last_seen_date`)
- `remax_listings_state` — UPSERT sidecar
- dlt internals: `_dlt_loads`, `_dlt_pipeline_state`, `_dlt_version` (shared with `zome_dlt`)

**PostgreSQL** (`bronze_listings_staging` schema, dlt-managed):
dlt creates a separate `<dataset>_staging` schema for the SCD2 merge dance.
Treat as dlt internals — never query from silver.

---

## DAG

### `remax_dlt` — RE/MAX API → MinIO (audit) + Postgres (SCD2 bronze)

| Setting | Value |
|---------|-------|
| Schedule | `0 6 * * 2` (Tuesdays 06:00 UTC) |
| Pass 2 parallelism | 4 workers × 1s per-worker delay (≈ 4 req/s effective) |
| Pass 2 runtime | ~37 min for ~3,800 online units (vs ~5h sequential — 8× speedup) |
| Total runtime | ~38 min end-to-end |
| Pass 1 timeout | 30s per request |
| Pass 2 timeout | 15s per request |
| Failure isolation | Pass 2 fetch failures yield NULL enrichment, never block the load |
| State directory | `/opt/airflow/dlt_state/remax` (persistent named volume `dlt_state`) |
| Schema contract | `data_type=freeze` (type drift fails loud), `columns=evolve` (new fields land NULL) |
| Tags | `remax`, `bronze`, `dlt`, `scd2` |

**Lifecycle semantics for downstream silver:**

A listing is considered active when:
```sql
remax_listings_state.last_seen_date >= current_date - 21
```

The 21-day floor: weekly cadence (7) + one missed run (7) + slack (7).
Do not lower below 14 days. SCD2 history of price / status / area changes is
queryable via `_dlt_valid_from` / `_dlt_valid_to` on the `remax_listings` and
`remax_developments` tables.

---

## Bronze schema

DDL is managed by dlt. Source-of-truth column names + types are inferred on
first load and locked thereafter via `schema_contract={"data_type": "freeze"}`
in [source.py](source.py). Inspect with:

```sql
\d+ bronze_listings.remax_developments
\d+ bronze_listings.remax_listings
\d+ bronze_listings.remax_listings_state
```

Columns added by dlt on the SCD2 fact tables:

| Column | Purpose |
|---|---|
| `_dlt_valid_from` | Version active-from timestamp (insert/update time) |
| `_dlt_valid_to` | NULL = current version; non-NULL = retired |
| `_dlt_load_id` | Which load wrote this version |
| `_dlt_id` | dlt-internal row id |
| `row_hash` | SHA256 over the curated version columns (see `LISTINGS_VERSION_COLUMNS` / `DEVELOPMENTS_VERSION_COLUMNS` in [source.py](source.py)). Drives the SCD2 diff. |

**What's in / out of the SCD2 row_hash** (decisions documented in [source.py](source.py)):

| Excluded | Why |
|---|---|
| `gallery`, `building_pictures`, `listing_rooms`, `listing_pictures`, `raw_json` | JSONB arrays; Next.js may reorder between calls |
| `market_days`, `previous_price` | Pass 2 snapshot-derived; change every run |
| `address`, `apartment_number`, `construction_year`, `latitude`, `longitude` | Immutable physical attributes; if they change, it's a data correction not a real event |
| `name`, `slug` | Display-only; semantic name changes are rare and noisy |

**Sidecar columns** (`remax_*_state`):

| Column | Type | Notes |
|---|---|---|
| `listing_id` / `development_id` | int (PK) | Same as fact-table PK |
| `last_seen_date` | DATE | Updated on every load via UPSERT |
| `_dlt_load_id`, `_dlt_id` | dlt internals | |

---

## API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/Development/PaginatedSearch` | POST | List all developments (paginated, 50/page) |
| `/api/Development/SearchFeatured` | GET | 493 featured developments |
| `/api/Development/GetDevelopmentByTitle?developmentPublicId={id}` | GET | Single development |
| `/_next/data/{buildId}/en/imoveis/{slug}/{title}.json` | GET | Unit detail (base64-encoded `pageProps.listingEncoded`) |
| `/_next/data/{buildId}/en/empreendimento/{slug}/{id}.json` | GET | Development detail |

### Note: buildId

The `buildId` changes on each RE/MAX deployment. Extracted automatically by
`source._get_build_id()` from the comprar-empreendimentos page:

```bash
curl -s "https://remax.pt/en/comprar-empreendimentos" | grep -oE '"buildId":"[^"]*"'
```

### RE/MAX Collection

`remaxcollection.pt` uses the same API — 100% ID overlap confirmed. The
`is_special` flag on the development identifies Collection properties.
No separate scrape needed.

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| Unit prices mostly hidden | Only ~65% of units have non-zero price | `previous_price` available via Pass 2 |
| Detail endpoint requires buildId | Changes on each RE/MAX deployment | Auto-extracted at load start |
| Pass 2 only for online units | ~45% of units get enrichment | Offline/sold units have basic data from Pass 1 |
| `floor_id` vs `floor_number` mismatches | ~5% of rows have inconsistent values (agent data entry) | Silver should prefer `floor_description` (Pass 2) when available |
| Pass 2 timeouts | ~2% of detail fetches time out at 15s | Failed fetches yield NULL enrichment, never block the load |

---

## Configuration

### Environment

| Variable | Where | Value |
|----------|-------|-------|
| `MINIO_ENDPOINT` | Airflow Variable | `minio:9000` |
| `MINIO_ACCESS_KEY` | Airflow Variable | Set via `airflow-init` |
| `MINIO_SECRET_KEY` | Airflow Variable | Set via `airflow-init` |
| `WAREHOUSE_HOST` / `WAREHOUSE_PORT` / `WAREHOUSE_USER` / `WAREHOUSE_PASSWORD` / `WAREHOUSE_DB` | Env vars | Postgres credentials for dlt destination |

### Tuning constants (in [source.py](source.py))

| Constant | Default | Purpose |
|---|---|---|
| `PAGE_SIZE` | 50 | Pass 1 paginated search page size |
| `MAX_PAGES` | 20 | Safety upper bound; pagination stops on empty page or `hasNextPage=False` |
| `PASS1_DELAY_S` | 1.0 | Rate limit between Pass 1 page requests |
| `PASS2_MAX_WORKERS` | 4 | Pass 2 parallelism (raise to 8 once stable) |
| `PASS2_PER_WORKER_DELAY_S` | 1.0 | Per-worker rate limit (effective req/s = workers × 1/delay) |
| `REQUEST_TIMEOUT_S` | 30 | Pass 1 request timeout |
| `DETAIL_TIMEOUT_S` | 15 | Pass 2 request timeout (per detail fetch) |

### Directory structure

```
pipelines/api/remax/
├── __init__.py                       # Package marker
├── source.py                         # dlt source: 4 resources + Pass 2 helpers
├── remax_dlt_dag.py                  # DAG: audit → load_facts → validate_facts
├── CUTOVER.md                        # Migration runbook + decommission gate (historical)
├── rollback_remax.sql                # Legacy DDL for emergency rollback (historical)
└── README.md                         # This file
```
