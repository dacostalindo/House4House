---
title: Sprint 1 — Infrastructure & Geography
type: plan
last_verified: 2026-05-09
tags: [sprint, plan, infrastructure, geography, weeks-1-2]
status: done
sprint_number: "1"
weeks: "1-2"
last_status_update: 2026-05-09
---

## For future Claude

This is the **Sprint 1** page (Weeks 1-2): Docker infrastructure, GIS + API ingestion templates, P0 geography sources loaded to bronze, and dim_geography built. It shipped fully — Airflow + MinIO + PostGIS + dbt + Cosmos + OSRM + Nominatim + Metabase + Streamlit are all running. Read this page when you need to know what foundational infrastructure was set up first, or what's already loaded as the spatial backbone for everything downstream.

## Goal

Stand up the local-first data warehouse infrastructure (Airflow + MinIO + PostGIS + dbt + Cosmos), build reusable ingestion DAG templates for Flow A (REST API) and Flow C (GIS), and ingest the P0 foundational sources — [[caop]] (administrative boundaries), [[bgri]] (Census 2021 statistical geography), [[osm]] (POIs + transport + roads), [[ine]] (statistical indicators) — into bronze. Final output: `gold_analytics.dim_geography` with 3,049 freguesias and dual-CRS geometry, ready as the spatial dimension everything else joins to.

## Deliverables

- ✅ Docker Compose: Airflow + MinIO + PostGIS + Metabase + Streamlit running
- ✅ Airflow GIS ingestion template (Flow C reusable factory)
- ✅ Airflow API ingestion template (Flow A reusable factory)
- ✅ [[caop]] boundaries → MinIO + bronze_geo (3,049 freguesias + 308 municípios + 18 distritos)
- ✅ [[bgri]] Census 2021 → MinIO + bronze_ine (203,264 subsection polygons + 32 census columns)
- ✅ [[osm]] Portugal extract → MinIO + bronze_location (18 layers, 5.2M features)
- ✅ [[ine]] API indicators → MinIO + bronze_ine (33 indicators, 907,533 rows from JSON-stat)
- ✅ PostGIS warehouse service (postgis/postgis:16-3.4 + 15 schemas, see [[medallion-layering]])
- ✅ dbt-postgres 1.9 with custom schema macro and Cosmos integration
- ✅ `gold_analytics.dim_geography` (3,049 freguesias, dual-CRS, census-enriched)
- ✅ OSRM build (3 profiles: car/walking/cycling on ports 5050/5051/5052)
- ✅ Nominatim geocoder (port 8088, forward + reverse)
- ✅ Metabase + Streamlit base apps running (per audit: shipped, status was originally `Pending` in README)

## Exit criteria

All bronze tables populated; `dim_geography` live; Nominatim + OSRM responding; Metabase + Streamlit accessible. **Met.**

## Key decisions

- Self-hosted single-server posture (no cloud-native alternatives chosen) — landed as ADR in PR 6 (`single-server-self-hosted`).
- PostGIS + MinIO chosen over Snowflake/BigQuery + S3 — landed as ADRs in PR 6 (`postgis-as-warehouse`, `minio-not-s3`).
- Airflow 2.10 retained over Airflow 3 — see [[2026-05-05-cosmos-pin]].
- Cross-platform: per [[2026-05-05-uv-workspace-shape]], single workspace with apps + pipelines members.
- [[airflow-home-isolation]]: `make verify` exports `AIRFLOW_HOME=$(PWD)/.airflow-home` to dodge the `~/airflow/airflow.cfg` bleed gotcha discovered during this Phase 1 spike.

## Status update history

- 2026-Q1: declared in README §12 initial draft; status `planned`
- 2026-Q1: `planned` → `in_progress` (Docker + dbt + first GIS ingestions started)
- 2026-Q1: `in_progress` → `done` (all bronze tables loaded, dim_geography live)
- 2026-05-09: Metabase + Streamlit task statuses corrected from `Pending` to `done` per Phase 1 README cleanup audit (containers had been running but README hadn't been updated)

## See also

- [[caop]], [[bgri]], [[osm]], [[ine]] — the four P0 sources Sprint 1 ingested
- [[medallion-layering]] — the bronze/silver/gold + per-source-bronze-schema layout this sprint set up
- [[airflow-home-isolation]] — gotcha discovered during Sprint 1's spike
- [[2026-05-05-uv-workspace-shape]], [[2026-05-05-cosmos-pin]] — foundational ADRs from this sprint
- [[sprint-02]] — next sprint (Core Market Data)
- [[sprint-dev-tooling]] — parallel dev-tooling track running alongside
