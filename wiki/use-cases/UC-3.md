---
title: UC-3 — End-to-End Plot Economic Value Pipeline (Scout → Inspect → Assemble → Build out → Value → Profit → Competitive Intel)
type: plan
last_verified: 2026-05-12
tags: [use-case, plan, uc-3, land-development, plot-economic-value, competitive-intel, wedge, gis, m3]
uc_number: "3"
status: planned
sprint_target: "sprint-08"
last_status_update: 2026-05-12
---

## For future Claude

This is the **UC-3** page — the end-to-end plot economic-value pipeline. Reframed on 2026-05-12 from the original "national-scope spatial-overlay Land Development Opportunity Detection" framing per [[2026-05-12-uc3-expanded-scope]]. Now organized as a 7-stage funnel (Scout → Inspect → Assemble → Build out → Value → Profit → Competitive Intel) with a tightly-scoped v1 wedge: Aveiro município + Stages 1-4 + two narrow Stage-7 slices (SCE unit aggregation + LLM construction-area extraction on idealista plot listings) + a small unification layer for development dedup. v1 wedge ships across [[sprint-08]] + [[sprint-09]]. Stages 5-6 (Value + Profit) defer to v2; full Stage 7 (national rollout + promoter dedup) defers to v3. The data-assembly-moat thesis underlying this reframe is unvalidated — three developer interviews per [[2026-05-12-uc3-expanded-scope]] are the kill gate. Read this before editing any UC-3-related dbt model, DAG, or wiki page.

## Users

**Eventual users**: PT land developers, real-estate promoters, investment funds, and municipal development offices. They source plots to develop, need to triage shortlists before approaching landowners, and currently do this work themselves with QGIS + spreadsheets + manual Caderneta Predial lookups (status-quo read per the office-hours session — unvalidated).

**v1 actual user**: the project owner (scouting plots for self / family / close contacts in PT) + three interviewed PT land developers per the wedge-validation assignment. Validation gate is whether ≥2 of 3 interviewed developers can describe a specific recent decision they would have made differently with this tool.

## The 7-stage funnel

| # | Stage | What it answers | Where it lives |
|---|---|---|---|
| 1 | **Scout** | "Which plots in região X match zoning Y, land use Z, area > N, no hard-gate SRUP?" | Filter projection of `gold.fn_assess_polygon` results |
| 2 | **Inspect** | "Tell me everything about this drawn polygon" — deep readout: zoning, gates, slope, vegetation, COS class, nearby developments, nearby plot listings | `gold.fn_assess_polygon(input_geom)` Postgres function |
| 3 | **Assemble** | "Cluster contiguous parcels into a developable site" | `ST_Intersects` between input polygon and `parcel_universe`; returned as `assembled_parcels[]` |
| 4 | **Build out** | "What can I legally build here?" — GBA from zoning (max_floors × coverage × density) | `silver_geo.zoning` density extraction (consumed by `fn_assess_polygon`) |
| 5 | **Value** *(v2)* | "What's it worth built?" — GDV from [[UC-1]] hedonic × GBA, construction cost from `ref_construction_costs`, soft costs (IMT/IS/IMI), ARU tax benefits | `gold_analytics.site_economics` (v2) |
| 6 | **Profit** *(v2)* | "Is it worth doing?" — residual land value, ROI, ±10% sensitivity, Build-to-Sell / Build-to-Rent / mixed-use scenarios | `gold_analytics.site_economics` (v2) |
| 7 | **Competitive Intel** *(slices in v1, full in v3)* | "Who else is building nearby? How many units? What's the market saying?" | v1 = `silver_sce_buildings` + `silver_plot_listings_enriched` + `silver_unified_developments`. v3 = + Approach A promoter slice (building permits + NIF) + national rollout |

## v1 wedge (Aveiro município)

**Scope** (per [[2026-05-12-uc3-expanded-scope]]):

- **Stages 1-4** fully (Scout / Inspect / Assemble / Build out)
- **Stage 7 narrow**: SCE unit aggregation (`silver_sce_buildings`) + LLM construction-area extraction on **idealista** plot listings only (`silver_plot_listings_enriched`) + development dedup (`silver_unified_developments`)
- **Aveiro município** only (matches existing [[sce]] scope)
- **NOT in v1 wedge**: Stages 5-6 (economics depth), national rollout, jll/remax/zome plot extraction (deferred to v1.5), Approach A promoter slice (deferred to v3), ARU overlay, building permits, Caderneta UX

**Effort**: ~10-13 weeks honest for one solo dev across [[sprint-08]] (Foundations) + [[sprint-09]] (Wedge completion + demo) + 2-3 weeks calendar parallel for developer-interview outreach.

**Architecture keystone**: `gold.fn_assess_polygon(input_geom geometry) RETURNS jsonb` — Postgres SQL function. Single entry point for the entire backend. Streamlit-component (v1) calls it directly via psycopg2; v2 web app wraps it via FastAPI/PostgREST shim — no backend rewrite at v2.

**Primary user journey**: draw-your-own-polygon (Desenhar CTA per variant B-prime, per `~/.gstack/projects/dacostalindo-House4House/designs/aveiro-parcel-assessment-inspect-20260506/approved.json`). Click-anywhere-to-assess was explicitly dropped in the approved Atlas mockup. The drawn polygon flows through `fn_assess_polygon` and the result populates the dark-chrome left-side readout panel.

## Decision output

**Per drawn polygon**, the assessment returns JSONB with:

```
{
  zoning: { zone_category, max_floors, max_density_index, max_coverage_ratio, land_designation },
  gates: [ { reason: "RAN_full" | "DPH" | "IC" | ..., severity: 0-4 } ],
  soft_constraints: [ { flag: "ZPE" | "ZEC" | ..., area_pct } ],
  land_use: { cos_dominant_class, vegetation_class, is_vacant, is_agricultural, is_built },
  terrain: { slope_mean_pct, slope_p90_pct, slope_max_pct, elevation_mean_m },
  nearby_developments_sce: [...],     // raw SCE building rows within 500m
  nearby_plot_listings: [...],        // raw idealista plot listings within 500m
  nearby_unified_developments: [...], // deduped via spatial + name similarity
  assembled_parcels: [...]            // BUPI parcels intersecting the input polygon
}
```

Surfaced as the **Atlas Site Inspector** (Streamlit-component in v1 at [apps/pages/4_site_inspector.py](../../apps/pages/4_site_inspector.py), replaces existing `4_parcel_explorer.py` + `5_site_analyzer.py` placeholders). v2 promotes the Inspector to a standalone web app per [[2026-05-12-uc3-expanded-scope]].

## What makes a plot a development opportunity

Same logic as the original UC-3 framing, but now computed live for an arbitrary drawn polygon rather than precomputed for every BUPI parcel:

- Located in a [[crus]] urban-expansion or urbanizable zone but currently vacant or underutilized ([[cos]] non-artificial land use)
- No blocking [[srup-ogc]] constraints (RAN, REN, DPH, heritage protection) — or constraints are manageable (severity ≤ 2)
- Assemblable area from contiguous [[bupi]] parcels exceeds minimum viable development size
- Building coverage ratio is low (deferred to v2 alongside MS Building Footprints ingestion)
- Estimated development return (deferred to v2 — Stages 5-6 economics)
- Ownership is traceable via `NumeroMatriz` + `Dicofre` → Caderneta Predial at Finanças (manual user step, deferred even from v1.5 unless interviews surface it as a top-3 ask)

## Analytical layers (v1 wedge)

| Layer | Where it lives | Sprint | Notes |
|---|---|---|---|
| **Spatial backbone (parcel_universe)** | `silver_parcels.parcel_universe` | [[sprint-08]] | Union [[cadastro]] + [[bupi]] for Aveiro município. dbt incremental materialization. |
| **Buildability assessment** | `silver_geo.zoning` (extends existing) | [[sprint-08]] | CRUS density extraction — `max_floors`, `max_density_index`, `max_coverage_ratio` parsed from `land_designation`. Already partially present. |
| **Constraint precomputation** | `silver_geo.parcel_constraints` (extends existing pattern) | [[sprint-08]] | Per-parcel `ST_Intersects` with [[srup]] RAN / DPH / IC. Severity 0=none, 1=DPH buffer, 2=RAN partial, 3=RAN full, 4=heritage. |
| **Land use** | `silver_geo.land_use` (existing — extends) | [[sprint-08]] | Already covers COS dominant class. Verify `is_vacant` / `is_agricultural` / `is_built` flags. |
| **Terrain stats** | `bronze_terrain.parcel_terrain_stats` | [[sprint-08]] | DGT LiDAR DTM 2m for Aveiro tiles. Slope mean / p90 / max + elevation mean per parcel. Materialized via zonal-stats DAG. |
| **SCE buildings (Slice B)** | `silver_sce_buildings` | [[sprint-08]] / [[sprint-09]] | SCE certificates aggregated via `ST_ClusterDBSCAN(eps=30m)` + Levenshtein-ratio dedup on normalized address. Per-building: `frac_count`, `energy_class_dist`, `first_emission`, `last_emission`, `dominant_state`. Geocoding via CTT centroids + Nominatim fallback. |
| **Plot listings enriched (Slice C, idealista-only)** | `silver_plot_listings_enriched` | [[sprint-09]] | LLM-extracted construction area, construction index, max height from idealista plot-listing descriptions via Pydantic-AI on Claude Haiku 4.5. Derived-validity check flags rows where `index × parcel_area ≠ extracted_gba` by > 10%. |
| **Unified developments (dev dedup)** | `silver_unified_developments` | [[sprint-09]] | Joins SCE buildings + idealista plot listings via spatial proximity (≤ 50m) + optional Levenshtein-ratio name similarity. Each row = one canonical development with `provenance` JSONB. |
| **Assessment function** | `gold.fn_assess_polygon(input_geom)` Postgres function | [[sprint-09]] | Single backend entry point. Takes WGS84 input, `ST_Transform` to EPSG:3763 internally, runs 7 spatial joins, returns JSONB. P95 < 3s. |

**Architecture pivot** (per [[2026-05-12-uc3-expanded-scope]] / eng-review D3): no per-parcel materialized `parcel_assessment` table. Upstream silver tables stay materialized + GIST-indexed; assessment runs live via the function. The previous UC-3 framing's `gold_analytics.vacant_parcels` / `parcel_constraints` / `development_sites` precomputed tables are NOT built — they'd be wasteful for a draw-polygon UX.

## Conceptual data model (v1 wedge)

```
                  ┌─────────────────────────────┐
                  │   DRAWN POLYGON (user input)│
                  │   WGS84 from Mapbox/Leaflet │
                  └──────────────┬──────────────┘
                                 │
                                 ▼
                  ┌─────────────────────────────┐
                  │  gold.fn_assess_polygon()   │
                  │  ST_Transform 4326 → 3763   │
                  └──────────────┬──────────────┘
                                 │
       ┌───────────────────┬─────┴─────┬───────────────────┐
       │                   │           │                   │
┌──────┴───────┐  ┌────────┴────────┐ ┌┴──────────────┐  ┌─┴──────────────┐
│  SPATIAL     │  │  COMPETITIVE    │ │   TERRAIN     │  │  ASSEMBLED     │
│  BACKBONE    │  │  INTEL          │ │               │  │  PARCELS       │
│              │  │                 │ │               │  │                │
│ parcel_univ  │  │ silver_sce_     │ │ parcel_terr-  │  │ ST_Intersects  │
│ silver_geo.* │  │ buildings       │ │ ain_stats     │  │ parcel_universe│
│ stg_srup_*   │  │ silver_plot_    │ │ (LiDAR        │  │                │
│              │  │ listings_       │ │  DTM 2m,      │  │                │
│ zoning,      │  │ enriched        │ │  slope p90,   │  │                │
│ land_use,    │  │ silver_unified_ │ │  elevation)   │  │                │
│ gates        │  │ developments    │ │               │  │                │
└──────────────┘  └─────────────────┘ └───────────────┘  └────────────────┘

                                 │
                                 ▼
                  ┌─────────────────────────────┐
                  │   JSONB result              │
                  │   → Streamlit Inspector     │
                  │   → (v2) FastAPI shim       │
                  └─────────────────────────────┘
```

## Serving layer

Single surface in v1:

| Surface | Tool | Purpose | Status |
|---|---|---|---|
| **Atlas Site Inspector** | Streamlit-component at [apps/pages/4_site_inspector.py](../../apps/pages/4_site_inspector.py) | Draw polygon → click Analisar → dark-chrome left-panel readout with 8 sections (zoning, gates, soft_constraints, land_use, terrain, nearby_developments_sce, nearby_plot_listings, assembled_parcels) | v1 (replaces existing 4_parcel_explorer + 5_site_analyzer placeholders) |
| **Standalone web app** | Next.js or similar at `apps/inspector/` (TBD) | Production-quality variant B-prime UI | **v2 — gated on interview validation** |
| **Land Dashboard** | Metabase OSS | Top opportunities by ROI, constraint distribution | **Deferred — v2 (paired with Stages 5-6 economics)** |

Per [[medallion-layering]]: all v1 wedge layers live in `silver_*` (precomputed) + `gold.*` (the assessment function). No materialized `gold_analytics.*` tables in v1.

## Dependencies

**v1 wedge prerequisites:**

- [[sprint-01]] — `dim_geography` (spatial backbone) — DONE
- [[sprint-03]] — UC-3 GIS bronze + staging ([[bupi]], [[cos]], [[crus]], [[srup]], [[cadastro]]) — DONE
- Existing [[sce]] scrape (Aveiro distrito only) — DONE, load-bearing for Slice B
- Existing [[idealista]] scraper — DONE, load-bearing for Slice C
- CI/CD scaffolding (Phase 4, commit `fda6d6c`) — DONE, extended in v1 wedge for pgTAP + Playwright
- DGT LiDAR Aveiro tile availability — TO VERIFY before [[sprint-08]] commits ([[2026-05-12-uc3-expanded-scope]] open question)

**Cross-UC dependency (v2 only):** UC-3 Stages 5-6 economics REQUIRE [[UC-1]]'s hedonic model. Without it, GDV estimates are guesswork. v1 wedge does NOT depend on UC-1.

**The actual load-bearing dependency for v1**: the developer-interview assignment per [[2026-05-12-uc3-expanded-scope]]. Three named PT land developers, three real conversations, kill-criteria pre-committed. Outreach starts Day 1 in calendar parallel with [[sprint-08]] engineering. If interviews kill the wedge, the [[2026-05-12-uc3-expanded-scope]] ADR gets a `superseded_by:` field and v1 work stops.

## See also

- [[2026-05-12-uc3-expanded-scope]] — the ADR that reframed this page
- [[sprint-08]] — v1 wedge Part 1 (Foundations: WS1 templates + WS3 LiDAR + Slice B start)
- [[sprint-09]] — v1 wedge Part 2 (Wedge completion: WS4 finish + Atlas Inspector + dev dedup + demo)
- [[bupi]], [[cos]], [[crus]], [[crus-ogc]], [[srup]], [[srup-ogc]], [[cadastro]] — spatial backbone (unchanged at staging level)
- [[sce]] — load-bearing for Slice B (Aveiro distrito scope is now load-bearing)
- [[idealista]] — load-bearing for Slice C (LLM extraction on plot listings, idealista-only in v1)
- [[lidar]] — DGT 2m DTM/DSM for Aveiro terrain stats
- [[osm]] — drive-time integration (deferred to v2 economics)
- [[apa]] — flood-risk overlay (v2)
- [[lneg]] — geology (v2)
- [[bgri]], [[caop]] — spatial backbone (unchanged)
- [[medallion-layering]] — silver/gold pattern + new `bronze_enrichment` schema
- [[bronze-permissive]] — LLM enrichment writes to bronze_enrichment, not silver directly
- [[UC-1]] — hedonic foundation (UC-3 economics depend on it; v2 only)
- [[UC-2]] — sibling sharing portal-enrichment infrastructure (the LLM pipeline from Slice C could power UC-2 enrichment in the future)
- Office-hours design doc: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-design-20260512-151500.md`
- 2026-05-03 Aveiro demo design (absorbed): `~/.gstack/projects/dacostalindo-House4House/manuellindo-main-design-20260503-163252.md`
- Variant B-prime UI mockup: `~/.gstack/projects/dacostalindo-House4House/designs/aveiro-parcel-assessment-inspect-20260506/approved.json`
- /plan-eng-review test plan: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-eng-review-test-plan-20260512-155850.md`
