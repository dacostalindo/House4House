---
title: Sprint 7 — UC-2 MVP Pricing Strategy
type: plan
last_verified: 2026-05-09
tags: [sprint, plan, uc-2, pricing, milestone, weeks-14-15]
status: planned
sprint_number: "7"
weeks: "14-15"
last_status_update: 2026-05-09
---

## For future Claude

This is the **Sprint 7** page (Weeks 14-15). It ships **🏁 Milestone 2: UC-2 MVP LIVE** — developers can price new units with market-calibrated premiums. Builds on Sprint 5's hedonic model + Sprint 4.5's `competitive_developments`/`development_units`/`development_lifecycle`/`absorption_rate_model`. Read this when you need to know how the Pricing Dashboard + Pricing Simulator are powered.

## Goal

Extend Sprint 4.5's competitive-development framework with hedonic-derived pricing (base €/m², predicted GDV, margin, sell-through forecast). Decompose hedonic coefficients into reusable per-feature premium tables (location, floor/view/orientation). Recommend per-unit prices via `base_sqm × premiums × market_position`. Expose via Metabase Pricing Dashboard + Streamlit Pricing Simulator.

## Deliverables

- Extend `silver_properties.competitive_developments` with hedonic pricing: add `base_price_sqm` and `predicted_avg_price_sqm` via JOIN to `property_valuation`. Position each development vs hedonic fair value
- Extend `gold_analytics.development_lifecycle` with hedonic calibration: predicted GDV at completion, hedonic-based margin estimate, cross-reference with `ref_construction_costs`
- Extend `gold_analytics.absorption_rate_model` with pricing calibration: price elasticity (absorption rate vs price point), price-adjusted sell-through forecast. Historical trend from bronze snapshots + hedonic residuals
- `gold_analytics.location_price_premiums`: extract hedonic coefficients as lookup (metro proximity → €/m² premium)
- `gold_analytics.ref_unit_premiums`: floor/view/orientation premium/discount lookup from hedonic residuals. Uses `floor_plan_rooms` (Sprint 4) for area-by-room optimization
- `gold_analytics.unit_pricing_recommendation`: per-unit `base €/m² × premiums × market position` → recommended price → **UC-2 LIVE**
- `gold_analytics.project_pricing_summary`: roll up unit recommendations → project GDV, margin, sell-through timeline
- Serving — Pricing Dashboard (Metabase): unit pricing matrix, competition map (2km radius), absorption timeline, floor/view premium chart
- Serving — Pricing Simulator (Streamlit): select development project → adjust unit attributes → see recommended price, margin, absorption forecast

Also folds in §17 serving content from README into this UC's serving sections (per `/plan-design-review` Pass 1 finding 2).

## Exit criteria

`unit_pricing_recommendation` live; Pricing Dashboard + Pricing Simulator rendering against real data; developers can price new units with hedonic-calibrated premiums.

## Key decisions

- Extend existing Sprint 4.5 models (don't rebuild) — `competitive_developments`, `development_lifecycle`, `absorption_rate_model` get hedonic columns ADDED, not replaced
- Hedonic coefficients exposed as static lookup tables (`location_price_premiums`, `ref_unit_premiums`) — easier to interpret + audit than re-running the model per query
- §17 serving folds into UC pages (NOT a separate `wiki/serving/` folder) per the design-review locked taxonomy — each UC has its own serving needs

## Status update history

- 2026-04-18: declared in README §12; status `planned`

## See also

- [[idealista]], [[remax]], [[zome]] — sources feeding `competitive_developments`
- [[medallion-layering]] — gold materialization pattern
- [[sprint-05]] — predecessor (hedonic model)
- [[sprint-04.5]] — predecessor (silver/gold base for competitive_developments)
- [[sprint-06]] — sibling milestone (UC-1)
- [[sprint-08]] — successor (UC-3, depends on hedonic for development economics)

## 🏁 Milestone

**Milestone 2 (Week 15): UC-2 MVP LIVE.** Developers can price new units with market-calibrated premiums.
