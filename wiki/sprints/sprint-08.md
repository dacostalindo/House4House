---
title: Sprint 8 — UC-3 v1 wedge Part 1 (Foundations + Aveiro Vertical Slice)
type: plan
last_verified: 2026-05-12
tags: [sprint, plan, uc-3, wedge, foundations, lidar, sce, ingestion-template, weeks-16-18]
status: planned
sprint_number: "8"
weeks: "16-18"
last_status_update: 2026-05-12
---

## For future Claude

This is **Sprint 8** (Weeks 16-18). Restructured twice on 2026-05-12:
1. First, per [[2026-05-12-uc3-expanded-scope]]: replaces the previous "UC-3 MVP Land Development Opportunities" framing; now ships Part 1 of the [[UC-3]] v1 wedge (foundations + Aveiro vertical slice setup).
2. Second, post-recovery (commit `171114d`): 26 lost GIS pipeline files were recovered from .pyc decompilation + the `feature/pdm` branch. **Six pipelines/gis/ subdirs (`apa/ crus_ogc/ lidar/ lneg/ pdm/ srup_ogc/`) are now in HEAD.** This means WS3 (LiDAR) flips from "build-from-scratch" to "validate-recovered-code-against-WS1-adapters" and WS1 expands from a single OGC template to a full `ingestion_template.py` with three adapters specified by the recovered DAGs' imports. ~3 days saved.

Sprint 8 deliverables: WS1 (`ingestion_template.py` with `UnifiedIngestionConfig` + `OgcApiAdapter` + `ArcgisRestAdapter` + `DgtStacAdapter` — the API surface is fully specified by the recovered DAGs in `pipelines/gis/{apa,crus_ogc,lidar,lneg,srup_ogc}/`); WS3 (smoke-test the recovered [[lidar]] DAGs end-to-end on Aveiro tiles, add `silver/parcels/parcel_universe.sql` + `silver/geo/parcel_constraints.sql` + zoning density extraction); WS4 Slice B Part 1 (SCE address normalization + geocoding DAG + silver_sce_buildings skeleton). [[sprint-09]] completes the wedge with WS4 finish + Atlas Inspector + dev dedup + demo. Developer-interview outreach runs in calendar parallel from Day 1. Read this before touching any v1 wedge code.

## Goal

Land the foundations the [[UC-3]] v1 wedge depends on: the unified `ingestion_template.py` (WS1) that the recovered GIS DAGs need to run, smoke-test the recovered [[lidar]] pipeline end-to-end against those adapters (WS3), `parcel_universe` materialization, density extraction in [[silver_geo.zoning]], SCE address geocoding, and the start of `silver_sce_buildings` (Slice B). Set the stage for [[sprint-09]] to ship `gold.fn_assess_polygon` + the Atlas Inspector + Slice C LLM extraction + dev dedup + demo.

**Prerequisite (load-bearing, calendar parallel from Day 1):** developer-interview outreach per [[2026-05-12-uc3-expanded-scope]] kill criteria. Three named PT land developers, three real conversations. Outreach via APEMIP, AICCOPN, LinkedIn warm — hit-rate ~5-30% depending on channel. Do not start WS4 Slice B (`silver_sce_buildings`, the wedge differentiator) until ≥1 interview is scheduled.

**Confirm before WS3 commits**: DGT LiDAR Aveiro tile availability via `cdd.dgterritorio.gov.pt` ([[2026-05-12-uc3-expanded-scope]] open question 1). Without LiDAR coverage, the slope-contrast demo moment falls back to Copernicus EEA-10 (10m resolution, lower wow).

## Recovery (already done, commit `171114d` 2026-05-12)

26 lost GIS pipeline files are now in HEAD. Wedge implications:
- **Load-bearing for WS3**: `pipelines/gis/lidar/` (6 files) — `lidar_config.py`, `lidar_ingestion_dag.py`, `lidar_bronze_dag.py`, `derive_terrain_dag.py`, `parcel_zonal_stats_dag.py`. The `parcel_zonal_stats_dag.py` has TWO modes: `bulk` (all Aveiro BUPI parcels) and `polygon` (ad-hoc WKT via XCom — the keystone for [[sprint-09]]'s draw-polygon Atlas Inspector UX).
- **Bonus v1 candidate**: `pipelines/gis/srup_ogc/` (4 files) — 22-layer SRUP OGC registry (REN×2, áreas protegidas, ZPE, ZEC, defesa militar ×2, perigosidade incêndio rural, SGIFR ×3, RAN OGC, etc.). **Day-8 evaluation gate**: smoke-test against existing legacy SRUP WFS bronze tables; if richer, `silver/geo/parcel_constraints.sql` (Day 10) uses `stg_srup_*_ogc` instead of legacy 3-layer WFS path.
- **Bonus quick win**: `pipelines/gis/pdm/` (4 files from `feature/pdm` branch) — Plano Director Municipal CRUS WFS for 5 munis incl. Aveiro. Strengthens the zoning answer in demo.
- **v2 scope (preserve only)**: `pipelines/gis/{apa,crus_ogc,lneg}/` — ARPSI floodplain (188 polys), CRUS national OGC (~236,920 features), LNEG geology + aquíferos (282 + 63 polys). Committed for preservation; not wired into v1 wedge dbt models or demo.

All recovered DAGs import from `pipelines.gis.template.ingestion_template` (`UnifiedIngestionConfig`, `OgcApiAdapter`, `ArcgisRestAdapter`, `DgtStacAdapter`) — that module is what WS1 must produce. The recovered DAG signatures fully determine the API surface.

## Deliverables

### Workstream 1 — Unified ingestion template (~1.5 weeks, NET-NEW with expanded scope post-recovery)

Scope expanded from "extract `ogcapi_template.py`" (the original 2026-05-03 design) to a full `ingestion_template.py` with three protocol adapters. Specification fully determined by the recovered DAGs' import signatures.

- `pipelines/gis/template/ingestion_template.py` containing:
  - `UnifiedIngestionConfig(BaseModel)` — Pydantic model: `dag_id`, `source_name`, `description`, `protocol` (`"ogc_api"` | `"arcgis_rest"` | `"dgt_stac"`), `endpoint_url`, `collection_id` (optional, used by OGC + STAC), `page_size`, `request_delay_seconds`, `request_timeout_seconds`, `bbox_4326` (optional, STAC filter), `auth_cookie_variable` (optional, Airflow Variable name), `minio_prefix`, `bronze_schema_table`.
  - `OgcApiAdapter(cfg).probe() / .fetch_to(tmp_dir)` — port the streaming pagination loop from [[cadastro]]'s `_fetch_all_features_to_file`. Consumed by `crus_ogc` + `srup_ogc` recovered DAGs.
  - `ArcgisRestAdapter(cfg).probe() / .fetch_to(tmp_dir)` — paginated GET with `outSR=3763` for server-side reproject. Consumed by [[apa]] + [[lneg]] recovered DAGs. LNEG quirk: handle self-signed SSL via `verify=False` (`lneg_ingestion_dag.py` wraps `requests.Session.request`).
  - `DgtStacAdapter(cfg).probe() / .fetch_to(tmp_dir)` — STAC search pagination + Keycloak cookie auth + 302→MinIO presigned URL handling. Writes per-tile GeoTIFFs + `manifest.json`. Consumed by [[lidar]] recovered DAGs.
- All three adapters return identical `meta` dicts from `.fetch_to()`: `{feature_count, pages, bytes, files: list[paths]}`. The recovered DAGs unpack this dict.
- Refactor [[cadastro]] DAG onto the new `OgcApiAdapter`; **row-count parity test** vs. previous run within 1% (Test #1 from Appendix C of the eng-review plan).
- `dbt test` macro `gis_dual_run_count_parity` for future WFS→OGC cutovers (deferred-utility — not load-bearing for v1 wedge demo).
- `pipelines/gis/template/raster_template.py` — separate from `ingestion_template.py`; tile-manifest CSV → parallel download → `rio cogeo create` → MinIO upload → manifest row insert. Used by the Day-5 Copernicus EEA-10 pilot. The recovered lidar pipeline uses `DgtStacAdapter` instead (no raster_template dependency); raster_template is therefore only for the pilot.

### Workstream 3 — LiDAR (RECOVERED) + parcel_universe + silver_geo extensions (~2 weeks)

LiDAR work flips from build to smoke-test-and-validate. The recovered code lives at HEAD; validation gates ensure it works end-to-end against the WS1 adapters.

- **Smoke-test `lidar_aveiro_ingestion`** end-to-end: trigger DAG, verify ~489 tiles per collection (MDT-2m + MDS-2m) download to MinIO under `raw/lidar/{COLLECTION}/{YYYYMMDD}/tiles/{tile_id}.tif`. Manifest.json per collection. Uses `DgtStacAdapter` with Keycloak cookie via Airflow Variable `DGT_CDD_COOKIE`. If adapter interface mismatches DAG expectations, patch the adapter — the recovered DAG signatures are authoritative.
- **Smoke-test `lidar_aveiro_bronze_load`**: writes one row per tile into `bronze_terrain.raw_lidar_mdt_2m_manifest` + `..._mds_2m_manifest`. Tile-id + EPSG:3763 footprint geom + minio_object + datetime + version + file_size_bytes per row.
- **Smoke-test `lidar_derive_terrain`** with `limit=5` first (smoke), then `limit=0` (full ~489 tiles). Outputs slope COGs at `raw/lidar/derived/slope_2m/{date}/tiles/{tile_id}_slope.tif`, manifests in `bronze_terrain.derived_lidar_slope_2m_manifest`. `gdaldem slope -alg Horn -compute_edges` + `rio cogeo create --nodata -9999 --cog-profile deflate` per tile, ~1 sec each.
- **Smoke-test `lidar_parcel_zonal_stats`** in both modes: `polygon` mode (ad-hoc WKT, XCom result — keystone for [[sprint-09]] Atlas Inspector) AND `bulk` mode (all Aveiro BUPI parcels, writes `bronze_terrain.parcel_terrain_stats`). **20-parcel manual spot-check vs QGIS-computed slope** here (pulled forward from [[sprint-09]]). If recovered stats diverge > 5% from QGIS, investigate tile-edge handling.
- **PDM quick win**: `pipelines/gis/pdm/` is in HEAD (4 files from feature/pdm). Trigger the existing PDM DAGs to populate the PDM zoning bronze for Aveiro município. Strengthens the zoning answer in [[sprint-09]] demo without additional code.
- **Day-8 `srup_ogc` evaluation gate** (decision point): trigger `srup_ogc_ingestion` with `layer_filter=srup_ran_ogc,srup_ren_areal,srup_ren_linear`. Compare row counts vs. legacy [[srup]] WFS bronze tables. Decision: if OGC data is meaningfully richer or cleaner, integrate into Day-10 `parcel_constraints.sql` (3 sources → up to 22 sources); if marginal, leave as committed v2 work. Default = preserve as v2.
- `dbt/models/silver/parcels/parcel_universe.sql` (NEW) — UNION [[cadastro]] + [[bupi]] for Aveiro, deduplicated. `materialized=table` + `post_hook` GIST on `geom_pt` + `geom_4326`. **Test #12 from Appendix C**: dedup correctness via custom singular test.
- Extend [[silver_geo.zoning]] with density extraction — parse `max_floors`, `max_density_index`, `max_coverage_ratio` from CRUS `land_designation` text via regex.
- Create `dbt/models/silver/geo/parcel_constraints.sql` — per-parcel `ST_Intersects` against [[srup]] RAN / DPH / IC (legacy WFS) OR `stg_srup_*_ogc` if Day-8 gate passes. Severity 0-4 column. `materialized=table` + GIST + B-tree on `(parcel_id, severity)`.

### Workstream 4 Slice B — SCE Unit Aggregation Part 1 (~1.5 weeks, NET-NEW)

Unchanged from prior plan; SCE work is fresh (no recovery applies to Slice B).

- **SCE address normalization spike** (2-3 days): deterministic `normalized_address` function per Appendix A of the design doc. Pytest against ~50 sample SCE rows from Aveiro distrito at `tests/fixtures/sce_addresses_aveiro.jsonl`. Levenshtein-ratio threshold ≤ 0.15; tighten to 0.10 if false-merge rate > 5%.
- `pipelines/enrichment/sce_geocode_dag.py` — joins [[sce]] `localidade` + `concelho` to **CTT postal-code centroids** (free, INE-published, ~500m geocoding accuracy sufficient for 500m-radius spatial joins). Nominatim local Docker fallback for CTT misses. Writes `bronze_enrichment.raw_sce_geocoded(doc_number, address_lat, address_lng, geocode_source, geocode_confidence, normalized_address)`. **Idempotent on `doc_number`**. New schema: `bronze_enrichment` per [[bronze-permissive]] rule.
- Extend `dbt/models/staging/regulatory/stg_sce_certificates.sql` with coordinate join + `normalized_address` lookup. **Test #1 from Appendix C (MANDATORY REGRESSION)**: row count unchanged after the modification; all existing downstream dbt tests still pass.
- Start of `dbt/models/silver/regulatory/silver_sce_buildings.sql` — schema + `materialized=table` + post_hook GIST on `geom`. Empty body (`SELECT NULL::bigint AS sce_building_id, ... LIMIT 0`). Full aggregation logic finishes in [[sprint-09]].

### CI/CD extensions (extending Phase 4 scaffolding, commit `fda6d6c`)

- Add **pgTAP** test step to CI (swap CI postgres image to `postgis/postgis:16-3.4`, install pgTAP via PGXN, run `pg_prove tests/sql/*.sql`). Empty directory passes through green this sprint; activates for [[sprint-09]] `fn_assess_polygon` tests.
- Tests #1, #7-#12 from Appendix C — wired into existing `make dbt-test` step.
- Tests #13-#15 from Appendix C — wired into existing `make test` step.

## Exit criteria

- **WS1**: `pipelines/gis/template/ingestion_template.py` exists; recovered DAGs (apa, crus_ogc, lidar, lneg, srup_ogc) all parse successfully in Airflow (no broken imports). [[cadastro]] DAG refactored onto `OgcApiAdapter` with row-count parity within 1%.
- **WS3 [[lidar]]**: `bronze_terrain.raw_lidar_mdt_2m_manifest` has ≥ 400 rows (per `expected_min_features` in `lidar_config.LIDAR_LAYERS`). `bronze_terrain.derived_lidar_slope_2m_manifest` ≥ 400 rows. `bronze_terrain.parcel_terrain_stats` populated for Aveiro parcels. 20-parcel manual spot-check matches QGIS-computed values within 5%.
- **WS3 [[pdm]]**: PDM CRUS bronze populated for Aveiro município.
- **WS3 evaluation gate**: `srup_ogc` Day-8 decision documented in a follow-up commit or comment in [[sprint-09]].
- **WS3 silver**: `parcel_universe` materialized (~50K rows) with dedup tests passing. `silver_geo.zoning` density extraction landed. `silver_geo.parcel_constraints` materialized with severity classification.
- **WS4**: `bronze_enrichment.raw_sce_geocoded` populated for Aveiro distrito SCE rows. ≥90% non-null coordinates. `stg_sce_certificates` regression test passes. `silver_sce_buildings` skeleton present.
- **CI/CD**: pgTAP step added, ruff/format/pytest/dbt-parse all green.
- **Wedge validation**: ≥1 PT land developer interview SCHEDULED. Outreach in flight; kill-criteria pre-committed in design doc.

## Key decisions

- **WS1 scope expanded** to full `ingestion_template.py` with 3 adapters (not just OGC). API surface is determined by the recovered DAGs' imports — non-negotiable.
- **WS3 reframed** from build-from-scratch to validate-recovered-code. Saves ~3 days vs the original 2026-05-03 Aveiro design's framing. The polygon mode of `parcel_zonal_stats_dag.py` is the keystone for [[sprint-09]]'s Atlas Inspector.
- **Workstream 2 (national OGC migration) DROPPED** from v1 wedge per [[2026-05-12-uc3-expanded-scope]]. The `srup_ogc` recovered code IS available if Day-8 gate passes — that's a tactical activation, not WS2 rollout.
- **No per-parcel materialized `parcel_assessment` table** — wasteful for the draw-polygon UX. Upstream silver tables stay materialized + GIST-indexed; the assessment runs live via `fn_assess_polygon` in [[sprint-09]].
- **SCE geocoding via CTT centroids + Nominatim fallback** (NOT pure Nominatim). CTT-first is faster and free; Nominatim is fallback for misses.
- **Aveiro município is the only target** in v1 wedge. National rollout is v2 work.
- **Demo-grade error handling** posture per eng-review D5: fail-fast at boundaries, no retries, no circuit breaker. Production-grade in v2.
- **Idealista-only for Slice C** in v1 wedge per eng-review D1; jll/remax/zome plot extraction lands in v1.5.

## Tests added (per /plan-eng-review Appendix C)

Tests landing in Sprint 8 (the rest land in [[sprint-09]]):

- **#1 (MANDATORY REGRESSION)**: `stg_sce_certificates` row count unchanged after `normalized_address` apply; all existing downstream dbt tests still pass
- **#7-11**: `silver_sce_buildings` aggregation tests (DBSCAN, Levenshtein dedup, frac_count, energy_class_dist, cluster_split) — schema lands in sprint-08, aggregation logic + tests fire in sprint-09
- **#12**: `parcel_universe` dedup correctness
- **#13-15**: `sce_geocode_dag` tests (CTT lookup, Nominatim fallback, idempotency)
- **Recovered-code validation tests** (new, post-recovery): smoke-test artifacts from triggering each recovered DAG land in CI as parity tests. e.g. `tests/test_lidar_recovered_smoke.py` — boots Airflow, triggers `lidar_aveiro_ingestion`, asserts MinIO tile count + manifest row count match `LIDAR_LAYERS[*].expected_min_features`. Same pattern for apa/crus_ogc/lneg/srup_ogc/pdm.

All wired into existing `make dbt-test` / `make test` in CI/CD per Phase 4 scaffolding.

## Day-by-day plan (15 working days)

See the engineering plan at `~/.claude/plans/wobbly-kindling-hopcroft.md` for the day-by-day breakdown. Summary:

- **Days 1-5 (Week 1)**: WS1 `ingestion_template.py` build + cadastro refactor + parity test + `raster_template.py` skeleton + Copernicus EEA-10 pilot.
- **Days 6-8 (Week 2 start)**: WS3 smoke-test the recovered lidar/apa/crus_ogc/lneg/srup_ogc/pdm DAGs end-to-end; Day-8 srup_ogc evaluation gate decision.
- **Days 9-10 (Week 2 end)**: WS3 silver work — `parcel_universe.sql`, `silver_geo.zoning` density extraction, `parcel_constraints.sql`.
- **Days 11-15 (Week 3)**: WS4 Slice B Part 1 — SCE address normalization spike, geocoding DAG, `stg_sce_certificates` regression + `silver_sce_buildings` skeleton, CI pgTAP setup.

Day 1 prerequisite gates: DGT LiDAR Aveiro tile availability check, CTT postal-code centroid sourcing investigation, developer-interview outreach kickoff (5 cold emails).

## Status update history

- 2026-04-18: original "UC-3 MVP Land Development Opportunities" declared in README §12; status `planned`
- 2026-05-12 (am): restructured to "UC-3 v1 wedge Part 1 (Foundations + Aveiro Vertical Slice)" per [[2026-05-12-uc3-expanded-scope]]. WS2 (national OGC migration) dropped from v1 wedge. SCE geocoding pulled forward from [[sprint-09]]. Status `planned`.
- 2026-05-12 (pm): post-recovery reshape. 26 lost GIS pipeline files recovered + committed (`171114d`). WS1 scope expanded to full `ingestion_template.py` (3 adapters) per recovered DAG imports. WS3 reframed from build-from-scratch to validate-recovered-code; ~3 days saved. PDM available as bonus quick win; SRUP-OGC evaluation gate added on Day 8. Status `planned`.

## See also

- [[2026-05-12-uc3-expanded-scope]] — the ADR driving this sprint's reshape
- [[UC-3]] — use case page (also reframed 2026-05-12)
- [[sprint-09]] — successor sprint (v1 wedge Part 2: completion + demo)
- [[bupi]], [[cos]], [[crus]], [[srup]], [[cadastro]] — spatial backbone sources
- [[sce]] — load-bearing data source for Slice B
- [[lidar]] — DGT LiDAR Aveiro source (recovered DAGs in HEAD)
- [[apa]] — ARPSI floodplain (recovered, v2 scope)
- [[crus-ogc]] — CRUS national OGC API (recovered, v2 scope)
- [[lneg]] — geology + aquíferos (recovered, v2 scope)
- [[srup-ogc]] — SRUP OGC API (recovered, Day-8 evaluation gate)
- [[caop]] — Aveiro município bbox for tile-manifest filter
- [[medallion-layering]] — silver/gold pattern + `bronze_enrichment` schema
- [[bronze-permissive]] — enrichment writes to bronze, not silver directly
- Office-hours design doc: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-design-20260512-151500.md`
- /plan-eng-review test plan: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-eng-review-test-plan-20260512-155850.md`
- Sprint-08 engineering plan: `~/.claude/plans/wobbly-kindling-hopcroft.md`

## 🏁 Milestone

**Milestone 3 Part 1 (Week 18): UC-3 v1 wedge Foundations LIVE.** Spatial backbone + LiDAR + SCE geocoding in place. Recovered DAGs validated end-to-end. Wedge differentiator (Atlas Inspector + dev dedup + Slice C LLM extraction + demo) lands in [[sprint-09]]. Developer interviews in flight.
