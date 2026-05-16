---
title: Go/No-Go milestones (M1 / M2 / M3)
type: plan
last_verified: 2026-05-10
tags: [planning, milestones, go-no-go, mvp, plan]
---

## For future Claude

This is the **milestones** page — the explicit Go/No-Go criteria for each use-case MVP (M1 [[UC-1]], M2 [[UC-2]], M3 [[UC-3]]) plus the MVP hedonic-model feature-coverage table that gates UC-1's accuracy claim. Read this before declaring a sprint "done", validating an MVP ship, or scoping a milestone-blocking risk. Decomposed from README §17 (Go/No-Go Milestones) + README §17 (MVP Hedonic Feature Coverage).

## What it is

Three MVP milestones, each with a hard-fail / soft-fail criteria table. A use case "ships" only when all `Hard Fail? = Yes` rows pass. Soft-fail rows are nice-to-have; a sprint can ship with some soft-fails missing if their work is queued for an enhancement sprint (Sprint 9+).

## Milestone 1 — UC-1 MVP (Week 12, end of Sprint 6)

| Criteria | Target | Hard Fail? | Status |
|---|---|---|---|
| `dim_geography` populated | ≥ 3,000 freguesias | Yes | ✅ shipped Sprint 1 (3,049 freguesias from [[caop]]) |
| `unified_listings` active sale count | ≥ 80,000 | Yes | Pending Sprint 4.5 unification |
| Geocoding success rate | ≥ 95% to freguesia | Yes | ✅ verified in Sprint 1 + 2 (per [[risks|R5]] mitigation) |
| Hedonic model R² (holdout) | ≥ 0.70 | Yes | Pending Sprint 5 model build (per [[risks|R3]]) |
| `property_valuation` coverage | ≥ 90% of active listings | Yes | Gated on hedonic model ship |
| `investment_yield` available | ≥ 80% of listings with rental comps | No | Soft-fail acceptable |
| `neighbourhood_trajectory` | ≥ 80% of active freguesias | No | Soft-fail acceptable |
| Metabase **Investment Dashboard** | Accessible with working filters | Yes | Pending Sprint 6 |
| **Investment Map** (Kepler.gl) | Listing points rendered with valuation-gap coloring | Yes | Pending Sprint 6 |
| **Property Valuator** (Streamlit) | Address lookup returns predicted value + comps | No | Soft-fail acceptable |

**Critical path for M1:** Sprint 4.5 listing unification → Sprint 5 hedonic model → Sprint 6 valuation + serving surfaces. R3 (hedonic R² < 0.70) is the dominant risk; mitigations in [[risks]] include interaction terms + Random Forest fallback + per-concelho segmentation.

## Milestone 2 — UC-2 MVP + Production (Week 16, end of Sprint 7)

| Criteria | Target | Hard Fail? | Status |
|---|---|---|---|
| `competitive_developments` | ≥ 15 projects (LX + Porto) | Yes | Pending Sprint 4.5 (Flow F) |
| `absorption_rate_model` | ≥ 3 quarters historical | Yes | Pending Sprint 7 |
| `location_price_premiums` | ≥ 8 significant features | Yes | Reuses UC-1 hedonic features |
| `unit_pricing` for sample project | Pricing for all units | Yes | Pending Sprint 7 |
| All daily DAGs succeeding | ≥ 95% success rate (2 weeks) | Yes | Operational gate; tracked in [[orchestration]]'s `dag_freshness_monitor` |
| Data freshness | No source > 2× expected interval | No | Soft-fail; tracked via [[heartbeat-sidecar]] / `dag_freshness_monitor` |
| Documentation | Data dictionary complete | No | dbt-docs covers most; soft-fail acceptable |
| Metabase **Pricing Dashboard** | Accessible with unit matrix + competition map | Yes | Pending Sprint 7 |
| **Pricing Simulator** (Streamlit) | Unit-attribute adjustment returns recommended price | No | Soft-fail acceptable |

**Critical path for M2:** Sprint 4.5 development-portal cross-reference (Flow F) → Sprint 7 pricing premiums + absorption + serving. Gates UC-1 production hardening: M2 shipping means daily-DAG operational stability validated for 2 weeks.

## Milestone 3 — UC-3 v1 wedge LIVE (Week 21, end of Sprint 9)

**Reframed 2026-05-12 per [[2026-05-12-uc3-expanded-scope]].** Original M3 was "UC-3 MVP Land Development Opportunities" at Week 18 with three serving surfaces (Metabase Land Dashboard, Kepler.gl Parcel Explorer, Streamlit Site Analyzer). UC-3 reframed into a 7-stage end-to-end plot economic-value pipeline; v1 wedge ships only **Atlas Site Inspector** in v1; Land Dashboard + Site Analyzer (three-surface model) defer to v2+. M3 milestone now lands at Week 21 (end of [[sprint-09]]), not Week 18.

| Criteria | Target | Hard Fail? | Status |
|---|---|---|---|
| Aveiro [[bupi]] + [[cadastro]] union → `parcel_universe` | ~50K rows for Aveiro município | Yes | Pending [[sprint-08]] |
| [[crus]] / [[crus-ogc]] zoning density extraction | `max_floors`, `max_density_index`, `max_coverage_ratio` parsed from `land_designation` for Aveiro | Yes | Pending [[sprint-08]] |
| LiDAR Aveiro coverage | DGT DTM 2m tiles ingested + slope p90 per parcel via zonal stats | Yes | Pending [[sprint-08]] (or Copernicus EEA-10 fallback if DGT tiles unavailable) |
| [[sce]] aggregation to developments | `silver_sce_buildings` materialized for Aveiro distrito | Yes | Pending [[sprint-08]]+[[sprint-09]] |
| LLM extraction on [[idealista]] plot listings | Per-field accuracy ≥ thresholds in Appendix B (85% on `construction_area_m2_allowed`) | Yes | Pending [[sprint-09]] |
| Development dedup | `silver_unified_developments` collapses SCE + idealista by spatial proximity ≤ 50m + name similarity | Yes | Pending [[sprint-09]] |
| `gold.fn_assess_polygon` Postgres function | Single backend entry point; P95 < 3s for typical Aveiro polygons | Yes | Pending [[sprint-09]] |
| **Atlas Site Inspector** (Streamlit-component) | Draw polygon → Analisar → 8-section readout per variant B-prime | Yes | Pending [[sprint-09]]. **Replaces** the original M3 three-surface model (Land Dashboard / Parcel Explorer / Site Analyzer). |
| 3 PT developer interviews completed + kill-criteria applied | Per [[2026-05-12-uc3-expanded-scope]] kill criteria | Yes | **The actual gate** — wedge validated / killed / resized post-demo |
| 22 critical tests passing in CI | Per /plan-eng-review test plan Appendix C | Yes | Pending [[sprint-08]]+[[sprint-09]] (CI extended with pgTAP + Playwright) |
| Building footprints (MS S42) | ≥ 4M footprints loaded | No | **Deferred from v1 wedge** to v2 with Stages 5-6 economics |

**Critical path for M3:** [[sprint-03]] GIS foundation → [[sprint-08]] (WS1 templates + WS3 LiDAR + Slice B start + SCE geocoding) → [[sprint-09]] (Slice B/C/B-prime completion + `fn_assess_polygon` + Atlas Inspector + demo). Hardest gate: NOT spatial-join performance at scale (R12 mitigates via Aveiro-only scope + GIST indexes + draw-polygon UX), but **developer-interview reachability** — if 3 PT land developers cannot be reached in 2-3 weeks via APEMIP/AICCOPN/LinkedIn warm, the wedge is unvalidated regardless of engineering completion.

## MVP hedonic-model feature coverage

Per README §17 — what's available at MVP vs. what's in the full blueprint:

| Feature | MVP Source | Full Blueprint Source | Accuracy Impact at MVP |
|---|---|---|---|
| Area, rooms, bathrooms, floor | [[idealista]] / [[remax]] | Same | None |
| Building age, condition | [[idealista]] / [[remax]] | Same | None |
| Energy class | [[idealista]] / [[remax]] listing field | [[sce]] (S13 ADENE) | Minor (~80% populated from listings; better data via [[sce]] in P3) |
| Elevator, parking, terrace, pool | [[idealista]] / [[remax]] | Same | None |
| Transport score | [[osm]] | [[osm]] + S24 GTFS | Minor (OSM has stops; GTFS adds frequency) |
| Walkability / POI density | [[osm]] | Same | None |
| Drive-time accessibility | [[osm]]-derived OSRM (per [[2026-05-10-nominatim-osrm-self-hosted]]) | Same | None |
| Education score | S22 InfoEscolas (deferred Sprint 7 P1) | Same | None (NULL until Sprint 7; per [[risks|R7]]) |
| Healthcare score | S23 SNS (deferred Sprint 7 P1) | Same | None (NULL until Sprint 7) |
| Neighbourhood median price | [[ine]] / [[idealista]] | Same | None |
| Demographics | [[bgri]] | Same | None |
| Zoning category | [[crus]] / [[crus-ogc]] | Same | None |
| **Noise exposure** | **Not available** | S27 noise maps | **~2-3% R² loss in noisy areas** (per [[roadmap-p3-p4]] Phase 2A) |
| **Flood risk** | **Not available** | S35 APA flood (broader than [[apa]]'s ARPSI scope) | **~1-2% R² loss in flood zones** (per [[apa]] EU-Floods-Directive caveat + [[roadmap-p3-p4]] Phase 2A) |
| **Solar/sun exposure** | **Simplified compass-bearing lookup** | S28 PVGIS | **Negligible** at MVP |

**MVP R² target = 0.70.** The two material gaps (noise + flood) account for ~3-5% R² collectively. Hitting 0.70 with the MVP feature set is the [[risks|R3]] mitigation challenge.

## See also

- [[UC-1]], [[UC-2]], [[UC-3]] — use-case pages with detailed analytical-layer specs
- [[sprint-06]], [[sprint-07]], [[sprint-08]] — the sprint pages where each milestone ships
- [[risks]] — risks that threaten each milestone
- [[resources]] — effort budget for the sprints leading to each milestone
- [[roadmap-p3-p4]] — what unlocks once MVP gates clear
- README §17 — the canonical source for this content
