---
title: P3/P4 future-expansion roadmap
type: plan
last_verified: 2026-05-10
tags: [planning, roadmap, p3, p4, future-expansion, plan]
---

## For future Claude

This is the **P3/P4 roadmap** — deferred sources organized into four post-MVP phases (2A Risk & Environment, 2D Land Development Intelligence, 2B Supply & Costs, 2C Coverage & Niche). Read this when an MVP source escalates an enrichment trigger ("we keep hitting the noise/flood gap"), when scoping a P3+ sprint, or when a deferred source becomes relevant to a use case. Decomposed from README §16.

## What it is

The deferred-source landscape: 18+ sources that were excluded from the MVP scope (Sprints 1-9, weeks 1-20) but offer concrete enrichment value once the MVP stabilizes. Each source has a predicted "value add" + an expected accuracy/feature improvement. Sources are batched into four expansion phases that align with use-case enrichment cycles.

The phases are NOT strict-sequential. Pick the source that addresses an actual pain point. The phase grouping is "kinds of value that make sense to land together" rather than a calendar order.

## Phase 2A — Risk & Environment (Weeks 17-20 originally; now post-MVP)

Reduces R² loss in the hedonic model from currently-missing risk features.

| Source | Value Add | Expected Improvement | Trigger condition |
|---|---|---|---|
| [[apa]] expansion (full ARPSI + non-EU-Floods-Directive flood layers) | `flood_risk_level` in hedonic model + UC-3 buildability | +1-2% R² in flood zones | UC-1 hedonic R² ≤ 0.72 in coastal/riverbank concelhos |
| S35 APA Flood Risk (broader than ARPSI) | Comprehensive flood-risk feature beyond EU directive scope | +1-2% R² | Same as APA expansion |
| S27 Noise Maps (LX/Porto) | `noise_level_db` in hedonic + UC-2 pricing premium | +2-3% R²; `noise_discount` in UC-2 | Listings near major roads/airports show unexplained price variance |
| S13 ADENE Certificates (if FOI succeeds) | `kWh/m²`, `CO2`, detailed energy stats | Better energy-class premium calibration than [[sce]] alone | UC-2 energy-class premium estimates inconsistent with field validation |

Phase 2A is the "improve UC-1's hedonic accuracy" phase; benefits cascade to UC-2 + UC-3.

## Phase 2D — Land Development Intelligence (Weeks 17-22 originally; aligned with UC-3 enhancement cycles)

Extends UC-3 from "screening tool" to "decision-grade analysis."

| Source | Value Add | Trigger condition |
|---|---|---|
| S42 MS Building Footprints | Vacant-plot detection (vs. [[bupi]]'s "any parcel" baseline); building coverage per parcel | UC-3 produces too many false-positive vacant flags |
| S43 Sentinel-1 SAR | Active-construction detection (cloud-independent); identifies parcels currently under development that haven't appeared in [[cos]] yet | UC-3 finds opportunity sites that turn out to already be under construction |
| S20 ARU Boundaries | Tax-benefit flagging for rehabilitation zones (Áreas de Reabilitação Urbana) — material to UC-3 economics | UC-3 economics models miss tax-incentive premium |
| S21 INE Building Permits | Authorized-construction validation; supplements UC-3 buildability analysis | UC-3 buildability flags need ground-truth validation |
| [[srup-ogc]] REN expansion (Phase 2 of SRUP) | Ecological-reserve constraint for buildability gating | Already partially in scope via [[srup-ogc]] WS2a/b; full validation gates this row |

Phase 2D unblocks UC-3 production-grade analysis. Currently UC-3 ships in Sprint 8 with screening-grade output.

## Phase 2B — Supply Pipeline & Costs (Weeks 23-26)

Calibrates UC-2 pricing and UC-3 economics with real cost data.

| Source | Value Add | Trigger condition |
|---|---|---|
| S25 IMPIC Construction Costs | Real construction-cost indices to calibrate the renovation-cost model and UC-3 development economics | UC-2 / UC-3 economics produce cost estimates that field-validation rejects |
| S28 PVGIS Solar | Precise sun exposure for orientation premiums (vs. simplified compass-bearing lookup at MVP) | UC-1 hedonic shows orientation premium variance that simplified lookup misses |

## Phase 2C — Coverage & Niche (Weeks 27+)

Tail of nice-to-have sources; enabled when steady-state operations frees solo-dev bandwidth.

| Source | Value Add | Notes |
|---|---|---|
| S07 Casa Sapo | Third listing portal; +5-10% unique listings | Same pattern as [[idealista]] / [[remax]] / [[zome]] / [[jll]] |
| S26 DGPC Heritage | Heritage flag for renovation constraints | Pairs with [[srup]] IC for protection-of-cultural-heritage classification |
| S33 Google Trends | Demand leading indicator in trajectory model | Free API but rate-limited; quality varies by topic |
| S30 Porta 65 Rent Caps | Government rental benchmark cross-check | Mostly Lisbon/Porto; useful for [[UC-2]] rental pricing |
| S32 PORDATA | Additional socioeconomic granularity beyond [[ine]] | Free API but ~3-5 month publication lag |
| S36 ICNF Fire Risk | Rural property risk factor | Complements [[srup-ogc]] perigosidade_inc_rural at parcel-grain |
| S37 Municipal Open Data | Hyperlocal amenity enrichment | One-off per municipality (similar to [[aveiro-pmot]]) |

## Schema-evolution principle

Per README §16 closing note: **all deferred fields are nullable.** Models automatically incorporate new features without schema changes. When a P3+ source lands:

1. Bronze schema gets a new table per [[bronze-permissive]] policy.
2. Silver staging adds a new model joining the new bronze table to existing silver entities (listing × new feature, parcel × new constraint, etc.).
3. Hedonic model picks up the new feature in the next training run; missing values handled via mean imputation per the model's existing missing-data strategy.
4. UC dashboards add the new feature as a filter / display column where useful; missing-values render as "N/A" rather than blocking.

This compositional schema lets P3+ work proceed incrementally — no big-bang re-architecting.

## Sprint integration

Sprints 9-10 (operationally) absorb Phase 2A + 2D priorities. Phase 2B + 2C absorb post-Sprint-10. Specific source escalations are handled per-source via the trigger conditions in the tables above; [[risks]]'s monitoring discipline surfaces when an MVP gap warrants P3+ pull-forward.

## See also

- [[risks]] — risk register; some P3+ sources address active risks (R7, R8, R10, R13)
- [[resources]] — budget + effort estimates assume MVP scope; P3+ adds to both
- [[milestones]] — MVP gates that, once cleared, unlock P3+ scope decisions
- [[UC-1]], [[UC-2]], [[UC-3]] — use-case pages that benefit from specific P3+ sources
- [[bronze-permissive]] — the schema-evolution principle that lets P3+ work compose
- [[apa]], [[srup-ogc]], [[lidar]], [[lneg]] — sources already partially in scope that overlap with P3+ enrichment categories
- README §16 — the canonical source for this content
