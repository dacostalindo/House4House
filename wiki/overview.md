---
title: House4House — project overview
type: plan
last_verified: 2026-05-08
tags: [overview, blueprint, synthesis]
---

## For future Claude

This is a 1-page synthesis of the project's strategic blueprint, distilled from the root README's 16 sections (~4,500 lines). It tells a future Claude session WHY this project exists, WHO it serves, WHAT data sources are P0, and HOW the medallion warehouse is shaped — in five minutes of reading. Most of the detail lives in the README; outbound `[[wikilinks]]` connect into the wiki for the rules, sources, and decisions referenced. Read this when starting any session that touches a new area of the project, when you need orientation before answering a strategic question, or as a launchpad to the relevant deeper pages.

## What this project is

House4House is a Portugal real-estate + regulatory-GIS data warehouse, built solo, optimized for self-hosted deployment on a single powerful server. It compiles structured data from real-estate portals (sale + rent + plots + new developments), regulatory GIS layers (administrative boundaries, cadastral parcels, land-use zoning, environmental constraints, terrain), and macro-financial indicators (housing prices, mortgage rates, demographic context) into a queryable medallion warehouse for property analytics.

**Stack** (per README §3): PostgreSQL 16 + PostGIS 3.4 (warehouse) · Apache Airflow 2.10 (orchestration) · dbt Core (transformations, via Cosmos for Airflow integration — see [[2026-05-05-cosmos-pin]]) · MinIO (raw object storage) · uv workspace (Python packaging — see [[2026-05-05-uv-workspace-shape]]) · Streamlit + Kepler.gl (analyst surface, optional Metabase BI) · Nominatim + OSRM (self-hosted geocoding + routing, derived from [[osm]]).

## Use cases (README §1)

Three primary use cases drive the data model:

- **UC-1 — Investor / property buyer**: "find me undervalued listings within X commute time of Y, with Z constraints (no flood risk, energy-class B+, RAN-clear)." Requires listings × spatial-join × hedonic-valuation.
- **UC-2 — Pricing analyst**: "what's the recent transaction-median in concelho X by typology, vs. asking price, vs. days-on-market?" Requires SCD2-versioned listings × [[ine]] transaction medians × [[bpstat]] mortgage flows.
- **UC-3 — Site analyzer / developer**: "given this parcel, what zoning applies, what neighbors, what risks, what comparables?" Requires [[bupi]] / [[cadastro]] × [[srup-ogc]] × [[crus-ogc]] × [[apa]] × neighbor-listings.

Detailed UC pages land in `wiki/plan/use-cases/` in PR 4 (per design-doc PR 3+ iterative pattern).

## Data sources (README §2 — 31 sources, 23 wiki pages active)

**Real-estate portals (4)** — see [[idealista]], [[jll]], [[remax]], [[zome]].

**Statistical & financial APIs (4)** — see [[ine]], [[bpstat]], [[ecb]], [[eurostat]].

**Energy-certificate scraper (1)** — [[sce]] (only nodriver-based scraper in the stack).

**Regulatory + spatial GIS (14)**:
- Administrative boundaries: [[caop]] (P0 foundation source — every entity resolves to a `freguesia` via spatial join).
- Property parcels: [[bupi]] (modern simplified, 152 concelhos), [[cadastro]] (legacy formal, 2000-2007 surveys only).
- Land-use: [[cos]] (national observed land cover), [[crus]] / [[crus-ogc]] (regulatory zoning per municipal master plan; legacy 5-município WFS being replaced by national OGC API).
- Constraints: [[srup]] / [[srup-ogc]] (heritage / agricultural reserve / hydric domain / military / wildfire / etc.; legacy WFS being replaced by 22-layer OGC API), [[apa]] (EU Floods Directive floodplain — coverage caveat: NOT all flood zones).
- Demographics + Census: [[bgri]] (Census 2021, 32 variables across 4 themes).
- Terrain: [[lidar]] (2m DTM + DSM, Aveiro region only; expandable).
- Geology + hydrogeology: [[lneg]] (1:500k national, scope-narrowed due to higher-res gaps).
- Generic geography: [[osm]] (POIs, roads, buildings via Geofabrik daily extract).
- Municipal-specific: [[aveiro-pmot]] (one-off bulk WMS-GFI extractor for Aveiro WebGIS).

Source priority tiers (P0 / P1 / P2) live in `wiki/plan/sources-by-priority/` in PR 5.

## Architecture — medallion (README §5)

See [[medallion-layering]] for the schema map. In short:

- **Bronze** (per-source schemas, PostGIS): source-faithful capture; [[bronze-permissive]] policy + [[scd2-row-hash]] for portals + [[heartbeat-sidecar]] for delisting detection.
- **Silver** (`silver_properties` / `silver_geo` / `silver_market` / `silver_ref`): conformed by domain (NOT by source); a unified listings model collapses [[idealista]] / [[jll]] / [[remax]] / [[zome]] differences.
- **Gold** (`gold_analytics` / `gold_reporting`): analytical models, denormalizations for BI tools, derived KPIs.

Where transformations belong: ingest = dlt + scrapers (bronze); type discipline + cross-source unification = dbt staging + silver intermediates; aggregations = dbt marts (gold).

## Ingest patterns (README §6 — four flow types)

- **Flow A — REST API**: [[ine]], [[bpstat]], [[ecb]], [[eurostat]], [[idealista]] (RE API path).
- **Flow B — scraping**: [[idealista]] (Universal Scraper paths via [[zenrows-universal-vs-re-api]] + [[payload-cache-lifecycle]]), [[sce]], future expansions.
- **Flow C — GIS**: [[caop]], [[osm]], [[crus]] / [[crus-ogc]], [[srup]] / [[srup-ogc]], [[apa]], [[lneg]], [[lidar]], [[bgri]], [[bupi]], [[cadastro]], [[cos]], [[aveiro-pmot]] (template at `pipelines/gis/template/`).
- **Flow D — derived**: dbt-only; no ingestion DAG (location scores, valuations, hedonic regression outputs).

## Project rules (concept layer)

The wiki concept pages encode the load-bearing rules every Claude Code session must follow when editing this codebase:

- [[bronze-permissive]] — bronze accepts whatever the source returns; validation lives in dbt staging.
- [[pydantic-not-in-dlt]] — Pydantic in configs YES, in dlt resources NO.
- [[scd2-row-hash]] — the curated-column-subset row-hash for SCD2 versioning.
- [[heartbeat-sidecar]] — UPSERT companion table answering "is this entity still in the source?"
- [[zenrows-universal-vs-re-api]] — [[idealista]]'s mixed-API strategy.
- [[payload-cache-lifecycle]] — module-level cache saving ~85% of [[idealista]]'s ZenRows spend.
- [[medallion-layering]] — the bronze/silver/gold schema map.
- [[airflow-home-isolation]] — the `~/airflow/airflow.cfg` bleed gotcha + `make verify`'s `AIRFLOW_HOME=$(PWD)/.airflow-home` fix.

## Foundational decisions (decision layer)

The 5 ADRs locked at the time of this overview's authorship:

- [[2026-05-05-uv-workspace-shape]] — single root pyproject + apps/pipelines members.
- [[2026-05-05-cosmos-pin]] — `astronomer-cosmos>=1.6,<1.7` until Airflow 3 migration.
- [[2026-05-08-sqla-1.4-concession]] — workspace-wide SQLA 1.4 because Airflow 2.10 requires <2.0.
- [[2026-05-08-phase-2-5-closure]] — Phase 2.5 absorbed into Phase 2 (zero work surfaced; audit in design doc).
- [[2026-05-08-idealista-enrichment-architecture]] — three coexisting streams + Phase 5 LLM enrichment writes to silver, not bronze.

README content not yet captured as ADRs (stack rationale: PostGIS / MinIO / Airflow 2.10 / dbt / Nominatim / OSRM / Streamlit choices, single-server-self-hosted posture, Scrapy+Selenium scraper-stack pick) lands iteratively in PR 3+ alongside the `wiki/plan/` content per the design-doc Phase 3e + PR 3+ pattern.

## Plan (`wiki/plan/`)

Plan content arrives iteratively across PR 3+. Recommended sequencing (per design-doc, not strict — pick by operational pain):

| PR | Content | Pages | Source in README |
|---|---|---|---|
| PR 3 | `wiki/plan/sprints/*` | ~11 | §12 Sprint Plan (10 sprints / 20 weeks) |
| PR 4 | `wiki/plan/use-cases/*` | 3 | §1 Business Use Cases |
| PR 5 | `wiki/plan/sources-by-priority/*` | 3 | §2 31-source priority table |
| PR 6 | `wiki/plan/data-flows/*` | 6 | §6 Data Flows by Source Type |
| PR 7 | `wiki/plan/conceptual-models/*` | 3 | §7 Conceptual Data Models per UC |
| PR 8 | Single-page topics: tech-stack, infra, data-quality, risks, resources, roadmap-p3-p4 | 6 | §3, §4, §13, §14, §15, §16 |

`wiki/plan/README.md` is the orientation page for this section.

## See also

- [[2026-05-05-uv-workspace-shape]] — workspace topology
- [[2026-05-05-cosmos-pin]] — Cosmos / Airflow version constraint
- [[2026-05-08-sqla-1.4-concession]] — SQLAlchemy concession
- [[2026-05-08-phase-2-5-closure]] — Phase 2.5 closure
- [[2026-05-08-idealista-enrichment-architecture]] — Phase 5 enrichment placement
- [[medallion-layering]] — schema map
- [[bronze-permissive]] — bronze policy
- [[scd2-row-hash]], [[heartbeat-sidecar]], [[pydantic-not-in-dlt]], [[zenrows-universal-vs-re-api]], [[payload-cache-lifecycle]], [[airflow-home-isolation]] — the project's load-bearing rules
- All 23 source pages in `wiki/sources/`
- [README.md](../README.md) — the canonical source for every section above
