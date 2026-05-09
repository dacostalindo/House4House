---
title: UC-1 — Undervalued Property Identification
type: plan
last_verified: 2026-05-09
tags: [use-case, plan, uc-1, investment, hedonic, m1]
uc_number: "1"
status: planned
sprint_target: "sprint-06"
last_status_update: 2026-05-09
---

## For future Claude

This is the **UC-1** page — the investment-opportunity-ranking use case. It's the foundation for [[UC-2]] and [[UC-3]] (both depend on UC-1's hedonic price model). MVP ships at [[sprint-06]] (🏁 Milestone 1, Week 13). Read this when you need to know who consumes the Investment Dashboard / Investment Map / Property Valuator app, what business questions they ask, what the composite `investment_score` actually combines, and which sprint ships which analytical layer.

## Users

Real estate **investors**, **property promoters**, **fund managers**, and **flippers**. They want a ranked list of properties on the market that are below their predicted fair value, with enough surrounding context (yield, renovation upside, neighbourhood trajectory) to act on the top results.

## Business questions

These five questions drive every analytical layer in this UC:

1. **Which properties on the market are priced below their predicted fair value?** Gap between asking price and predicted hedonic price.
2. **Which neighbourhoods are on an upward trajectory where prices haven't caught up to fundamentals?** Demographic shift + infrastructure investment + supply pipeline + price momentum.
3. **Where can I buy, renovate, and sell/rent at the highest ROI?** Renovation cost vs. post-reno value gap.
4. **What rental yield (long-term and short-term) does each property offer?** LTR rent / STR Airbnb yield, net of taxes.
5. **What infrastructure or regulatory catalysts will drive future appreciation?** Metro extensions, hospital openings, ARU designation, zoning changes.

## Decision output

A ranked list of investment opportunities with a composite `investment_score` (0-100) combining valuation gap, yield potential, renovation upside, neighbourhood momentum, and catalyst proximity. Surfaced via Metabase dashboard (sortable + filterable), Kepler.gl map (spatial exploration), and Streamlit app (single-listing deep-dive).

## What makes a property undervalued

- Listed price is significantly below the predicted price for its characteristics and location ([[idealista]] price vs. hedonic prediction)
- The neighbourhood is on an upward trajectory (gentrification, infrastructure investment, demographic shift) but prices haven't caught up yet
- The property has renovation potential where post-renovation value substantially exceeds acquisition + renovation cost (CV-classified condition `cv_condition` from [[sprint-04]] feeds this)
- STR yield potential exceeds the asking price justification (Inside Airbnb data)
- Regulatory tailwinds exist (ARU tax benefits via [[sprint-09]], new metro line via OSM transport stops, zoning change via [[crus]] / [[crus-ogc]])

## Analytical layers

| Layer | Where it lives | Sprint | Notes |
|---|---|---|---|
| **Hedonic pricing model** | `gold_analytics.property_valuation` (predicted €/m² + comp-weighted blended fair value) | [[sprint-05]] | OLS/Ridge on `log(price_sqm)` ~ property + location + neighbourhood + cv_* + energy_class_final. Foundation for all 3 UCs. R² target ≥ 0.73, MAPE < 18%. |
| **Residual analysis** ("the alpha") | `gold_analytics.property_valuation.gap_pct`, `valuation_signal` (undervalued / fair / overpriced) | [[sprint-05]] | Gap between asking price and predicted value |
| **Neighbourhood trajectory scoring** | `gold_analytics.neighbourhood_trajectory` | [[sprint-06]] | YoY price trend + population growth + vacancy change + catalyst proximity + [[sce]] supply signal (PCE issuance as 12-18 month leading indicator) |
| **Renovation upside model** | `gold_analytics.renovation_opportunity` | [[sprint-06]] | Reno cost (`ref_renovation_costs` seed) × CV-classified condition → post-reno value, ROI % |
| **Yield analysis** | `gold_analytics.investment_yield_analysis` | [[sprint-06]] | LTR yield (€/m² rent ÷ price), STR yield (Airbnb RevPAR × occupancy), net of IMI/IMT/condominium |
| **Catalyst detection** | `gold_analytics.ref_area_catalysts` (manual seed) | [[sprint-06]] | Known infrastructure projects: metro extensions, hospitals, university campuses, with geo + timeline |
| **Composite scoring** | `gold_analytics.investment_opportunities` (materialized view) | [[sprint-06]] | `investment_score` = f(valuation_gap, yield, renovation_roi, trajectory, catalysts, listing_freshness) |

Per [[medallion-layering]]: every layer above lives in `gold_analytics`, fed by `silver_properties.unified_listings` + `silver_market.macro_timeseries` + `silver_geo.census_demographics` + `silver_location.*`.

## Conceptual data model

```
                    ┌─────────────────────┐
                    │     PROPERTY        │
                    │   (unified listing) │
                    └──────────┬──────────┘
                               │
              has              │              has
    ┌─────────────────┐        │        ┌────────────────┐
    │  VALUATION      │        │        │  LOCATION      │
    │                 │        │        │  SCORE         │
    │ predicted_price │◄───────┤────────►│               │
    │ asking_price    │        │        │ transport      │
    │ hedonic_gap_%   │        │        │ walkability    │
    │ comp_gap_%      │        │        │ education      │
    │ blended_gap     │        │        │ healthcare     │
    │ signal          │        │        │ overall        │
    └─────────────────┘        │        └────────────────┘
                               │
    ┌─────────────────┐        │        ┌────────────────┐
    │  YIELD          │        │        │  RENOVATION    │
    │  ANALYSIS       │        │        │  OPPORTUNITY   │
    │                 │◄───────┤────────►│               │
    │ gross_yield     │        │        │ reno_cost      │
    │ net_yield       │        │        │ post_reno_val  │
    │ STR_yield       │        │        │ ROI            │
    │ cash_on_cash    │        │        │ is_ARU         │
    │ 5y_total_return │        │        │ tier           │
    └─────────────────┘        │        └────────────────┘
                               │
         is located in         │
    ┌─────────────────┐        │        ┌────────────────┐
    │ NEIGHBOURHOOD   │        │        │  CATALYST      │
    │ TRAJECTORY      │◄───────┘────────►│               │
    │                 │                 │ type (metro,   │
    │ price_momentum  │                 │  ARU, school)  │
    │ supply_demand   │  near           │ name           │
    │ demographics    │◄────────────────│ completion_dt  │
    │ trajectory_score│                 │ impact_%       │
    │ label           │                 │ impact_radius  │
    └─────────────────┘                 └────────────────┘
            │
            ▼
    ┌─────────────────────────────────────┐
    │      INVESTMENT OPPORTUNITY         │
    │     (composite scoring view)        │
    │                                     │
    │  investment_score (0-100)           │
    │  = f(valuation_gap, yield,          │
    │      renovation_roi, trajectory,    │
    │      catalysts, listing_freshness)  │
    └─────────────────────────────────────┘
```

PROPERTY (one row per active sale listing in [[idealista]] / [[remax]] / [[zome]] / [[jll]]) is the central entity. It has many attached signals (valuation, location score, yield, renovation, neighbourhood, catalysts), all materialized in `gold_analytics`. The `investment_opportunity` materialized view joins them into a single ranked surface.

## Serving layer

Three surfaces, all shipping in [[sprint-06]] (Week 13, Milestone 1 LIVE):

| Surface | Tool | Purpose | Filters / interactions |
|---|---|---|---|
| **Investment Dashboard** | Metabase OSS 0.48+ on port 3000 | KPIs, ranked table by `investment_score`, yield-vs-price scatter | Budget, location, typology, min yield |
| **Investment Map** | Kepler.gl 3.0 embedded in Streamlit (`streamlit-keplergl` 0.3.0 — no separate container per [[2026-05-08-streamlit-keplergl-not-superset]] decision; ADR lands in PR 6) | Spatial exploration: listing points colored by valuation gap, neighbourhood-trajectory polygons, infrastructure catalysts | Layer toggles, zoom-level filtering, click-for-details |
| **Property Valuator** | Streamlit 1.41+ on port 8501 | Single-listing deep-dive: enter address/listing URL → predicted value, valuation gap, comparable sales, neighbourhood stats | Address autocomplete via Nominatim |

Database access: Metabase + Streamlit roles SELECT-only on `gold_analytics`, `silver_geo`, `silver_properties`, `silver_market` (per `warehouse/init/001_create_schemas.sql` schema layout, see [[medallion-layering]]).

## Dependencies

Sequential prerequisites:

- [[sprint-01]] — `dim_geography` (3,049 freguesias, dual-CRS, census-enriched)
- [[sprint-02]] — `silver_market.macro_timeseries` (rates, HPI for affordability context)
- [[sprint-03]] — `silver_properties.unified_listings` v1 (resale-only, [[idealista]] feed)
- [[sprint-04]] — image classification (`cv_condition`, `cv_finish_quality`) + location scores (transport + POI proximity) + [[sce]] energy certificates
- [[sprint-04.5]] — `silver_properties.unified_listings` v2 (cross-portal: [[idealista]] + [[remax]] + [[zome]])
- [[sprint-05]] — **the hedonic model itself** — UC-1 cannot ship without it
- [[sprint-06]] — UC-1 MVP composes all of the above into the serving surfaces

UC-1's hedonic model also unlocks [[UC-2]] (pricing decomposition reuses hedonic coefficients as `location_price_premiums` lookup) and [[UC-3]] (development economics: GDV = GBA × predicted €/m²).

## See also

- [[idealista]], [[remax]], [[zome]], [[jll]] — listing sources feeding UC-1
- [[sce]] — energy certificate enrichment ([[sprint-05]] joins by address)
- [[ine]], [[bpstat]], [[ecb]], [[eurostat]] — macro/financial indicators feeding affordability + neighbourhood trajectory
- [[bgri]], [[caop]], [[osm]] — spatial backbone
- [[medallion-layering]], [[scd2-row-hash]], [[zenrows-universal-vs-re-api]], [[payload-cache-lifecycle]] — concepts
- [[2026-05-08-idealista-enrichment-architecture]] — drives Phase 5 description enrichment that feeds hedonic features
- [[sprint-05]] — predecessor (hedonic model)
- [[sprint-06]] — UC-1 MVP delivery (🏁 M1)
- [[UC-2]], [[UC-3]] — siblings that depend on UC-1's hedonic model
- [README §1.1 + §7.2 + §17](../../README.md) — canonical sources
