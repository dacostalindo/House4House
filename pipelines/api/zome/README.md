# Zome Portugal — Developments + Listings

**Zome Portugal** — 302 developments and 8,975 listings fetched from a Supabase PostgreSQL REST API with a public anon key. Provides ERA-style absorption tracking (available/reserved/sold counts per development) and per-unit status flags. Second-largest development dataset after RE/MAX.

> **Pipeline note (2026-04):** ingestion was rewritten on top of `dlt` with SCD2
> bronze tables. The DAG `zome_dlt` replaces the legacy three-DAG chain. Legacy
> DAGs (`zome_api_ingestion`, `zome_bronze_load_developments`,
> `zome_bronze_load_listings`) are paused pending decommission — see
> [CUTOVER.md](CUTOVER.md) for the gating criteria.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | Zome Portugal |
| API | Supabase REST (PostgREST) at `luvskhnljpxllkxpeasu.supabase.co` |
| Auth | Public anon key (embedded in frontend JS, expires 2032) |
| Schema | `pt_prod` (via `Accept-Profile` header) |
| Format | JSON |
| Coverage | Portugal (national) |
| Refresh | Weekly |

---

## What it fetches

Two Supabase tables, fetched via paginated REST requests:

### `tab_ventures` — 302 developments

| Field | Coverage | Notes |
|-------|----------|-------|
| Development name (`nome`) | 100% | |
| EMID (development code) | 100% | e.g. `EMPT194896` |
| Location (district/municipality/parish) | 100% | 3-level hierarchy |
| GPS coordinates | 98% | lat/lng strings |
| Price | 80% | Formatted string + numeric |
| Typology groups | 98% | e.g. "T1,T2,T3" |
| Units available | 81% | `imoveisdisponiveis` |
| Units reserved | 36% | `imoveisreservados` |
| Units sold | 14% | `imoveisvendidos` |
| Finishing map (PDF) | 100% | Direct URL to acabamento PDF |
| Gallery images | Yes | JSON array (multiple resolutions) |
| Video / Virtual reality | Yes | JSON (YouTube embeds, VR links) |
| Consultant | Yes | Name, email, phone, hub |
| Exclusivity flag | Yes | Boolean |
| Description | Yes | Multi-language JSONB (PT/EN/ES/FR/NL/DE/IT/CN) |

**Aggregate unit status: ~1,700 available + ~440 reserved + ~160 sold = ~2,300 tracked units**

### `tab_listing_list` — 8,975 listings

| Field | Coverage | Notes |
|-------|----------|-------|
| Price | 65% | Formatted string + numeric |
| Previous price (`valorantigo`) | 2% | PT-formatted string (e.g. "1.299.000") |
| Area (useful) | 80% | `areautilhab` m2 |
| Area (gross) | 87% | `areabrutaconst` m2 |
| Bedrooms | 70% | `totalquartossuite` |
| Bathrooms | 79% | `attr_wcs` |
| Garage | 47% | Count + number of spots |
| GPS coordinates | 100% | lat/lng |
| Unit state | 100% | 1=Available (65%), 2=Reserved (33%), 3=Sold (2%) |
| Unit condition | 82% | Novo/Renovado/Usado/Em construcao/etc. (8 levels) |
| Property type | 70% | Apartamento/Moradia/Terreno/etc. |
| Development link | 14% | FK to `tab_ventures` via `idemp` |
| Date entered network | Yes | `dataentradarede` |

### How it complements other sources

| Gap | Zome fills with | Join path |
|-----|-----------------|-----------|
| ERA has unit status but fewer devs | 302 devs with Available/Reserved/Sold counts | Development name + location |
| RE/MAX has 16% unit pricing | 65% unit pricing coverage | Cross-portal dedup |
| No finishing specifications | 100% acabamento PDF links (unique) | Per development |
| No condition classification elsewhere | 8-level system (Novo to Ruina) | Per listing |

---

## How it works (post-cutover)

```
audit_to_minio        # raw JSON → s3://raw/zome/... (audit copy, best-effort)
      |
      v
load_facts            # dlt SCD2: developments, listings + heartbeat sidecars
      |
      +-> load_refs       # dlt REPLACE: 3 lookup tables (soft-fail)
      |
      +-> validate_facts  # asserts _dlt_loads.status='loaded_data' + count bands
```

All Supabase requests include headers `apikey`, `Authorization: Bearer`, `Accept-Profile: pt_prod`.

`audit_to_minio` is an **audit copy** of the raw API response — it is NOT the load
source. `load_facts` makes its own HTTP requests against Supabase. See [CUTOVER.md](CUTOVER.md)
for rationale.

---

## How to run

### 1. Trigger the DAG

Runs on a **weekly** schedule (Mondays at **06:00 UTC**, cron `0 6 * * 1`).

To run an out-of-cycle refresh: Airflow UI -> **`zome_dlt`** -> **Trigger DAG**.

No configuration needed. API key is read from the `ZOME_SUPABASE_KEY` environment variable.

### 2. Where it lands

**MinIO** (audit copy):
```
s3://raw/zome/tab_ventures/{timestamp}.json
s3://raw/zome/tab_listing_list/p{0..9}/{timestamp}.json
```

**PostgreSQL** (`bronze_listings` schema):
- `zome_developments` — SCD2 (versioned by `row_hash` over curated columns)
- `zome_listings` — SCD2
- `zome_developments_state` — UPSERT sidecar (`venture_id`, `last_seen_date`)
- `zome_listings_state` — UPSERT sidecar
- `ref_zome_condition`, `ref_zome_property_type`, `ref_zome_business_type` — REPLACE on each load
- dlt internals: `_dlt_loads`, `_dlt_pipeline_state`, `_dlt_version`

**PostgreSQL** (`bronze_listings_staging` schema, dlt-managed):
dlt creates a separate `<dataset>_staging` schema for the SCD2 merge dance.
Staging tables receive each load's incoming rows; the merge step (close
retired versions + insert new versions) reads from there into the target
tables in `bronze_listings`. After a successful merge the staging tables
contain the most recent load's payload only — they're transient by intent
and should not be queried by silver. Treat as dlt internals.

---

## DAG

### `zome_dlt` — Supabase API -> MinIO (audit) + Postgres (SCD2 bronze)

| Setting | Value |
|---------|-------|
| Schedule | `0 6 * * 1` (Mondays 06:00 UTC) |
| Indicators | 1 ventures + 10 listing pages = 11 fetches per task that needs them |
| Rate limit | 0.5s between paginated requests |
| Timeout | 60s per request |
| Failure isolation | Refs in a separate dlt pipeline; ref schema drift cannot block facts |
| State directory | `/opt/airflow/dlt_state/zome` (persistent named volume `dlt_state`) |
| Schema contract | `data_type=freeze` (type drift fails loud), `columns=evolve` (new fields land NULL) |
| Tags | `zome`, `bronze`, `dlt`, `scd2` |

**Lifecycle semantics for downstream silver:**

A listing is considered active when:
```sql
zome_listings_state.last_seen_date >= current_date - 21
```

The 21-day floor is: weekly cadence (7) + one missed run (7) + slack (7). Do not
lower below 14 days. SCD2 history of price / status / area changes is queryable
via `_dlt_valid_from` / `_dlt_valid_to` on the `listings` and `developments` tables.

---

## Bronze schema

DDL is managed by dlt. Source-of-truth column names + types are inferred on
first load and locked thereafter via `schema_contract={"data_type": "freeze"}`
in [source.py](source.py). Inspect with:

```sql
\d+ bronze_listings.zome_developments
\d+ bronze_listings.zome_listings
\d+ bronze_listings.zome_listings_state
```

Columns added by dlt on the SCD2 fact tables:

| Column | Purpose |
|---|---|
| `_dlt_valid_from` | Version active-from timestamp (insert/update time) |
| `_dlt_valid_to` | NULL = current version; non-NULL = retired |
| `_dlt_load_id` | Which load wrote this version |
| `_dlt_id` | dlt-internal row id |
| `row_hash` | SHA256 over the curated version columns (see `LISTINGS_VERSION_COLUMNS` / `DEVELOPMENTS_VERSION_COLUMNS` in [source.py](source.py)). Drives the SCD2 diff. |

**Why a curated row_hash instead of dlt's auto-hash:** Supabase reorders JSONB
arrays (`gallery`, `raw_json`, `descricaocompleta`, `video`, `virtualreality`)
between calls. With auto-hashing, every weekly run creates a spurious version
for every listing, inflating `price_change_count` downstream. The curated
`row_hash` excludes these and only diffs business-meaningful columns.

**Sidecar columns** (`zome_*_state`):

| Column | Type | Notes |
|---|---|---|
| `listing_id` / `venture_id` | int (PK) | Same as fact-table PK |
| `last_seen_date` | DATE | Updated on every load via UPSERT |
| `_dlt_load_id`, `_dlt_id` | dlt internals | |

---

## Reference tables

The Supabase instance also exposes lookup tables used for decoding IDs:

### Unit condition (`idcondicaoimovel`)

| ID | PT | EN |
|----|----|----|
| 1 | Novo | New |
| 2 | Renovado | Renewed |
| 3 | Usado | Used |
| 4 | Em construcao | In construction |
| 5 | Para recuperar | To rebuild |
| 6 | Ruina | Ruin |
| 7 | Nao Aplicavel | Not applicable |
| 9 | Semi-novo | Semi-new |

### Property type (`idtipologia`)

| ID | PT | EN |
|----|----|----|
| 1 | Apartamento | Apartment |
| 2 | Moradia | House |
| 3 | Terreno | Land |
| 4 | Loja | Store |
| 5 | Escritorio | Office |
| 9 | Quinta | Farm |
| 20 | Predio | Building |

### Business type (`idtiponegocio`)

| ID | Description |
|----|-------------|
| 1 | Sale |
| 2 | Rent |

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| Supabase caps at 1000 rows/request | Listings require 10 paginated requests | Handled via offset pagination in `source.listings()` |
| `valorantigo` is PT-formatted string | e.g. "1.299.000" instead of numeric | Stored as TEXT in bronze, parsed in dbt silver layer |
| Floor plans mixed into gallery | No dedicated planta field; floor plans are regular JPGs in gallery array | Identifiable by filename patterns or CV classification |
| No energy certificates | Not available in Supabase tables | Complement with SCE data |
| No construction dates | Unlike KW, no completion/start dates | Cross-reference with KW `dwellDate`/`fundDate` |

---

## Configuration

### Environment

| Variable | Where | Value |
|----------|-------|-------|
| `ZOME_SUPABASE_KEY` | Environment variable | Public anon key (JWT, expires 2032) |
| `MINIO_ENDPOINT` | Airflow Variable | `minio:9000` |
| `MINIO_ACCESS_KEY` | Airflow Variable | Set via `airflow-init` |
| `MINIO_SECRET_KEY` | Airflow Variable | Set via `airflow-init` |
| `WAREHOUSE_HOST` | Airflow Variable | `warehouse` |

### Directory structure

```
pipelines/api/zome/
├── __init__.py                       # Package marker
├── source.py                         # dlt source: 7 resources across 2 sources
├── zome_dlt_dag.py                   # DAG: audit -> facts (SCD2) -> refs / validate
├── tests/
│   └── test_source.py                # Unit tests for _stable_hash + normalization
├── CUTOVER.md                        # Migration runbook + decommission gate
├── rollback_zome.sql                 # Legacy DDL for emergency rollback
├── zome_config.py                    # (deprecated) URL + headers; rest pending decommission
├── zome_ingestion_dag.py             # (deprecated, paused) legacy DAG stub
├── zome_bronze_developments_dag.py   # (deprecated, paused) legacy DAG stub
├── zome_bronze_listings_dag.py      # (deprecated, paused) legacy DAG stub
└── README.md                         # This file
```
