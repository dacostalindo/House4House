# Idealista Portugal — Resale + New Developments + Plots

**Idealista Portugal** — Three coexisting bronze streams sourced from the
ZenRows family of APIs:

| Stream | Bronze table(s) | Source | Status |
|---|---|---|---|
| **Resale catalog** (`/comprar-casas/`) | `raw_idealista` (legacy) | ZenRows **Real Estate API** discovery + detail | **Active**, slated for eventual decommission |
| **New construction** developments + their member units | `idealista_developments`, `idealista_development_units` (+ heartbeats) | ZenRows **Universal Scraper** (Pass 1+2 for dev pages) + ZenRows **RE API** (Pass 3 for unit detail) | **Active** — new dlt pipeline (2026-04) |
| **Plots / terrenos** | `idealista_plots` (+ heartbeat) | ZenRows **RE API** discovery + detail | **Active** — new dlt pipeline (2026-04) |

The two new dlt streams (developments + plots) live in **`idealista_dlt.py`**
DAG (id `idealista_developments_dlt`); the legacy resale pipeline lives in
**`idealista_ingestion_dag.py`** (id `idealista_ingestion`) +
**`idealista_bronze_dag.py`** (id `idealista_bronze_load`).

> **Cross-pipeline conventions** are documented in
> [../../wiki/concepts/scd2-row-hash.md](../../wiki/concepts/scd2-row-hash.md),
> [../../wiki/concepts/portal-naming-conventions.md](../../wiki/concepts/portal-naming-conventions.md), and
> [../../wiki/concepts/portal-plot-conventions.md](../../wiki/concepts/portal-plot-conventions.md). Field names in the
> three new dlt tables match RE API verbatim — same column names as `raw_idealista`
> for migration-friendly drop-in replacement when the legacy table is decommissioned.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | Idealista Portugal |
| Anti-bot | DataDome (one of the toughest — defeats plain `requests` + headless Chrome) |
| Auth | None on idealista.pt directly; ZenRows API key required |
| Coverage | Portugal (national) |
| Refresh | Resale: daily 03:00 UTC. New developments + plots: weekly Wednesdays 06:00 UTC. |

### When to use which API path

| Need | Endpoint | Cost |
|---|---|---|
| Resale catalog (housing not in a development) | RE API discovery → RE API detail with `tld=.pt` | $0.0015/call |
| Developments index (`/comprar-empreendimentos/`) | Universal Scraper (no RE API equivalent) | $0.007/call (25× tier) |
| Per-development detail page | Universal Scraper | $0.007/call |
| Per-unit detail (any unit, dev-rooted or standalone) | RE API detail with `tld=.pt` | $0.0015/call |
| Plots discovery (`/comprar-terrenos/`) | RE API discovery | $0.0015/call |
| Per-plot detail | RE API detail with `tld=.pt` | $0.0015/call |

**Critical**: RE API detail requires the `tld=".pt"` parameter. Without it,
the endpoint resolves against `idealista.es` and returns 4-6-field stubs for
PT property IDs (cross-country namespace collision).

---

## What it fetches

Three coexisting streams — see per-stream subsections below.

### Stream 1 — Legacy resale (`raw_idealista`, slated for decommission)

Crawls `/comprar-casas/{distrito}/` and `/arrendar-casas/{distrito}/` URLs
via ZenRows RE API discovery, then enriches each `property_id` with RE API
detail + `tld=.pt`. Two-phase Airflow DAG:

```
idealista_ingestion DAG  →  Discovery + Detail JSONL → MinIO
                                     ↓
                            (TriggerDagRunOperator)
                                     ↓
idealista_bronze_load DAG  →  raw_idealista bronze table
```

**Active distritos** (configurable in `idealista_config.ACTIVE_DISTRITOS`):
currently `aveiro`, `coimbra`, `leiria`. Set to `None` to crawl all 18.
Manual triggers can override per-run with `{"distrito": "porto", "operation": "sale"}`.

**Schema**: 40+ columns including `property_id`, `property_url`, `property_price`,
`bedroom_count`, `bathroom_count`, `lot_size`, `property_features` (JSONB),
`property_images` (JSONB), `latitude`, `longitude`, `agency_name`, `status`,
`modified_at`, `last_deactivated_at`, `operation`. Source-oriented: stores
RE API fields verbatim.

**Decommission plan (timeline confirmed Sprint 4.4):**

`raw_idealista` is supported until Sprint 4.5's silver `unified_listings`
canonical model is operational. After that:

- `idealista_ingestion_dag.py` — deprecated. DAG marked paused; no scheduled runs.
- `idealista_bronze_dag.py` — deprecated. DAG marked paused.
- `dbt/models/staging/listings/stg_idealista.sql` — retired. Removed once
  `unified_listings` covers resale flows via `raw_idealista`'s replacement
  source (TBD in Sprint 4.5: probably extending `idealista_development_units`
  with non-development listings, or a new `idealista_resale` resource on the
  dlt pipeline).

**Field-name compatibility:** the new tables (`idealista_development_units`,
`idealista_plots`) use verbatim RE API field names — same shape as
`raw_idealista`. Silver staging models can swap the source declaration with
minimal rename churn.

**Timing gate:** decommission only when the silver `unified_listings`
canonical model is shipped, validated against a hand-labeled sample
(precision ≥ 0.9), and at least one downstream model (e.g., hedonic
features) has cut over.

**Cross-references:**
- Sprint 4.5 plan in repo-root [README.md](../../../README.md) — silver
  models that consume the replacement.
- ADR 003 — dlt for portals (architectural rationale).
- [`../../wiki/concepts/portal-plot-conventions.md`](../../wiki/concepts/portal-plot-conventions.md) —
  "Decommission paths" section.

See [idealista_config.py](idealista_config.py) for the full distrito/operation
matrix and [idealista_ingestion_dag.py](idealista_ingestion_dag.py) /
[idealista_bronze_dag.py](idealista_bronze_dag.py) for task graphs.

---

### Stream 2 — New developments + their member units

Distinct from resale: covers `/comprar-empreendimentos/` (new-construction
developments) and the units that belong to each development. The Real Estate
API has no equivalent endpoint for the developments index, so Pass 1+2 must
go through Universal Scraper. Pass 3 (per-unit detail) uses RE API for cost
+ structure reasons.

### Three-pass strategy

```
Pass 1 (Universal):  GET /comprar-empreendimentos/{distrito}/pagina-{n}
                     → discovery cards (id, url, name, min_price, typology)

Pass 2 (Universal):  GET /empreendimento/{development_id}/
                     → og: meta, h1, promoter_name, full description,
                       embedded list of /imovel/{unit_id} child links

Pass 3 (RE API):     GET realestate.api.zenrows.com/.../properties/{unit_id}?tld=.pt
                     → 28-30 structured JSON fields per unit
```

Pass 2 + Pass 3 are pre-fetched in parallel via `ThreadPoolExecutor`
(`max_workers=8`, `0.5s/worker delay` ≈ 16 req/s aggregate). Module-level
`_payload_cache` shares one fetch across the four resource generators.

### Tables produced

| Table | Disposition | PK | Notes |
|---|---|---|---|
| `idealista_developments` | SCD2 | `development_id` | One row per dev; `unit_links` JSONB lists children |
| `idealista_developments_state` | UPSERT | `development_id` | heartbeat sidecar |
| `idealista_development_units` | SCD2 | `unit_id` | RE API verbatim names; FK `development_id` → developments |
| `idealista_development_units_state` | UPSERT | `unit_id` | heartbeat sidecar (also ticks for stub-skipped units) |

### Coverage scope

7 distritos (configured in `source.TARGET_AREAS`):
- `aveiro-distrito`, `braga-distrito`, `coimbra-distrito`, `leiria-distrito`,
  `lisboa-distrito`, `porto-distrito`, `setubal-distrito`.

Lisboa + Setúbal distritos together cover the AML (Área Metropolitana de
Lisboa) plus surrounding rural concelhos — minor over-fetch vs enumerating
the 18 AML concelhos individually.

### Aveiro test override

For low-cost validation, the DAG accepts a `target_areas_override` Param:

```
Airflow UI → idealista_developments_dlt → Trigger DAG w/ config:
  {"target_areas_override": {"aveiro": ["aveiro-distrito"]}}
```

The override is threaded through the source factory as a function arg —
no module-state mutation. When in use, the DAG's row-count bands are
skipped (Pass 2 / Pass 3 quality gates still apply). Verified end-to-end:
81 devs, 399 units, 0 stubs, 0 RE API errors, ~10 min runtime.

### Stub handling

Some dev-rooted unit IDs return a degraded 4-6-field stub from RE API
(typically because the unit was deactivated long ago or the `tld=.pt` scope
flipped). To avoid phantom SCD2 versions on stub↔full oscillation:

- **Stub rows are SKIPPED from the SCD2 table** (`if detail.get("_re_api_stub"): continue`)
- **Heartbeat sidecar still emits** for the unit (so silver can detect
  "re-listed after deactivation" via the 21-day floor)

Threshold: `RE_API_STUB_FIELD_THRESHOLD = 6` fields, OR all of
`property_price` + `address` + `property_features` missing.

### Cost

| Pass | Calls/run (est., 7 distritos) | $/run |
|---|---|---|
| 1 (Universal: discovery pages) | ~30 | $0.21 |
| 2 (Universal: dev detail pages) | ~700 | $4.90 |
| 3 (RE API: unit detail) | ~14,000–21,000 | $21–32 |
| **Total** | | **~$26–38/run, ~$110–160/month** |

(After the Aveiro test, units/dev average came out to ~5 — full-scope cost
may settle closer to $5–10/run. Refine after first 7-distrito run.)

---

### Stream 3 — Plots (terrenos)

Distinct from developments: plots are a single-grain entity (no dev↔units
1:N relationship). Both passes use RE API → cheap, structured JSON, no
HTML parsing needed.

### Two-pass strategy

```
Plots Pass 1 (RE API):  GET realestate.api.zenrows.com/.../discovery/?url=
                        https://www.idealista.pt/comprar-terrenos/{distrito}/&page={n}&tld=.pt
                        → list of plot stubs

Plots Pass 2 (RE API):  GET realestate.api.zenrows.com/.../properties/{property_id}?tld=.pt
                        → 28-30 structured fields (incl. lot_size,
                          lot_size_usable, property_subtype, agency, etc.)
```

Same parallelism as units (`max_workers=8`, `0.5s/worker delay`).
Independent of the dev+units load — runs as a parallel `load_plots` task
in the DAG, not folded into `load_facts`. This means a plot-side failure
doesn't block dev/units, and vice versa.

### Tables produced

| Table | Disposition | PK | Notes |
|---|---|---|---|
| `idealista_plots` | SCD2 | `external_listing_id` (= RE API `property_id`) | RE API verbatim names |
| `idealista_plots_state` | UPSERT | `external_listing_id` | heartbeat sidecar (ticks for every Pass 1 hit, including stubs) |

### Cost

~$5/run for 7-distrito scope (~3,000 plots × $0.0015). ~$20/month weekly.

---

## Pipeline architecture

DAG `idealista_developments_dlt`:

```
audit_to_minio        # Pass 1 page-1 discovery HTML → s3://raw/idealista_developments/...
       |              # (audit copy only; load_facts re-fetches independently)
       v
   ┌───┴────┐
   │        │
load_facts  load_plots    # Two independent dlt sources running in parallel
   │        │
   └───┬────┘
       v
validate_facts        # _dlt_loads OK + Pass 2/3 enrichment floors + stub/error ceilings
```

### Validation gates (in `validate_facts`)

- **Pass 2 (dev detail) enrichment floor**: ≥80% of devs have `_has_detail = TRUE`
- **Pass 3 (unit detail) enrichment floor**: ≥95% of (Pass 3 attempts − stubs) land in `idealista_development_units`
- **Pass 3 stub rate ceiling**: <10% (cross-country `tld` leakage check)
- **Pass 3 RE API error rate ceiling**: <5% (catches 429 rate limiting)
- **Plots Pass 2 stub rate ceiling**: <10%
- **Row-count bands** (skipped when `target_areas_override` is in use)

When a band is breached, the load is hard-failed — bronze stays clean.

---

## How to run

### 1. Trigger the DAG

Runs on a **weekly** schedule (Wednesdays 06:00 UTC, cron `0 6 * * 3`).
Wednesday avoids the Monday clash with `zome_dlt` and Tuesday with `remax_dlt`.

Out-of-cycle refresh: Airflow UI → **`idealista_developments_dlt`** → **Trigger DAG**.

For a single-distrito test run, supply config:
```json
{"target_areas_override": {"aveiro": ["aveiro-distrito"]}}
```

### 2. Where it lands

**MinIO** (audit copy of Pass 1 only):
```
s3://raw/idealista_developments/discovery/{area_key}/{slug}/{timestamp}.html
```

**PostgreSQL** (`bronze_listings` schema, dlt-managed):
- `idealista_developments` + `idealista_developments_state`
- `idealista_development_units` + `idealista_development_units_state`
- `idealista_plots` + `idealista_plots_state`
- `raw_idealista` (legacy resale, separate pipeline)
- dlt internals: `_dlt_loads`, `_dlt_pipeline_state`, `_dlt_version` (shared with `zome_dlt` / `remax_dlt`)

**dlt state directories** (persistent named volume `dlt_state`):
- `/opt/airflow/dlt_state/idealista_developments` — dev+units pipeline
- `/opt/airflow/dlt_state/idealista_plots` — plots pipeline

---

## DAG settings

`idealista_developments_dlt` — Universal Scraper + RE API → MinIO (audit) + Postgres (SCD2 bronze):

| Setting | Value |
|---------|-------|
| Schedule | `0 6 * * 3` (Wednesdays 06:00 UTC) |
| Pass parallelism | 8 workers × 0.5s per-worker delay (≈ 16 req/s aggregate) |
| Total runtime | ~25–40 min for full 7-distrito scope |
| Universal timeout | 180s per request, 3 retries × 5s backoff |
| RE API timeout | 60s per request, 3 retries × 5–60s exponential backoff |
| Failure isolation | `load_facts` (devs+units) and `load_plots` run in parallel; one failing does NOT block the other |
| State directory | `/opt/airflow/dlt_state/idealista_developments` + `/opt/airflow/dlt_state/idealista_plots` |
| Schema contract | `data_type=freeze` (type drift fails loud), `columns=evolve` (new fields land NULL) |
| Tags | `idealista`, `bronze`, `dlt`, `scd2`, `zenrows` |

**⚠️ macOS host sleep**: when triggering manually from a laptop, run
`caffeinate -i -d -s -u -t 14400 &` first. macOS Idle Sleep pauses Docker
→ Airflow heartbeat times out → task restarts from scratch (no resumability —
`_payload_cache` is process-local).

---

## Bronze schema

DDL is managed by dlt. Source-of-truth column names are inferred on first
load and locked thereafter via `schema_contract={"data_type": "freeze"}`.

Inspect with:
```sql
\d+ bronze_listings.idealista_developments
\d+ bronze_listings.idealista_development_units
\d+ bronze_listings.idealista_plots
\d+ bronze_listings.raw_idealista       -- legacy
```

### dlt-added columns on SCD2 tables

| Column | Purpose |
|---|---|
| `_dlt_valid_from` | Version active-from timestamp |
| `_dlt_valid_to` | NULL = current version; non-NULL = retired |
| `_dlt_load_id` | Which load wrote this version |
| `_dlt_id` | dlt-internal row id |
| `row_hash` | SHA256 over the curated `*_VERSION_COLUMNS` (see [source.py](source.py)) |
| `_has_detail` | Pass-2 enrichment flag (boolean); `TRUE` when the detail fetch succeeded |

### Sidecar columns (`*_state`)

| Column | Type | Notes |
|---|---|---|
| `{entity}_id` (PK) | int / text | Same as fact-table PK |
| `last_seen_date` | DATE | Updated on every load via UPSERT |
| `_dlt_load_id`, `_dlt_id` | dlt internals | |

---

## Lifecycle semantics for downstream silver

A unit/plot/development is **currently active** when:

```sql
{table}_state.last_seen_date >= current_date - 21
```

The 21-day floor: weekly cadence (7) + one missed run (7) + slack (7). Do not
lower below 14 days. SCD2 history of price / status / area changes is queryable
via `_dlt_valid_from` / `_dlt_valid_to` on the fact tables.

---

## Known limitations

| Issue | Detail | Resolution |
|---|---|---|
| RE API stub responses | ~few % of unit IDs return 4-6 field stubs (deactivated or wrong-tld) | Skipped from SCD2 table; heartbeat still ticks. Stub-rate ceiling 10% in validation. |
| Universal Scraper intermittent stubs | ~1 in 5 calls returns 12 KB JS shell w/o cards | Mitigated by `wait_for='article.item'` (Pass 1) / `wait_for='h1'` (Pass 2) |
| Pagination URL pattern differs across stream types | `pagina-{n}` for empreendimentos, `pagina-{n}.htm` for resale listings | Documented in source.py; verified end-to-end |
| `_payload_cache` lost on host sleep / heartbeat restart | Process-local cache; restart redoes Pass 2/3 from scratch | Use `caffeinate` when triggering from a laptop. Disk-persistence is a backlog item. |
| Resale legacy table coexists with new dlt tables | `raw_idealista` + `idealista_*` write to same schema | Decommission resale once new pipeline reaches feature parity (field names already match for drop-in replacement) |

---

## Configuration

### Environment

| Variable | Where | Value |
|----------|-------|-------|
| `ZENROWS_API_KEY` | Airflow Variable | Real key (40 chars). Note: RE-API tier credit balance is separate from Universal Scraper quota — verify both are funded. |
| `MINIO_ENDPOINT` | Airflow Variable | `minio:9000` |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | Airflow Variables | Set via `airflow-init` |
| `WAREHOUSE_HOST` / `WAREHOUSE_PORT` / `WAREHOUSE_DB` / `WAREHOUSE_USER` / `WAREHOUSE_PASSWORD` | Env vars | Postgres credentials for dlt destination |

### Tuning constants (in [source.py](source.py))

| Constant | Default | Purpose |
|---|---|---|
| `DISCOVERY_MAX_PAGES` | 50 | Pass 1 max pages per area before bailing |
| `PASS1_DELAY_S` | 1.0 | Delay between Pass 1 page requests |
| `PASS2_PASS3_MAX_WORKERS` | 8 | Parallelism for Pass 2 + Pass 3 + plots Pass 2 |
| `PASS_PER_WORKER_DELAY_S` | 0.5 | Per-worker rate limit |
| `REQUEST_TIMEOUT_S` | 180 | Universal Scraper timeout |
| `ZENROWS_RETRIES` | 3 | Universal retries before giving up |
| `RE_API_TIMEOUT_S` | 60 | RE API timeout |
| `RE_API_RETRIES` | 3 | RE API retries (5s..60s exponential backoff) |
| `RE_API_STUB_FIELD_THRESHOLD` | 6 | RE API payloads ≤ this many fields = stub |

### Pagination URL pattern (idealista quirk)

For empreendimentos: `pagina-{n}` (no `.htm`, no trailing slash).
For listings (legacy resale): `pagina-{n}.htm`. The conventions differ.

### `wait_for` selectors (Universal Scraper)

ZenRows occasionally returns a 12 KB JS shell without rendered listing
cards (intermittent ~1 in 5 calls). To force a stable render:
- Pass 1 discovery: `wait_for='article.item'`
- Pass 2 dev detail: `wait_for='h1'`

### Files

```
pipelines/portals/idealista/
├── __init__.py                          # Package marker
├── source.py                            # NEW dlt source: 6 resources across 2 sources (developments+units, plots)
├── idealista_dlt.py                     # NEW DAG: audit → load_facts ⫽ load_plots → validate_facts
├── CUTOVER.md                           # First-run runbook for the new dlt pipeline
├── rollback_idealista.sql               # Drop-and-replay SQL for the new dlt pipeline
├── idealista_config.py                  # LEGACY: distrito/operation matrix + ZenRows endpoint constants (also reused by source.py)
├── idealista_ingestion_dag.py           # LEGACY DAG: discovery + detail JSONL → MinIO
├── idealista_bronze_dag.py              # LEGACY DAG: MinIO JSONL → raw_idealista bronze table
├── image_classification_dag.py          # Claude Vision classification on listing images
└── README.md                            # This file
```

---

## Backlog / known follow-ups

- **Decommission `raw_idealista`** once the new `idealista_developments_dlt`
  pipeline reaches feature parity. Field names already match RE API verbatim
  for drop-in replacement.
- **Validate first 7-distrito run** of dev+units + plots once it lands. Refine
  the cost band in this README based on actual call counts.
- **Persist `_payload_cache` to disk** so a host-sleep restart doesn't redo
  Pass 2/3 from scratch.
