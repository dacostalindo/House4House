---
title: Tech stack — primary + alternatives considered
type: plan
last_verified: 2026-05-10
tags: [architecture, tech-stack, rationale, plan]
---

## For future Claude

This is the **tech stack** page — every technology choice in House4House with a one-line rationale, plus the alternative-stack-considered table that names what was rejected. The decisions behind individual stack picks (PostGIS, MinIO, Airflow 2, dbt vs SQLModel, Nominatim + OSRM self-hosted, Streamlit + Kepler.gl, single-server-self-hosted) live as ADRs in [[wiki/decisions/]] and are linked inline below. Read this when adding a new tool to the project, when asked "why did we pick X?", or when scoping a future stack migration.

## What it is

The stack chosen for House4House: a single-server, self-hosted, spatial-first data warehouse. PostGIS at the centre, MinIO for raw landing, Airflow 2 + dbt + Cosmos for orchestration, Streamlit + Kepler.gl for the analyst surface, plus a small set of supporting tools (Pydantic, dlt, Scrapy/Selenium, ZenRows, OSRM, Nominatim).

## Primary stack

Per README §3.1, deployed as Docker services on a Hetzner AX102 (see [[infra]]):

| Component | Technology | Version | Rationale | ADR |
|---|---|---|---|---|
| **Core database** | PostgreSQL + PostGIS | 16 + 3.4 | First-class spatial support; mature ecosystem; industry standard for geospatial warehousing. | [[2026-05-10-postgis-as-warehouse]] |
| **Object storage** | MinIO (self-hosted) | latest | Raw file storage for PDFs, GeoPackages, HTML snapshots. S3-compatible API; zero per-request cost. | [[2026-05-10-minio-not-s3]] |
| **Transformation** | dbt Core | 1.7+ | SQL-based transformations with lineage, testing, documentation. Bronze → Silver → Gold per [[medallion-layering]]. | [[2026-05-10-dbt-not-sqlmodel]] |
| **Orchestration** | Apache Airflow | 2.10 | Battle-tested for complex DAGs with mixed task types (API calls, scraping, file processing, dbt runs). | [[2026-05-10-airflow-2-not-3]] + [[2026-05-05-cosmos-pin]] |
| **Airflow ↔ dbt** | astronomer-cosmos | 1.6.x | Auto-generates per-model task graphs from dbt's manifest; pinned `>=1.6,<1.7` because 1.7+ imports `airflow.sdk` (Airflow-3-only). | [[2026-05-05-cosmos-pin]] |
| **Analytical engine** | DuckDB (supplement) | 0.10+ | Fast analytical queries on Parquet files alongside PostgreSQL for heavy OLAP scans. Optional. | — |
| **Geocoding** | Nominatim (self-hosted) | 4.4 | OSM-based, no API limits, GDPR-compliant. Geocodes scraped + listing addresses. | [[2026-05-10-nominatim-osrm-self-hosted]] |
| **Routing** | OSRM (self-hosted) | latest | Drive-time isochrones + distance calculations. Loaded with Portugal OSM extract from [[osm]]. | [[2026-05-10-nominatim-osrm-self-hosted]] |
| **Scraping** | Scrapy + Selenium + nodriver + ZenRows | 2.11 / 4.x / latest | Web scraping (Scrapy), JS-rendered sites (Selenium), Cloudflare Turnstile (nodriver — only [[sce]] uses), anti-bot bypass (ZenRows for [[idealista]] per [[zenrows-universal-vs-re-api]]). | — (per-source choices, not stack-wide) |
| **PDF parsing** | tabula-py + camelot | latest | Extract tables from PDF reports (IMPIC, market reports). | — |
| **Spatial Python** | GeoPandas + Shapely | 0.14 / 2.0 | Geo ETL, spatial operations in Python (the airlock between bronze and dbt where Python wins over SQL). | — |
| **ML / stats** | scikit-learn + statsmodels | latest | Hedonic regression model training and evaluation (UC-1 hedonic). | — |
| **BI viz** | Metabase | 0.48+ | Business dashboards — Investment Board (UC-1), Pricing Board (UC-2). | [[2026-05-10-metabase-streamlit-not-superset]] |
| **Spatial viz** | QGIS + Kepler.gl | 3.34 / 3.0 | Spatial analysis (QGIS, desktop) + interactive map visualization (Kepler.gl, embedded in Streamlit via `streamlit-keplergl`). | [[2026-05-10-metabase-streamlit-not-superset]] |
| **Custom apps** | Streamlit | 1.30+ | Host for Kepler.gl maps + custom apps — property valuator, pricing simulator, site analyzer. | [[2026-05-10-metabase-streamlit-not-superset]] |
| **Data quality** | dbt tests + Great Expectations | latest | Schema validation, freshness checks, anomaly detection. See [[data-quality]]. | — |
| **Validation** | Pydantic + pydantic-settings | v2 | Configs use Pydantic; dlt resources do NOT (per [[pydantic-not-in-dlt]] guardrail). | [[2026-05-08-phase-2-5-closure]] |
| **Bronze ingestion** | dlt | 1.25 | SCD2 + heartbeat sidecars for portal sources (per [[scd2-row-hash]] + [[heartbeat-sidecar]]). Schema-contract `data_type=freeze, columns=evolve`. | — |
| **Language** | Python | 3.12 | Floor pinned by Airflow base image + keplergl/pyarrow wheel coverage. | — |
| **Packaging** | uv (workspace) | latest | Single root `pyproject.toml` + apps/pipelines members; one lockfile. | [[2026-05-05-uv-workspace-shape]] |
| **Lint + format** | Ruff | latest | Replaces black + flake8 + isort + a half-dozen other tools. | — |
| **Version control** | Git + GitHub | — | All dbt models, Airflow DAGs, scraper code. | — |
| **Container runtime** | Docker + Docker Compose | — | Reproducible dev + production environment. All services containerized. | [[2026-05-10-single-server-self-hosted]] |

## Alternative stack considered

Per README §3.2, the alternative-stack-considered table names what was rejected and why:

| Component | Self-hosted (chosen) | Cloud alternative (rejected) | Reason |
|---|---|---|---|
| PostgreSQL + PostGIS | Docker / bare metal | AWS RDS PostgreSQL + PostGIS, Google Cloud SQL | Cost: solo-dev budget; spatial workloads benefit from local I/O. |
| MinIO | Docker | AWS S3 | Cost: high-volume raw landing (~50 GB/month) racks up egress + storage cheaply on local disk. |
| Airflow | Docker | AWS MWAA, GCP Cloud Composer, Astronomer | Cost: managed Airflow ~$0.49/hour minimum (~$350/month); local Airflow is ~free. |
| dbt Core | CLI | dbt Cloud | dbt Cloud pricing scales with seats; solo-dev gets nothing extra over CLI for ~$100/month. |
| Metabase | Docker | Metabase Cloud, Looker, Preset | Cost: same as Airflow — managed Metabase priced for teams. |
| Nominatim | Docker | Google Maps Geocoding API | Cost: ~$5/1000 requests; bulk geocoding of ~500k listings = $2,500. Self-hosted is ~free. |
| OSRM | Docker | Google Distance Matrix API | Cost: same as Nominatim. Routing UC-1 + UC-3 features at scale would burn the API budget weekly. |

**Net pattern**: every component picked self-hosted on the cost axis. The trade-off is operational overhead (we run our own Docker services) for ~10× cost savings over cloud-managed equivalents.

## Why this shape

**Single-server, self-hosted, spatial-first** — see [[2026-05-10-single-server-self-hosted]] for the locked decision. Three load-bearing claims:

1. **Spatial workloads benefit enormously from local I/O and memory.** PostGIS queries against [[bgri]]'s 200k census subsections, [[bupi]]'s 3.25M parcels, and [[osm]]'s 4.5M features perform at memory-resident speeds when the Postgres instance sits 1ms from the warehouse. Cloud-managed Postgres trades that for elastic scaling we don't need.
2. **Cloud egress costs add up fast with large GIS datasets.** A ~600 MB BUPI GeoPackage download mirrored to S3 + read by an EC2 worker ≈ ~$0.10. Doing that monthly for ~30 sources ≈ ~$36/year just in egress. Trivial for a team; visible for solo-dev.
3. **Solo-dev operations is doable on a single Hetzner AX102** (16 cores / 128 GB RAM / 2× 2TB NVMe / ~€85/month). The same workload on AWS would cost ~€1,500/month for equivalent compute + storage.

**Could change if:**
- Multi-region serving becomes a need (no current trigger; PT-only for the foreseeable future).
- A team forms (operational overhead becomes worth offloading).
- Spatial data volume crosses ~1 TB (single-NVMe-pair becomes the bottleneck).

## See also

- [[infra]] — Docker Compose service map + server spec
- [[orchestration]] — Airflow DAG taxonomy operationalizing this stack
- [[data-quality]] — dbt tests + Great Expectations layer of the stack
- [[medallion-layering]] — the bronze/silver/gold schema design served by this stack
- [[ingest-flows]] — the six-flow ingest taxonomy this stack supports
- All 7 stack-decision ADRs landed in PR 6 ([[2026-05-10-postgis-as-warehouse]], [[2026-05-10-minio-not-s3]], [[2026-05-10-airflow-2-not-3]], [[2026-05-10-dbt-not-sqlmodel]], [[2026-05-10-nominatim-osrm-self-hosted]], [[2026-05-10-metabase-streamlit-not-superset]], [[2026-05-10-single-server-self-hosted]])
- [[overview]] — 1-page project synthesis
- README §3 (Technology Stack) + §3.2 (Alternative Cloud-Native Stack) — the canonical source for this content
