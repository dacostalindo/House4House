# Wiki Index

## For future Claude

This is the **catalog** of every wiki page — read it FIRST when answering any factual question or before any ingest. It has every page grouped by type (Overview / Sources / Concepts / Decisions / Plan) with a 1-line summary so Claude can grep + select the relevant pages without reading the whole wiki on every query. The `Last reconcile run:` line is the freshness indicator (updated by `/wiki-reconcile`); a stale date means the reconcile skill hasn't fired recently and drift-detection coverage is degrading. (The legacy `/wiki-lint` skill was retired 2026-05-12 in favour of `/wiki-reconcile` which covers both layers; the historical `Last lint run:` date stays here for archaeology.)

Last lint run: 2026-05-08 (skill retired)
Last reconcile run: 2026-05-22 (post-sprint-09 Slice B-prime ship)

This is the catalog of every wiki page. Each entry has a 1-line summary. Updated on every ingest and on every weekly lint run.

## Overview

- [[overview]] — 1-page synthesis of the project from the root README's 16 sections; entry-point for orientation queries.

## By area of code

When editing files in a specific area of the repo, read the wiki pages listed for that area first. Each area links to the concepts, sources, decisions, architecture, and sprints that govern it. The wiki is the source of truth; root `CLAUDE.md` only points here.

### `pipelines/` (DAGs, dlt resources, scrapers, configs)

- **Concepts**: [[pydantic-not-in-dlt]] (configs Pydantic, dlt resources not) · [[bronze-permissive]] (bronze accepts whatever the source returns) · [[scd2-row-hash]] (curated version-column policy) · [[heartbeat-sidecar]] (UPSERT-only "still-alive" companion) · [[portal-naming-conventions]] (structural uniformity vs source-faithful leaf names) · [[portal-plot-conventions]] (plots in separate `*_plots` tables) · [[portal-field-map]] (cross-portal column correspondence matrix) · [[zenrows-universal-vs-re-api]] (mixed scrape strategy) · [[payload-cache-lifecycle]] (`_payload_cache` reuse) · [[airflow-home-isolation]] (`~/airflow/airflow.cfg` bleed gotcha) · [[ingest-flows]] (six-flow taxonomy + decision tree) · [[spatial-strategy]] (CRS, GIST, H3 for GIS pipelines)
- **Sources**: choose the relevant page under [Sources](#sources-24-pages-with-priority-p0p1p2-frontmatter--added-in-pr-5) — e.g. [[idealista]] / [[imovirtual]] / [[remax]] / [[jll]] / [[zome]] for portals; [[sce]] for the only nodriver scraper; [[caop]] / [[bgri]] / [[bupi]] / [[cadastro]] / [[cos]] / [[crus]] / [[crus-ogc]] / [[srup]] / [[srup-ogc]] / [[apa]] / [[lneg]] / [[lidar]] / [[osm]] / [[aveiro-pmot]] for GIS; [[ine]] / [[bpstat]] / [[ecb]] / [[eurostat]] for stats APIs.
- **Decisions**: [[2026-05-10-airflow-2-not-3]] (orchestrator pin) · [[2026-05-05-cosmos-pin]] (dbt-DAG generator pin) · [[2026-05-10-minio-not-s3]] (raw landing) · [[2026-05-10-nominatim-osrm-self-hosted]] (geocoding/routing) · [[2026-05-08-idealista-enrichment-architecture]] (three coexisting streams) · [[2026-05-08-sqla-1.4-concession]] (SQLA pin from Airflow)
- **Architecture**: [[orchestration]] (DAG taxonomy + schedule map) · [[infra]] (Compose service map) · [[data-quality]] (Great Expectations + `metadata.pipeline_runs` audit)
- **Sprints (currently relevant)**: [[sprint-04]] (Image Classification + Location Scores, `in_progress`) · [[sprint-04.5]] (Listings + Developments Cross-Portal Dedup) · [[sprint-08]] (UC-3 v1 wedge Part 1, GIS + SCE foundations)

### `dbt/` (models, macros, source YAMLs)

- **Concepts**: [[medallion-layering]] (bronze → silver → gold + per-source-bronze-schema + transformation-placement rules) · [[bronze-permissive]] (validation belongs in dbt staging, not bronze) · [[spatial-strategy]] (dual-CRS storage + GIST + H3 indexing patterns for silver_geo / gold_geo models) · [[srup-constraint-model]] (the `(constraint_code, zone_type)` → severity model behind `dim_constraint_severity` + the `stg_srup_*` staging models + the new 15th APA ARPSI layer) · [[srup-properties-schema]] (per-key `properties` JSONB breakdown for the `stg_srup_*` models) · [[sce-buildings-clustering]] (DBSCAN + GROUP BY normalized_address roll-up of SCE certificates into `silver_sce_buildings`) · [[cross-portal-dev-dedup]] (name-driven Jaccard dedup of the 4 portals into `silver_unified_developments`; SCE deliberately not merged) · [[silver-dq-baseline]] (4 universal silver-layer invariants + statistical-source topology; established by sprint-09 WS4)
- **Sources**: only relevant when adding/extending the corresponding staging model — pick from [Sources](#sources-24-pages-with-priority-p0p1p2-frontmatter--added-in-pr-5).
- **Decisions**: [[2026-05-10-postgis-as-warehouse]] (PostgreSQL 16 + PostGIS 3.4 chosen over Snowflake/BigQuery/RDS) · [[2026-05-10-dbt-not-sqlmodel]] (dbt Core for transformations) · [[2026-05-10-dual-crs-storage]] (`geom` 4326 + `geom_pt` 3763 invariant for spatial tables)
- **Architecture**: [[data-quality]] (dbt tests + Great Expectations layering) · [[infra]] (PostgreSQL schema organization: `bronze_*`, `silver_*`, `gold_*`, `metadata`)
- **Sprints (currently relevant)**: [[sprint-03]] (Silver Layer + UC-3 GIS Foundation, `mostly_done`) · [[sprint-05]] (Hedonic Model & Valuation) · [[sprint-08]] / [[sprint-09]] (UC-3 v1 wedge silver + gold)

### `apps/` (Streamlit pages, Kepler.gl maps)

- **Concepts**: [[spatial-strategy]] (which CRS to read into geopandas + display vs join trade-off)
- **Sources**: only the source page for whatever the page reads (typically silver or gold tables — see [[medallion-layering]] for where to point your queries).
- **Decisions**: [[2026-05-10-metabase-streamlit-not-superset]] (Metabase for BI + Streamlit + Kepler.gl for custom apps; Superset rejected) · [[2026-05-08-sqla-1.4-concession]] (apps/ accepts workspace SQLA 1.4) · [[2026-05-10-dual-crs-storage]] (read `geom` for Kepler.gl 4326, `geom_pt` for distance/area)
- **Architecture**: [[tech-stack]] (Streamlit + Kepler.gl + geopandas selection rationale) · [[infra]] (apps container in Compose)
- **Sprints (currently relevant)**: [[sprint-06]] (UC-1 MVP Investment Opportunities, 🏁 M1) · [[sprint-07]] (UC-2 MVP Pricing Strategy, 🏁 M2) · [[sprint-09]] (UC-3 Atlas Site Inspector page, 🏁 M3)

### `wiki/` (this knowledge base)

- See [[CLAUDE.md|wiki schema document]] for page conventions, ingest workflow, query workflow, lint workflow, write rules, propagation rule.

## Sources (25 pages, with `priority: P0|P1|P2` frontmatter — added in PR 5)

P0 (7): caop, bgri, osm, idealista, ine, bpstat, ecb. P1 (15): bupi, cadastro, cos, crus, crus-ogc, eurostat, imovirtual, jll, lidar, publico-rankings, remax, sce, srup, srup-ogc, zome. P2 (3): apa, aveiro-pmot, lneg.

### Real-estate portals (5)

- [[idealista]] — largest PT real-estate portal; ZenRows RE API + Universal Scraper mix; three coexisting streams (resale, developments+units, plots); SCD2 + heartbeat sidecars.
- [[imovirtual]] — OLX/Adevinta Nexus portal; direct Next.js `_next/data` JSON (no vendor); devs+units national (801/4,465) + plots Aveiro (4,894); SCD2 + heartbeat; retry/backoff rides out DataDome 403 bursts. See [[2026-06-05-imovirtual-portal-onboarding]].
- [[jll]] — JLL Residential PT; dlt-driven SCD2 from imoguia.com proxy; plots deliberately excluded.
- [[remax]] — RE/MAX Portugal; unified dlt SCD2 (replaces legacy 3-DAG); Pass 2 enrichment pre-fetched in source.py; plots via sitemap walk.
- [[zome]] — Zome PT; dlt SCD2 from Supabase REST; soft-fail refs / hard-fail facts; curated row_hash to fix JSONB-array reorder.

### Statistical & financial APIs (4)

- [[ine]] — INE Statistics Portugal; 47 indicators (33 active) via JSON-stat 1.0; monthly cron.
- [[bpstat]] — Banco de Portugal stats; ~311 series, JSON-stat 2.0; housing credit + interest rates + housing prices.
- [[ecb]] — ECB Euribor 3M/6M/12M; SDMX REST; the simplest source in the stack.
- [[eurostat]] — Eurostat PRC_HPI_Q only; SDMX 2.1; quarterly cross-EU benchmark.

### Scraping (1)

- [[sce]] — SCE energy-certificate registry; only nodriver scraper; Cloudflare Turnstile; current scope Aveiro distrito.

### Education (1)

- [[publico-rankings]] — Público annual school rankings (sec + 9ano Provas Finais); 2018-latest backfill via per-year URL resolver (3 hosting eras); soft-404 trap; the primary `mt` score signal for the [[2026-06-06-pt-education-amenity-design|education amenity pillar]].

### Regulatory + spatial GIS (14)

- [[caop]] — official administrative boundaries (distritos / municípios / freguesias); P0 foundation source.
- [[bupi]] — modern simplified cadastre; 152 concelhos, ~3.25M parcels.
- [[cadastro]] — legacy formal cadastre via OGC API; partial coverage (2000-2007 surveys only).
- [[cos]] — national land-use/cover map (COS 2023); ~784k polygons; 4-level hierarchical code.
- [[crus]] — legacy WFS land-use classification; 5 municipalities only; being replaced by [[crus-ogc]].
- [[crus-ogc]] — national CRUS via OGC API; ~236k features; dual-runs with [[crus]] for parity.
- [[srup]] — legacy WFS property constraints; Phase 1 categories (IC / RAN / DPH); being replaced by [[srup-ogc]].
- [[srup-ogc]] — modern OGC API for SRUP + SGIFR; 22 layers; per-layer page_size/timeout overrides.
- [[apa]] — APA ARPSI floodplain; EU Floods Directive scope (NOT all flood zones); ~188 polygons national.
- [[bgri]] — INE Census 2021 statistical geography; 32 variables across 4 themes; subsections + sections.
- [[lidar]] — DGT 2m DTM + DSM rasters; STAC Collections; Aveiro region; manifest tables in bronze.
- [[lneg]] — LNEG geology 1:500k + national aquifers; ArcGIS REST.
- [[osm]] — OpenStreetMap PT via Geofabrik; 18 layers, ~4.5M features; companion OSRM + Nominatim services.
- [[aveiro-pmot]] — Aveiro municipal WebGIS bulk WMS-GFI extractor; one-off, not a recurring DAG; ~1,669 feature types.

## Concepts (20 pages)



- [[bronze-permissive]] — bronze accepts whatever the source returns; validation lives in dbt staging; never-delete invariant.
- [[publico-rankings-column-legend]] — ground-truthed legend for the 91 cryptic columns in `bronze_education.raw_publico_rankings`; matched UI-label-to-DB-value against the Público school card for Escola Dr. Ferreira da Silva (eid=1069); 9 families (identity / headline / Superação / per-disciplina / Nota Interna CIF / prior-year carry / contexto socioeconómico / taxa retenção / equidade-equivalência); collision trap: 1-letter `ma` = Economia A, 2-letter `ma` = Matemática A.
- [[pydantic-not-in-dlt]] — Pydantic in configs YES, in dlt resources NO; the strict guardrail protecting [[bronze-permissive]].
- [[scd2-row-hash]] — curated `*_VERSION_COLUMNS` policy for SCD2 row versioning; include real business events, exclude noisy proxies.
- [[heartbeat-sidecar]] — UPSERT-only companion table answering "is this entity still in the source?"; the 21-day silver-layer floor.
- [[portal-naming-conventions]] — cross-pipeline naming policy for dlt portal pipelines; structural uniformity vs source-faithful leaf names.
- [[portal-plot-conventions]] — how plots/terrenos are modelled across the three portals (separate `*_plots` tables, plot-specific SCD2 cols).
- [[portal-field-map]] — cross-portal correspondence matrix (development / unit / plot grain) for [[remax]] + [[idealista]] + [[jll]] + [[zome]] (JLL plots out of scope per [[jll]] Quirks).
- [[zenrows-universal-vs-re-api]] — [[idealista]]'s mixed-API scrape strategy; ~5× cheaper RE API + Universal Scraper for HTML pages.
- [[payload-cache-lifecycle]] — module-level `_payload_cache` shared across [[idealista]]'s four resources; saves ~85% of ZenRows spend per run.
- [[medallion-layering]] — bronze/silver/gold + per-source-bronze-schema architecture; transformation-placement rules.
- [[ingest-flows]] — six-flow taxonomy (A REST / B scraping / C GIS / D derived / E spatial composition / F portal cross-reference) with decision tree for new sources.
- [[spatial-strategy]] — CRS dual-storage convention (4326 + 3763), GIST + H3 indexing, common spatial query templates, location-score computation.
- [[srup-constraint-model]] — how the 14 SRUP regulatory layers gate construction on a drawn polygon; the `(constraint_code, zone_type)` → severity model behind `dim_constraint_severity` + sprint-09's `fn_assess_polygon`.
- [[srup-properties-schema]] — per-key breakdown of the 16 `raw_srup_*` `properties` JSONB blobs (OGC lowercase vs WFS UPPERCASE conventions) → typed `stg_srup_*` columns.
- [[sce-buildings-clustering]] — DBSCAN(30m) + GROUP BY normalized_address roll-up of geocoded [[sce]] certificates into `silver_sce_buildings` rows; documents Decisions 1-5 (Nominatim-only filter, exact-match over Levenshtein, no parcel_id, no Splink, address-grouping vs coord-only).
- [[cross-portal-dev-dedup]] — name-driven word-set Jaccard dedup of the 4 listing portals into `silver_unified_developments`; documents why proximity-first failed, the normalization pipeline (typology + boilerplate + trailing-concelho strip), the geo hierarchy (JLL > Zome > RE/MAX > idealista), and why SCE is *not* merged here.
- [[dbt-source-column-descriptions]] — every column in every `_staging_<domain>__sources.yml` carries a `description:`; one line, names unit/scale, cites original source key when renamed, expands codebook letters inline; verification triad: `information_schema` ≡ YAML ≡ dbt manifest column counts must agree.
- [[silver-dq-baseline]] — 4 universal invariants every silver model follows (dual-CRS, surrogate PK, bronze→silver row-count parity, FK denorm integrity); deliberate exclusion of `accepted_values`; statistical-source silver topology mapping (macro_timeseries vs ine_indicators_long boundary). Established by sprint-09 WS4 quick-wins batch.
- [[airflow-home-isolation]] — the `~/airflow/airflow.cfg` bleed gotcha + `make verify`'s `AIRFLOW_HOME=$(PWD)/.airflow-home` fix.

## Architecture (4 pages — PR 6 seed)

The as-built / as-designed architecture, decomposed from README §3 + §4 + §11 + §13 with `[[wikilinks]]` to relevant ADRs and concepts. See [[architecture/README|architecture orientation]] for page conventions.

- [[tech-stack]] — every technology choice with rationale + alternatives-considered table.
- [[infra]] — Docker Compose service map + Hetzner AX102 server spec + PostgreSQL schema organization.
- [[orchestration]] — Airflow DAG taxonomy + schedule map for ~22 recurring DAGs.
- [[data-quality]] — dbt tests + Great Expectations + `metadata.pipeline_runs` audit trail.

## Planning (5 pages — PR 7 seed + pillar trackers)

Forward-looking project planning content (vs. as-built [[architecture/README|architecture]]). See [[planning/README|planning orientation]] for how each page gets maintained.

- [[risks]] — 15-row risk register; revisited at every sprint close.
- [[resources]] — team / budget / per-sprint effort / data-volume estimates from README §15.
- [[roadmap-p3-p4]] — deferred sources (~18) organized into Phase 2A / 2D / 2B / 2C with per-row trigger conditions.
- [[milestones]] — Go/No-Go gates for M1 ([[UC-1]]) / M2 ([[UC-2]]) / M3 ([[UC-3]]) + MVP hedonic feature coverage.
- [[pt-education-amenity-pillar]] — live Phase 0/1/2 tracking dashboard for the 5-source education ingest (KG → university, públicos + privados); source #1 [[publico-rankings]] shipped in [PR #52](https://github.com/dacostalindo/House4House/pull/52).

## Decisions (18 ADRs)

**Foundational** (Phase 1-3 dev-tooling, surfaced via gstack reviews):

- [[2026-05-05-uv-workspace-shape]] — single root pyproject + apps/pipelines workspace members; one lockfile.
- [[2026-05-05-cosmos-pin]] — `astronomer-cosmos>=1.6,<1.7` because 1.7+ imports `airflow.sdk` (Airflow-3-only).
- [[2026-05-08-sqla-1.4-concession]] — apps/ accepts workspace-wide SQLA 1.4 (Airflow 2.10 forces <2.0; apps had zero SQLA code).
- [[2026-05-08-phase-2-5-closure]] — Phase 2.5 absorbed into Phase 2 (zero Pydantic-eligible sites surfaced by audit).
- [[2026-05-08-idealista-enrichment-architecture]] — three coexisting streams; Phase 5 enrichment writes to silver, not bronze.

**Stack** (PR 6 — README §3 + §4 surfaced):

- [[2026-05-10-single-server-self-hosted]] — root decision; 6 other ADRs cascade from this.
- [[2026-05-10-postgis-as-warehouse]] — PostgreSQL 16 + PostGIS 3.4, rejecting Snowflake/BigQuery/RDS.
- [[2026-05-10-minio-not-s3]] — self-hosted MinIO for raw landing, rejecting S3/GCS.
- [[2026-05-10-airflow-2-not-3]] — Airflow 2.10 stay-the-course; Airflow 3 migration deferred.
- [[2026-05-10-dbt-not-sqlmodel]] — dbt Core for transformations, rejecting SQLModel + SQLMesh.
- [[2026-05-10-nominatim-osrm-self-hosted]] — Nominatim + OSRM self-hosted, rejecting Google Maps APIs.
- [[2026-05-10-metabase-streamlit-not-superset]] — Metabase (BI) + Streamlit + Kepler.gl (custom apps); rejecting Superset.

**Spatial** (PR 7 — README §9 surfaced):

- [[2026-05-10-dual-crs-storage]] — every spatial table stores `geom` (4326 for display + joins) + `geom_pt` (3763 for distance + area in metres).

**Dev-tooling** (Phase 4 + Phase 6 — gstack plan-eng-review + plan-devex-review + devex-review surfaced):

- [[2026-05-12-wiki-linter-deferred-to-phase-7]] — mechanical `wiki_health.py` moves to Phase 7 to co-design with structured `wiki/_schema.yaml` (single source of truth).
- [[2026-05-12-pre-commit-local-hook]] — pre-commit uses `language: system` + `uv run ruff` to eliminate version drift vs CI/Makefile.
- [[2026-05-12-phase-6-ty-advisory]] — Astral's `ty` (beta) ships as advisory CI check via Phase 4 annotation-grouping pattern; 3 concrete graduation triggers to BLOCKING.
- [[2026-06-05-imovirtual-portal-onboarding]] — 5th listing portal; direct Next.js `_next/data` JSON (no ZenRows, DataDome-resilient via retry/backoff); devs/units national + plots Aveiro; built, run & verified (801 devs / 4,465 units / 4,894 plots). `confidence: high`.

**Use cases** (UC-3 reframe — gstack /office-hours + /plan-eng-review surfaced):

- [[2026-05-12-uc3-expanded-scope]] — UC-3 reframed from national spatial-overlay into end-to-end 7-stage plot economic-value pipeline; v1 wedge = Aveiro Stages 1-4 + SCE + idealista LLM + dev dedup; `confidence: speculation`, gated on 3 PT developer interviews.

## Sprints (13 pages — PR 3 seed)

Two parallel tracks: 11 data-product sprints + 1 dev-tooling sprint (gstack-driven Phase 1-7 roadmap). See [[sprints/README|sprints orientation]] for the schema, status semantics, and living-roadmap mechanic.

### Data-product sprints

- [[sprint-01]] — Infrastructure & Geography (Weeks 1-2) — `done`
- [[sprint-02]] — Core Market Data (Weeks 3-4) — `done`
- [[sprint-03]] — Silver Layer + UC-3 GIS Foundation (Weeks 5-6) — `mostly_done`
- [[sprint-04]] — Image Classification + Location Scores (Weeks 7-8) — `in_progress`
- [[sprint-04.4]] — Pre-Sprint-4.5 Preparation (Week 8.5) — `done` (audit-corrected: shipped 2026-04-30)
- [[sprint-04.5]] — Listings + Developments Cross-Portal Dedup (Week 9) — `planned`
- [[sprint-05]] — Hedonic Model & Valuation (Weeks 10-11) — `planned`
- [[sprint-06]] — UC-1 MVP Investment Opportunities (Weeks 12-13) — `planned` 🏁 M1
- [[sprint-07]] — UC-2 MVP Pricing Strategy (Weeks 14-15) — `planned` 🏁 M2
- [[sprint-08]] — UC-3 v1 wedge Part 1 (Foundations + Aveiro Vertical Slice) (Weeks 16-18) — `planned` 🏁 M3 Part 1
- [[sprint-09]] — UC-3 v1 wedge Part 2 (Wedge Completion + Atlas Inspector + Demo) (Weeks 19-21) — `planned` 🏁 M3
- [[sprint-10]] — Production Hardening + Portal Expansion + UC-3 v2 Readiness (Weeks 22-24) — `planned`

### Dev-tooling sprint (parallel track)

- [[sprint-dev-tooling]] — gstack 7-Phase roadmap (Phase 1+2+3+4+6+7 done; Phase 2.5 closed; Phase 5 planned)

## Use cases (3 pages + 1 folder — PR 4 seed + UC-4 added 2026-05-29)

Each UC combines product narrative + conceptual data model + serving layer in one page (per `/plan-design-review` finding 2.3 lock). UC-4 is the deliberate folder exception — see [[UC-4]] for rationale. See [[use-cases/README|use-cases orientation]] for schema + cross-UC dependencies.

- [[UC-1]] — Undervalued Property Identification (investors / promoters / fund managers / flippers) — MVP at [[sprint-06]] 🏁 M1
- [[UC-2]] — New Housing Unit Pricing Strategy (developers / commercial directors / project managers) — MVP at [[sprint-07]] 🏁 M2; depends on UC-1 hedonic
- [[UC-3]] — End-to-End Plot Economic-Value Pipeline (7-stage funnel: Scout → Inspect → Assemble → Build out → Value → Profit → Competitive Intel; land developers / promoters / funds) — v1 wedge = Aveiro Stages 1-4 + SCE unit aggregation + idealista LLM plot extraction + dev dedup, ships across [[sprint-08]]+[[sprint-09]] 🏁 M3 Week 21. Stages 5-6 (Value/Profit, depends on UC-1 hedonic) + full Stage 7 (national rollout + promoter dedup) defer to v2/v3. Gated on 3 PT developer interviews per [[2026-05-12-uc3-expanded-scope]] kill criteria.
- [[UC-4]] (folder) — Qualitative Signal Layer (Agentic News / Project Actors / Regulatory Events) — turns the warehouse from structured-data lake into queryable KB by adding *who* (developer + architect), *what's said* (PT real-estate press), *what's changing* (DRE + municipal PDM events). Foundation PR at `sprint-04.7` between [[sprint-04.5]] dedup and [[sprint-05]] hedonic; 6 PRs over ~10 weeks. Strategy delivery order: Articles → Project Actors → Regulatory. Absorbs [[planning/PoCs/agentic-pipeline]]. Introduces Flow G (LLM-mediated typed extraction) as a new ingest-flow type. Sub-pages: [[UC-4/problem-statement]] · [[UC-4/project-plan]] · [[UC-4/sprint-plan]].

## Forthcoming (PR 5-8)

The README → wiki migration continues iteratively. Per locked plan:

| PR | New folder | Pages | README section |
|---|---|---|---|
| ~~PR 5~~ ✅ | extends `wiki/sources/` (priority frontmatter) + new `wiki/concepts/ingest-flows.md` | 23 frontmatter additions + 1 new concept | §2 + §6 |
| ~~PR 6~~ ✅ | `wiki/architecture/` | 4 pages (stack, infra, orchestration, data-quality) + 7 new ADRs | §3 + §4 + §11 + §13 |
| ~~PR 7~~ ✅ | `wiki/planning/` | 4 pages (risks, resources, roadmap-p3-p4, milestones) + 1 concept (spatial-strategy) + 1 ADR (dual-crs-storage) | §9 + §14 + §15 + §16 + §17 partial |
| ~~PR 8~~ ✅ | README → stub rewrite | 1 file | retire README's strategic narrative; wiki is now canonical |

§8 Physical Data Models is **dropped from migration**; dbt + dbt-docs is source of truth. See [[medallion-layering]] for the architecture.
