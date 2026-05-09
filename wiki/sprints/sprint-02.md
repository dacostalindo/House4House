---
title: Sprint 2 — Core Market Data
type: plan
last_verified: 2026-05-09
tags: [sprint, plan, market-data, idealista, weeks-3-4]
status: done
sprint_number: "2"
weeks: "3-4"
last_status_update: 2026-05-09
---

## For future Claude

This is the **Sprint 2** page (Weeks 3-4): Idealista listings (sale + rental) flowing daily, macro indicators ([[ecb]], [[bpstat]], [[eurostat]]) loaded, dbt restructured into Cosmos task groups, geocoding pipeline operational, and the first dim seeds (`dim_time`, `dim_property_type`) shipped. Read this page when you need to know how the core market-data layer was built — the foundation for hedonic modelling later.

## Goal

Get [[idealista]] flowing daily into bronze, load all macro/financial indicators ([[ecb]] Euribor, [[bpstat]] mortgage rates + housing prices, [[eurostat]] HPI), restructure dbt into domain-grouped staging models with Cosmos `DbtTaskGroup`, ship the geocoding pipeline ([[osm]]-derived Nominatim → reverse geocode listings), and seed the foundational dimensions (`dim_time`, `dim_property_type`).

## Deliverables

- ✅ [[idealista]] API integration → daily sale + rental ingestion to `bronze_listings.raw_idealista`
- ✅ [[idealista]] bronze schema (source-oriented, JSONB-permissive per [[bronze-permissive]])
- ✅ [[idealista]] DAG refactor (Pydantic config dataclass per [[pydantic-not-in-dlt]], tenacity retry, cleanup task, template alignment)
- ✅ [[ecb]] Euribor monthly DAG → `bronze_macro.raw_ecb` (3 series via SDMX API)
- ✅ [[bpstat]] monthly macro data → `bronze_macro.raw_bpstat` (3 domains, 16 datasets via JSON-stat)
- ✅ [[eurostat]] quarterly HPI → `bronze_macro.raw_eurostat` (38 EU countries, JSON-stat)
- ✅ dbt restructure + Cosmos: domain staging (`geo/`, `ine/`, `listings/`, `macro/`, `location/`), `DbtTaskGroup`, silver skeletons. 11 staging views + `silver_market.macro_timeseries`
- ✅ Geocoding pipeline: reverse geocoding via [[osm]] Nominatim → `bronze_listings.reverse_geocoded` (1,334 coords, 100% postal code coverage); address enrichment in `silver_properties.unified_listings` (58% → 93% street addresses)
- ✅ `gold_analytics.dim_time` seed (date dimension 2000-2035, 13,149 rows via dbt_utils.date_spine, YYYYMMDD integer key, ISO day-of-week, INE quarter labels)
- ✅ `gold_analytics.dim_property_type` seed (16-row static dimension: Idealista raw type/subtype → Portuguese labels)

## Exit criteria

[[idealista]] flowing daily; macro indicators loaded; dbt Cosmos pipeline operational; geocoding working; per-source Cosmos DAGs (`dbt_{source}_build`) wired to all 8 bronze DAGs. **Met.**

## Key decisions

- [[idealista]] Pydantic config moved out of the dlt resource per [[pydantic-not-in-dlt]] — config is project-internal (Pydantic OK), bronze ingest is permissive.
- Cosmos 1.6 pin retained from Sprint 1 ([[2026-05-05-cosmos-pin]]) — Cosmos 1.7+ breaks Airflow 2.10.
- Domain staging layout (one staging dir per source category) instead of flat `staging/` — matches the per-source-bronze-schema discipline of [[medallion-layering]].
- `silver_market.macro_timeseries` as a unified long-format `(date, series_id, value)` table across [[ecb]] + [[bpstat]] + [[eurostat]] — silver conforms across sources, gold consumes the conformed shape.

## Status update history

- 2026-Q1: declared in README §12; status `planned`
- 2026-Q1: `planned` → `in_progress` (Idealista DAG built, ECB live)
- 2026-Q1: `in_progress` → `done` (all bronze loaded, dbt Cosmos operational, geocoding pipeline live)

## See also

- [[idealista]], [[ecb]], [[bpstat]], [[eurostat]], [[osm]] — the five sources Sprint 2 wired up
- [[bronze-permissive]], [[pydantic-not-in-dlt]] — rules followed
- [[medallion-layering]] — the schema layout
- [[sprint-01]] — predecessor (foundational infrastructure)
- [[sprint-03]] — successor (silver layer unification + UC-3 GIS)
