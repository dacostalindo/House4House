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

## Milestone 3 — UC-3 MVP (Week 19, end of Sprint 8)

| Criteria | Target | Hard Fail? | Status |
|---|---|---|---|
| [[bupi]] parcels loaded | ≥ 3M parcels | Yes | Pending Sprint 9 ([[bupi]] is P1 + currently P1 priority) |
| [[crus]] / [[crus-ogc]] zoning loaded | ≥ 5 municipalities (legacy) OR national OGC | Yes | Partially shipped: legacy WFS in Sprint 1+2; OGC API in flight per [[crus-ogc]] |
| Building footprints loaded | ≥ 4M footprints for Portugal | Yes | Pending Sprint 9 (per [[risks|R13]]) |
| Opportunity sites identified | Sites in ≥ 4 of 5 CRUS municipalities | Yes | Pending Sprint 8 |
| Spatial-join coverage | 100% of BUPI parcels within CRUS extents processed | Yes | Pending Sprint 8 (per [[risks|R12]] performance mitigation) |
| `parcel_buildability` materialization | Refreshes in < 30 minutes | No | Soft-fail; performance optimization |
| Metabase **Land Dashboard** | Accessible with working filters | Yes | Pending Sprint 8 |
| **Parcel Explorer** (Kepler.gl) | BUPI parcels rendered with buildability coloring + constraint toggles | Yes | Pending Sprint 8 |
| **Site Analyzer** (Streamlit) | Click-to-analyze workflow returns parcel assembly + zoning + economics | No | Soft-fail; can ship Sprint 9 |

**Critical path for M3:** Sprint 3 GIS foundation → Sprint 9 BUPI ingest → Sprint 8 spatial composition (Flow E in [[ingest-flows]]). Hardest gate: spatial-join performance at scale (R12) per [[2026-05-10-postgis-as-warehouse]] + 128 GB RAM design.

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
