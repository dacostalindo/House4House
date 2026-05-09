---
title: Sprint 6 — UC-1 MVP Investment Opportunities
type: plan
last_verified: 2026-05-09
tags: [sprint, plan, uc-1, investment, milestone, weeks-12-13]
status: planned
sprint_number: "6"
weeks: "12-13"
last_status_update: 2026-05-09
---

## For future Claude

This is the **Sprint 6** page (Weeks 12-13). It ships **🏁 Milestone 1: UC-1 MVP LIVE** — investors can query ranked investment opportunities (valuation gap × yield × neighbourhood trajectory × location). Hedonic model from Sprint 5 unlocks this; UC-2 + UC-3 cascade afterward. Read this when you need to know what powers the Investment Dashboard, Investment Map, and Property Valuator app.

## Goal

Compose the hedonic valuation (Sprint 5) with rental-yield + neighbourhood-trajectory + renovation-opportunity signals into a single composite ranking, exposed via three serving surfaces: Metabase Investment Dashboard, Kepler.gl Investment Map, Streamlit Property Valuator app.

## Deliverables

- Seed `gold_analytics.ref_renovation_costs` (manual €/m² estimates by scope: cosmetic, light, full, structural)
- Seed `gold_analytics.ref_area_catalysts` (known infrastructure projects: metro extensions, hospitals, university campuses, with geo + timeline)
- Inside Airbnb ingestion (S15) → `bronze_listings.raw_airbnb` (Lisbon + Porto)
- `gold_analytics.investment_yield_analysis`: LTR yield (€/m² rent ÷ price), STR yield (Airbnb RevPAR × occupancy), net of IMI/IMT/condominium ([[idealista]] rental + Airbnb + IMI/IMT seeds)
- `gold_analytics.renovation_opportunity`: undervalued listings × reno cost estimates → post-reno value, ROI %
- `gold_analytics.neighbourhood_trajectory`: YoY price trend + population growth + vacancy change + catalyst proximity + **[[sce]] supply signal** (monthly PCE issuance per municipality as 12-18 month leading indicator of future supply; `active_developments_count` and `total_pipeline_units`) → trajectory score
- `gold_analytics.investment_opportunities` (materialized view): composite ranking valuation gap × yield × trajectory × location → **UC-1 LIVE**
- Serving — Investment Dashboard (Metabase): KPIs, ranked table, yield-vs-price scatter, filters (budget, location, typology, min yield)
- Serving — Investment Map (Kepler.gl): listing points colored by valuation gap, neighbourhood-trajectory polygons, infrastructure catalysts
- Serving — Property Valuator (Streamlit): enter address/listing URL → predicted value, valuation gap, comparable sales, neighbourhood stats

## Exit criteria

`investment_opportunities` materialized view live; Investment Dashboard + Investment Map + Property Valuator app all rendering against real data; investors can rank opportunities by composite score.

## Key decisions

- Inside Airbnb scoped to Lisbon + Porto for MVP (other municipalities deferred until validated)
- Renovation costs seeded manually (no scraped contractor data yet)
- Catalysts seeded manually (could automate from gov press feeds later, deferred)

## Status update history

- 2026-04-18: declared in README §12; status `planned`

## See also

- [[idealista]], [[sce]], [[ine]], [[bpstat]], [[ecb]] — sources feeding UC-1
- [[medallion-layering]] — gold materialization pattern
- [[sprint-05]] — predecessor (hedonic model is THE prerequisite)
- [[sprint-07]] — successor (UC-2 pricing) — uses same hedonic backbone
- [[sprint-08]] — UC-3 land development uses hedonic GDV predictions

## 🏁 Milestone

**Milestone 1 (Week 13): UC-1 MVP LIVE.** Investors can query ranked opportunities. Hedonic model unlocks UC-2 and UC-3.
