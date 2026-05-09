---
title: UC-3 — Land Development Opportunity Detection
type: plan
last_verified: 2026-05-09
tags: [use-case, plan, uc-3, land-development, gis, m3]
uc_number: "3"
status: planned
sprint_target: "sprint-08"
last_status_update: 2026-05-09
---

## For future Claude

This is the **UC-3** page — the land-development opportunity-detection use case. Identifies vacant/underutilized parcels in urban-expansion zones via spatial overlay ([[bupi]] × [[cos]] × [[crus]] × [[srup]]), assembles adjacent parcels via `ST_ClusterDBSCAN`, computes development economics (GDV from [[UC-1]] hedonic × GBA from zoning), scores opportunities, and surfaces them via Land Dashboard / Parcel Explorer / Site Analyzer. MVP ships at [[sprint-08]] (🏁 Milestone 3, Week 18). The most spatially-intensive of the three UCs — every layer is a PostGIS query.

## Users

**Land developers**, **real estate promoters**, **investment funds**, and **municipal development offices**. They source vacant/underutilized urban parcels to acquire and develop. Need answers about zoning constraints, ownership traceability, building potential, and economic viability before approaching landowners.

## Business questions

These nine questions drive UC-3 (the most question-rich of the three UCs):

1. **Which plots of land in urban expansion or rehabilitation zones are potentially available for development?** Spatial mismatch between [[crus]] (urban-expansion zoning) and [[cos]] (currently non-artificial land use).
2. **Under current zoning ([[crus]]), what can be built on a given plot?** Density, height, allowed use type extracted from `land_designation` text.
3. **Is the plot inside an ARU (tax benefits for rehabilitation)?** Spatial overlay with ARU boundaries (lands in [[sprint-09]]).
4. **What [[srup]] / [[srup-ogc]] constraints apply?** RAN (agricultural reserve), REN (ecological reserve), DPH (water domain), heritage protection, military zones.
5. **What is the current land use ([[cos]])?** Vacant, agricultural, already built, mixed?
6. **What [[bupi]] cadastral parcels compose the site?** Total assemblable area via `ST_ClusterDBSCAN` on touching/overlapping parcels.
7. **Who is the owner?** [[bupi]] gives `NumeroMatriz` + `Dicofre` → lookup key to **Caderneta Predial** at Finanças (manual retrieval; the wiki identifies opportunities, the user does the ownership pull).
8. **Is there active construction or recent building permits nearby?** Phase 1: MS Building Footprints spatial join to detect existing structures. Phase 2 (deferred): Sentinel-1 SAR change detection for cloud-independent monitoring.
9. **What is the estimated development return?** GBA × local €/m² (from [[UC-1]] hedonic) minus land + construction cost.

## Decision output

A ranked list of development sites with a composite `opportunity_score` (0-100) combining buildability (0.25), constraint clearance (0.20), assemblable area (0.20), development margin (0.25), and location score (0.10). Surfaced as Metabase Land Dashboard (top sites by ROI + constraint distribution) + Kepler.gl Parcel Explorer (multi-layer spatial drill-down) + Streamlit Site Analyzer (click-on-map → full site report).

## What makes a plot a development opportunity

- Located in a [[crus]] urban-expansion or urbanizable zone but currently vacant or underutilized ([[cos]] non-artificial land use)
- No blocking [[srup-ogc]] constraints (RAN, REN, DPH, heritage protection) — or constraints are manageable
- Assemblable area from contiguous [[bupi]] parcels exceeds minimum viable development size
- Building coverage ratio is low (few or no existing structures per MS Building Footprints)
- Estimated development return (GBA × local €/m² from [[UC-1]] hedonic minus land + construction cost) exceeds target margin
- Ownership is traceable via `NumeroMatriz` + `Dicofre` → Caderneta Predial at Finanças

## Analytical layers

| Layer | Where it lives | Sprint | Notes |
|---|---|---|---|
| **Vacant/underutilized land detection** | `gold_analytics.vacant_parcels` | [[sprint-08]] | [[bupi]] parcels WHERE `land_use.is_urban=FALSE` ([[cos]]) AND `zoning.zone_category IN ('urban_expansion', 'urban_consolidated')` ([[crus]]). Boolean flags `is_vacant`, `is_buildable`, `is_agricultural` |
| **Buildability assessment** | Enhanced `silver_geo.zoning` — density extraction from `land_designation` text | [[sprint-08]] | Parses `max_floors`, `max_density_index`, `max_coverage_ratio`. zone_category defaults where not parseable |
| **Constraint overlay** | `gold_analytics.parcel_constraints` | [[sprint-08]] | Per-parcel `ST_Intersects` with [[srup]] RAN / DPH / IC. Severity 0=none, 1=DPH buffer, 2=RAN partial, 3=RAN full, 4=heritage |
| **Parcel assembly** | `gold_analytics.development_sites` + `site_parcels` | [[sprint-08]] | `ST_ClusterDBSCAN(geom_pt, eps=5, minpoints=1)` on vacant buildable parcels. Pre-filter to ~50-100K candidates. Aggregate: total_area_m2, parcel_count, combined geometry (`ST_UnaryUnion`) |
| **ARU overlay** | `silver_geo.zoning.is_aru` flag + `gold_analytics.development_sites.aru_overlap_pct` | [[sprint-09]] | Tax-benefit eligibility. ARU boundaries ingest deferred to [[sprint-09]] |
| **Construction activity (P1)** | `silver_geo.building_footprints` + spatial join to [[bupi]] | [[sprint-08]] | MS Building Footprints (~5M polygons). Coverage ratio (building area / parcel area) |
| **Construction activity (P2)** | Deferred — Sentinel-1 SAR change detection | (not in MVP) | Backscatter ΔdB > 3dB = new hard surfaces. Optional coherence analysis. Deferred indefinitely |
| **Building permits validation** | `bronze_ine.raw_building_permits`, `stg_building_permits` | [[sprint-09]] | Active construction validation; recent permits as proximity flag |
| **Development economics** | `gold_analytics.development_sites.est_*` columns | [[sprint-08]] | GBA = area × density × coverage. GDV = GBA × predicted €/m² (from [[UC-1]] hedonic). Construction cost = GBA × `ref_construction_costs` seed. Land residual = GDV × (1 - margin) - costs |
| **Opportunity scoring** | `gold_analytics.development_sites.opportunity_score` | [[sprint-08]] | Composite weighted score (buildability + constraint clearance + assemblable area + margin + location score) |
| **Competition scan** | Reuses [[UC-1]]'s `gold_analytics.neighbourhood_market_stats` | [[sprint-06]] (already shipped for UC-1) | Per design-doc note: don't build a separate competition layer; reuse |
| **OSRM drive-time integration** | `gold_analytics.property_location_scores` upgraded with real travel times | [[sprint-08]] | Replaces crow-flies for hedonic v2 retrain (improves R²) |

Per [[medallion-layering]]: every layer above lives in `gold_analytics` (or `silver_geo` for the spatial intermediates). Heavy use of PostGIS — `ST_Within`, `ST_Intersects`, `ST_ClusterDBSCAN`, `ST_UnaryUnion`, `ST_SimplifyPreserveTopology`.

## Conceptual data model

```
                    ┌─────────────────────┐
                    │   DEVELOPMENT SITE  │
                    │   (opportunity)     │
                    └──────────┬──────────┘
                               │
       ┌───────────────┬───────┼───────┬───────────────┐
       │               │       │       │               │
┌──────┴───────┐ ┌─────┴─────┐ │ ┌─────┴─────┐ ┌──────┴───────┐
│ BUILDABILITY │ │  PARCELS  │ │ │ ECONOMICS │ │ CONSTRUCTION │
│              │ │  (BUPI)   │ │ │           │ │  ACTIVITY    │
│ zone_categ   │ │           │ │ │ total_area│ │              │
│ land_class   │ │ process_id│ │ │ est_gba   │ │ has_building │
│ is_urban_exp │ │ matrix_num│ │ │ local_€m2 │ │ coverage_%   │
│ srup_flags   │ │ dicofre   │ │ │ est_rev   │ │ sar_delta_db │
│ ren_overlap  │ │ area_m2   │ │ │ est_cost  │ │ is_active    │
│ is_aru       │ │ owner_key │ │ │ est_margin│ │ permit_flag  │
└──────────────┘ └───────────┘ │ └───────────┘ └──────────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
         ┌──────┴───────┐ ┌───┴──────┐ ┌─────┴──────┐
         │  LAND USE    │ │ BUILDING │ │ COMPETITION│
         │  (COS)       │ │ FOOTPRINT│ │  (UC-1)    │
         │ cos_level_1  │ │ (MS)     │ │            │
         │ is_vacant    │ │          │ │ nearby_lst │
         │ is_agri      │ │ bldg_area│ │ recent_txn │
         │ is_built     │ │ bldg_cnt │ │ avg_eur_m2 │
         └──────────────┘ └──────────┘ └────────────┘
```

**Key relationships:**

- Each **development site** is composed of one or more contiguous [[bupi]] parcels (grouped via `ST_ClusterDBSCAN`)
- **Buildability** is determined by [[crus]] zoning (what can be built) intersected with [[srup]] / [[srup-ogc]] constraints (what cannot)
- **Land use** from [[cos]] 2023 detects vacant/underutilized parcels in urban zones
- **Building footprints** (MS) validate vacancy and compute building coverage per parcel
- **Economics** reuses [[UC-1]]'s hedonic model for local €/m² estimates
- **Construction activity** (P2) uses Sentinel-1 SAR change detection — deferred indefinitely

## Serving layer

Three surfaces, all shipping in [[sprint-08]] (Week 18, Milestone 3 LIVE) — UC-3 is the most spatially-intensive and has the richest map experience:

| Surface | Tool | Purpose | Filters / interactions |
|---|---|---|---|
| **Land Dashboard** | Metabase OSS 0.48+ on port 3000 | Vacant land inventory by municipality, top 20 sites by ROI, constraint distribution | Zoning filter, municipality dropdown, constraint-severity filter |
| **Parcel Explorer** | Kepler.gl 3.0 embedded in Streamlit (`streamlit-keplergl`) | [[bupi]] parcels colored by buildability, [[srup-ogc]] constraint layers (toggleable: RAN/DPH/IC/REN), [[cos]] land use (toggleable), MS building footprints (toggleable), [[crus]] zoning boundaries | Layer toggles per-source, `ST_SimplifyPreserveTopology` for zoom-level performance |
| **Site Analyzer** | Streamlit 1.41+ on port 8501 | Click on map → assemblable parcels, zoning params, constraint summary, estimated GBA, projected GDV, residual land value, ROI. Generates a per-site PDF report | Click-to-drill, parcel-multi-select, scenario comparison |
| **Opportunity Heatmap** (deferred to [[sprint-09]]) | Kepler.gl in Streamlit | Hexbin aggregation of `opportunity_score`, development site polygons, ARU overlay | Density filter, score threshold |

Database access: same Metabase + Streamlit roles as [[UC-1]] — read-only on `gold_analytics`, `silver_geo`, `silver_properties`.

## Dependencies

Sequential prerequisites:

- [[sprint-01]] — `dim_geography` (spatial backbone)
- [[sprint-03]] — UC-3 GIS bronze + staging (lands [[bupi]], [[cos]], [[crus]], [[srup]], [[cadastro]], PDM, building-permits staging)
- [[sprint-05]] — [[UC-1]] hedonic model — UC-3 economics use predicted €/m² as the GDV anchor
- [[sprint-08]] — UC-3 MVP composes everything (parcel assembly, economics, opportunity scoring, all three serving surfaces, OSRM drive-time integration)
- [[sprint-09]] — UC-3 enhancements (ARU overlay, REN integration, building permits validation, hedonic model v2 retrain with OSRM drive-times + ARU flag)

Cross-UC dependency: UC-3 economics REQUIRES [[UC-1]]'s hedonic model. Without it, GDV estimates are guesswork.

## See also

- [[bupi]], [[cos]], [[crus]], [[crus-ogc]], [[srup]], [[srup-ogc]], [[cadastro]], [[osm]] — UC-3 spatial sources
- [[apa]] — flood-risk overlay (relevant for buildability constraint flag, lands in Sprint 9 if used)
- [[lidar]] — DGT 2m DTM/DSM (terrain awareness for parcel suitability; Aveiro region only)
- [[lneg]] — geology + aquifers (geological constraint awareness)
- [[bgri]], [[caop]] — spatial backbone
- [[medallion-layering]] — silver/gold pattern
- [[sprint-03]] — predecessor (UC-3 GIS bronze + staging foundation)
- [[sprint-05]] — predecessor (hedonic model — load-bearing for economics)
- [[sprint-08]] — UC-3 MVP delivery (🏁 M3)
- [[sprint-09]] — UC-3 enhancements (ARU + REN + permits + hedonic v2)
- [[UC-1]] — hedonic foundation (UC-3 economics depend on it)
- [[UC-2]] — sibling (different shape but shares hedonic + cross-portal-dev infrastructure)
- [README §1.3 + §7.5 + §17](../../README.md) — canonical sources
