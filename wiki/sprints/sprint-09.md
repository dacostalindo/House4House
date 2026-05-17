---
title: Sprint 9 — UC-3 v1 wedge Part 2 (Wedge Completion + Atlas Inspector + Demo)
type: plan
last_verified: 2026-05-17
tags: [sprint, plan, uc-3, wedge, completion, llm-extraction, dev-dedup, atlas-inspector, demo, weeks-19-21]
status: in_progress
sprint_number: "9"
weeks: "19-21"
last_status_update: 2026-05-17
---

## For future Claude

This is **Sprint 9** (Weeks 19-21, extended by 1 week from prior 19-20). Restructured 2026-05-12 per [[2026-05-12-uc3-expanded-scope]] to be **Part 2 of the [[UC-3]] v1 wedge** — completes Slice B silver_sce_buildings, ships Slice C LLM extraction (idealista-only), Slice B-prime dev dedup (silver_unified_developments), the `gold.fn_assess_polygon` Postgres function, the Atlas Site Inspector Streamlit-component, and runs the demo to the 3 interviewed PT land developers. Replaces the previous "Enhancements + Production Hardening" framing of Sprint 9 (Imovirtual scraper, RNAL, INE Building Permits, REN, hedonic v2 retrain, ARU) — those items defer to a future v1.5+ sprint to be created post-interview validation if the wedge passes its kill criteria. Read this before touching `fn_assess_polygon`, the Atlas Inspector, or the LLM extraction pipeline.

## Goal

Ship the [[UC-3]] v1 wedge differentiator: the data-assembly moat at parcel-grain expressed through `gold.fn_assess_polygon` and surfaced via the Atlas Site Inspector. Complete Slice B (SCE unit aggregation), ship Slice C (LLM extraction on idealista plot listings), ship Slice B-prime (dev dedup), and **run the demo against the 3 interviewed PT developers** per the [[2026-05-12-uc3-expanded-scope]] kill criteria.

**Hard gate before WS4 Slice C and B-prime start**: ≥1 developer interview must have completed (kill-criteria check) OR be scheduled to complete during the sprint. The wedge differentiator is **what's being validated** — building it without interviews in flight defeats the purpose of the staged migration plan.

## Deliverables

### Workstream 4 Slice B — SCE Unit Aggregation completion (~1 week, NET-NEW, DONE 2026-05-17)

Shipped: `dbt/models/silver/regulatory/silver_sce_buildings.sql` body-filled per [[sce-buildings-clustering]]. 12,634 buildings produced (1,166 in Aveiro concelho), build time 5.11s. 4 pgTAP tests landed at `tests/sql/sce_buildings_*.sql` — DBSCAN, address dedup, frac_count conservation, energy_class_dist completeness. All 8 dbt schema tests + all 10 pgTAP assertions pass.

**Design deltas vs original spec** (see [[sce-buildings-clustering]] for the full reasoning):
- **No Levenshtein** (Decision 2): exact-match on `normalized_address` within each DBSCAN cluster. 0% empirical leakage at 6k rows from the Appendix A normalizer makes fuzzy matching gilding-the-lily. v1.5 path documented if dev interviews surface false-splits.
- **No parcel_id / cluster_split** (Decision 3, "Option B"): empirically 97.7% of Nominatim-geocoded SCE points fall on street centerlines outside cadastral parcels (50-200m typical gap). The "tiebreak when cluster spans 2+ parcels" branch was unreachable; columns dropped. Atlas Inspector can join `parcel_universe` at query time when it wants per-parcel context. Test #11 retired.
- **No Splink / probabilistic linkage** (Decision 4): spatial DBSCAN(30m) + deterministic normalizer beats probabilistic matching for same-source within-30m. Deferred to `silver_unified_developments` if needed there.
- **DBSCAN + GROUP BY normalized_address** (Decision 5): chose adjacent-buildings-split-correctly over multi-frontage-buildings-merge-correctly. Suburban Aveiro adjacent buildings >> multi-frontage edges; revisit if interviews surface false-splits.

**Tier 1 CI added** ([tests/ci_bootstrap/bronze_sce.sql](tests/ci_bootstrap/bronze_sce.sql) + `dbt build --select +silver_sce_buildings` in [.github/workflows/ci.yml](.github/workflows/ci.yml)): structural validation against empty bronze tables. Catches type/JOIN/typo bugs that `dbt parse` misses. Per-PR additive convention — future Slice C/D PRs add their own `bronze_<source>.sql` bootstrap files. Tier-2 (seed-based dbt build with fixture data) deferred to [[sprint-10]] — gated on dev-interview validation.

#### Slice B follow-ups (small, NET-NEW)

- **`cluster_geocode_confidence > 1.0` bug**: Slice B verification surfaced one silver row with `cluster_geocode_confidence = 1.583` (out of the 0-1 range). Root cause is upstream in [[sprint-08]] Activity 7's geocoder — Nominatim's `importance` score sometimes exceeds 1.0 and we propagate it raw. Slice B just MINs whatever comes in. Fix: clamp `geocode_confidence` to `[0, 1]` in `pipelines/enrichment/sce_geocode_dag.py` and backfill `bronze_enrichment.raw_sce_geocoded`. ~30 min of work.

### Workstream 4 Slice C — LLM Construction-Area Extraction (idealista only, ~1-1.5 weeks, NET-NEW)

- **LLM eval-set construction spike** (1-2 days): hand-label ~50 idealista plot listings with construction-area-allowed extracted. Second-pass self-consistency check on 10 of them 1+ week later. Eval set at `tests/fixtures/plot_listings_eval.jsonl`. Per Appendix B of the design doc.
- `dbt/models/staging/portals/stg_plot_listings.sql` — filter [[idealista]] listings to `tipologia ∈ ('terreno', 'lote')` OR regex fallback (`\b(terreno|lote|prédio para construção)\b`). Mark `tipologia_source: structured|regex` for traceability.
- Pydantic schema `PlotListingExtraction(construction_area_m2_allowed, construction_index, parcel_area_m2, max_height_m, source_spans)` — **`construction_index` and `construction_area_m2_allowed` are SEPARATE fields** to avoid the confound where the LLM conflates `index × area` into the area field.
- `pipelines/enrichment/plot_listing_extraction_dag.py` — Pydantic-AI on **Claude Haiku 4.5** (cheapest reliable for PT prose) with structured outputs. Writes to **`bronze_enrichment.raw_plot_listing_extractions`** per [[bronze-permissive]]. Idempotent on `hash(listing_url + description_text)` — portal-side description edit triggers re-extraction.
- `dbt/models/silver/portals/silver_plot_listings_enriched.sql` — join `stg_plot_listings` + `bronze_enrichment.raw_plot_listing_extractions` → typed silver. Derived-validity dbt model: flag rows where `index × parcel_area` differs from extracted GBA by > 10%.
- Tests #16-#18 from Appendix C: per-field accuracy meets thresholds (85% on headline `construction_area_m2_allowed`), idempotency on listing hash, derived-validity flag correctness.
- **LLM eval-set CI gate**: any field below threshold blocks the prompt change. Runs on every Pydantic-AI prompt revision + model version pin bump.
- **Cost**: ~$40 one-time backfill for ~10K listings, ~$0.004 per new listing thereafter. With idealista-only scope, closer to ~$10-20 for ~2-3K plot listings.

### Workstream 4 Slice B-prime — Development Dedup (~1 day, NET-NEW)

- `dbt/models/silver/regulatory/silver_unified_developments.sql` — joins `silver_sce_buildings` + `silver_plot_listings_enriched` via:
  - Spatial proximity: `ST_DWithin(sce.geom, idealista.geom, 50)`
  - Optional Levenshtein-ratio ≤ 0.20 on normalized building name vs. listing title (where both populated)
- Each row = one canonical development with `provenance` JSONB: `{sce_building_ids: [...], idealista_listing_ids: [...]}` for traceability.
- Tests #21-#22 from Appendix C: proximity-only match collapses correctly; name-ambiguous case doesn't over-collapse.

### Workstream 4 — `gold.fn_assess_polygon` Postgres function (~3-5 days, NET-NEW, the keystone)

- `dbt/models/gold/fn_assess_polygon.sql` (or migration file) — defines the SQL function as a single backend entry point.
- `CREATE OR REPLACE FUNCTION gold.fn_assess_polygon(input_geom geometry) RETURNS jsonb`:
  - `ST_IsValid(input_geom)` guard → returns `{error: 'invalid polygon'}` on self-intersecting input.
  - `ST_Transform(input_geom, 3763)` — accepts WGS84 from Mapbox/Leaflet, transforms to PT-TM06 internally.
  - Spatial joins inside one function (single round-trip): zoning, the 14 `stg_srup_*` constraint layers joined to `dim_constraint_severity` for gates (per-layer `ST_Intersects`; REN-linear / Rede-Viária / Rede-Ferroviária buffered per the `buffer_m` / `buffer_ref` columns — see [[srup-constraint-model]]), land_use, terrain stats, nearby SCE developments (`ST_DWithin` 500m), nearby idealista plot listings (`ST_DWithin` 500m), assembled parcels (`ST_Intersects` against parcel_universe), nearby unified_developments.
  - Returns JSONB per the constraint-hit schema locked in [[srup-constraint-model]] + the wider shape in the [[UC-3]] page.
  - SQL comment block at function top documents the JSONB output shape.
- **GIST indexes (load-bearing for perf)**: ensure `parcel_universe.geom`, `silver_sce_buildings.geom`, `silver_plot_listings_enriched.geom`, `silver_unified_developments.geom`, `silver_geo.zoning.geom`, `silver_geo.land_use.geom` all have GIST indexes BEFORE the function is callable (the 16 `bronze_regulatory.raw_srup_*` geom columns the `stg_srup_*` views sit on are already GIST-indexed — verified in [[sprint-08]] Activity 6 PR 2). Confirm via `CREATE INDEX CONCURRENTLY` migrations.
- Tests #2-#6 from Appendix C (pgTAP): happy-path, invalid polygon, ocean/empty result, SRID transform, assembled parcels.

### Workstream 4 — Atlas Site Inspector (Streamlit-component, ~1 week, NET-NEW)

- `apps/pages/4_site_inspector.py` — Streamlit page with custom CSS for dark-chrome Atlas aesthetic.
- React component embedded via Streamlit-component (Streamlit-component supports React + Mapbox/Leaflet/deck.gl for the satellite-full-bleed background).
- Variant B-prime UX per `~/.gstack/projects/dacostalindo-House4House/designs/aveiro-parcel-assessment-inspect-20260506/approved.json`:
  - Dark chrome, full-bleed satellite basemap with CRUS zoning overlay at ~25% opacity.
  - Top-right address+GPS search input + LOCALIZAR button.
  - Floating Desenhar CTA (primary action) + Limpar (gray) + Analisar (blue primary) at bottom-center of map.
  - Drawn polygon rendered cyan with vertex handles.
  - Left dark panel: `DADOS DO LOCAL` structured key-value readout (8 sections).
- Layer toggle controls per Atlas pattern: hard gates (RAN/REN/áreas protegidas/defesa militar/DPH), floodplain (APA ARPSI), BUPI parcel grid.
- Frontend calls `SELECT gold.fn_assess_polygon(ST_GeomFromGeoJSON(...))` via psycopg2.
- **Delete** existing placeholders `apps/pages/4_parcel_explorer.py` + `apps/pages/5_site_analyzer.py` (replaced).
- Tests #19-#20 from Appendix C (Playwright E2E): happy-path draw-and-assess, invalid polygon error rendering.

### Deferred from Sprint-08 — national OGC bronze-loader fix (~1-2 days, NET-NEW)

`cos_ogc_bronze_load` and `crus_ogc_bronze_load` both **OOM at national scale** — `load_features` does an in-memory `json.load` of the whole GeoJSON (fine for the bbox smoke tests, fatal for the national ~784k-polygon COS and ~236k-polygon CRUS files; SIGKILL/-9). Verified 2026-05-14: national `cos_ogc_ingestion` succeeds (~1h48m) but the bronze load is killed; `crus_ogc_bronze_load` fails the same way. Until fixed, `bronze_geo.raw_cos_national_ogc` and `bronze_regulatory.raw_crus_national_ogc` stay empty and `silver_geo.land_use` reflects only the Aveiro smoke test (~4.5k rows). Deferred from [[sprint-08]] Activity 6 by user decision 2026-05-14.

- Rewrite the `load_features` task in `pipelines/gis/cos_ogc/cos_ogc_bronze_dag.py` + `pipelines/gis/crus_ogc/crus_ogc_bronze_dag.py` to stream/chunk the GeoJSON (e.g. `ijson` feature-streaming or batched `executemany` inserts) instead of `json.load`.
- Re-run both national bronze loads; verify `raw_cos_national_ogc` ≈ 784k rows and `raw_crus_national_ogc` ≈ 236k rows.
- Trigger `dbt_cos_build` + `dbt_crus_build`; verify `silver_geo.land_use` rebuilds to national scope.

### Deferred from Sprint-08 — freguesia-union mapping for SCE geocoding (~0.5-1 day, NET-NEW)

[[sprint-08]] Activity 7 shipped the `sce_geocode` cascade (Nominatim → freguesia-centroid → none) with **100% coverage on Aveiro concelho** but only **83.78% on Aveiro distrito**. The 16.2% gap is a CAOP-vs-SCE data drift: `gold_analytics.dim_geography` (CAOP 2025) carries pre-2013-reform separate freguesias (e.g. `Anta` 010707 + `Guetim` 010708), but the SCE portal uses post-2013-reform **union codes** (e.g. 010706 = "ANTA E GUETIM"). 19 union freguesias across Aveiro distrito → 9,047 SCE doc_numbers land at `geocode_source='none'` despite the bronze data being internally clean. v1 demo target (Aveiro concelho) is unaffected; national rollout needs this fixed.

- Source the official DGT freguesia-union mapping (DGT publishes a `freguesias_pre_pos_reform_2013.csv` or similar with the union→constituent code list).
- Create `bronze_enrichment.freguesia_union_map(union_dtmnfr, constituent_dtmnfr, constituent_name, weight)` — weight allows centroid-of-centroids when one union spans multiple pre-reform parishes.
- Extend the `sce_geocode_dag.py` cascade with a tier 2.5: when DTMNFR doesn't directly match `dim_geography`, look up via `freguesia_union_map` → take the average of constituent centroids (or the largest-weight one). `geocode_source='freguesia_union_centroid'`, `geocode_confidence=0.15`.
- Backfill the 9,047 existing 'none' rows via a targeted re-run (no need to re-call Nominatim — pure DB lookup).
- Verify distrito-wide coverage ≥95 %. Update [[sce]] coverage table.

Out of scope for this task: backporting the unions into `dim_geography` itself (that's a CAOP-version bump — separate work).

### Demo prep + execution (~3-5 days)

- 20-parcel spot-check on Aveiro: 5 hard-gate cases, 5 high-slope coastal, 5 urban centro, 5 rural periphery. Manual QGIS verification of `fn_assess_polygon` output per parcel.
- Cold load test: 20 random hand-drawn polygons across Aveiro (varying sizes — single-parcel, 5-parcel block, neighborhood-scale). P95 < 3s with both competitive-intel sections populated.
- **Demo dry-run** + actual demo with the 3 interviewed PT land developers per the [[2026-05-12-uc3-expanded-scope]] script. Demo script per the office-hours design doc.
- Interview notes saved to `~/.gstack/projects/dacostalindo-House4House/interviews/`.
- **Apply kill criteria** post-demo: wedge validated / killed / resized per the criteria in the [[2026-05-12-uc3-expanded-scope]] ADR.

## Exit criteria

- All 22 critical tests from Appendix C passing in CI.
- `gold.fn_assess_polygon` returns expected JSONB for 20 spot-check polygons.
- Atlas Site Inspector deployed and demo-able end-to-end within 3 second P95 for typical Aveiro polygons.
- LLM extraction eval-set accuracy ≥ thresholds (headline field at 85%).
- 3 PT land developer interviews COMPLETED. Notes saved. Kill-criteria applied. **The single binary post-sprint signal**: wedge validated, killed, or resized.

## Key decisions

- **Existing Sprint 9 scope** (Imovirtual scraper, RNAL, INE Building Permits, REN, hedonic v2 retrain, ARU, CI data integration, data-quality monitoring, documentation) **moved to [[sprint-10]]** — split across Track A (project hardening + portal expansion, always ships) and Track B (UC-3 v2 readiness, gated on this sprint's wedge-validation outcome). Per [[2026-05-12-uc3-expanded-scope]], these items now belong to v2 (hedonic v2 + ARU + REN + building permits as economics enablers) or v1.5 (Imovirtual + RNAL as portal expansion). NOT load-bearing for the v1 wedge demo.
- **SCE geocoding pulled forward** from this sprint (where it was deferred) into [[sprint-08]] as WS4 Slice B Step 1.
- **Cross-portal dedup** (originally part of Sprint 9 as `hash(address + area + typology)`) is partially superseded by Slice B-prime `silver_unified_developments` which deduplicates at the DEVELOPMENT level, not the portal-listing level. The original cross-portal dedup at the listing level remains a v1.5+ concern.
- **Demo-grade error handling** posture per /plan-eng-review D5: fail-fast at boundaries. Production-grade hardening is v2.
- **Idealista-only LLM extraction** per /plan-eng-review D1; jll/remax/zome plot extraction lands in v1.5.
- **No standalone web app** in v1 per /plan-eng-review D2; Streamlit-component is sufficient for the demo audience. Web app is v2 work post-interview.

## Tests added (per /plan-eng-review Appendix C)

All 22 critical tests integrated into CI/CD. Tests landing in Sprint 9 (the remainder from [[sprint-08]]):

- **#2-6 (pgTAP)**: `fn_assess_polygon` happy / invalid / empty / SRID transform / assembled parcels
- **#16-18 (LLM extraction)**: per-field accuracy on eval set, idempotency, derived-validity flag
- **#19-20 (Playwright E2E)**: Atlas Inspector happy-path, invalid-polygon error
- **#21-22 (dev dedup)**: proximity-only match, name-ambiguous case

## Status update history

- 2026-04-18: original "Enhancements + Production Hardening" declared in README §12; status `planned`
- 2026-05-12: restructured to "UC-3 v1 wedge Part 2 (Wedge Completion + Atlas Inspector + Demo)" per [[2026-05-12-uc3-expanded-scope]]. Existing scope (Imovirtual / RNAL / hedonic v2 / ARU / etc.) deferred to future v1.5+ sprint, gated on wedge validation. Weeks extended from 19-20 → 19-21. Status `planned`.
- 2026-05-14: added "Deferred from Sprint-08 — national OGC bronze-loader fix" deliverable (`cos_ogc` + `crus_ogc` `load_features` OOM on whole-GeoJSON `json.load`). `fn_assess_polygon` deliverable updated to the as-built constraint model — queries the 14 `stg_srup_*` layers + `dim_constraint_severity` (not the dropped `parcel_constraints` pre-compute). Status `planned`.
- 2026-05-15: added "Deferred from Sprint-08 — freguesia-union mapping" deliverable. Activity 7's `sce_geocode` cascade hit 83.78 % coverage on Aveiro distrito (vs ≥90 % target) due to pre-2013-reform freguesia codes in CAOP 2025 vs post-2013 union codes in the SCE portal. Aveiro concelho (v1 demo target) is at 100 %; only national rollout is affected. Status `planned`.
- 2026-05-17: Slice B SHIPPED. `silver_sce_buildings` body-fill landed with 12,634 buildings (1,166 Aveiro concelho), 4 pgTAP tests pass. Material design deltas vs original spec: no Levenshtein (Decision 2 — 0% empirical leakage), no parcel_id/cluster_split (Option B — 97.7% Nominatim-vs-cadastre semantics gap), no Splink (Decision 4). Tier-1 CI bootstrap landed alongside; Tier-2 deferred. New concept page [[sce-buildings-clustering]]. Slice B audit surfaced one immediate follow-up (clamp `geocode_confidence` to [0,1] in the Activity-7 geocoder) and triggered separate planning PRs for sprint-09 backlog (SCE bronze refactor + Slice B-prime expansion) and sprint-10 backlog (Tier-2 CI + CI/CD hardening workstream). Sprint status `planned` → `in_progress`.

## See also

- [[2026-05-12-uc3-expanded-scope]] — the ADR driving this sprint's reshape
- [[UC-3]] — use case page (also reframed 2026-05-12)
- [[sprint-08]] — predecessor sprint (v1 wedge Part 1: Foundations)
- [[idealista]] — load-bearing for Slice C (LLM extraction, idealista-only in v1)
- [[sce]] — load-bearing for Slice B (Aveiro distrito scope)
- [[bupi]], [[cadastro]], [[crus]], [[srup]], [[cos]], [[lidar]] — spatial backbone (unchanged)
- [[medallion-layering]], [[bronze-permissive]] — concepts applied
- Office-hours design doc: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-design-20260512-151500.md`
- /plan-eng-review test plan: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-eng-review-test-plan-20260512-155850.md`
- Variant B-prime UI mockup: `~/.gstack/projects/dacostalindo-House4House/designs/aveiro-parcel-assessment-inspect-20260506/approved.json`

## 🏁 Milestone

**Milestone 3 (Week 21): UC-3 v1 wedge LIVE.** Atlas Site Inspector deployed. 3 PT developer interviews done. Wedge validated / killed / resized per kill criteria. If validated, v2 planning begins (Stages 5-6 economics + national rollout + Approach A promoter slice). If killed, the [[2026-05-12-uc3-expanded-scope]] ADR gets `superseded_by:` and the wiki rewrites stand as historical record.
