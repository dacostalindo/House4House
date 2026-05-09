---
title: Sprint 8 — UC-3 MVP Land Development Opportunities
type: plan
last_verified: 2026-05-09
tags: [sprint, plan, uc-3, land-development, milestone, weeks-16-18]
status: planned
sprint_number: "8"
weeks: "16-18"
last_status_update: 2026-05-09
---

## For future Claude

This is the **Sprint 8** page (Weeks 16-18). It ships **🏁 Milestone 3: UC-3 MVP LIVE** — land developers can screen development opportunities with real economics (GDV = GBA × hedonic predicted €/m²). All UC-3 GIS data ([[bupi]] 3.25M parcels, [[cos]] 784K polygons, [[crus]] 5 munis, [[srup]] IC/RAN/DPH, [[cadastro]], PDM) was bronze-loaded in Sprint 3; this sprint builds the analytical models + serving layer on top. Also includes OSRM drive-time integration (deferred from Sprint 4).

## Goal

Detect vacant buildable parcels via spatial overlay ([[bupi]] × [[cos]] × [[crus]] × [[srup]]), assemble adjacent ones via `ST_ClusterDBSCAN`, compute development economics (GBA × hedonic GDV - construction costs - land cost = residual), score by composite opportunity factors, and expose via Land Dashboard + Parcel Explorer + Site Analyzer.

**Prerequisite:** UC-1 hedonic model complete (Sprint 5) — enables real GDV from `predicted €/m²`.

## Deliverables

- MS Building Footprints ingestion (S42, ~5M polygons) → `bronze_geo.raw_building_footprints`
- Building footprints staging + silver: cleaned, EPSG:3763 → `silver_geo.building_footprints`
- Seed `gold_analytics.ref_construction_costs`: CSV seed €/m² by typology, quality tier, region (INE indices + RICS benchmarks)
- Density extraction from zoning: parse `max_floors`, `max_density_index`, `max_coverage_ratio` from `land_designation` text in `silver_geo.zoning`. zone_category defaults where not parseable
- Vacant land detection: [[bupi]] parcels WHERE `land_use.is_urban = FALSE` ([[cos]]) AND `zoning.zone_category IN ('urban_expansion', 'urban_consolidated')` ([[crus]]). Boolean flags `is_vacant`, `is_buildable`, `is_agricultural` → `gold_analytics.vacant_parcels`
- Constraint overlay: per-parcel `ST_Intersects` with `stg_srup_ran`, `stg_srup_dph`, `stg_srup_ic`. Constraint severity 0=none, 1=DPH buffer, 2=RAN partial, 3=RAN full, 4=heritage → `gold_analytics.parcel_constraints`
- Parcel assembly via `ST_ClusterDBSCAN(geom_pt, eps=5, minpoints=1)` on vacant buildable. Pre-filter to candidates (~50-100K parcels). Aggregate: total_area_m2, parcel_count, combined geometry (`ST_UnaryUnion`) → `gold_analytics.development_sites` + `site_parcels`
- Development economics model: per-assembly GBA = area × density_index × coverage_ratio. GDV = GBA × predicted €/m² (from Sprint 5 hedonic). Construction cost = GBA × `ref_construction_costs`. Land residual = GDV × (1 - margin) - costs. ROI metrics → `development_sites.est_*` columns
- Opportunity scoring: composite `opportunity_score` (buildability 0.25 + constraint clearance 0.20 + assemblable area 0.20 + development margin 0.25 + location score 0.10)
- OSRM drive-time integration: batch [[osm]] OSRM API listing → city center / airport / nearest hospital. Upgrade `property_location_scores` from crow-flies to real travel time. Improves hedonic R²
- Serving — Land Dashboard (Metabase): vacant land inventory by municipality, top 20 sites by ROI, constraint distribution, zoning filter
- Serving — Parcel Explorer (Kepler.gl): [[bupi]] parcels colored by buildability, [[srup]] constraint layers (toggleable), [[cos]] land use (toggleable), building footprints (toggleable), [[crus]] boundaries. `ST_SimplifyPreserveTopology` for zoom-level performance
- Serving — Site Analyzer (Streamlit): click on map → assemblable parcels, zoning params, constraint summary, estimated GBA, projected GDV, residual land value, ROI

## Exit criteria

`development_sites` populated with parcel clusters + economics; Land Dashboard + Parcel Explorer + Site Analyzer rendering against real data; OSRM drive-time backfilling `property_location_scores`; UC-3 MVP LIVE.

## Key decisions

- Use [[srup-ogc]] (modern OGC API path) for any Phase-2 SRUP categories that emerge — [[srup]] WFS path retains for Phase 1 (IC, RAN, DPH) and dual-runs RAN until parity
- Building Footprints (S42) — added in Sprint 8 (was deferred); needed for accurate parcel coverage ratios
- OSRM drive-time was deferred from Sprint 4 because crow-flies KNN sufficient for MVP hedonic; Sprint 8 hedonic re-train (Sprint 9) benefits from real drive-times

## Status update history

- 2026-04-18: declared in README §12; status `planned`

## See also

- [[bupi]], [[cos]], [[crus]], [[crus-ogc]], [[srup]], [[srup-ogc]], [[cadastro]], [[osm]], [[apa]] — UC-3 spatial sources
- [[medallion-layering]] — silver/gold pattern
- [[sprint-03]] — predecessor (UC-3 GIS bronze + staging laid down here)
- [[sprint-05]] — predecessor (hedonic enables GDV)
- [[sprint-06]], [[sprint-07]] — sibling milestones (UC-1, UC-2)
- [[sprint-09]] — UC-3 model recalibration (ARU + REN + permits) lands in Sprint 9

## 🏁 Milestone

**Milestone 3 (Week 18): UC-3 MVP LIVE.** Land developers can screen development opportunities with real economics.
