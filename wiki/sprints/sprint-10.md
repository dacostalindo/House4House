---
title: Sprint 10 — Production Hardening + Portal Expansion + UC-3 v2 Readiness
type: plan
last_verified: 2026-05-17
tags: [sprint, plan, hardening, portal-expansion, imovirtual, rnal, hedonic-v2, aru, uc-3-v2, ci-tier-2, weeks-22-24]
status: planned
sprint_number: "10"
weeks: "22-24"
last_status_update: 2026-05-17
---

## For future Claude

This is **Sprint 10** (Weeks 22-24). Created 2026-05-12 to absorb scope displaced from the old [[sprint-09]] when [[sprint-09]] was restructured per [[2026-05-12-uc3-expanded-scope]] to be the [[UC-3]] v1 wedge completion sprint. Sprint 10 mixes project-wide hardening (Imovirtual, RNAL, data-quality monitoring, documentation) with [[UC-3]] v2 readiness work (ARU boundaries, REN ingestion, hedonic v2 retrain, building permits). **Most of Sprint 10 is GATED on the UC-3 wedge validation outcome at end of [[sprint-09]]** — if interviews kill the wedge, the UC-3 v2 items defer indefinitely and Sprint 10 contracts to portal expansion + hardening only. Read this when triaging post-wedge work or when planning v1.5+ enhancements.

## Goal

Two parallel tracks:

1. **Track A — Project hardening and portal expansion** (independent of UC-3 wedge outcome). Add Imovirtual portal, RNAL license registry, INE Building Permits, REN (SRUP Phase 2), data-quality monitoring, documentation. These items were in the original Sprint 9 framing and remain valuable regardless of whether the UC-3 wedge validates.
2. **Track B — UC-3 v2 readiness** (GATED on [[sprint-09]] wedge validation). ARU boundaries, hedonic v2 retrain with OSRM drive-times + ARU flag, UC-3 v2 economics (Stages 5-6) initial scoping. Only ships if ≥2 of 3 PT developer interviews validated the wedge per the kill criteria in [[2026-05-12-uc3-expanded-scope]].

## Deliverables

### Track A — Project hardening + portal expansion (always ships)

- **[[idealista]]-sibling: Imovirtual scraper (S05)** — second listing portal live → `bronze_listings.raw_imovirtual`. Selenium/HTML-only shape (non-API), high-friction relative to the dlt-driven portals. Originally planned earlier; pushed because the scraping shape is operationally heavier.
- **Cross-portal dedup** at the listing level: `hash(address + area + typology)` matching with fuzzy fallback. Output: `silver_properties.unified_listings.property_hash`, `silver_properties.listing_matches`. Distinct from the [[UC-3]] v1 wedge's `silver_unified_developments` which deduplicates at the DEVELOPMENT level (not listing level).
- **RNAL scraping (S14)** — Alojamento Local license registry → `bronze_listings.raw_rnal`. Useful for filtering short-term-rental listings out of long-term hedonic features.
- **INE Building Permits (S21)** — permit data → `bronze_ine.raw_building_permits`, `stg_building_permits`. **Load-bearing for future Approach A promoter slice (UC-3 v3)**; in Sprint 10 we ingest + stage but do not yet derive promoter signals.
- **REN ingestion (SRUP Phase 2 via [[srup-ogc]])** — Ecological Reserve areal + linear → `bronze_regulatory.raw_srup_ren`, `stg_srup_ren`. Closes the explicit Phase-2 TODO in [pipelines/gis/srup/srup_config.py](../../pipelines/gis/srup/srup_config.py). Useful for [[UC-3]] gate severity refinement and for ARU overlay logic.
- **CI data integration (if license obtained, S02)**: transaction prices from authoritative source → validate hedonic predictions, calibrate gap percentage. Licensee-gated; if commercial license fails, stays as a "deferred indefinitely" gap.
- **Data quality monitoring**: dbt tests + source freshness alerts + row count anomaly detection on every model. Already partial coverage from Phase 4 CI scaffolding (commit `fda6d6c`); Sprint 10 extends to all sources + all silver/gold models.
- **Documentation**: data dictionary + user guide + lineage diagrams. Auto-generated where possible (dbt docs); hand-written for the lineage narrative.
- **Tier-2 CI: seed-based `dbt build`** (~2-3 days, NET-NEW from [[sprint-09]] Slice B). [[sprint-09]] shipped Tier-1 — empty bronze tables in CI + `dbt build` structural validation. Tier-2 adds `dbt seed`-able CSV fixtures (~10-100 rows per bronze table along the v1-wedge path: SCE + cadastro + BUPI + SRUP + idealista). With fixtures in place, dbt's schema tests + singular tests fire meaningfully in CI, and the existing pgTAP tests at `tests/sql/sce_buildings_*.sql` can be refactored to query the live silver tables instead of inline-replicating the pipeline (~halving their length). Fixture maintenance becomes a real cost — keep fixtures small + targeted per source family. Gated on [[sprint-09]] wedge validation: if interviews kill the wedge, Tier-2 is sunk-cost CI infra; if validated, the v1.5+ workstreams ride on it.

### Track B — UC-3 v2 readiness (GATED on [[sprint-09]] wedge validation)

If [[sprint-09]] post-demo kill-criteria check returns **validated**:

- **ARU boundaries (S20)** — Urban Rehabilitation Areas → spatial overlay with [[UC-3]] assessment. Adds `is_aru` flag to `silver_geo.zoning` (extending); adds `aru_overlap_pct` to `gold.fn_assess_polygon` output JSONB. Tax-benefit relevance: ARU zones get IMT/IS/IRS rebates that materially affect Stage 5 (Value) calculations.
- **Hedonic v2 retrain**: add OSRM real travel times (replacing crow-flies KNN in `gold_analytics.property_location_scores`) + ARU flag to feature vector → retrain `gold_analytics.hedonic_features`, `property_valuation`. Improves R² and unlocks [[UC-3]] v2 Stages 5-6 GDV estimates.
- **OSRM drive-time integration** (originally scheduled for old Sprint 8 / UC-3 MVP): batch [[osm]] OSRM API listing → city center / airport / nearest hospital → upgrade `property_location_scores` from crow-flies to real travel time.
- **[[UC-3]] v2 design scoping**: Stages 5-6 (Value + Profit) economics layer design — `gold_analytics.site_economics` schema, scenario builder (Build-to-Sell / Build-to-Rent / mixed-use), ±10% sensitivity. Spec-level work in Sprint 10; implementation lands in a future v2 sprint.

If [[sprint-09]] post-demo kill-criteria check returns **killed** or **resized**:

- Track B items defer indefinitely. ARU/REN/hedonic-v2 remain valuable for [[UC-1]] but lose their [[UC-3]] urgency. The [[2026-05-12-uc3-expanded-scope]] ADR gets a `superseded_by:` field; new ADR documents the pivot.

## Exit criteria

**Track A** (always required):
- Imovirtual scraper live; rows landing in `bronze_listings.raw_imovirtual`.
- Cross-portal listing dedup running; `silver_properties.listing_matches` populated.
- RNAL + INE Building Permits + REN bronze/staging in place.
- Data quality monitoring extended to all silver/gold models.
- Documentation: dbt docs generated + lineage narrative published.

**Track B** (conditional on wedge validation):
- ARU boundaries ingested + `is_aru` flag on zoning.
- Hedonic v2 deployed (OSRM drive-times + ARU); R² improvement measured.
- UC-3 v2 economics schema spec'd (no implementation yet).

## Key decisions

- **Sprint 10 is mixed-track**: Track A (project-wide hardening) is uncoupled from UC-3 wedge outcome. Track B (UC-3 v2 readiness) is gated. Allows the project to make progress on independent items regardless of the wedge result.
- **Imovirtual ships LAST among portals** — JLL / RE/MAX / Zome / [[idealista]] are the canonical 4 (already shipped). Imovirtual was pushed because its non-API scraping shape is operationally heavier.
- **Hedonic v2 retrain triggered by OSRM drive-times + ARU**; not a fundamental architecture change, just a feature-vector expansion.
- **CI data integration is licensee-gated**; if commercial license fails, stays as "deferred indefinitely."
- **The original Sprint 9 SCE geocoding bullet** is **NOT in Sprint 10** — it moved into [[sprint-08]] as part of [[UC-3]] v1 wedge WS4 Slice B Step 1. Sprint 10 inherits zero SCE work.
- **The original Sprint 9 "UC-3 model recalibration" bullet** is superseded by the UC-3 reframe per [[2026-05-12-uc3-expanded-scope]]; UC-3 v2 means something different now (full Stages 5-6 economics, not just feature expansion).

## Status update history

- 2026-05-12: created to absorb scope displaced from old [[sprint-09]] when [[sprint-09]] was restructured to UC-3 v1 wedge Part 2 per [[2026-05-12-uc3-expanded-scope]]. Status `planned`. Track B gated on [[sprint-09]] wedge-validation outcome.
- 2026-05-17: added Track A item "Tier-2 CI: seed-based dbt build" (~2-3 days). Originates from sprint-09 Slice B where Tier-1 (empty bronze tables + structural `dbt build`) shipped — Tier-2 (seed-fixture-based `dbt build` enabling data-invariant tests + simpler pgTAP tests) deferred here per Slice B pushback on sprint-09 overload. Bundled into Track A (always ships) because the value is CI infrastructure independent of UC-3 wedge outcome — only the v1.5+ pay-off is wedge-gated.

## See also

- [[2026-05-12-uc3-expanded-scope]] — the ADR that displaced this scope from old [[sprint-09]]
- [[sprint-08]] — UC-3 v1 wedge Part 1 (Foundations)
- [[sprint-09]] — UC-3 v1 wedge Part 2 (Wedge Completion + Demo) — the kill-criteria gate for Track B
- [[idealista]], [[sce]] — portal sources (idealista already shipped; Imovirtual lands here)
- [[srup]], [[srup-ogc]] — SRUP REN ingestion path (Phase 2)
- [[osm]] — OSRM drive-time integration
- [[ine]] — INE Building Permits source
- [[UC-1]] — hedonic v2 retrain affects this primarily
- [[UC-3]] — v2 readiness work (Track B) gated on wedge validation
- [[medallion-layering]], [[scd2-row-hash]], [[bronze-permissive]] — concepts applied
- Phase 4 CI/CD scaffolding (commit `fda6d6c`) — predecessor for data quality monitoring extension
