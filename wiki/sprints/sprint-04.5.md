---
title: Sprint 4.5 — Listings + Developments Cross-Portal Dedup
type: plan
last_verified: 2026-05-09
tags: [sprint, plan, silver, gold, cross-portal-dedup, week-9]
status: planned
sprint_number: "4.5"
weeks: "9"
last_status_update: 2026-05-09
---

## For future Claude

This is the **Sprint 4.5** page (Week 9): the cross-portal silver + gold work. Scope locked to 3 portals ([[remax]], [[idealista]], [[zome]] — JLL/ERA/C21/KW deferred to Sprint 4.6+). Goal is end-to-end clean, deduplicated cross-portal view of listings AND developments — every record gets normalized in silver, deduped across portals, and rolled up into gold models ready for UC-1, UC-2, UC-3. Builds directly on Sprint 4.4's foundational cleanup.

## Goal

Deliver `silver_properties.developments_canonical` (~2k unique real-world developments with portal cross-references), `silver_properties.unified_listings` v2 (one row per real-world listing across 3 portals — replaces previous resale-only version), `gold_analytics.development_lifecycle` (PCE→CE→on-market timeline), and `gold_analytics.absorption_rate_model` (sell-through from RE/MAX `isSold` + Zome state changes + Idealista listing disappearance). Foundation for hedonic model (Sprint 5) and UC-1/UC-2/UC-3.

**Volumes in scope:** ~2,914 developments (RE/MAX 615 + Idealista 1,994 + Zome 305); ~30,450 development units; 526,810 general listings (Idealista resale dedup).

## Deliverables

- Bronze cleanup & consistency: per-source READMEs, DAG parity, CI/CD baseline + dbt source freshness, RE/MAX sitemap+Next.js cutover (12× coverage from ~3,900 to ~47,205), RE/MAX nationwide expansion, Zome state coverage (Sale/Reserved/Sold)
- Silver staging review (one model per source × entity): Portuguese normalization library (dbt macros + Python), `stg_remax_*`, `stg_idealista_*`, `stg_zome_*` review passes with canonical column-set parity
- Cross-portal dedup framework (`pipelines/matching/`): blocking by GPS cell + concelho; scorers = GPS distance, name trigram, unit-count tolerance, typology overlap; hand-curate 50 known matches → calibrate
- **Phase 1 — Development dedup** (small N, ~3k): pairwise links → `silver_matching.development_links`
- **Phase 2 — Listings within matched developments** (link by floor + typology + area + price)
- **Phase 3 — Orphan listing dedup** (GPS ≤30m + typology + area ±5% + price ±10%)
- Match-quality validation (200-pair hand-labeled sample for developments + 200-pair for listings; precision/recall computed)
- Silver unified models: `developments_canonical`, `development_units`, `unified_listings` v2, `development_source_xref`
- `silver_properties.sce_certificates` ([[sce]] joined to `dim_geography` via UPPER(concelho)+UPPER(freguesia); `tipo_documento` distinguishes PCE/CE/DCR; indexes on matrix_article, geo_key, issued_date, normalized_address)
- Gold analytics: `development_lifecycle` (construction timeline: PCE issued → CE issued → portal first_seen → sold-out), `absorption_rate_model` (per-development sell-through), `competitive_developments` (≤2km neighbors with price/typology/status), `fact_all_listings` (UNION view: resale + new-development)
- Documentation: `silver_matching/README.md` (blocking rules, scorers, threshold rationale, how-to-add-portal); dbt exposures declaring UC-1/UC-2 dependencies on `developments_canonical` + `unified_listings`

## Exit criteria

`developments_canonical` lists ~2k unique real-world developments with portal cross-references. `unified_listings` provides one row per real-world listing across all 3 portals. `development_units` star schema operational. `development_lifecycle` and `absorption_rate_model` populated. Match quality validated >0.9 precision on hand-labeled sample. SCE certificates operational. Foundation in place for Sprint 5 hedonic model.

## Key decisions

- **Three portals only this sprint:** RE/MAX, Idealista, Zome. JLL/ERA/C21/KW deferred to Sprint 4.6 (mechanical add once matching framework exists)
- **Two-phase dedup:** developments first (small N, hand-tunable), then listings constrained by matched developments (precision boost). Orphan listings as a third pass
- **Splink as a tool, not a framework:** evaluated only for high-volume Idealista intra-source dedup. Hand-rolled scorers cover the other cases
- **Schema parity in staging:** every `stg_{source}_*` model exposes the same canonical column set so silver doesn't have N×M source-specific JOIN logic
- **Attribute priority RE/MAX > Idealista > Zome:** revisit per-field once data is profiled (e.g., Idealista may have better address quality)
- **SCE cross-reference preserved:** `sce_certificates` joins to `developments_canonical` via concelho + freguesia + matrix_article + GPS proximity for ground-truth unit counts and lifecycle dates
- **Shared CV service preserved:** floor-plan extraction stays portal-agnostic via `source_type` column on `floor_plan_rooms`

## Status update history

- 2026-04-18: declared in README §12; status `planned`

## See also

- [[remax]], [[idealista]], [[zome]], [[jll]], [[sce]] — sources used (JLL deferred to 4.6)
- [[scd2-row-hash]], [[heartbeat-sidecar]], [[bronze-permissive]], [[medallion-layering]] — concepts applied
- [[2026-05-08-idealista-enrichment-architecture]] — drives the `raw_idealista` decommission gate that blocks completion of this sprint
- [[sprint-04]], [[sprint-04.4]] — predecessors
- [[sprint-05]] — successor (hedonic model uses `unified_listings` v2)
