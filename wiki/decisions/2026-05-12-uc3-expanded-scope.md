---
title: UC-3 reframed as end-to-end land economic-value pipeline; v1 wedge = Aveiro Stages 1-4 + SCE + LLM-on-plots (idealista) + dev dedup
type: decision
last_verified: 2026-05-12
tags: [uc-3, scope, wedge, decision, speculation, gstack-office-hours, gstack-plan-eng-review]
confidence: speculation
---

## For future Claude

This is a decision record about reframing [[UC-3]] from "national-scope spatial-overlay Land Development Opportunity Detection" (the pre-2026-05-12 framing) into an end-to-end **plot economic-value pipeline** with seven stages (Scout → Inspect → Assemble → Build out → Value → Profit → Competitive Intel) and a tightly-scoped v1 wedge. The original framing and the 2026-05-03 Aveiro GIS demo design get absorbed. `confidence: speculation` because the data-assembly-moat thesis underlying the reframe has not yet been validated against a real Portuguese land developer — the assignment to interview 3 developers is the gate. Read this before editing [[UC-3]] or [[sprint-08]] / [[sprint-09]], or before adding to any of the new gold/silver models the v1 wedge introduces.

## Decision

UC-3 is replaced. The new framing:

- **7-stage roadmap**: (1) Scout, (2) Inspect, (3) Assemble, (4) Build out, (5) Value, (6) Profit, (7) Competitive Intel.
- **v1 wedge ships Stages 1-4 + two narrow Stage-7 slices** (SCE unit aggregation + LLM construction-area extraction on idealista plot listings) + a small unification layer (silver_unified_developments) for development dedup. Aveiro município only.
- **Stages 5-6 (Value + Profit) defer to v2.** Economics depth (GDV from [[UC-1]] hedonic, residual land value, ROI, scenarios, ±10% sensitivity) is post-wedge work.
- **Full Stage 7 (national rollout + promoter dedup via building permits / Approach A) defers to v3.**
- **Primary user journey is draw-your-own-polygon** (Desenhar CTA per variant B-prime), not click-a-pre-computed-parcel. The `click-anywhere-to-assess` affordance was explicitly dropped in the approved Atlas mockup.
- **Architecture keystone**: `gold.fn_assess_polygon(input_geom geometry) RETURNS jsonb` as a Postgres SQL function. Streamlit-component in v1 calls it directly; v2 web app wraps it via FastAPI/PostgREST shim — no backend rewrite at v2.
- **v1 UI** = Streamlit-component at `apps/pages/4_site_inspector.py` (replaces existing `4_parcel_explorer.py` + `5_site_analyzer.py` placeholders). **v2 UI** = standalone web app gated on interview validation.
- **Demo-grade error handling** for v1 (fail-fast at boundaries, no retries, no last-good fallback). Production-grade in v2.
- **Slice C scope cut to idealista-only** in v1 (jll/remax/zome plot LLM extraction land in v1.5).
- **No per-parcel materialized `parcel_assessment` table** — wasteful for draw-polygon UX. Upstream silver tables stay materialized + GIST-indexed; assessment runs live via the function.

The 2026-05-03 Aveiro GIS demo design (`~/.gstack/projects/dacostalindo-House4House/manuellindo-main-design-20260503-163252.md`) is absorbed as the inherited foundation (Workstreams 1 + 3 of the v1 wedge plan). Workstream 2 of that design (national OGC migration) is **dropped from the v1 wedge** as sunk-cost inheritance unrelated to single-município validation.

## Why

The original UC-3 framing was a national-scope spatial-overlay product (BUPI × COS × CRUS × SRUP + `ST_ClusterDBSCAN` assembly + economics + opportunity scoring + 3 serving surfaces). It overlapped substantially with the Aveiro GIS demo design and had no clear demand validation. The reframe was driven by an [[2026-05-12-uc3-expanded-scope|office-hours session]] (design doc at `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-design-20260512-151500.md`) that established:

1. **The customer is hypothetical.** No specific PT land developer / fund / promoter has been interviewed. Demand evidence is market inference only (Atlas Inteligência Territorial exists; CBRE/JLL publish PT market reports; DGT publishes machine-readable cadastre).
2. **Status-quo read: "doing nothing because the data is too hard."** The data-assembly moat thesis is "nobody else has stitched cadastre + zoning + SRUP + LiDAR + COS + portal listings + SCE + promoter data at parcel grain in Portugal." Highest-ambition framing, also the riskiest (can mask low demand).
3. **The wedge needs to test the moat thesis specifically.** Original UC-3 didn't add the SCE / LLM-on-plots data layers that make the moat unique. Without them, the demo is "Atlas-clone with terrain awareness" — interesting but not differentiated.
4. **The Aveiro demo's "demo IS the architecture" framing is right but oversized.** The 2026-05-03 design pulled in national OGC migration (Workstream 2) as part of the demo plan. The reframe drops WS2 from v1: it's national infrastructure work that has zero bearing on whether a single Aveiro user-interview validates the moat thesis.

The reframe also accommodates a major architectural pivot surfaced during `gstack /plan-eng-review`: the primary user journey is **draw-your-own-polygon**, not click-a-pre-computed-parcel. The approved variant B-prime mockup explicitly dropped `click-anywhere-to-assess` as an affordance in favor of `Desenhar`. The original UC-3 + Aveiro demo design both implicitly assumed per-parcel materialization, which is wasteful when the actual interaction is on-demand polygon assessment.

Decision recorded with `confidence: speculation` because the underlying thesis is unvalidated. Three developer interviews (assignment per the office-hours session) are the gate that flips this to `confidence: medium`. Kill criteria are pre-committed in the design doc; the wedge is killed (and this ADR gets a `superseded_by:` field) if ≥2 of 3 developers cannot describe a specific recent decision they would have made differently with this tool.

## Consequences

Downstream wiki and code changes:

1. [[UC-3]] page rewritten in place. Old 9-question framing replaced with the 7-stage funnel + v1 wedge scope.
2. [[sprint-08]] restructured to be **v1 wedge Foundations** (Workstreams 1 + 3 + start of WS4 Slice B + dev dedup setup) instead of "UC-3 MVP Land Development Opportunities."
3. [[sprint-09]] restructured to be **v1 wedge Completion + demo** (WS4 finish + Atlas Site Inspector + dev dedup completion + demo dry-run). Existing sprint-09 content (Imovirtual scraper, RNAL, INE Building Permits, REN, hedonic v2, ARU) is deferred — much of it now belongs in v2 (post-interview) work.
4. New `bronze_enrichment` schema introduced for LLM extraction outputs (honors [[bronze-permissive]] rule).
5. SCE geocoding moves from sprint-09 (where it was deferred) into v1 wedge sprint-08 (Workstream 4 Slice B Step 1).
6. Atlas-style web UI (variant B-prime, `~/.gstack/projects/dacostalindo-House4House/designs/aveiro-parcel-assessment-inspect-20260506/approved.json`) replaces the original UC-3 Kepler.gl Parcel Explorer as the canonical inspection surface.
7. `apps/pages/4_parcel_explorer.py` + `apps/pages/5_site_analyzer.py` are deleted; replaced by `apps/pages/4_site_inspector.py`.
8. **20 critical tests** added to the v1 wedge plan (CI-integrated: dbt + pgTAP + pytest + LLM eval-set + Playwright). Long-tail edge cases (~44 of 64 codepaths) addressed during implementation review.
9. **Rollback plan if interviews kill the wedge**: this ADR gets a `superseded_by:` field pointing at a new ADR documenting the pivot. The wiki rewrites in UC-3 + sprint-08 + sprint-09 stay as historical record of what was attempted.

Sibling pages affected (propagation per Rule 3 in `wiki/CLAUDE.md`) — to be revisited if interviews validate the wedge:

- [[UC-1]] — UC-3 now depends on UC-1 hedonic only for v2 (Stages 5-6).
- [[UC-2]] — shared dependency on the new LLM-extraction pipeline (Slice C infrastructure could power UC-2 portal enrichment).
- [[sprint-03]] — UC-3 GIS bronze + staging still load-bearing (no change).
- [[sprint-05]] — UC-3 economics dependency moved from sprint-08 to v2 sprint.
- [[sce]] — Aveiro distrito scope is now load-bearing for the v1 wedge; SCE address normalization spec lands as Appendix A of the design doc.
- [[idealista]] — load-bearing for Slice C (LLM extraction on plot listings, idealista-only in v1).
- [[bupi]], [[cos]], [[crus]], [[srup]], [[cadastro]], [[lidar]] — unchanged at staging level; new gold composition via `fn_assess_polygon`.
- [[medallion-layering]] — new `bronze_enrichment` schema added.

## Status

accepted (the *decision to test the thesis* is accepted; the *thesis itself* is unvalidated and the wedge is gated on developer interviews — see Decision section for kill criteria)

## See also

- [[UC-3]] — the page this decision reframes
- [[sprint-08]] — v1 wedge Part 1
- [[sprint-09]] — v1 wedge Part 2
- [[UC-1]] — hedonic dependency moves to v2
- [[UC-2]] — sibling sharing portal-enrichment infrastructure
- [[sce]] — load-bearing data source for Slice B
- [[idealista]] — load-bearing for Slice C
- [[bupi]], [[cos]], [[crus]], [[srup]], [[cadastro]], [[lidar]] — spatial backbone (unchanged)
- [[medallion-layering]], [[bronze-permissive]] — concepts applied
- Office-hours design doc: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-design-20260512-151500.md`
- 2026-05-03 Aveiro demo design (absorbed): `~/.gstack/projects/dacostalindo-House4House/manuellindo-main-design-20260503-163252.md`
- Variant B-prime UI mockup: `~/.gstack/projects/dacostalindo-House4House/designs/aveiro-parcel-assessment-inspect-20260506/approved.json`
- /plan-eng-review test plan: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-eng-review-test-plan-20260512-155850.md`
