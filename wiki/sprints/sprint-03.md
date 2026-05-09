---
title: Sprint 3 — Silver Layer + UC-3 GIS Foundation
type: plan
last_verified: 2026-05-09
tags: [sprint, plan, silver, uc-3, gis, weeks-5-6]
status: mostly_done
sprint_number: "3"
weeks: "5-6"
last_status_update: 2026-05-09
---

## For future Claude

This is the **Sprint 3** page (Weeks 5-6): silver layer for listings + the UC-3 GIS foundation. `silver_properties.unified_listings` ships with normalized prices/areas/typologies + Nominatim address enrichment + spatial join to `dim_geography` + SCD Type 2 price tracking. UC-3 regulatory GIS sources ([[bupi]], [[cos]], [[crus]], [[srup]], [[cadastro]]) are bronze-loaded with staging models. Marked `mostly_done` because the [[idealista]]-only listing scope means cross-portal dedup is deferred (Sprint 4.5+).

## Goal

Build the canonical silver listing table (`silver_properties.unified_listings`) — typed, geocoded, SCD2-tracked — and ingest the full UC-3 land-development GIS stack to bronze + staging so Sprint 8 can build the analytical models. Also seed reference tables (IMI/IMT) and the census-demographics silver model.

## Deliverables

- ✅ Listing normalization: parse TEXT → typed (`price` NUMERIC, `area` NUMERIC, typology "T3" → `rooms` SMALLINT, floor codes, condition/energy to Portuguese, JSONB feature extraction for construction year, orientation, heating, amenities). Human-readable property_type/subtype/type_group columns
- ✅ Address cleaning via [[osm]] Nominatim reverse geocoding (street-name fallback when raw lacks prefix; postal code always from Nominatim). 58% → 93% street addresses; 0% → 100% postal codes
- ✅ Geocode join: `ST_Within(point, freguesia_geom)` → `dim_geography.geo_key` + freguesia/concelho/distrito codes
- ✅ SCD Type 2 price tracking: incremental merge preserves `first_seen_date`, `initial_price_eur`, `_created_at`. Tracks `price_change_count`, `listing_age_days`. Staleness-based `is_active` (3-day rule + post-hook UPDATE)
- ✅ IMI/IMT reference tables: 16-row IMT transfer-tax brackets (primary/secondary/rural/other urban, 2025) + 278-municipality IMI rates (urban 0.30%-0.45%) — VALUES-based SQL models in `gold_analytics`
- ✅ Census demographics: [[bgri]] 203K subsections → 2,882 freguesias (population by age band, household size, dwelling vacancy/tenure 42% avg vacancy / 82% owner-occupied; INE building aging ratio + repair %). 135 BGRI codes unmatched to [[caop]] (boundary changes; documented gap)
- ✅ [[bupi]] cadastral parcels (3.25M MultiPolygons with NumeroMatriz keys) → `bronze_regulatory.raw_bupi`
- ✅ [[cos]] 2023 land use (784K polygons, 4-level hierarchy) → `bronze_geo.raw_cos2023`
- ✅ [[crus]] DGT WFS zoning (5 municipalities: Aveiro, Lisboa, Porto, Coimbra, Leiria) → `bronze_regulatory.raw_crus_*`
- ✅ [[srup]] Phase 1 constraints (IC heritage, RAN agricultural reserve, DPH water domain) → `bronze_regulatory.raw_srup_*`
- ✅ [[cadastro]] OGC API (formal surveyed boundaries, partial coverage) → `bronze_regulatory.raw_cadastro`
- ✅ PDM Zoning (LX + Porto ArcGIS REST) → `bronze_regulatory.raw_pdm_*`
- ✅ dbt staging: regulatory sources (`stg_bupi`, `stg_cos2023`, `stg_crus_ordenamento`, `stg_srup_ic`, `stg_srup_ran`, `stg_srup_dph`, `stg_cadastro`)
- ✅ Silver land use: `silver_geo.land_use` (COS hierarchy + boolean flags `is_urban`, `is_residential`, `is_agricultural`, `is_forest` + freguesia assignment)
- ✅ Silver zoning: `silver_geo.zoning` (CRUS/PDM normalized `zone_category`, buildability params)
- Deferred: Imovirtual scraper (S05) — second listing portal not built; deferred to Sprint 9
- Deferred: Cross-portal dedup — depends on second portal; pulled into Sprint 4.5 instead

## Exit criteria

`unified_listings` with ~100K+ active listings; >95% geocoded; `census_demographics` populated; UC-3 GIS data ingested and staged ([[bupi]], [[cos]], [[crus]], [[srup]], [[cadastro]], PDM all bronze-loaded with staging models operational). **Met for the in-scope items;** Imovirtual + cross-portal dedup explicitly deferred — hence `mostly_done`.

## Key decisions

- [[scd2-row-hash]] for unified_listings: incremental merge with curated row hash (not auto-hash on full row) to avoid phantom version churn from JSONB array reorder.
- COS Level-1 + Level-2 boolean flags (vs Level-4 enum) for silver — granularity trade-off; deeper levels deferred until a use case demands them.
- IMT/IMI as gold reference seeds (not silver) — small, static, lookup-shaped; gold is the right tier.
- Cross-portal dedup pushed to Sprint 4.5 once 4 portal APIs (RE/MAX, Idealista, Zome, JLL — and later ERA/C21/KW per [[2026-05-08-idealista-enrichment-architecture]]) are aligned.

## Status update history

- 2026-Q1: declared in README §12; status `planned`
- 2026-Q1: `planned` → `in_progress` (silver listings work began, UC-3 ingestion templates scaffolded)
- 2026-Q1: `in_progress` → `mostly_done` (all in-scope shipped; Imovirtual + cross-portal dedup explicitly deferred to Sprint 4.5/9)

## See also

- [[idealista]], [[bgri]], [[caop]], [[osm]], [[bupi]], [[cos]], [[crus]], [[srup]], [[cadastro]] — sources used
- [[scd2-row-hash]], [[heartbeat-sidecar]], [[bronze-permissive]], [[medallion-layering]] — concepts applied
- [[sprint-02]] — predecessor (Idealista + macro)
- [[sprint-04]] — successor (image classification + location scores)
- [[sprint-04.5]] — where deferred Imovirtual/cross-portal-dedup work landed
