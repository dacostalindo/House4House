---
title: Sprint 9 — UC-3 v1 wedge Part 2 (Wedge Completion + Atlas Inspector + Demo)
type: plan
last_verified: 2026-06-03
tags: [sprint, plan, uc-3, wedge, completion, llm-extraction, dev-dedup, cross-portal, atlas-inspector, demo, weeks-19-21]
status: in_progress
sprint_number: "9"
weeks: "19-21"
last_status_update: 2026-06-03
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

- **[[remax]] `PaginatedSearch` coverage gap**: Slice B-prime PR-C verification found `remax_developments` is missing developments that still have live RE/MAX detail pages — e.g. "Edifício Elsa" (`remax.pt/en/empreendimento/edificio-elsa/7481`) has a working page but `development_id` 7481 is absent from `bronze_listings.remax_developments` entirely (any SCD2 version), so it never reaches `silver_unified_developments`. Hypothesis: the `POST /api/Development/PaginatedSearch` discovery feed only returns developments with active online listings — sold-out developments keep a detail page but drop out of the scrape. Investigate `pipelines/portals/remax/source.py`: confirm whether PaginatedSearch is the sole discovery path and whether a sitemap or detail-page sweep is needed to capture sold-out developments. Affects cross-portal dedup completeness.

### Workstream 4 Slice C — LLM Construction-Area Extraction (idealista only, ~1-1.5 weeks, NET-NEW)

- **LLM eval-set construction spike** (1-2 days): hand-label ~50 idealista plot listings with construction-area-allowed extracted. Second-pass self-consistency check on 10 of them 1+ week later. Eval set at `tests/fixtures/plot_listings_eval.jsonl`. Per Appendix B of the design doc.
- `dbt/models/staging/portals/stg_plot_listings.sql` — filter [[idealista]] listings to `tipologia ∈ ('terreno', 'lote')` OR regex fallback (`\b(terreno|lote|prédio para construção)\b`). Mark `tipologia_source: structured|regex` for traceability.
- Pydantic schema `PlotListingExtraction(construction_area_m2_allowed, construction_index, parcel_area_m2, max_height_m, source_spans)` — **`construction_index` and `construction_area_m2_allowed` are SEPARATE fields** to avoid the confound where the LLM conflates `index × area` into the area field.
- `pipelines/enrichment/plot_listing_extraction_dag.py` — Pydantic-AI on **Claude Haiku 4.5** (cheapest reliable for PT prose) with structured outputs. Writes to **`bronze_enrichment.raw_plot_listing_extractions`** per [[bronze-permissive]]. Idempotent on `hash(listing_url + description_text)` — portal-side description edit triggers re-extraction.
- `dbt/models/silver/portals/silver_plot_listings_enriched.sql` — join `stg_plot_listings` + `bronze_enrichment.raw_plot_listing_extractions` → typed silver. Derived-validity dbt model: flag rows where `index × parcel_area` differs from extracted GBA by > 10%.
- Tests #16-#18 from Appendix C: per-field accuracy meets thresholds (85% on headline `construction_area_m2_allowed`), idempotency on listing hash, derived-validity flag correctness.
- **LLM eval-set CI gate**: any field below threshold blocks the prompt change. Runs on every Pydantic-AI prompt revision + model version pin bump.
- **Cost**: ~$40 one-time backfill for ~10K listings, ~$0.004 per new listing thereafter. With idealista-only scope, closer to ~$10-20 for ~2-3K plot listings.

### Workstream 4 Slice B-prime — Cross-portal Development Dedup (~7-9 days, EXPANDED 2026-05-17)

**Originally scoped at 1 day** (SCE buildings ↔ idealista plots only). **Expanded 2026-05-17** to 4-portal cross-portal dedup at the development grain per user decision. Replaces the previous narrow Slice B-prime in full. Load delta: +6-8 days net-new on sprint-09; see Status update history.

**Goal**: produce one canonical row per real-world development across the 4 listing portals + SCE buildings, so that `fn_assess_polygon` and the Atlas Inspector show consolidated counts ("this neighbourhood has 5 distinct developments, listed across 12 portal pages") rather than raw portal-page lists.

**Empirical inputs** (audited 2026-05-17 via warehouse):

| Portal | Total devs | Aveiro devs | Project-name field | Geocoord at dev level |
|---|---|---|---|---|
| [[idealista]] | 2,005 | ~13 | ❌ `name` = address itself | ❌ derive via JOIN to units |
| [[jll]] | 215 | **0** (Lisboa/Porto/Faro/Setúbal only) | ✓ `name` + `title` | ✓ `gps_lat`, `gps_lon` |
| [[remax]] | 1,289 | ~10 | ✓ `name` (project names like "Barroka", "Domus Ria") | ✓ `latitude`, `longitude` |
| [[zome]] | 352 | 3 | ✓ `nome` | ⚠️ `geocoordinateslat` (varchar — cast in staging) |

Scale: ~26 developments in Aveiro across the 4 portals. **Probabilistic record linkage (Splink) is huge overkill at this scale** — simple spatial-DBSCAN + fuzzystrmatch.levenshtein on normalized project name suffices. Splink stays parked for v1.5+ if national rollout exposes the deterministic limits.

**Sub-deliverable 1 — Extend [[portal-field-map]] to include JLL (~0.5 day)**

[[portal-field-map]] currently documents idealista + remax + zome at field grain. JLL is missing. Sub-deliverable: extend the correspondence matrix to include JLL's 62 columns at development + listing grain. Flag JLL's Lisboa/Porto/Faro/Setúbal-only geographic coverage explicitly — relevant for sprint-10 portal expansion but zero v1-wedge demo value. Output: 4-portal field correspondence matrix instead of 3-portal.

**Sub-deliverable 2 — Canonical per-portal staging models (~1-1.5 days × 4 = 4-6 days)**

Four new `dbt/models/staging/portals/stg_portal_developments_<portal>.sql` models with consistent schema across portals:

```
portal              text           -- 'idealista' | 'jll' | 'remax' | 'zome'
portal_dev_id       text           -- cast to varchar; idealista is already varchar
canonical_name      text           -- project name where exposed; fallback to address_text
address_text        text           -- raw address string for downstream fuzzy match
city                text           -- mode'd to UPPER+TRIM concelho
parish              text           -- freguesia
postal_code         text           -- NNNN-NNN PT format
geom_3763           geometry       -- for spatial joins
geom_4326           geometry       -- for display
total_units         integer        -- where exposed
listing_url         text           -- for human-link from Inspector
raw_meta            jsonb          -- escape hatch for fields not in the canonical schema
_loaded_at          timestamptz
```

Portal-specific concerns surfaced in audit:
- **idealista** has no dev-level geom. Derive via `(SELECT AVG(lat), AVG(lng) FROM idealista_development_units WHERE development_id = ...)`. Where no units geocoded, set to NULL.
- **idealista** `name` IS the address — sets `canonical_name = NULL` and lets sub-deliverable 3 fall back to spatial-only matching for idealista.
- **zome** stores geocoords as varchar — `::numeric` cast in staging.
- **JLL** carries dev-level geom directly but every Aveiro row will be empty (no JLL Aveiro coverage). The staging model SHOULD work; it just won't contribute to Aveiro silver_unified_developments rows.

**Sub-deliverable 3 — silver_unified_developments (~1-2 days)**

`dbt/models/silver/regulatory/silver_unified_developments.sql`. Reads from the 4 canonical staging models + `silver_sce_buildings`. Pipeline:

1. UNION ALL the 4 portal staging models + cast silver_sce_buildings rows into the same shape (`portal='sce'`, `portal_dev_id=sce_building_id::text`, `canonical_name=parish || ' ' || normalized_address`, `geom_3763=cluster_geom_3763`, ...).
2. `ST_ClusterDBSCAN(geom_3763, eps := 50, minpoints := 1) OVER ()` — eps wider than Slice B's 30m because portal listings + SCE points can disagree by 30-50m on the same building.
3. Within each cluster, secondary match via fuzzystrmatch.levenshtein on `canonical_name` where both sides have it. Idealista rows with NULL canonical_name match purely on spatial proximity.
4. Output one row per cluster with `portal_refs` JSONB: `{"idealista": [...ids], "jll": [...], "remax": [...], "zome": [...], "sce": [...sce_building_ids]}`. Plus `member_count`, `unified_geom_3763` (cluster centroid), and `match_confidence` (1.0 if name-matched, 0.5 if spatial-only).
5. `materialized='table'` + GIST index on `unified_geom_3763` (for fn_assess_polygon's `ST_DWithin` query).

**Sub-deliverable 4 — Tests + concept page + wiki updates (~0.5-1 day)**

- 4 pgTAP tests at `tests/sql/silver_unified_developments_*.sql`:
  - DBSCAN(50m) collapses 2 portal-listings 30m apart with similar names → one unified row.
  - DBSCAN spread: a single development with 5 portal-listings + 1 SCE building all within 50m → one unified row, `portal_refs` contains all 6.
  - Name dissimilarity within a cluster keeps developments separate (e.g. two adjacent buildings with distinct project names).
  - JLL row in Lisboa doesn't merge with Aveiro rows (sanity check on the spatial filter).
- New concept page `wiki/concepts/cross-portal-dev-dedup.md` documenting design decisions (4-portal scope, 50m eps, name + spatial hybrid, Splink deferred to v1.5).
- Extend [[portal-field-map]] with the 4-portal extension (sub-deliverable 1).
- Update [[idealista]], [[jll]], [[remax]], [[zome]] source pages with cross-link to the new concept page.
- `tests/ci_bootstrap/bronze_portals.sql` — empty stubs for the 4 portal bronze tables (continues the per-source-family pattern from sprint-09 Slice B).

**Verification**:

- `dbt build --select +silver_unified_developments` against the warehouse — green, row count between 26 (perfect dedup of Aveiro) and ~30 (some over-fragmentation acceptable).
- Manual spot-check: known cross-portal development pairs (e.g. "Domus Ria" on RE/MAX + the same building on idealista if listed) end up in the SAME row.
- `portal_refs` JSONB integrity: every row has at least 1 portal contributor; `member_count` matches the JSONB array sum.

**Implementation split — 3 PRs** (locked 2026-05-18):

The 4 sub-deliverables map to 3 PRs landed in sequence. Each PR is independently reviewable and mergeable; PR-A has no code dependencies, PR-B + PR-C share a per-portal staging dependency.

**PR-A — Foundation: extend [[portal-field-map]] with JLL** (~0.5d, wiki-only)

Scope: sub-deliverable 1. The [[portal-field-map]] concept page currently documents idealista + RE/MAX + Zome at field grain. Add JLL's 62 columns (development + listing grain) to the correspondence matrix. Flag JLL's Lisboa/Porto/Faro/Setúbal-only geographic coverage explicitly.

Files: `wiki/concepts/portal-field-map.md` (extend matrix). Bump `last_verified`. Update [[index]] concept entry summary.

Test plan: wiki-only PR — CI green; [[wikilinks]] resolve.

**PR-B — Canonical per-portal staging models + CI bronze stubs** (~4-6d)

Scope: sub-deliverable 2. Build the 4 `stg_portal_developments_<portal>.sql` models that expose the canonical 13-column schema. Add dbt sources for RE/MAX, Zome, JLL (idealista already has a source). Add CI bronze stubs so `dbt build` validates structurally.

Files NEW:
- `dbt/models/staging/portals/stg_portal_developments_idealista.sql` (regexp_match on `title` for canonical_name; AVG(lat,lng) over units for geom)
- `dbt/models/staging/portals/stg_portal_developments_remax.sql` (template — RE/MAX has cleanest fields; document parish-centroid coord caveat in YAML)
- `dbt/models/staging/portals/stg_portal_developments_zome.sql` (`::numeric` cast on varchar coords)
- `dbt/models/staging/portals/stg_portal_developments_jll.sql` (greenfield — also adds JLL dbt source first)
- `dbt/models/staging/portals/_staging_portals__sources.yml` (4 portal bronze sources, idealista already exists in `staging/listings/` and stays there)
- `dbt/models/staging/portals/_staging_portals__models.yml` (column docs + `not_null` / `accepted_values` tests + cross-reference to [[portal-field-map]])
- `tests/ci_bootstrap/bronze_portals.sql` (empty stubs for 4 portal bronze tables, continues per-source-family pattern from sprint-09 Slice B PR #31)

Test plan: per-portal `dbt parse` green; `dbt build --select stg_portal_developments_*` against the local warehouse — row counts match bronze; spot-check on idealista title-regex extraction (expect 100% on Aveiro); spot-check on Zome varchar→numeric cast; verify RE/MAX 51% NULL coord rate (documented expected).

Recommended landing order within PR-B (split into 2 commits if reviewer prefers): RE/MAX template first, then Zome + Idealista + JLL in one batch.

**PR-C — silver_unified_developments + tests + concept page + final wiki** (~1.5-3d)

Scope: sub-deliverables 3 + 4. Build the silver model, the 4 pgTAP tests, the new concept page, and broaden CI dbt build selector.

Files NEW:
- `dbt/models/silver/regulatory/silver_unified_developments.sql` (DBSCAN + name-similarity connected-components + portal_refs JSONB)
- `tests/sql/silver_unified_developments_cluster_collapse.sql` (Test #21)
- `tests/sql/silver_unified_developments_multi_portal_match.sql` (Test #22)
- `tests/sql/silver_unified_developments_name_split.sql` (Test #23 — RE/MAX 4-distinct-devs-at-same-coord scenario)
- `tests/sql/silver_unified_developments_spatial_filter.sql` (Test #24)
- `wiki/concepts/cross-portal-dev-dedup.md` (locks Decisions 1-8: dev-grain, DBSCAN+Levenshtein, 4-portal scope, 50m eps, idealista title-regex, portal_refs JSONB, sub-deliverable order, name_similarity v1 load-bearing)

Files MODIFIED:
- `dbt/models/silver/regulatory/_silver_regulatory__models.yml` (append silver_unified_developments entry)
- `wiki/sources/idealista.md`, `wiki/sources/jll.md`, `wiki/sources/remax.md`, `wiki/sources/zome.md` (cross-link to new concept; bump `last_verified`)
- `wiki/sprints/sprint-09.md` (flip Slice B-prime status DONE; add 2026-05-18 status-history entry)
- `wiki/index.md` (register new concept under Concepts + dbt/ area-of-code routing)
- `wiki/log.md` (append ship entry)
- `.github/workflows/ci.yml` (broaden dbt build selector: `+silver_sce_buildings` → `+silver_unified_developments` since the new model transitively builds Slice B too)

Test plan: `dbt build --select +silver_unified_developments` green (Aveiro: 26-30 rows); 4 pgTAP green locally + in CI; concrete cross-portal pair "Alpha View" (idealista) ↔ "ALPHA VIEW" (Zome) merges into one unified row; RE/MAX 4-distinct-devs-at-shared-coord scenario produces 4 unified rows (not 1) via the name_similarity split.

**Dependencies**: PR-A is independent. PR-B can ship after or alongside PR-A (no code dependency on the wiki update). PR-C depends on PR-B (the silver model imports the 4 staging models). Recommended merge order: A → B → C.

**Out of scope** (defer to sprint-10 or later):
- Splink / probabilistic linkage — overkill at Aveiro scale; revisit when national rollout exposes deterministic limits.
- LISTING-level cross-portal dedup (the `hash(address + area + typology)` pattern in sprint-10 Track A). This Slice B-prime is DEVELOPMENT-level; listing-level is a different problem.
- Cross-portal listing↔SCE-fração linkage (one portal listing maps to multiple SCE certificates within one building). v1.5 work.

### Workstream 4 — `fn_assess_polygon` input data gaps (~5-6 days total, NET-NEW, audited 2026-05-22; quick-wins batch SHIPPED 2026-06-02)

Construction-suitability inputs the `fn_assess_polygon` function depends on but which lack silver models today. The 2026-05-22 audit found bronze freshness is *not* the problem — most static-reference bronze (CAOP, OSM, BGRI, BUPI, Cadastro, COS, legacy SRUP) is correctly loaded once and refreshed on annual cycles. The gaps are downstream of those: staging/silver models not yet built, plus two stalled OGC migrations and one empty pipeline scaffold. Build order is by construction-suitability impact, not by effort.

- **APA floods → silver** ✅ **DONE 2026-06-02 (quick-wins batch)**: `bronze_hydrology.raw_apa_arpsi_floodplain` loaded (188 rows). Shipped as sibling `silver_geo.floodplains` (NOT folded into zoning) + extended `dim_constraint_severity` with `ARPSI_Floodplain` (T100=3 hard, T1000=2 conditioned, new `flood_risk` category). 15th regulatory layer alongside the 14 SRUP siblings — see [[srup-constraint-model]]. Tests per [[silver-dq-baseline]].
- **LiDAR terrain → silver** ✅ **DONE 2026-06-03 (sprint-09 WS4 PR A)**: Live discovery showed the sprint-09 "bronze empty / pipeline never run" claim was wrong — bronze had 489×3 manifests + 10,339 parcel stats. Original parcel-proxy plan rejected (BUPI coverage gaps + sub-parcel imprecision). Shipped **Option C — in-DB postgis_raster** instead: `bronze_terrain.raster_lidar_slope_2m` holds 489 slope rasters loaded via Python `ST_FromGDALRaster(bytea, 3763)` (raster2pgsql not in airflow image; same end result). `silver_geo.terrain_slope_raster` is a thin view adding GIST-indexed convex-hull footprints for fast `ST_Intersects` pre-filter. `fn_assess_polygon` does `ST_Clip(rast, drawn_polygon) + ST_SummaryStatsAgg` inline for exact-per-polygon slope stats. **Cleanup**: dropped `parcel_zonal_stats_dag.py` + `bronze_terrain.parcel_terrain_stats` + `derived_lidar_slope_2m_manifest` (all redundant under Option C). See [[lidar]].
- **LNEG aquifers + geology → silver** ✅ **DONE 2026-06-02 (quick-wins batch)**: two siblings — `silver_geo.aquifers` (63 rows) + `silver_geo.geology` (282 rows). Raw bronze fields exposed only — `aquifer_vulnerability` and `foundation_difficulty` derived columns DROPPED from v1 after web-research pass on PT regulations (DRASTIC requires inputs not in bronze; Eurocode 7 requires site-specific testing; Aveiro Cretaceous "Argilas de Aveiro" formation contradicted the proposed era-prefix CASE per Galhano & Rocha). See [[lneg]].
- **Aveiro PMOT → bronze + silver** (~2-3d, NOT DONE): no bronze visible — the [[aveiro-pmot]] WMS-GFI extractor is described as one-off (~1,669 feature types). Run the extractor, land in bronze, then staging + silver. Local PMOT plans matter for the Aveiro v1 wedge — they're the municipal layer below SRUP/CRUS.
- **INE indicators → silver** ✅ **DONE 2026-06-02 (quick-wins batch)**: `silver_market.ine_indicators_long` exposes 33 active indicators at parish/concelho/NUTS granularity. Distinct from `silver_market.macro_timeseries` (national rates/HPI) — see [[silver-dq-baseline]] §"Statistical-source silver topology". Bronze schema migration: added `indicator_category` column written by bronze loader from `INE_INDICATORS[code].category` (single source of truth in `ine_config.py`). See [[ine]].

**Also surfaced by the 2026-05-22 audit** — two empty OGC-migration bronze tables not powering anything: `bronze_geo.raw_cos_national_ogc` and `bronze_regulatory.raw_crus_national_ogc`. Legacy COS / CRUS are powering silver correctly, so the migrations aren't urgent. Decide per source: finish migrating (re-run loaders) or drop the empty shells to stop the noise.

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

### Deferred from Sprint-08 — national OGC bronze-loader fix (~1-2 days, DONE 2026-06-03)

**Shipped** (WS4 batch 2 PR B): replaced `json.load` with `ijson.items(f, "features.item", use_float=True)` streaming in both `cos_ogc_bronze_dag.py` + `crus_ogc_bronze_dag.py`. National COS bronze loaded in ~7 min (842,413 rows, +7.5% vs. legacy 783,760); national CRUS in ~3 min (236,920 rows, 0% delta vs. legacy 5-muni subset). `silver_geo.land_use` rebuilt to 842,413; `silver_geo.zoning` rebuilt to 236,920. Legacy `bronze_geo.raw_cos2023` + `bronze_regulatory.raw_crus_ordenamento` + stale `staging_dbt.stg_pdm_ordenamento` view dropped (parity verified before drop). `use_float=True` is required to avoid ijson's Decimal returns breaking `json.dumps(geom)`. `ijson` added to `pipelines/pyproject.toml`; Airflow image rebuilt. 2 stale dbt YAML descriptions fixed (`_staging_geo__models.yml`, `_staging_regulatory__models.yml`).

### Deferred from Sprint-08 — freguesia-union mapping for SCE geocoding (~0.5-1 day, NET-NEW)

[[sprint-08]] Activity 7 shipped the `sce_geocode` cascade (Nominatim → freguesia-centroid → none) with **100% coverage on Aveiro concelho** but only **83.78% on Aveiro distrito**. The 16.2% gap is a CAOP-vs-SCE data drift: `gold_analytics.dim_geography` (CAOP 2025) carries pre-2013-reform separate freguesias (e.g. `Anta` 010707 + `Guetim` 010708), but the SCE portal uses post-2013-reform **union codes** (e.g. 010706 = "ANTA E GUETIM"). 19 union freguesias across Aveiro distrito → 9,047 SCE doc_numbers land at `geocode_source='none'` despite the bronze data being internally clean. v1 demo target (Aveiro concelho) is unaffected; national rollout needs this fixed.

- Source the official DGT freguesia-union mapping (DGT publishes a `freguesias_pre_pos_reform_2013.csv` or similar with the union→constituent code list).
- Create `bronze_enrichment.freguesia_union_map(union_dtmnfr, constituent_dtmnfr, constituent_name, weight)` — weight allows centroid-of-centroids when one union spans multiple pre-reform parishes.
- Extend the `sce_geocode_dag.py` cascade with a tier 2.5: when DTMNFR doesn't directly match `dim_geography`, look up via `freguesia_union_map` → take the average of constituent centroids (or the largest-weight one). `geocode_source='freguesia_union_centroid'`, `geocode_confidence=0.15`.
- Backfill the 9,047 existing 'none' rows via a targeted re-run (no need to re-call Nominatim — pure DB lookup).
- Verify distrito-wide coverage ≥95 %. Update [[sce]] coverage table.

Out of scope for this task: backporting the unions into `dim_geography` itself (that's a CAOP-version bump — separate work).

### SCE bronze refactor — replace-not-append (~1 day, NET-NEW 2026-05-17)

Slice B's verification audit surfaced that `bronze_regulatory.raw_sce_certificates` keeps full scrape history (current `(doc_number, _batch_id)` UNIQUE), producing ~3× row inflation (279k bronze rows for ~55-60k distinct certificates). The SCE portal preserves state transitions itself — our scrape-history is redundant. Refactor bronze to UPSERT-by-doc_number so bronze always reflects "current portal state."

- Schema: drop `(doc_number, _batch_id)` UNIQUE; add `PRIMARY KEY (doc_number)` and `_last_seen_at TIMESTAMPTZ` ([[heartbeat-sidecar]] pattern, inlined). `_batch_id` stays as a trace column (last-writer), not part of the PK.
- One-off SQL migration: dedup existing rows down to one-per-`doc_number` (latest `_scrape_date`); ~279k → ~55-60k. Backup to `bronze_regulatory.raw_sce_certificates_pre_2026_05_dedup` before applying.
- Loader: rewrite [pipelines/scraping/sce/sce_bronze_load_dag.py](pipelines/scraping/sce/sce_bronze_load_dag.py) INSERT → `INSERT ... ON CONFLICT (doc_number) DO UPDATE SET ..., _last_seen_at = NOW()`. Tombstone behavior for certificates that disappear from the portal: do nothing — `_last_seen_at` going stale is the signal. Silver/Gold can filter on `_last_seen_at > NOW() - INTERVAL '90 days'` if "still in registry" matters (revisit when interviews surface the need).
- Drop the `DISTINCT ON (doc_number)` dedup in [dbt/models/staging/regulatory/stg_sce_certificates.sql](dbt/models/staging/regulatory/stg_sce_certificates.sql) — bronze now guarantees uniqueness.
- Wiki: update [[sce]] Schema + Quirks sections ("every run re-scrapes the full active-certificate set within scope. Dedup happens on the UNIQUE constraint at insert time" → "Bronze upserts by doc_number; latest scrape wins. `_last_seen_at` tracks freshness.") Cross-link [[bronze-permissive]] (SCE bronze becomes a documented exception to the never-delete invariant: we *update* rows, never historical-version them).
- Verification: re-scrape Aveiro distrito post-deploy. Confirm bronze row count ~= distinct `doc_number` count. Confirm `_last_seen_at` populated. Re-build `silver_sce_buildings` — `frac_count` totals unchanged (the staging dedup was already doing this work).

Side-benefit: silver_sce_buildings rebuild gets faster (no DISTINCT ON in staging), ad-hoc debug/audit queries against bronze stop needing to dedup. The pattern generalizes — once validated on SCE, the same refactor applies to other re-scrape bronze sources ([[idealista]], [[jll]], [[remax]], [[zome]], [[bupi]]) in a future sprint.

Out of scope: changing CDC capture (the SCE portal doesn't expose deltas; we'd still do full-scope re-scrapes — just landing them as UPSERTs).

### Clean re-scrape of JLL + RE/MAX + Zome portals (~1 day, NET-NEW 2026-05-19)

PR-B1 audit surfaced a **dlt SCD2 close-row miss** across multiple portal bronze tables — small percentages of PKs end up with 2 "active" SCD2 versions (`_dlt_valid_to IS NULL` set twice). Empirical rates measured 2026-05-19:

| Bronze table | Dupe PKs / total active | Rate |
|---|---|---|
| `remax_listings` | 55 / 8,266 | 0.67% |
| `remax_developments` | 2 / 603 | 0.33% |
| `remax_plots` | 6 / 12,440 | 0.05% |
| `jll_listings` | 15 / 7,502 | 0.20% |
| `zome_listings` | 2 / 9,143 | 0.02% |

The dlt SCD2 config is correct (`strategy=scd2`, `primary_key=<pk>`); the bug is dlt 1.x's close-row UPDATE occasionally missing on the previous version's row_hash when a new version is inserted. **Fresh re-scrapes after TRUNCATE produce zero dupes** — verified on idealista 2026-05-18 (0 of 85 dev rows; 0 of 444 unit rows; 0 of 1,000 plot rows).

Tactical fix: TRUNCATE + clean re-scrape for the affected portals, following the same pattern used for idealista 2026-05-18.

- TRUNCATE the 6 SCD2 facts tables: `bronze_listings.{jll_developments,jll_listings,remax_developments,remax_developments_state,remax_listings,remax_listings_state,remax_plots,remax_plots__listing_rooms,zome_developments,zome_developments_state,zome_listings,zome_listings_state,zome_plots,zome_plots_state}`. Plus their `_dlt_pipeline_state` rows for `jll_facts`, `remax_facts`, `zome_facts`.
- Trigger 3 Airflow DAGs: `jll_developments_dlt`, `remax_developments_dlt`, `zome_developments_dlt` (verify the actual DAG IDs against `airflow dags list`).
- Each scope-narrowed if practical (e.g. `target_areas_override` Param for the dlt DAGs, following the idealista precedent). For JLL: full-scope (~215 devs) since no Aveiro-only narrowing useful. For RE/MAX + Zome: consider Aveiro-only via the Param if the DAG supports it.
- Verify post-scrape: re-run the dupe-PK SQL audit, expect 0 dupes per table.

Estimated cost: minimal — these are dlt-driven REST/JSON pipelines (not ZenRows-heavy like idealista). Each portal scrape is a few minutes against the respective upstream APIs.

Side-benefit: PR-C's `silver_unified_developments` gets clean inputs across all 4 portals; the defensive `DISTINCT ON (development_id)` guards in PR-B1/2/3/4 staging models still work but become belt-and-suspenders rather than load-bearing.

Out of scope: investigating the dlt SCD2 close-row bug at the framework level (deeper dlt internals work; better as a sprint-10 portal data-quality investigation, OR upgrading dlt to a version that fixes this). The clean re-scrape is the v1 unblock.

### Workstream 5 — Portal bronze column trim (4-portal × 3-grain audit, ~6-10 days, NET-NEW 2026-06-02)

Sprint-09 verification work has repeatedly surfaced bronze columns that aren't consumed anywhere downstream while genuinely useful structured fields stay buried (e.g. [[idealista]]'s `property_features` JSONB carries "Superfície edificável 82.592 m²" for plot 34632291 but the LLM-extraction labeling fixture at [`pipelines/enrichment/plot_listing_extraction/sample_eval_set.py:134-135`](../../pipelines/enrichment/plot_listing_extraction/sample_eval_set.py#L134-L135) reads only `description`, `lot_size`, `property_price` — the field never reaches the labeler or the LLM prompt). The "every column, raw" posture from [[bronze-permissive]] is leaking complexity into staging, eval fixtures, the LLM-extraction prompt, the colleague-review tooling, and the Atlas Inspector readouts. **Decision** (locked in sub-deliverable 1 below): revise [[bronze-permissive]] from *"keep every column the source returns"* to *"keep an explicit, audited kept-set + one `raw_payload` JSONB sidecar that preserves the unparsed source row."* Per-portal audit picks the kept set; dropped columns leave the bronze DDL + dlt resource. Audit trail moves into `raw_payload`, so the three reasons the original policy cites (upstream regression capture, decoupling from moving targets, "what did the source say on date X?") are all still satisfied.

This stream is **orthogonal to the v1-wedge demo critical path** (`fn_assess_polygon` + Atlas Inspector). It's labelled Workstream 5 to signal that — load impact is real (sprint-09 was already running ~4-5 weeks of work in 3 weeks per the 2026-05-17 status-history entry; +6-10 days on top likely slips past Week 21). May land partially in sprint-09 and finish in sprint-10; that's accepted at planning time.

**Sub-deliverable 1 — Policy ADR + [[bronze-permissive]] rewrite (~0.5 day)**

New `wiki/decisions/2026-06-02-bronze-trim-revises-bronze-permissive.md`. Locks the revised rule:
- Bronze keeps an explicit kept-column set + one `raw_payload` JSONB column carrying the unparsed dlt source row, for upstream-regression audit and field-recovery without re-scrape.
- Schema contract stays `data_type=freeze, columns=evolve` for the kept columns; `raw_payload` absorbs everything else (so new upstream fields still land, just inside the JSONB).
- The never-delete-from-bronze invariant remains for SCD2 row-versions; the column SCHEMA can be tightened in subsequent migrations as long as the prior payload survives in `raw_payload` or the dropped column was provably empty across all SCD2 versions.

Rewrite [[bronze-permissive]] to point at the ADR + state the revised rule. Cross-link [[scd2-row-hash]] (row-hash inputs change when bronze schema tightens — every per-portal PR rebuilds row_hash and thus closes all current SCD2 versions; document the migration shape). Cross-link [[pydantic-not-in-dlt]] (still no Pydantic on incoming rows; the kept-set is enforced via the dlt resource's column list, not a model).

**Sub-deliverables 2-5 — Per-portal bronze trim (~1.5-2 days × 4 = 6-8 days; one PR per portal)**

Each PR walks the same 6-step ritual:
1. Inventory current bronze columns at each grain (developments / listings / plots — skip the grain if the portal doesn't have it).
2. Cross-check against actual downstream consumers: `dbt/models/staging/portals/stg_portal_*.sql`, `dbt/models/silver/**/*.sql`, the LLM extraction fixture, the `fn_assess_polygon` SELECT list, the Atlas Inspector readouts, the Streamlit pages.
3. Pick the kept set + the dropped set. A dropped column needs evidence: zero downstream consumers AND (provably empty across SCD2 history OR the value lives in `raw_payload` post-trim).
4. Update the dlt resource ([`pipelines/portals/<portal>/source.py`](../../pipelines/portals/)) to emit only the kept columns + `raw_payload`. Update the bronze DDL (`<portal>_bronze_dag.py` or the SCD2 dlt config) to drop the columns. Recompute the row_hash input set.
5. SCD2 migration: backup `bronze_<schema>.<table>` → `<table>_pre_trim_2026_06`; recreate; replay from `raw_payload` where possible, OR clean re-scrape (cheap for dlt-driven JSON portals, expensive for ZenRows-heavy [[idealista]] — decide per portal).
6. Per-PR wiki updates: flip dropped columns to "(trimmed YYYY-MM-DD)" in [[portal-field-map]]; update the source page Schema section; bump `last_verified`.

| Portal | Grains | Bronze tables affected | Re-scrape cost |
|---|---|---|---|
| [[idealista]] | devs + units + plots | `bronze_listings.idealista_{developments,units,plots}` + state tables | ZenRows-heavy — prefer `raw_payload` replay; full re-scrape ~$5-15 per scope |
| [[jll]] | devs + listings (no plots) | `bronze_listings.jll_{developments,listings}` + state tables | Cheap (REST/JSON) — clean re-scrape, follows the 2026-05-19 precedent |
| [[remax]] | devs + listings + plots | `bronze_listings.remax_{developments,listings,plots}` + state tables | Cheap (REST/JSON) — clean re-scrape |
| [[zome]] | devs + listings + plots | `bronze_listings.zome_{developments,listings,plots}` + state tables | Cheap (REST/JSON) — clean re-scrape |

**Sub-deliverable 6 — Cross-cutting wiki updates (~0.5 day, lands with the last per-portal PR)**

- Rewrite [[portal-field-map]] header + matrix to reflect the trimmed canonical set across all 4 portals.
- Bump [[bronze-permissive]] `last_verified` and confirm the rewrite from sub-deliverable 1 still matches the as-implemented behaviour.
- Update [[index]] entries for [[bronze-permissive]] + every trimmed source page summary if the prior summary said "every column raw."
- Append per-portal ship lines to [`wiki/log.md`](../log.md).

**Verification (per portal PR)**
- `dbt build --select +stg_portal_developments_<portal> +stg_portal_listings_<portal> +stg_portal_plots_<portal>` green.
- Spot-check: a representative bronze row's `raw_payload` JSONB contains the dropped fields exactly as upstream emitted them.
- Re-run downstream consumers ([[cross-portal-dev-dedup|silver_unified_developments]], the LLM eval-set generator, Atlas Inspector spot-render) — outputs unchanged at the cell level (or, where they ARE expected to change because a previously-buried column is now surfaced, the diff is intentional and captured in the PR description).
- pgTAP per portal: assert `raw_payload IS NOT NULL` AND `raw_payload ? '<sample-dropped-field>'` (the canary that audit trail survived).
- The 34632291 canary: after the idealista trim, the LLM eval fixture surfaces "Superfície edificável 82.592 m²" to the labeler (whether via a new `property_features` kept column or via JSONB unpack in staging — decided at PR time).

**Implementation order**: Sub-deliverable 1 (ADR + concept rewrite) blocks 2-5. Within 2-5, **start with [[zome]]** — small footprint, cheap re-scrape, Aveiro coverage present (3 devs) so the silver_unified_developments verification path is exercised on the first trim. Then [[jll]] (zero Aveiro coverage — useful sanity check that the trim doesn't break a "no-overlap" portal), [[remax]], and [[idealista]] last (biggest blast radius, ZenRows cost, and the most-consumed bronze in the codebase).

**Out of scope (defer to [[sprint-10]] or later)**
- GIS bronze tables (`bronze_geo.*`, `bronze_hydrology.*`, `bronze_geology.*`, `bronze_regulatory.raw_srup_*`, `bronze_terrain.*`, etc.) — same pattern applies but is a separate ~5-8 sources × 1-2 days workstream. Track under [[sprint-10]] Production Hardening.
- [[sce]] bronze — already getting a refactor under "SCE bronze refactor — replace-not-append" in this sprint; the column-trim audit lands as a follow-up to that PR, not as a sub-deliverable here.
- Re-running enrichment DAGs (LLM extraction, sce_geocode, etc.) — they re-run when their inputs change; nothing in this stream changes the *content* of bronze, only its column shape.
- Listing-level cross-portal dedup that would benefit from a leaner schema — still v1.5+ scope per the existing sprint-09 Key decisions section.

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
- 2026-05-17: Slice B-prime EXPANDED from 1 day (SCE↔idealista plots) → 7-9 days (4-portal cross-portal dev dedup, includes idealista + JLL + RE/MAX + Zome + SCE). User decision after warehouse audit surfaced that the field-level mapping ([[portal-field-map]]) exists for 3 of 4 portals but the runnable canonical staging models don't. JLL has 0 Aveiro coverage (Lisboa/Porto/Faro/Setúbal only) but is included for future-proofing. **Load impact**: sprint-09 was already running ~4-5 weeks of work in 3 weeks; this adds +6-8 days. Mitigations: either move JLL staging to sprint-10 (still get 3-portal dedup in v1), defer Slice C (LLM extraction) to sprint-10, or accept a sprint-09 slip to ~4 weeks. Decision deferred to mid-sprint check. **Also added** "SCE bronze refactor — replace-not-append" (~1 day) — Slice B audit found bronze keeps 3× scrape history; SCE portal preserves state transitions itself so our scrape-history is redundant. Refactor to UPSERT-by-doc_number with `_last_seen_at` heartbeat.
- 2026-05-18: Slice B-prime detailed plan landed (`~/.claude/plans/wobbly-kindling-hopcroft.md`). Two material design corrections via warehouse audit: (a) idealista DOES have project names — in `title` column via `regexp_match('^Empreendimento (.+?) anuncia ')` pattern with 100% Aveiro extraction rate; Decision 5 reversed from "spatial-only" to "title-extracted name". (b) RE/MAX coords are parish-centroid-level (4 distinct Coimbra devs share one lat/lng); the `name_similarity` Levenshtein CTE — originally scoped as v1.5 dead-code — is promoted to v1 LOAD-BEARING via connected-components recursive CTE. New Decision 8 documents this. Slice B-prime split into **3 PRs** for landing: PR-A = portal-field-map JLL extension (wiki-only, 0.5d); PR-B = 4 canonical per-portal staging models + dbt sources + CI bronze stubs (4-6d); PR-C = silver_unified_developments + 4 pgTAP tests + new concept page + final wiki (1.5-3d). Merge order A → B → C; PR-A is independent, PR-C depends on PR-B's staging models.
- 2026-05-19: PR-B (4 portal staging models) **further split into 4 sequential PRs** (PR-B1 through PR-B4), one per portal. PR-B1 (RE/MAX template) is the foundation: creates `dbt/models/staging/portals/` folder + `_staging_portals__models.yml` skeleton + `tests/ci_bootstrap/bronze_portals.sql` skeleton + the RE/MAX staging model. PR-B2/B3/B4 each append their portal (Zome / Idealista / JLL). PR-B1 audit also surfaced a **dlt SCD2 close-row miss** affecting multiple portal bronze tables at 0.02-0.67% rates (55 dupe PKs in remax_listings, 15 in jll_listings, etc.); new sprint-09 deliverable "Clean re-scrape of JLL + RE/MAX + Zome portals" (~1 day) tracks the tactical TRUNCATE+re-scrape fix. Verified clean on idealista 2026-05-18 (0 dupes post-truncate); same pattern applies. Staging models include defensive `DISTINCT ON` guards in the meantime.
- 2026-06-02: NET-NEW deliverable added — "Workstream 5 — Portal bronze column trim" (~6-10 days). Per-portal audit + bronze DDL trim across [[idealista]], [[jll]], [[remax]], [[zome]] at devs/listings/plots grain. Locks a revision of [[bronze-permissive]]: bronze keeps an explicit kept-column set + `raw_payload` JSONB sidecar (not "every column raw"). Triggered by recurring sprint-09 verification work that surfaced unused-but-load-bearing bronze columns — concretely, idealista's `property_features` carries "Superfície edificável 82.592 m²" for plot 34632291 that the LLM-extraction labeling fixture never reads. Load impact: +6-10 days on top of an already-overloaded sprint-09; user accepted the tradeoff vs. parking to sprint-10 (Production Hardening). Will likely slip past Week 21 demo; that's OK — demo is gated on `fn_assess_polygon` + Atlas Inspector, not on this trim. Labelled Workstream 5 to keep it visually orthogonal to the Workstream 4 v1-wedge stack.
- 2026-05-22: Slice B-prime **SHIPPED** as PR-C — `silver_unified_developments` de-duplicates the 4 portals into 1,050 marketed-development rows via name-driven word-set Jaccard matching (≥0.6 within concelho, 1km distance ceiling), with the geometry hierarchy JLL > Zome > RE/MAX > idealista. New concept page [[cross-portal-dev-dedup]]; 1 multi-assertion pgTAP test for Phase 1 invariants; Tier-1 CI extended with `bronze_geography.sql` stubs for CAOP + INE BGRI. **Major design deltas vs the original 9-decision plan**: (a) Phase 2 (SCE match-or-promote) removed — empirical exploration showed SCE buildings and portal developments resist clean merging; `fn_assess_polygon` queries `silver_unified_developments` and [[silver_sce_buildings]] side-by-side. (b) Decision 9 (`total_units_authoritative`) retired with no SCE anchor; `portal_unit_counts` JSONB exposes per-portal counts without picking. (c) Levenshtein replaced by word-set Jaccard — the distortions in the wild are whole boilerplate words (`empreendimento`, `edifício`, `the`, typology `T1+1`, trailing concelho), not character typos. (d) DBSCAN-first replaced by name-driven graph — portal coords routinely disagree by 200-300m+. **Companion fix to [[silver_sce_buildings]]**: post-cluster fração-grain collapse (renewals counted as separate units; Aveiro `frac_count` 2,650 → 2,573); Test #9 invariant updated. **One follow-up logged**: [[remax]] `PaginatedSearch` coverage gap (sold-out developments like Edifício Elsa have detail pages but aren't in bronze).
- 2026-06-02: **WS4 quick-wins batch SHIPPED** (~1.5d) — 3 of 5 fn_assess_polygon input-data-gap sub-tasks landed in one PR: APA ARPSI floodplains (188 rows → `silver_geo.floodplains` as 15th constraint layer alongside the 14 SRUP siblings, T100=3/T1000=2 in extended `dim_constraint_severity` with new `flood_risk` category, buffer_m=0); LNEG aquifers + geology (63 + 282 rows → `silver_geo.aquifers` + `silver_geo.geology` raw-fields-only); INE indicators (1.17M rows → `silver_market.ine_indicators_long` at parish/concelho/NUTS granularity, distinct from `macro_timeseries`). **Bronze schema migration**: `bronze_ine.raw_indicators` gained `indicator_category` column written by loader from `INE_INDICATORS[code].category` — single source of truth in `ine_config.py`. **New concept page** [[silver-dq-baseline]] codifies 4 universal silver-layer invariants (dual-CRS, surrogate PK, bronze→silver row-count parity, FK denorm integrity), deliberate exclusion of `accepted_values`, and statistical-source silver topology. **Key non-obvious decisions during planning**: (a) LNEG derived `aquifer_vulnerability` + `foundation_difficulty` columns DROPPED from v1 after PT-regulation web-research found DRASTIC requires inputs not in bronze + Eurocode 7 requires site-specific testing + Aveiro Cretaceous Argilas de Aveiro formation contradicted the proposed era-prefix CASE (Galhano & Rocha). (b) `geological_era_label` DROPPED from v1 — would have required pre-verification of actual prefix distribution; v2 adds via discovery query. (c) Canonical dual-CRS naming (`geom`=4326, `geom_pt`=3763 per [[2026-05-10-dual-crs-storage]]) applied to new silvers; SRUP+COS sibling drift logged as sprint-10 cleanup. (d) INE kept SEPARATE from `macro_timeseries` — merging would force LCD schema dropping freguesia/concelho granularity. **Out of scope** (still pending): LiDAR terrain → silver (~1.5d, bronze empty), Aveiro PMOT → bronze + silver (~2-3d, extractor not yet run), 1:50k JPGw raster ingest as Atlas Inspector WMS layer (sprint-10+).
- 2026-06-03: **WS4 batch 2 PR A — LiDAR terrain via postgis_raster SHIPPED** (~1d). Pivoted from the original parcel-proxy plan to Option C (in-DB postgis_raster, on-the-fly ST_Clip + ST_SummaryStatsAgg) on user pushback re sub-parcel imprecision + BUPI coverage gaps. Live discovery (silver-dq-baseline Rule 0) revealed sprint-09's "bronze empty / pipeline never run" claim was wrong — bronze had been fully populated with 489×3 manifests + 10,339 parcel stats; the wiki was drifted, the warehouse was authoritative. Shipped: `bronze_terrain.raster_lidar_slope_2m` (489 single-band Float32 rasters loaded via Python `ST_FromGDALRaster` — `raster2pgsql` not in Airflow image), `silver_geo.terrain_slope_raster` (thin view + GIST-indexed convex-hull footprints for fn_assess_polygon's pre-filter). **DAG topology Y' applied**: merged raster_load into `lidar_derive_terrain` for 3 LiDAR DAGs total (down from 4). **No MinIO slope archive** — derived from MDT in ~25-40 min via DAG re-run. **Cleanup post-QA** (20-parcel raster vs proxy spot-check, max diff 0.069° vs 0.5° tolerance): dropped `parcel_zonal_stats_dag.py` + `bronze_terrain.parcel_terrain_stats` + `bronze_terrain.derived_lidar_slope_2m_manifest`. **PostGIS raster operational pattern locked**: `postgis.gdal_enabled_drivers='GTiff PNG JPEG'` via `ALTER DATABASE` in prod + CI, plus `SET LOCAL` in DAG as belt-and-braces. **Still pending**: OGC streaming fix (PR B, sprint-09 deferred-from-sprint-08), Aveiro PMOT (PR C).
- 2026-06-03: **WS4 batch 2 PR B — OGC streaming bronze loader SHIPPED** (~0.5d). Replaced `json.load` with `ijson.items(f, "features.item", use_float=True)` in both `cos_ogc_bronze_dag.py` + `crus_ogc_bronze_dag.py` to fix the OOM at national scale flagged in the deferred-from-sprint-08 deliverable. National COS bronze loaded in ~7 min (842,413 rows, +7.5% vs. legacy 783,760 — the OGC API publishes the same dataset at the same revision but with slightly different per-feature splits); national CRUS in ~3 min (236,920 rows, 0% delta vs. legacy 5-muni subset). `use_float=True` is required: by default ijson returns Decimal for numbers (precision-preserving) but `json.dumps(geom)` on a feature with Decimal coordinates raises TypeError. **Silver rebuilt**: `silver_geo.land_use` to 842,413 rows; `silver_geo.zoning` to 236,920 rows. **Legacy cleanup** (post-parity-check, user-approved "drop both"): `bronze_geo.raw_cos2023` dropped; `bronze_regulatory.raw_crus_ordenamento` dropped CASCADE — taking with it a stale `staging_dbt.stg_pdm_ordenamento` view (leftover from a deleted dbt model; no source file in repo, no dependents). 2 stale dbt YAML descriptions fixed (`_staging_geo__models.yml` line 42 + `_staging_regulatory__models.yml` line 6 — both referenced the now-dropped legacy tables). **Note on Airflow DAG triggers**: `dbt_cos_build` and `dbt_crus_build` DAGs exist (auto-generated by `pipelines/dbt/dbt_source_dags.py` factory) but the bronze DAG's `TriggerDagRunOperator` failed with `DagNotFound` mid-run — likely a stale-parse race; silvers were instead built via direct `dbt run` from the host shell (idempotent path). Triggered both DAGs manually at end of work — both queued cleanly. **Still pending**: Aveiro PMOT (PR C).

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
