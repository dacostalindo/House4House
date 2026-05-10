---
title: Infrastructure & deployment
type: plan
last_verified: 2026-05-10
tags: [architecture, infrastructure, docker-compose, postgresql, plan]
---

## For future Claude

This is the **infrastructure** page — Docker Compose service map, server spec, and PostgreSQL schema organization. Read this when adding a new service to docker-compose, debugging port conflicts, planning a server upgrade, or asked "where does X live?". The companion page [[tech-stack]] explains WHY each component was picked; this page documents HOW it's deployed.

## What it is

House4House runs as a Docker Compose stack on a single self-hosted server (Hetzner AX102 or equivalent). All persistent services containerized; PostgreSQL is the warehouse + Airflow metadata DB; MinIO is the raw object store; Airflow orchestrates DAGs; Nominatim + OSRM are companion services for [[osm]]; Metabase + Streamlit are the analyst surfaces.

## Docker Compose service map

Per README §4.1, the service topology:

| Service | Image | Ports | Volumes | Notes |
|---|---|---|---|---|
| **postgres** | `postgis/postgis:16-3.4` | `5432` | `pgdata:/var/lib/postgresql/data` | `shm_size: 4g`; `shared_buffers=8GB`, `effective_cache_size=24GB`, `work_mem=256MB`, `maintenance_work_mem=2GB`. |
| **minio** | `minio/minio` | `9000` (API), `9001` (console) | `minio_data:/data` | S3-compatible object store; raw landing zone for every source. |
| **airflow-webserver** | `apache/airflow:2.10.4-python3.12` | `8080` | `./dags`, `./plugins` | Per [[2026-05-05-cosmos-pin]]: bound to Airflow 2.10 + Cosmos 1.6 stack. |
| **airflow-scheduler** | `apache/airflow:2.10.4-python3.12` | — | `./dags`, `./plugins` | LocalExecutor; scheduler + workers in one process. |
| **airflow-worker** | `custom-airflow-worker` (Dockerfile.airflow) | — | `./dags`, `./plugins`, `./pipelines` | Custom image with Scrapy + Selenium + GeoPandas + Cosmos + dlt. Built via `Dockerfile.airflow.uv` per [[2026-05-05-uv-workspace-shape]]. |
| **nominatim** | `mediagis/nominatim:4.4` | `8088` | `nominatim_data:/var/lib/postgresql/14/main` | First startup ~30-45 min on PT import; `PBF_URL: https://download.geofabrik.de/europe/portugal-latest.osm.pbf`. See [[osm]]. |
| **osrm** | `osrm/osrm-backend` | `5050` (car), `5051` (walking), `5052` (cycling) | `osrm_data:/data` | 3 profiles, each with its own port. Built from same OSM PBF + `osrm-routed --algorithm mld`. See [[osm]]. |
| **metabase** | `metabase/metabase:v0.48.0` | `3000` | — | BI dashboards (UC-1 Investment Board, UC-2 Pricing Board). DB metadata in its own postgres user/db. |
| **streamlit** | built from `apps/Dockerfile.uv` | `8501` | — | Custom apps + Kepler.gl maps via `streamlit-keplergl`. |
| **selenium** | `selenium/standalone-chromium` | `4444` | — | `shm_size: 2g`. Used by JS-rendered scrapers; companion to Scrapy in Flow B. |

**Boot order:** `postgres` → `minio` → all Airflow services + Metabase + Streamlit (which depend on postgres). Nominatim + OSRM independent (built from OSM PBF on cron / manual trigger).

## Server specification

| Component | Spec |
|---|---|
| **Server** | Hetzner AX102 (or equivalent) |
| **CPU** | AMD Ryzen 9 7950X (16 cores / 32 threads) |
| **RAM** | 128 GB DDR5 |
| **Storage** | 2 × 2TB NVMe SSD (RAID 1 or separate; current: separate, one for `pgdata`, one for `minio_data` + Nominatim) |
| **Cost** | ~€85/month |
| **OS** | Ubuntu LTS (24.04 or 22.04) |

**Why this spec:** see [[2026-05-10-single-server-self-hosted]] for the load-bearing claims. In short: spatial workloads benefit from local I/O + 128 GB RAM lets PostGIS keep [[bgri]] / [[bupi]] / [[osm]] hot in `shared_buffers`; cloud-equivalent compute would be ~€1,500/month.

## PostgreSQL schema organization

Per `warehouse/init/001_create_schemas.sql` (see [[medallion-layering]] for the full discussion of WHY this layout):

**Bronze** (per-source schemas, raw):

```sql
CREATE SCHEMA bronze_listings;     -- portals: idealista, jll, remax, zome
CREATE SCHEMA bronze_regulatory;   -- caop, bupi, cadastro, cos, crus, srup, srup-ogc, sce
CREATE SCHEMA bronze_geo;          -- general geography intermediates
CREATE SCHEMA bronze_macro;        -- ecb, bpstat, eurostat (financial / macro)
CREATE SCHEMA bronze_ine;          -- ine + bgri (Census 2021 geo) — same publisher
CREATE SCHEMA bronze_terrain;      -- lidar (DTM / DSM manifest tables)
CREATE SCHEMA bronze_geology;      -- lneg geology layer
CREATE SCHEMA bronze_hydrology;    -- apa floodplain + lneg aquifers
CREATE SCHEMA bronze_location;     -- geocoding caches, location-resolution intermediates
CREATE SCHEMA bronze_tourism;      -- tourism-specific feeds (deferred)
```

**Silver** (conformed, by domain):

```sql
CREATE SCHEMA silver_properties;   -- unified residential listing model (across 4 portals)
CREATE SCHEMA silver_geo;          -- clean administrative + boundary entities
CREATE SCHEMA silver_location;     -- POI / routing / geocoded entities
CREATE SCHEMA silver_market;       -- market aggregates, transaction data, price indices
CREATE SCHEMA silver_ref;          -- reference / dimension lookups (incl. manually-seeded refs)
```

**Gold** (analytical):

```sql
CREATE SCHEMA gold_analytics;      -- facts + dimensions feeding analytical workloads
CREATE SCHEMA gold_reporting;      -- denormalized models for BI tools / dashboards
```

**Support:**

```sql
CREATE SCHEMA staging;             -- dbt staging models land here when generating ephemeral views
CREATE SCHEMA metadata;            -- dbt-managed run metadata, lint state, pipeline_runs table
```

**Schema deltas vs. the original full blueprint** (per README §4.3 note):
- `bronze_energy` removed (S13 ADENE deferred — [[sce]] handles the energy-certificate piece via scraper)
- `bronze_market` removed (S33 Google Trends and S32 PORDATA deferred)
- `bronze_ref` merged into `silver_ref` since reference tables (renovation costs, IMT/IMI rates) are manually seeded rather than ingested

## Data flows by schema

| Bronze schema | Sources (priority) | Silver consumers |
|---|---|---|
| `bronze_listings` | [[idealista]] P0, [[jll]] P1, [[remax]] P1, [[zome]] P1 | `silver_properties.unified_listings` |
| `bronze_regulatory` | [[caop]] P0, [[bupi]] P1, [[cadastro]] P1, [[cos]] P1, [[crus]] P1, [[crus-ogc]] P1, [[srup]] P1, [[srup-ogc]] P1, [[sce]] P1 | `silver_geo.*`, `silver_properties.parcel_buildability` |
| `bronze_macro` | [[ecb]] P0, [[bpstat]] P0, [[eurostat]] P1 | `silver_market.*` |
| `bronze_ine` | [[ine]] P0, [[bgri]] P0 | `silver_geo.*` (BGRI), `silver_market.*` (INE) |
| `bronze_terrain` | [[lidar]] P1 | `silver_geo.*` (DTM/DSM-derived) |
| `bronze_geology` | [[lneg]] P2 | UC-3 silver layer |
| `bronze_hydrology` | [[apa]] P2, [[lneg]] P2 | UC-3 silver layer |
| `bronze_location` | [[osm]] P0 | `silver_location.*` |

## How to deploy

1. Provision the Hetzner AX102 (or equivalent self-hosted server).
2. Install Docker + Docker Compose; clone the repo.
3. `make setup` — creates the uv workspace + installs dev dependencies.
4. `make up` — boots `postgres` + `minio` + Airflow services + Metabase + Streamlit.
5. `warehouse/init/001_create_schemas.sql` runs once on first container start (via `docker-entrypoint-initdb.d`); creates the schemas above.
6. Trigger initial ingestion DAGs in Airflow UI to populate bronze (per [[orchestration]] for schedule).

`make install-cron` separately registers the Sunday `/wiki-lint` launchd cron (host-side, not in Docker — see [[airflow-home-isolation]] for the AIRFLOW_HOME-bleed gotcha that made host isolation important).

## See also

- [[tech-stack]] — the technologies behind this layout
- [[orchestration]] — Airflow DAG taxonomy + schedule map
- [[data-quality]] — dbt tests + Great Expectations on top of these schemas
- [[medallion-layering]] — bronze/silver/gold rationale
- [[2026-05-10-single-server-self-hosted]] — single-server + self-hosted decision
- [[2026-05-10-postgis-as-warehouse]] — PostGIS-as-warehouse decision
- [[2026-05-10-minio-not-s3]] — MinIO-not-S3 decision
- [[2026-05-05-uv-workspace-shape]] — Docker images built via uv workspace
- [warehouse/init/001_create_schemas.sql](../../warehouse/init/001_create_schemas.sql) — the canonical source for the schema list
- README §4 — the original infrastructure section
