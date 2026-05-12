---
title: Sprint 8 — UC-3 v1 wedge Part 1 (Aveiro foundations)
type: plan
last_verified: 2026-05-12
tags: [sprint, plan, uc-3, wedge, foundations, lidar, sce, ingestion-template, weeks-16-18]
status: planned
sprint_number: "8"
weeks: "16-18"
last_status_update: 2026-05-12
---

## For future Claude

This is **Sprint 8** (Weeks 16-18) — Part 1 of the [[UC-3]] v1 wedge. The job this sprint: load every piece of data the Aveiro plot-assessment depends on (parcels, zoning rules, constraint severity, terrain, geocoded SCE), and land the shared GIS ingestion template that the recovered DAGs need to run. No UI this sprint — that's [[sprint-09]]. Read this before touching any v1 wedge code. The companion ADR is [[2026-05-12-uc3-expanded-scope]].

## Objective

By week 18, every Aveiro plot has its constraint, zoning, terrain, and SCE picture loaded into PostGIS and ready for assessment. **No user-facing UI yet** — that's [[sprint-09]]. The sprint also lands the shared GIS ingestion template that all five recovered pipelines ([[lidar]], [[apa]], [[crus-ogc]], [[lneg]], [[srup-ogc]]) need to actually run.

## Outcomes (verifiable at sprint end)

- All Aveiro parcels merged into one table — `silver_parcels.parcel_universe` (~50K rows, dedup-tested)
- LiDAR slope + elevation computed per parcel — `bronze_terrain.parcel_terrain_stats`, 20-parcel QGIS spot-check within 5%
- Zoning rules parsed — `max_floors`, `max_density_index`, `max_coverage_ratio` populated on the zoning silver model
- Constraint severity pre-classified per parcel — `silver_geo.parcel_constraints` with severity 0-4
- SCE certificates pinned to coordinates — `bronze_enrichment.raw_sce_geocoded` with ≥90% non-null lat/lng
- One shared ingestion template runs OGC API + ArcGIS REST + DGT STAC — `pipelines/gis/template/ingestion_template.py`
- [[cadastro]] DAG refactored onto the template with row-count parity within 1%
- pgTAP test runner wired into CI (empty test dir passes through green this sprint; gate activates [[sprint-09]])
- ≥1 PT land developer interview SCHEDULED (kill-criteria check from [[2026-05-12-uc3-expanded-scope]])

## Activities

### 1. Plug the recovered GIS pipelines into a shared template

**Why:** five GIS pipelines were recovered in commit `171114d` from .pyc decompilation. They all import from `pipelines.gis.template.ingestion_template`, which doesn't exist yet. Until it ships, none of them parse — [[lidar]] (load-bearing for this sprint), [[apa]], [[crus-ogc]], [[lneg]], [[srup-ogc]].

- Create `pipelines/gis/template/ingestion_template.py` with `UnifiedIngestionConfig` (Pydantic) + three adapters: `OgcApiAdapter` (OGC API Features), `ArcgisRestAdapter` (with `outSR=3763` server-side reproject), `DgtStacAdapter` (Keycloak cookie auth + 302 → MinIO presigned URL).
- All three adapters expose the same shape: `.probe()` + `.fetch_to(tmp_dir) -> {feature_count, pages, bytes, files}`.
- Refactor [[cadastro]] ingestion DAG onto `OgcApiAdapter`.
- Add `dbt/macros/gis_dual_run_count_parity.sql` for future WFS→OGC cutovers (deferred-utility, not load-bearing for v1).

**DONE WHEN:** all 5 recovered DAGs + the refactored cadastro DAG import cleanly in Airflow; cadastro row count within 1% of the pre-refactor baseline.

### 2. Validate the recovered LiDAR pipeline end-to-end on Aveiro

**Why:** the LiDAR pipeline code is in HEAD post-recovery, but never ran. Without it, no terrain stats — and slope is the demo's coastal-vs-flat contrast moment.

- Trigger `lidar_aveiro_ingestion`: expect ~489 tiles per collection (MDT-2m + MDS-2m) landed in MinIO under `raw/lidar/{COLLECTION}/{YYYYMMDD}/tiles/{tile_id}.tif`. Requires Airflow Variable `DGT_CDD_COOKIE` (Keycloak session).
- Trigger `lidar_aveiro_bronze_load`: one row per tile in `bronze_terrain.raw_lidar_mdt_2m_manifest` + `..._mds_2m_manifest`.
- Trigger `lidar_derive_terrain` with `limit=5` for smoke, then `limit=0` for full run. Slope COGs land in `bronze_terrain.derived_lidar_slope_2m_manifest`.
- Trigger `lidar_parcel_zonal_stats` in both `polygon` mode (ad-hoc WKT — the keystone for [[sprint-09]]'s draw-polygon Inspector) and `bulk` mode (writes `bronze_terrain.parcel_terrain_stats`).
- Trigger the existing PDM zoning DAGs (in HEAD from `feature/pdm` branch) to populate PDM zoning bronze for Aveiro município — a quick-win zoning enrichment for the demo.
- **Spot-check**: pick 20 random Aveiro parcels, compute slope in QGIS, compare to `slope_p90_pct`. If divergence > 5%, investigate tile-edge handling.

**DONE WHEN:** `bronze_terrain.parcel_terrain_stats` populated for Aveiro parcels; 20-parcel spot-check matches QGIS within 5%; PDM CRUS bronze populated for Aveiro município.

### 3. Decide whether to use the richer OGC SRUP data

**Why:** the recovered [[srup-ogc]] config covers 22 constraint layers (REN×2, áreas protegidas, ZPE, ZEC, defesa militar ×2, perigosidade incêndio rural, SGIFR ×3, RAN OGC, etc.) — substantially richer than the legacy [[srup]] WFS path (3 layers: RAN / DPH / IC). Day 8 is the decision gate.

- Trigger `srup_ogc_ingestion` with `layer_filter=srup_ran_ogc,srup_ren_areal,srup_ren_linear` — the three layers that overlap legacy SRUP.
- Compare row counts + coverage vs. existing `bronze_regulatory.raw_srup_ran` etc.
- **Decision recorded as a follow-up commit comment or inline in [[sprint-09]]**: if OGC is meaningfully richer or cleaner, Activity 6 (`parcel_constraints.sql`) builds on `stg_srup_*_ogc` (3 sources → up to 22 sources). If marginal, leave the OGC pipelines as committed v2 work.
- Default decision = preserve as v2.

**DONE WHEN:** decision documented in a commit or sprint-09 page; if "yes", Activity 6 plan updated accordingly.

### 4. Build the parcel universe for Aveiro

**Why:** [[cadastro]] and [[bupi]] both have Aveiro parcels with overlap and gaps. The assessment function needs one canonical table to spatial-join against.

- Create `dbt/models/silver/parcels/parcel_universe.sql` — `UNION` of [[cadastro]] + [[bupi]] for Aveiro município, deduplicated via `ST_Equals` OR `dicofre + matrix_number` match.
- `materialized=table` + `post_hook` GIST on `geom_pt` (EPSG:3763) and `geom_4326`.
- Create `dbt/models/silver/parcels/_silver_parcels__models.yml` with the dedup-correctness test.
- Add `dbt/tests/dedup_parcel_universe_known_overlap.sql` — a singular test exercising a hand-picked known-overlap parcel.

**DONE WHEN:** `silver_parcels.parcel_universe` has ~50K rows; the dedup test passes; GIST indexes are present.

### 5. Extract density rules from zoning text

**Why:** the zoning silver model currently has `land_designation` as freetext. The Inspector's "what can I legally build" answer needs `max_floors`, `max_density_index`, `max_coverage_ratio` as typed columns.

- Extend `dbt/models/silver/geo/zoning.sql` with regex extraction over `land_designation`:
  - `max_floors` from `(\d+)\s*piso`
  - `max_density_index` from `índice\s*[:=]?\s*([\d,.]+)`
  - `max_coverage_ratio` from `cobertura\s*[:=]?\s*([\d,.]+)%`
- Defaults NULL when the regex doesn't match.
- Document the three new columns in `dbt/models/silver/geo/_silver_geo__models.yml`.

**DONE WHEN:** the three columns are populated for Aveiro zoning rows where the source text contains the pattern; NULL otherwise; dbt tests pass.

### 6. Pre-classify constraint severity per parcel

**Why:** the Inspector needs to surface gates ("RAN_full", "DPH", "IC", etc.) instantly. Computing them live for every query is wasteful — precompute once per parcel.

- Create `dbt/models/silver/geo/parcel_constraints.sql` — per-parcel `ST_Intersects` against [[srup]] RAN / DPH / IC bronze (legacy WFS, default) OR `stg_srup_*_ogc` if Activity 3 gated green.
- `severity` column: 0 = none, 1 = DPH buffer, 2 = RAN partial, 3 = RAN full, 4 = heritage / ZEC.
- `materialized=table` + GIST + B-tree on `(parcel_id, severity)`.

**DONE WHEN:** every Aveiro parcel has a `parcel_constraints` row (severity 0 if unaffected); a hand-picked known-RAN parcel returns severity ≥ 3.

### 7. Geocode the SCE certificates

**Why:** [[sce]] addresses are freetext ("Rua das Acácias 12, 3°D, 3810-123 Aveiro"). Without coordinates, the SCE rows can't be spatially joined to parcels — and the spatial join is what unlocks the per-building unit aggregation in [[sprint-09]] (this sprint sets up the geocoding; [[sprint-09]] does the aggregation).

- Spike `pipelines/enrichment/sce_address_norm.py` — deterministic `normalize_address(morada, fracao, localidade, concelho) -> str` per Appendix A of the design doc. The Levenshtein-ratio threshold is 0.15; tighten to 0.10 if false-merge rate on the sample > 5%.
- Pytest fixture at `tests/fixtures/sce_addresses_aveiro.jsonl` with ~50 hand-picked Aveiro SCE rows.
- Extract the Nominatim helper from `pipelines/portals/idealista/idealista_bronze_dag.py:526-641` into `pipelines/common/geocoding.py` as `nominatim_geocode_batch(addresses, url, rate_limit_s)`. **Do NOT refactor `idealista_bronze_dag.py`** to use the helper this sprint (two callers don't justify cleanup yet).
- Create `pipelines/enrichment/sce_geocode_dag.py`. Inputs: SCE rows where `doc_number NOT IN bronze_enrichment.raw_sce_geocoded`. Order: CTT postal-code centroid lookup → Nominatim fallback. Writes `bronze_enrichment.raw_sce_geocoded(doc_number, address_lat, address_lng, geocode_source, geocode_confidence, normalized_address)` in a new schema (`bronze_enrichment` per [[bronze-permissive]]).
- Extend `dbt/models/staging/regulatory/stg_sce_certificates.sql` with a LEFT JOIN onto the geocoded rows; add `geom_4326` + `geom_3763` derived columns.

**DONE WHEN:** `bronze_enrichment.raw_sce_geocoded` populated for Aveiro distrito; ≥90% non-null coordinates; the `stg_sce_certificates` regression test (Test #1) passes — row count unchanged after the JOIN.

### 8. Lay the SCE buildings skeleton

**Why:** the actual SCE aggregation (DBSCAN clustering + Levenshtein dedup + per-cluster aggregates) is a [[sprint-09]] deliverable. This sprint lands the empty model + schema so [[sprint-09]] only writes the body.

- Create `dbt/models/silver/regulatory/silver_sce_buildings.sql` — schema declaration + `materialized=table` + post_hook GIST on `geom`. Body is empty: `SELECT NULL::bigint AS sce_building_id, ... LIMIT 0`.

**DONE WHEN:** `silver.silver_sce_buildings` exists in PostGIS with the right columns and the GIST index; `dbt build --select silver_sce_buildings` returns 0 rows without error.

### 9. Set up the pgTAP test runner

**Why:** [[sprint-09]]'s polygon-assessment function (`gold.fn_assess_polygon`) needs pgTAP tests. The CI plumbing has to exist this sprint so the [[sprint-09]] tests can land cleanly.

- Swap the CI postgres service container from `postgres:16` to `postgis/postgis:16-3.4` (silver tests need PostGIS).
- Install pgTAP via PGXN inside the CI container.
- Add `pg_prove tests/sql/*.sql` step to `.github/workflows/ci.yml` after the pytest step. Empty `tests/sql/.gitkeep` directory passes through green this sprint.

**DONE WHEN:** the CI pipeline shows a new pgTAP step (green, empty); the next time a `tests/sql/*.sql` file lands, it runs automatically.

## Out of scope (and why)

- **Atlas Site Inspector UI** — that's the [[sprint-09]] deliverable. Building it without the data layers ready is pointless.
- **`gold.fn_assess_polygon`** — same, [[sprint-09]]. The data is in place; the function ties it together.
- **SCE building aggregation** (DBSCAN, Levenshtein, per-cluster aggregates) — [[sprint-09]] writes the body of `silver_sce_buildings`; this sprint just lays the empty model.
- **LLM extraction on [[idealista]] listings** — an [[sprint-09]] activity; not load-bearing for the data foundations.
- **National rollout** — v1 wedge is Aveiro município only. National rollout is v2 work post-interview validation.
- **Stages 5-6 economics (GDV, ROI, ARU)** — v2 work; depends on [[UC-1]] hedonic model.
- **Other portals' plot listings** (jll / remax / zome) — deferred to v1.5 per /plan-eng-review D1.
- **Refactoring `idealista_bronze_dag.py`** to use the new `pipelines/common/geocoding.py` helper — two callers don't justify the cleanup yet (Karpathy Rule 3).
- **Production-grade error handling** in the recovered DAGs — demo-grade fail-fast is acceptable per /plan-eng-review D5. Hardening is v2.
- **APA / CRUS-OGC / LNEG silver models** — the recovered pipelines preserve those modules but they're v2 scope; only their imports get fixed (via Activity 1) so they parse.

## Dependencies / blockers

**Must be true before the sprint starts:**

- DGT LiDAR Aveiro tile catalog count > 100 (Day-1 check on `cdd.dgterritorio.gov.pt`). If fewer, fall back to Copernicus EEA-10 (10m resolution, smaller wow factor — same code path).
- CTT postal-code centroid sourcing decision recorded (Day 1): real CTT data → Activity 7 uses it; sourcing fails → Nominatim-only fallback for v1.
- Airflow Variables present: `DGT_CDD_COOKIE` (Keycloak session, weekly refresh), `MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY`, `WAREHOUSE_HOST/PORT/DB/USER/PASSWORD`.

**Calendar-parallel (must be in flight from Day 1):**

- Developer-interview outreach. APEMIP cold emails + AICCOPN + LinkedIn warm. **Do not start [[sprint-09]]'s listing-extraction and dev-dedup activities until ≥1 interview is scheduled** — they're the wedge differentiator and building them without interview feedback defeats the staged-validation point. Hit-rate ~5-30% depending on channel.

**Upstream dependencies that are already DONE:**

- [[sprint-01]] — `dim_geography` spatial backbone
- [[sprint-03]] — UC-3 GIS bronze + staging ([[bupi]], [[cos]], [[crus]], [[srup]], [[cadastro]])
- Existing [[sce]] scrape for Aveiro distrito
- CI/CD scaffolding (Phase 4, commit `fda6d6c`)
- GIS pipeline recovery (commit `171114d`): 26 files restored across `pipelines/gis/{apa,crus_ogc,lidar,lneg,pdm,srup_ogc}/`

## Exit criteria

- [ ] `pipelines/gis/template/ingestion_template.py` exists; all 5 recovered DAGs + refactored [[cadastro]] DAG parse cleanly
- [ ] [[cadastro]] row-count parity test passes within 1%
- [ ] `bronze_terrain.raw_lidar_mdt_2m_manifest` has ≥ 400 rows (per `LIDAR_LAYERS[*].expected_min_features`)
- [ ] `bronze_terrain.derived_lidar_slope_2m_manifest` ≥ 400 rows
- [ ] `bronze_terrain.parcel_terrain_stats` populated for Aveiro parcels; 20-parcel QGIS spot-check within 5%
- [ ] PDM CRUS bronze populated for Aveiro município
- [ ] `srup_ogc` evaluation-gate decision documented
- [ ] `silver_parcels.parcel_universe` materialized (~50K rows); dedup test passing
- [ ] `silver_geo.zoning` density columns landed
- [ ] `silver_geo.parcel_constraints` materialized with severity classification
- [ ] `bronze_enrichment.raw_sce_geocoded` populated for Aveiro distrito with ≥90% non-null coords
- [ ] `stg_sce_certificates` regression test (Test #1) passes
- [ ] `silver_sce_buildings` skeleton present (empty body OK)
- [ ] pgTAP CI step green
- [ ] ruff / ruff-format / pytest / dbt-parse all green in CI
- [ ] ≥1 PT land developer interview SCHEDULED

## Tests delivered

Maps to /plan-eng-review Appendix C — the 22-test plan. This sprint lands:

- **#1 (MANDATORY REGRESSION)** — `stg_sce_certificates` row count unchanged after the geocoding JOIN
- **#7-#11** — `silver_sce_buildings` aggregation tests (DBSCAN, Levenshtein dedup, `frac_count`, `energy_class_dist`, `cluster_split`). Schema lands here; aggregation logic + tests fire in [[sprint-09]]
- **#12** — `parcel_universe` dedup correctness
- **#13-#15** — `sce_geocode_dag` tests (CTT lookup, Nominatim fallback, idempotency)
- **Recovered-DAG smoke tests** (new) — `tests/test_lidar_recovered_smoke.py` (+ siblings) trigger the recovered DAGs in CI and assert MinIO tile count + manifest row count match `LIDAR_LAYERS[*].expected_min_features`

All wired into existing `make dbt-test` / `make test` per Phase 4 scaffolding.

## Key decisions

- **Aveiro município is the only target in v1 wedge.** National rollout is v2 work.
- **No per-parcel materialized `parcel_assessment` table** — wasteful for the draw-polygon UX. Upstream silver tables stay materialized + GIST-indexed; assessment runs live via `fn_assess_polygon` in [[sprint-09]].
- **SCE geocoding uses CTT centroids first, Nominatim fallback** — not pure Nominatim. CTT is faster, free, and good enough for 500m-radius spatial joins.
- **Recovered-DAG signatures are authoritative** — if the new ingestion template's API doesn't match a recovered DAG's expectations, patch the template, not the DAG.
- **Karpathy Rule 3**: do not refactor `idealista_bronze_dag.py` to use the new geocoding helper this sprint. Two callers don't justify cleanup yet.
- **OGC-vs-WFS SRUP integration is a Day-8 evaluation gate**, not a sprint commitment. Default = preserve OGC code as v2; activate only if richer.

## Status update history

- 2026-04-18: original "UC-3 MVP Land Development Opportunities" declared in README §12; status `planned`
- 2026-05-12 (am): restructured to "UC-3 v1 wedge Part 1 (Foundations + Aveiro Vertical Slice)" per [[2026-05-12-uc3-expanded-scope]]. WS2 (national OGC migration) dropped from v1 wedge. SCE geocoding pulled forward from [[sprint-09]]. Status `planned`.
- 2026-05-12 (pm): post-recovery reshape. 26 lost GIS pipeline files recovered + committed (`171114d`). Shared ingestion template scope expanded from one OGC adapter to three (OGC + ArcGIS REST + DGT STAC) per the recovered DAGs' imports. LiDAR work reframed from build-from-scratch to validate-recovered-code; ~3 days saved. PDM available as bonus quick win; SRUP-OGC evaluation gate added. Status `planned`.
- 2026-05-12 (evening): refactored for clarity — plain-language objectives + activities; "WS1/WS3/WS4 Slice B" jargon dropped in favor of named activities. No scope change. Status `planned`.

## See also

- [[2026-05-12-uc3-expanded-scope]] — the ADR driving this sprint's reshape
- [[UC-3]] — use case page (also reframed 2026-05-12)
- [[sprint-09]] — successor sprint (v1 wedge Part 2: completion + demo)
- [[bupi]], [[cadastro]], [[cos]], [[crus]], [[srup]] — spatial backbone (load-bearing in this sprint)
- [[sce]] — load-bearing for the geocoding activity
- [[lidar]] — DGT 2m DTM/DSM for Aveiro terrain stats
- [[apa]], [[crus-ogc]], [[lneg]], [[srup-ogc]] — recovered pipelines that need the shared template to parse (v2 scope otherwise)
- PDM zoning — bonus quick win (zoning enrichment from `feature/pdm` branch)
- [[caop]] — Aveiro município bbox for tile-manifest filter
- [[medallion-layering]] — silver/gold pattern + `bronze_enrichment` schema
- [[bronze-permissive]] — enrichment writes to bronze, not silver directly
- Office-hours design doc: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-design-20260512-151500.md`
- /plan-eng-review test plan: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-eng-review-test-plan-20260512-155850.md`
- Day-by-day engineering plan (out of date — superseded by this page's activities): `~/.claude/plans/wobbly-kindling-hopcroft.md`

## 🏁 Milestone

**Milestone 3 Part 1 (Week 18): UC-3 v1 wedge foundations LIVE.** Spatial backbone + LiDAR + SCE geocoding in place; recovered pipelines validated. The Inspector UI + LLM extraction + dev dedup + demo land in [[sprint-09]].
