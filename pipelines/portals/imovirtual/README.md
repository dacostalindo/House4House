# imovirtual portal pipeline

dlt-driven bronze ingestion for **imovirtual.com** (PT real estate, OLX/Adevinta
Nexus platform). 5th listing portal alongside idealista / remax / jll / zome.

Full design + verified field maps: [`wiki/decisions/2026-06-05-imovirtual-portal-onboarding.md`](../../../wiki/decisions/2026-06-05-imovirtual-portal-onboarding.md).
Source page: [`wiki/sources/imovirtual.md`](../../../wiki/sources/imovirtual.md).

## How it works

- **Acquisition:** direct Next.js `GET /_next/data/{buildId}/{path}.json` — no
  scraping vendor. `buildId` is scraped fresh per run from a page's
  `__NEXT_DATA__` (it rotates on deploys; `_next_data` refreshes it on a 404).
  DataDome is present but does not challenge this traffic (canary 2026-06-05:
  20 rapid JSON calls, 0 blocks). ZenRows Universal Scraper is the fallback.
- **No scraping API key needed.** Plain `requests` + a browser UA.

## Grains → bronze tables (`bronze_listings`)

| Table | PK | Scope | Source |
|-------|----|-------|--------|
| `imovirtual_developments` (+ `_state`) | `development_id` | national | `/pt/empreendimento/{slug}` |
| `imovirtual_development_units` (+ `_state`) | `unit_id` (FK `development_id`) | national | embedded `ad.paginatedUnits` |
| `imovirtual_plots` (+ `_state`) | `listing_id` | **Aveiro** | `/pt/anuncio/{slug}` (terreno) |

Developments + units share a national crawl (`imovirtual_developments_facts_source`);
plots are a separate Aveiro-scoped crawl (`imovirtual_plots_facts_source`). The
dev `paginatedUnits` view is complete, so there is **no per-unit Pass 3**.

SCD2 `row_hash` + heartbeat sidecars follow the standard policy
([`scd2-row-hash`](../../../wiki/concepts/scd2-row-hash.md),
[`heartbeat-sidecar`](../../../wiki/concepts/heartbeat-sidecar.md)); attributes
arrive as a Nexus `characteristics: [{key, value}]` array that the normalizers
pivot into columns.

## Key files

- [`source.py`](source.py) — dlt resources, `_next/data` fetch + buildId
  bootstrap, characteristics pivot, dev→units FK at parse time, SCD2 + heartbeats.
- [`imovirtual_dlt_dag.py`](imovirtual_dlt_dag.py) — `audit_to_minio → [load_facts, load_plots] → validate_facts`. Schedule `0 6 * * 4` (Thu).
- [`tests/test_source.py`](tests/test_source.py) — offline pure-function tests
  (33; fixtures from live 2026-06-05 payloads). Run:
  `PYTHONPATH=. pytest pipelines/portals/imovirtual/tests/`.

## Two confirm-at-build items (flagged in the decision record)

1. **Unit pagination param** — `_iter_dev_units` fetches additional unit pages
   via `?page=N` on the empreendimento `_next/data`; dedup-by-`unit_id` guards a
   wrong guess. Confirm against a development with >10 listed units.
2. **Terreno `characteristics.type` enum** — captured raw; dbt staging maps to a
   canonical plot classification (rústico / urbano / agrícola / …).

## Run locally

```bash
# unit tests (offline)
PYTHONPATH=. pytest pipelines/portals/imovirtual/tests/

# trigger the DAG (inside the Airflow container)
airflow dags trigger imovirtual_dlt
```
