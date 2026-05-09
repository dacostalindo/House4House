---
title: UC-2 — New Housing Unit Pricing Strategy
type: plan
last_verified: 2026-05-09
tags: [use-case, plan, uc-2, pricing, developer-tooling, m2]
uc_number: "2"
status: planned
sprint_target: "sprint-07"
last_status_update: 2026-05-09
---

## For future Claude

This is the **UC-2** page — the new-development unit-pricing use case. Developers price units in their own projects with hedonic-calibrated premiums + competitive-set positioning + absorption forecasts. Depends on [[UC-1]]'s hedonic model from [[sprint-05]]. MVP ships at [[sprint-07]] (🏁 Milestone 2, Week 15). Read this when you need to know who consumes the Pricing Dashboard / Pricing Simulator, what business questions developers actually ask, and how the per-unit recommendation is decomposed into base-€/m² + premiums + positioning.

## Users

Real estate **developers/promoters**, **commercial directors**, and **project managers**. They run new-build projects and need a defensible per-unit price recommendation that's calibrated against hedonic fundamentals, the competitive set within 2km, expected absorption rate, and target margin.

## Business questions

These five questions drive the analytical layers:

1. **What is the optimal asking price per sqm for each unit in my new development?** Decompose hedonic prediction into base + premiums + positioning.
2. **How much premium can I charge for higher floors, river views, south-facing orientation?** Floor / view / orientation premium lookup tables (extracted from hedonic residuals).
3. **How does my pricing compare to competing developments within 2km?** Spatial competitive-set query against `silver_properties.competitive_developments` ([[sprint-04.5]]).
4. **At price X, how many months will it take to sell all units?** `absorption_rate_model` — sell-through forecast given price elasticity.
5. **What is the minimum price per unit to achieve our target margin?** Inverse: given target margin, what price clears it?

## Decision output

A unit-level pricing recommendation with floor/view/orientation premiums, competitive positioning, absorption forecast, and margin analysis. Surfaced as Metabase Pricing Dashboard (overview + competition map + absorption timeline) + Streamlit Pricing Simulator (per-project sandbox: adjust unit attributes → see recommended price + margin + days-to-sell).

## What makes a sound pricing recommendation

- Anchored to hedonic fair value from [[UC-1]] (`property_valuation.predicted_price_sqm`)
- Decomposed: `base_sqm × floor_premium × view_premium × orientation_premium × terrace_premium`
- Cross-checked against `competitive_developments` within 2km radius
- Absorption-aware: pricing too high → high `days_to_sell` forecast; pricing too low → leaves margin on the table
- Margin-validated: `predicted_margin = (rec_price × units) - (land_cost + construction_cost)` clears target

## Analytical layers

| Layer | Where it lives | Sprint | Notes |
|---|---|---|---|
| **Comparable sales engine** | `gold_analytics.property_comparables` (KNN top-10 within 2km, same typology band) | [[sprint-05]] | Foundation reused from UC-1's hedonic feature space |
| **Hedonic price decomposition** | `gold_analytics.location_price_premiums` (hedonic coefficients as a lookup table — metro proximity → €/m² premium) | [[sprint-07]] | Coefficients extracted from sprint-05 hedonic regression as static lookup; easier to interpret + audit than re-running the model per query |
| **Micro-location premium model** | `gold_analytics.location_price_premiums` (same table, finer-grained features) | [[sprint-07]] | River-view, sea-view, park-adjacent premiums |
| **Competitive supply analysis** | `silver_properties.competitive_developments` extended in [[sprint-07]] with `base_price_sqm` + `predicted_avg_price_sqm` columns via JOIN to `property_valuation` | [[sprint-04.5]] base + [[sprint-07]] hedonic-extension | 2km-radius spatial query, with absorption metrics |
| **Absorption rate forecasting** | `gold_analytics.absorption_rate_model` extended in [[sprint-07]] with price elasticity (`price_adjusted_forecast` column) | [[sprint-04.5]] base + [[sprint-07]] elasticity | Per-development sell-through from [[remax]] `isSold` + [[zome]] state changes + [[idealista]] listing-disappearance signal. Historical trend from bronze SCD2 snapshots. |
| **Sensitivity / price elasticity** | `gold_analytics.absorption_rate_model.price_elasticity` | [[sprint-07]] | Absorption rate vs. price point; drives what-if scenarios in the Streamlit Simulator |
| **Unit premium calibration** | `gold_analytics.ref_unit_premiums` (floor/view/orientation premium/discount lookup) | [[sprint-07]] | Extracted from hedonic residuals; uses `silver_properties.floor_plan_rooms` ([[sprint-04]]) for area-by-room optimization |
| **Per-unit recommendation** | `gold_analytics.unit_pricing_recommendation` | [[sprint-07]] | `base €/m² × premiums × market_position` → recommended price |
| **Project rollup** | `gold_analytics.project_pricing_summary` (materialized view) | [[sprint-07]] | Total revenue, blended margin, by-typology, vs-competition, absorption forecast |
| **Lifecycle context** | `gold_analytics.development_lifecycle` extended with predicted-GDV-at-completion + hedonic-margin estimate | [[sprint-04.5]] base + [[sprint-07]] | [[sce]] PCE → CE → on-market timeline; cross-references `ref_construction_costs` |

Per [[medallion-layering]]: every layer above is in `gold_analytics` (or `silver_properties` for the development-canonical models from [[sprint-04.5]]). Reuses [[UC-1]]'s hedonic infrastructure heavily.

## Conceptual data model

```
    ┌──────────────────┐         ┌──────────────────┐
    │  DEVELOPMENT     │ 1     * │  UNIT            │
    │  PROJECT         ├─────────┤                  │
    │                  │         │  typology        │
    │  name            │         │  area_m2         │
    │  location        │         │  floor           │
    │  total_units     │         │  orientation     │
    │  total_cost      │         │  view_type       │
    │  target_margin   │         │  has_parking     │
    │                  │         │  status          │
    └────────┬─────────┘         └────────┬─────────┘
             │                            │
    competes │                    priced  │
      with   │                     by     │
             ▼                            ▼
    ┌──────────────────┐         ┌──────────────────┐
    │  COMPETITIVE     │         │  PRICING         │
    │  DEVELOPMENT     │         │  RECOMMENDATION  │
    │                  │         │                  │
    │  project_name    │         │  base_price_sqm  │
    │  developer       │  used   │  + floor_prem    │
    │  avg_price_sqm   │──in──►  │  + view_prem     │
    │  units_available │         │  + orient_prem   │
    │  absorption_rate │         │  + terrace_prem  │
    └──────────────────┘         │  = rec_price_sqm │
                                 │  rec_price_eur   │
    ┌──────────────────┐         │  margin_%        │
    │  ABSORPTION      │         │  days_to_sell    │
    │  RATE MODEL      │ used    │  confidence      │
    │                  │──in──►  └──────────────────┘
    │  typology        │                  │
    │  price_segment   │                  │
    │  days_on_market  │         aggregates
    │  %_sold_30/60/90d│                  │
    └──────────────────┘                  ▼
                                 ┌──────────────────┐
    ┌──────────────────┐         │  PROJECT PRICING │
    │  LOCATION PRICE  │         │  SUMMARY         │
    │  PREMIUMS        │         │                  │
    │                  │ used    │  total_revenue   │
    │  feature_name    │──in──►  │  blended_margin  │
    │  coefficient_eur │  all    │  by_typology     │
    │  coefficient_%   │ models  │  vs_competition  │
    │  scope (LX/Porto)│         │  absorption_fcst │
    └──────────────────┘         └──────────────────┘
```

DEVELOPMENT PROJECT (one row per real-world dev, dedup'd in [[sprint-04.5]]) has many UNITs (one row per unit, also dedup'd). Pricing recommendation is per-unit; project rollup aggregates. Three lookup tables (`competitive_developments`, `absorption_rate_model`, `location_price_premiums`) feed the recommendation logic.

## Serving layer

Two surfaces, both shipping in [[sprint-07]] (Week 15, Milestone 2 LIVE):

| Surface | Tool | Purpose | Filters / interactions |
|---|---|---|---|
| **Pricing Dashboard** | Metabase OSS 0.48+ on port 3000 | Unit pricing matrix, competition map (2km radius), absorption timeline, floor/view premium chart | Project selector, typology filter, price-band filter |
| **Pricing Simulator** | Streamlit 1.41+ on port 8501 | Per-project sandbox: select development → adjust unit attributes (floor, view, orientation, terrace) → see recommended price, margin, absorption forecast | Slider-based what-if; saves scenarios |

Database access: same Metabase + Streamlit roles as [[UC-1]] — read-only on `gold_analytics`, `silver_properties`, `silver_geo`, `silver_market`.

## Dependencies

Sequential prerequisites:

- [[sprint-04.5]] — `silver_properties.developments_canonical` + `development_units` + `competitive_developments` + `development_lifecycle` (ground floor for UC-2)
- [[sprint-05]] — UC-2 reuses [[UC-1]]'s hedonic model heavily (location premiums extracted as a lookup; predicted €/m² becomes the anchor for the per-unit recommendation)
- [[sprint-07]] — UC-2 MVP composes all of the above into the serving surfaces

Cross-UC dependency: UC-2 builds on [[UC-1]]'s `property_valuation` + `property_comparables`. Without UC-1's hedonic, UC-2 has no anchor.

## See also

- [[remax]], [[idealista]], [[zome]] — competitive-development sources fed by [[sprint-04.5]] cross-portal dedup
- [[jll]] — JLL development data (deferred to Sprint 4.6+; not in MVP scope per [[2026-05-08-idealista-enrichment-architecture]] phasing)
- [[sce]] — PCE / CE issuance dates feed `development_lifecycle` (construction-to-market timeline)
- [[bgri]], [[caop]], [[osm]] — spatial backbone
- [[ine]], [[bpstat]], [[ecb]] — macro context (rates, mortgage flows) feeding affordability projections
- [[scd2-row-hash]], [[heartbeat-sidecar]] — concepts powering historical price-trend analysis from bronze SCD2 snapshots
- [[medallion-layering]] — silver/gold pattern
- [[2026-05-08-idealista-enrichment-architecture]] — drives the dev-stream coexistence + decommission gates
- [[sprint-04.5]] — ground floor (canonical developments + initial competitive_developments)
- [[sprint-05]] — hedonic model (UC-2 reuses heavily)
- [[sprint-07]] — UC-2 MVP delivery (🏁 M2)
- [[UC-1]] — hedonic foundation (UC-2 depends on it)
- [[UC-3]] — sibling (depends on hedonic same as UC-2)
- [README §1.2 + §7.3 + §17](../../README.md) — canonical sources
