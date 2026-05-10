---
title: Resource requirements & costs
type: plan
last_verified: 2026-05-10
tags: [planning, resources, budget, effort, plan]
---

## For future Claude

This is the **resources** page — team composition, infrastructure budget, per-sprint effort estimates, and data-volume projections for the MVP. Read this when scoping a new sprint, validating budget against actuals, sanity-checking volume estimates against ingest reality, or onboarding a contributor. Decomposed from README §15.

## What it is

The originally-scoped MVP plan: 20 weeks, ~170 engineering-days, ~€688 infrastructure cost, ~28 GB Postgres + ~35 GB MinIO. Solo-dev reality has compressed some phases (Phase 2.5 closed with no work per [[2026-05-08-phase-2-5-closure]]) and expanded others (Phase 3 dev-tooling is itself ~5-7 days that was implicit in the original "Sprint 1 — Infrastructure"). Use the README §15 numbers as the order-of-magnitude floor; track sprint actuals in [[sprints/README|wiki/sprints/]] for ground truth.

## Team

Per README §15.1:

| Role | Count | Sprints | Focus |
|---|---|---|---|
| Data Engineer (Lead) | 1 | 1-8 | PG/PostGIS, dbt, Airflow, Docker |
| Data Engineer (Scraping) | 1 | 2-8 | Scrapy, Selenium, geocoding, dedup |
| Data Scientist | 0.5 | 5-8 | Hedonic model, premium calibration |

**Solo-dev reality:** all three roles consolidated to one person. Effort allocation in practice: ~60% data engineering (lead), ~30% scraping, ~10% data science (Sprint 5+ once UC-1 hedonic work starts). The roles are useful for thinking about WORK STREAMS even when one person owns all of them.

## Budget

Per README §15.2 — infrastructure-only (no team cost):

| Item | Monthly | Total (16 weeks) |
|---|---|---|
| Hetzner AX102 server | €85 | €340 |
| Hetzner Storage Box (backup) | €12 | €48 |
| Proxy service (scraping) | €75 | €300 |
| **Total infrastructure** | **€172** | **€688** |

**Optional:**
- CI license (€2-10K/year) — deferred per [[risks|R4]]
- Google Maps API (~€50-100/month if Nominatim insufficient) — currently mitigated per [[risks|R5]]; not in active budget

**Per [[2026-05-10-single-server-self-hosted]] + [[2026-05-10-minio-not-s3]] + [[2026-05-10-nominatim-osrm-self-hosted]]**, the budget reflects the self-hosted-everywhere posture. A cloud-equivalent stack would be ~10× this monthly cost (≥€1,500/month). The €172/month delta is what funds 80+ sprints of solo-dev runway.

**ZenRows costs are NOT in this table** — they're per-source consumables tracked in [[idealista]]'s page (~$26-38/run for the full 7-distrito scope, daily). Annualized: ~$10,000-14,000 if scope expands beyond 7 distritos. Significant relative to the infrastructure budget; tracked separately because it scales with scope rather than with time.

## Effort summary

Per README §15.3 — sprint-by-sprint:

| Sprint | Weeks | Eng-Days | Theme | Milestone |
|---|---|---|---|---|
| [[sprint-01]] | 1-2 | 14 | Infrastructure + geography | ✅ Platform live |
| [[sprint-02]] | 3-4 | 15 | Core market data | ✅ Data flowing |
| [[sprint-03]] | 5-6 | 20 | Silver unification + UC-3 GIS foundation | ✅ Unified listings + GIS data banked |
| [[sprint-04]] | 7-8 | 10 | Image classification + location scores | 🔄 CV pipeline + amenity scores |
| [[sprint-04.4]] | 8.5 | (audit-corrected: shipped 2026-04-30) | Pre-Sprint-4.5 prep | ✅ |
| [[sprint-04.5]] | 9 | — | Listings + Developments cross-portal dedup | Planned |
| [[sprint-05]] | 10-11 | 18 | Hedonic model + valuation | Valuations live |
| [[sprint-06]] | 12-13 | 18 | UC-1: investment opportunities + serving | 🏁 **UC-1 MVP (M1)** |
| [[sprint-07]] | 14-15 | 17 | UC-2: pricing strategy + serving | 🏁 **UC-2 MVP (M2)** |
| [[sprint-08]] | 16-18 | 28 | UC-3: land analytics + serving (GIS data ready from Sprint 3) | 🏁 **UC-3 MVP (M3)** |
| [[sprint-09]] | 19-20 | 30 | Enhancements + production hardening | All UCs enhanced |
| **Total** | **20** | **170** | | **All three use cases live** |

**Plus dev-tooling work** ([[sprint-dev-tooling]]) — gstack-driven 7-Phase roadmap running in parallel; not in the table above. Cost: ~5-7 days for Phase 1+2+3 (mostly shipped); ~2-3 days for Phase 4 (CI/CD); ~1-2 days for Phase 5 enrichment build (when UC-1 hedonic provides the trigger); ~1-2 days for Phase 6+7. Total parallel: ~10-15 days across 20 sprint weeks.

## Data volume estimates

Per README §15.4 — order-of-magnitude per dataset:

| Dataset | Source | Records | Storage | Growth |
|---|---|---|---|---|
| Listings (2 portals, historical) | [[idealista]] + [[remax]] (Sprint 4.5+ adds [[jll]] + [[zome]]) | ~1.5M snapshots/year | 8 GB/year | ~4K/day |
| INE transactions | [[ine]] | ~500K records | 200 MB | Quarterly |
| Census 2021 BGRI | [[bgri]] | ~200K subsection polygons | 200-400 MB | Static (~2031) |
| CAOP boundaries | [[caop]] | ~3,100 freguesias | 500 MB (geometries) | Annual |
| OSM Portugal | [[osm]] | ~20M features (note: source page reports ~4.5M for the 18 GeoPackage layers we ingest) | 5 GB | Monthly |
| RNAL | (deferred Sprint 7 P1) | ~120K licenses | 100 MB | Monthly |
| Inside Airbnb | (deferred Sprint 7 P1) | ~50K listings/snapshot | 200 MB/year | Quarterly |
| Macro time series | [[bpstat]] + [[ecb]] + [[eurostat]] | ~100K observations | 50 MB | Monthly |
| PDM zoning | [[crus]] / [[crus-ogc]] | ~5K WFS-only / ~236K national OGC | 100-500 MB | Static / Ad-hoc |
| Transport stops | [[osm]] subset | ~30K stops | 50 MB | Quarterly |
| Schools + Healthcare | (deferred Sprint 7) | ~13K facilities | 70 MB | Annual |
| Location scores | gold derivation | matches listing count | 500 MB | Weekly |
| BUPI cadastral parcels | [[bupi]] | ~3.25M polygons | 2 GB | Monthly |
| COS 2023 land use | [[cos]] | ~784K polygons | 500 MB | ~5 years |
| CRUS zoning | [[crus]] / [[crus-ogc]] | as above | as above | Ad-hoc |
| SRUP constraints | [[srup]] / [[srup-ogc]] | ~4K legacy IC+RAN+DPH / ~22 layers OGC | 400 MB total | Ad-hoc |
| Cadastro Predial | [[cadastro]] | partial coverage 2000-2007 | 300 MB | Ad-hoc |
| MS Building Footprints | (deferred Sprint 9 P1) | ~5M polygons | 1.5-2 GB | Annual |
| Sentinel-1 SAR | (deferred Sprint 10 P2) | per-parcel flags | 50 MB | Monthly |
| **Plus PR 7 additions:** [[apa]] + [[lneg]] + [[lidar]] + [[aveiro-pmot]] + [[sce]] | as per [[wiki/sources/]] | small (P2) | <500 MB total | Manual / on-demand |

**Total estimated: ~28 GB in PostgreSQL + ~35 GB in MinIO at MVP.** With current infrastructure (4 TB NVMe), capacity is good for ~10× this growth before NVMe pressure (per [[2026-05-10-single-server-self-hosted]] capacity ceiling discussion).

## Net read

The MVP plan is feasible on the locked stack + budget. Scaling beyond MVP (P3/P4 sources, UC enhancements, multi-region) re-opens budget + capacity questions. See [[roadmap-p3-p4]] for the post-MVP source landscape.

## See also

- [[risks]] — companion planning page; risks that threaten budget or effort
- [[milestones]] — Go/No-Go gates that the effort estimates support
- [[roadmap-p3-p4]] — post-MVP source expansion
- [[sprints/README]] — sprint-by-sprint actuals
- [[2026-05-10-single-server-self-hosted]] — the budget-funding architectural decision
- [[idealista]] — for ZenRows scope-dependent cost beyond the infrastructure budget
- README §15 — the canonical source for this content
