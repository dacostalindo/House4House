---
title: Sprint 5 — Hedonic Model & Valuation
type: plan
last_verified: 2026-05-09
tags: [sprint, plan, hedonic, valuation, ml, weeks-10-11]
status: planned
sprint_number: "5"
weeks: "10-11"
last_status_update: 2026-05-09
---

## For future Claude

This is the **Sprint 5** page (Weeks 10-11): the hedonic regression model that becomes the foundation for UC-1 investment scoring (Sprint 6), UC-2 pricing (Sprint 7), and UC-3 development economics (Sprint 8). [[sce]] energy-class enrichment lands here as a JOIN onto `unified_listings`. Read this when you need to know how the model that predicts €/m² for any listing is built.

## Goal

Train a hedonic regression (OLS/Ridge) that predicts `log(price_sqm)` from property + location + neighbourhood + image-classification + energy-class features. Cross-validation target: R² ≥ 0.73, MAPE < 18%. Output: `gold_analytics.property_valuation` with predicted fair value, valuation gap, and signal (undervalued/fair/overpriced) for every active sale listing.

## Deliverables

- Enrich `unified_listings` with [[sce]] energy class: LEFT JOIN `sce_certificates` on `freguesia_code` + `pg_trgm SIMILARITY(address_clean, normalized_address) > 0.6`. New columns: `sce_energy_class`, `sce_doc_number`, `energy_class_final = COALESCE(sce_energy_class, energy_class)`. Requires `pg_trgm` extension
- `gold_analytics.neighbourhood_market_stats`: per-freguesia median €/m², listing count, inventory months, QoQ price trend, dominant property type, CV condition distribution
- `gold_analytics.hedonic_features`: join `unified_listings` + `property_location_scores` + `census_demographics` + `neighbourhood_market_stats` + `zoning` into feature vector. Uses `energy_class_final` (SCE-enriched). `is_sce_certified` flag + `development_unit_count` from `new_developments` join. Filters: `operation_type = 'sale'`, `is_active = TRUE`, `price_eur ∈ [20000, 5000000]`
- Hedonic model training: OLS/Ridge on `log(price_sqm) ~ property + location + neighbourhood + cv_condition + cv_finish_quality + energy_class_final`. Image classification + SCE features expected to improve R²
- Model validation: cross-validation (R² ≥ 0.73, MAPE < 18%); residual analysis by geography
- `gold_analytics.property_comparables`: KNN on feature space; top-10 similar listings within 2km, same typology band
- `gold_analytics.property_valuation`: predicted €/m² + comp-weighted €/m² → blended fair value, gap %, signal (undervalued/fair/overpriced)

## Exit criteria

Every sale listing has predicted fair value and `valuation_signal`. SCE energy class enrichment live. Hedonic model serves as foundation for UC-1, UC-2, UC-3.

## Key decisions

- **Pydantic AI for [[idealista]] description enrichment** (planned Phase 5 of dev-tooling roadmap) writes to silver, NOT bronze — per [[2026-05-08-idealista-enrichment-architecture]] (silver respects [[bronze-permissive]]; LLM output IS validated via `ListingEnrichment` Pydantic AI strict-mode parse, but at silver-write time)
- Description-hash cache `(listing_id, sha256(description))` for re-run idempotency and cost control
- Dead-letter table for Pydantic AI parse failures
- Phase 5 (gstack dev-tooling) ships separately from Sprint 5 (data-product) — different roadmaps, parallel execution possible per [[sprint-dev-tooling]]

## Status update history

- 2026-04-18: declared in README §12; status `planned`

## See also

- [[idealista]], [[sce]], [[bgri]], [[caop]] — sources feeding hedonic features
- [[2026-05-08-idealista-enrichment-architecture]] — locked architecture for Phase 5 description enrichment
- [[bronze-permissive]] — why LLM enrichment writes to silver, not bronze
- [[medallion-layering]] — silver/gold pattern this sprint extends
- [[sprint-04]] — predecessor (cv_* + location scores feed hedonic features)
- [[sprint-04.5]] — predecessor (`unified_listings` v2 + `developments_canonical`)
- [[sprint-06]] — first downstream consumer (UC-1 investment scoring)
- [[sprint-07]] — second downstream consumer (UC-2 pricing decomposition)
- [[sprint-08]] — third downstream consumer (UC-3 development economics)
- [[sprint-dev-tooling]] — Phase 5 description-enrichment work runs in parallel
