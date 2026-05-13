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
- Constraint severity pre-classified per parcel — `silver_geo.parcel_constraints` with severity 0-4, sourced from OGC SRUP layers + legacy DPH/IC
- SCE certificates pinned to coordinates — `bronze_enrichment.raw_sce_geocoded` with ≥90% non-null lat/lng
- One shared ingestion template runs OGC API + ArcGIS REST + DGT STAC — `pipelines/gis/template/ingestion_template.py`
- One shared MinIO upload helper — `pipelines/common/minio_upload.py`, called by 7 GIS DAGs (no duplicated boilerplate)
- [[cadastro]] DAG refactored onto the template with row-count parity within 1%
- Legacy WFS pipelines retired where the DGT OGC API has equivalents — `pipelines/gis/{crus,pdm,cos}/` removed; `pipelines/gis/srup/` slimmed to DPH + IC only (the two layers OGC doesn't publish); replaced by `crus_ogc`, `srup_ogc`, and new `cos_ogc`
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

### 2. Cleanup pass — extract MinIO helper + retire legacy WFS pipelines now superseded by OGC

**Why:** Activity 1 surfaced two patterns. (a) Every adapter caller duplicates ~15 lines of MinIO client construction + `bucket_exists` check + `fput_object` loop — 11 GIS DAGs now repeat it. (b) Several legacy WFS pipelines (`pipelines/gis/crus/`, `pipelines/gis/pdm/`, parts of `pipelines/gis/srup/`) are fully redundant with their OGC equivalents that the recovery brought online. A WebFetch on `ogcapi.dgterritorio.gov.pt/collections` 2026-05-12 confirmed which legacy layers have OGC successors and which don't.

- **Extract** `pipelines/common/minio_upload.py` exposing `upload_files_to_minio(files, bucket, prefix, date_str, source_name) -> dict`. Single source for: env-driven `Minio()` client construction, idempotent `bucket_exists` + `make_bucket`, `fput_object` loop, return-summary shape.
- **Migrate** 7 DAGs onto the helper: [[cadastro]], [[apa]], [[crus-ogc]], [[lneg]], [[srup-ogc]], [[lidar]], plus `derive_terrain_dag` (LiDAR slope-COG upload).
- **Drop `pipelines/gis/crus/`** — legacy per-município CRUS WFS (5 munis). Superseded by [[crus-ogc]] which the OGC API publishes nationally as the `crus` collection. Redirect `stg_crus_ordenamento` to read `bronze_regulatory.raw_crus_national_ogc`.
- **Drop `pipelines/gis/pdm/`** — also legacy CRUS WFS per-município. Same data, same successor (`crus_ogc`). No separate OGC PDM collection exists; the OGC `crus` collection serves both. PDM's "Aveiro quick-win" reframes as "trigger `crus_ogc_ingestion` filtered to Aveiro município".
- **Refactor `pipelines/gis/srup/`** to keep ONLY the DPH + IC layers. The OGC API publishes 20+ SRUP layers (REN×2, RAN, áreas protegidas, ZPE, ZEC, defesa militar ×2, perigosidade incêndio rural, SGIFR×3, etc.) but **does not publish DPH (Domínio Público Hídrico) or IC (Imóveis Classificados)** — those stay on legacy WFS as the only PT public source. Drop the legacy RAN component (replaced by `srup_ran_ogc` in [[srup-ogc]]).
- **Build `pipelines/gis/cos_ogc/`** using `OgcApiAdapter` with `collection_id="cos2023v1"` + Aveiro bbox filter (v1 wedge scope is Aveiro-only; bbox-filter on a paginated OGC call returns Aveiro polygons in ~30s vs ~5 min for a national bulk download). New bronze table `bronze_geo.raw_cos_national_ogc` (same schema as the legacy `bronze_geo.raw_cos2023`, with new OGC-only columns `municipio` / `nutsii` / `nutsiii`). **Drop `pipelines/gis/cos/`** (the bulk-GPKG path); redirect the existing `stg_cos2023` consumer to read from the new OGC bronze table.
- Update `dbt/models/staging/regulatory/_staging_regulatory__sources.yml` (and `_staging_landuse__sources.yml` if it exists): remove dropped source entries; add new OGC ones.

**DONE WHEN:**
- `pipelines/common/minio_upload.py` exists; 7 adapter+derived DAGs use it; `py_compile` + `ruff` clean.
- `pipelines/gis/crus/`, `pipelines/gis/pdm/`, `pipelines/gis/cos/` directories removed from HEAD.
- `pipelines/gis/srup/` contains only DPH + IC layers (RAN code path removed).
- `pipelines/gis/cos_ogc/` exists with config + ingestion + bronze DAGs.
- All downstream dbt models compile cleanly against the new bronze sources (`dbt parse --target ci` green).
- LiDAR re-audit recorded: only `lidar_ingestion_dag.py` consumes the new template (via `DgtStacAdapter`); the other 3 LiDAR DAGs (`lidar_bronze_dag`, `derive_terrain_dag`, `parcel_zonal_stats_dag`) read MinIO-landed manifests/tiles and are architecturally separate from the template — correct as-is.

### 3. Validate the recovered LiDAR pipeline end-to-end on Aveiro

**Why:** the LiDAR pipeline code is in HEAD post-recovery, but never ran. Without it, no terrain stats — and slope is the demo's coastal-vs-flat contrast moment.

- Trigger `lidar_aveiro_ingestion`: expect ~489 tiles per collection (MDT-2m + MDS-2m) landed in MinIO under `raw/lidar/{COLLECTION}/{YYYYMMDD}/tiles/{tile_id}.tif`. Requires Airflow Variable `DGT_CDD_COOKIE` (Keycloak session).
- Trigger `lidar_aveiro_bronze_load`: one row per tile in `bronze_terrain.raw_lidar_mdt_2m_manifest` + `..._mds_2m_manifest`.
- Trigger `lidar_derive_terrain` with `limit=5` for smoke, then `limit=0` for full run. Slope COGs land in `bronze_terrain.derived_lidar_slope_2m_manifest`.
- Trigger `lidar_parcel_zonal_stats` in both `polygon` mode (ad-hoc WKT — the keystone for [[sprint-09]]'s draw-polygon Inspector) and `bulk` mode (writes `bronze_terrain.parcel_terrain_stats`).
- **Spot-check**: pick 20 random Aveiro parcels, compute slope in QGIS, compare to `slope_p90_pct`. If divergence > 5%, investigate tile-edge handling.

**DONE WHEN:** `bronze_terrain.parcel_terrain_stats` populated for Aveiro parcels; 20-parcel spot-check matches QGIS within 5%.

### 4. Build the parcel universe for Aveiro

**Why:** [[cadastro]] and [[bupi]] both have Aveiro parcels with overlap and gaps. The assessment function needs one canonical table to spatial-join against.

- Create `dbt/models/silver/parcels/parcel_universe.sql` — `UNION` of [[cadastro]] + [[bupi]] for Aveiro município, deduplicated via `ST_Equals` OR `dicofre + matrix_number` match.
- `materialized=table` + `post_hook` GIST on `geom_pt` (EPSG:3763) and `geom_4326`.
- Create `dbt/models/silver/parcels/_silver_parcels__models.yml` with the dedup-correctness test.
- Add `dbt/tests/dedup_parcel_universe_known_overlap.sql` — a singular test exercising a hand-picked known-overlap parcel.

**DONE WHEN:** `silver_parcels.parcel_universe` has ~50K rows; the dedup test passes; GIST indexes are present.

### 5. Extract density rules from zoning text — **DEFERRED to [[sprint-09]] (2026-05-13)**

**Original plan**: extend `silver_geo.zoning` with `max_floors` / `max_density_index` / `max_coverage_ratio` parsed via regex over the CRUS `land_designation` freetext.

**Why deferred**: the approach is structurally wrong for the data we have. Verification against live Aveiro data on 2026-05-13 showed `land_designation` is a hierarchical zone classification (e.g. "Solo Urbano - Espaços Habitacionais - Espaço Habitacional Tipo 1"), NOT a freetext spec sheet. None of the keywords `piso` / `índice` / `cobertura` / `densidade` / `altura` / `implementação` appear in any of the 1,148 Aveiro zoning rows. The actual density rules live in the **PDM Regulamento** per município (a separate text document, typically PDF), not in the CRUS OGC spatial feature properties.

**[[sprint-09]] redesign options** (decision when the activity starts):
- (a) Build a hand-curated zone-category → density lookup table (heuristic; gives the Inspector quantitative answers but the numbers are typical-PT defaults, not Aveiro-specific)
- (b) PDM Regulamento integration — parse the actual Aveiro Regulamento PDF/text and produce a per-município lookup. Doesn't generalize but is exact for the demo target.
- (c) Both — heuristic by default, override with PDM data where parsed.

**Carry-forward**: the regex extraction code was landed in commit `b3bfd09` and reverted on 2026-05-13 in the same commit that deferred. Use that commit as a reference for the regex starting point if the sprint-09 redesign retains any of it.

### 6. Pre-classify constraint severity per parcel

**Why:** the Inspector needs to surface gates ("RAN_full", "DPH", "IC", "REN", "defesa militar", etc.) instantly. Computing them live for every query is wasteful — precompute once per parcel.

- Create `dbt/models/silver/geo/parcel_constraints.sql` — per-parcel `ST_Intersects` against the OGC [[srup-ogc]] layers (`stg_srup_ran_ogc`, `stg_srup_ren_areal`, `stg_srup_ren_linear`, `stg_srup_areas_protegidas`, `stg_srup_defesa_militar`, `stg_srup_zpe`, `stg_srup_zec`, `stg_srup_perigosidade_inc_rural`) plus legacy [[srup]] DPH + IC (the two layers DGT does not publish via OGC API).
- `severity` column: 0 = none, 1 = soft constraint (ZPE/ZEC/SGIFR/DPH buffer), 2 = moderate gate (RAN partial / defesa militar zona), 3 = hard gate (RAN full / REN / áreas protegidas core / DPH core), 4 = heritage (IC / monumentos).
- `constraint_codes` array column listing every layer hit per parcel (e.g. `['RAN', 'ZPE']`) for the Inspector readout.
- `materialized=table` + GIST + B-tree on `(parcel_id, severity)`.

**DONE WHEN:** every Aveiro parcel has a `parcel_constraints` row (severity 0 if unaffected); a hand-picked known-RAN parcel returns severity ≥ 3; a hand-picked known-IC parcel returns severity 4.

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
- [ ] `pipelines/common/minio_upload.py` exists; 7 GIS DAGs use it (no duplicated MinIO boilerplate)
- [ ] `pipelines/gis/{crus,pdm,cos}/` directories removed; `pipelines/gis/srup/` slimmed to DPH + IC; `pipelines/gis/cos_ogc/` created
- [ ] `dbt parse --target ci` green against the new bronze sources (legacy sources removed, OGC sources added)
- [ ] `bronze_terrain.raw_lidar_mdt_2m_manifest` has ≥ 400 rows (per `LIDAR_LAYERS[*].expected_min_features`)
- [ ] `bronze_terrain.derived_lidar_slope_2m_manifest` ≥ 400 rows
- [ ] `bronze_terrain.parcel_terrain_stats` populated for Aveiro parcels; 20-parcel QGIS spot-check within 5%
- [ ] `silver_parcels.parcel_universe` materialized (~50K rows); dedup test passing
- [ ] `silver_geo.zoning` density columns landed
- [ ] `silver_geo.parcel_constraints` materialized with severity classification (OGC SRUP + legacy DPH/IC)
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
- **Legacy WFS pipelines retire when their OGC equivalent exists** — `crus`, `pdm`, RAN-component-of-`srup`, and bulk-GPKG `cos` are all dropped, replaced by `crus_ogc` / `srup_ogc` / new `cos_ogc`. DPH and IC stay on legacy WFS (no OGC equivalent at DGT). Source of truth: WebFetch on `ogcapi.dgterritorio.gov.pt/collections`, 2026-05-12.
- **COS via OGC API is bbox-filtered for Aveiro** — `cos2023v1` collection, ~30s ingestion for the v1 wedge scope vs ~5 min for the legacy national bulk-GPKG download.

## Status update history

- 2026-04-18: original "UC-3 MVP Land Development Opportunities" declared in README §12; status `planned`
- 2026-05-12 (am): restructured to "UC-3 v1 wedge Part 1 (Foundations + Aveiro Vertical Slice)" per [[2026-05-12-uc3-expanded-scope]]. WS2 (national OGC migration) dropped from v1 wedge. SCE geocoding pulled forward from [[sprint-09]]. Status `planned`.
- 2026-05-12 (pm): post-recovery reshape. 26 lost GIS pipeline files recovered + committed (`171114d`). Shared ingestion template scope expanded from one OGC adapter to three (OGC + ArcGIS REST + DGT STAC) per the recovered DAGs' imports. LiDAR work reframed from build-from-scratch to validate-recovered-code; ~3 days saved. PDM available as bonus quick win; SRUP-OGC evaluation gate added. Status `planned`.
- 2026-05-12 (evening): refactored for clarity — plain-language objectives + activities; "WS1/WS3/WS4 Slice B" jargon dropped in favor of named activities. No scope change. Status `planned`.
- 2026-05-12 (late): added **Activity 2 (cleanup pass)** — extract MinIO upload helper + retire legacy WFS pipelines superseded by OGC (`crus`, `pdm`, RAN-component-of-`srup`, bulk-GPKG `cos`) + new `cos_ogc` pipeline for Aveiro bbox. The prior Activity 3 ("srup-ogc evaluation gate") removed — decision resolved (use OGC by default, keep legacy WFS only for DPH + IC which DGT does not publish via OGC). 9 activities total. Status `planned`.

## See also

- [[2026-05-12-uc3-expanded-scope]] — the ADR driving this sprint's reshape
- [[UC-3]] — use case page (also reframed 2026-05-12)
- [[sprint-09]] — successor sprint (v1 wedge Part 2: completion + demo)
- [[bupi]], [[cadastro]], [[cos]], [[crus]], [[srup]] — spatial backbone (load-bearing in this sprint)
- [[sce]] — load-bearing for the geocoding activity
- [[lidar]] — DGT 2m DTM/DSM for Aveiro terrain stats
- [[apa]], [[crus-ogc]], [[lneg]], [[srup-ogc]] — recovered pipelines that need the shared template to parse (v2 scope otherwise)
- [[caop]] — Aveiro município bbox for tile-manifest filter
- [[medallion-layering]] — silver/gold pattern + `bronze_enrichment` schema
- [[bronze-permissive]] — enrichment writes to bronze, not silver directly
- Office-hours design doc: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-design-20260512-151500.md`
- /plan-eng-review test plan: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-eng-review-test-plan-20260512-155850.md`
- Day-by-day engineering plan (out of date — superseded by this page's activities): `~/.claude/plans/wobbly-kindling-hopcroft.md`

## 🏁 Milestone

**Milestone 3 Part 1 (Week 18): UC-3 v1 wedge foundations LIVE.** Spatial backbone + LiDAR + SCE geocoding in place; recovered pipelines validated. The Inspector UI + LLM extraction + dev dedup + demo land in [[sprint-09]].
