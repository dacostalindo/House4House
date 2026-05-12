---
title: Sprint 8 — UC-3 v1 wedge Part 1 (Foundations + Aveiro Vertical Slice)
type: plan
last_verified: 2026-05-12
tags: [sprint, plan, uc-3, wedge, foundations, lidar, sce, weeks-16-18]
status: planned
sprint_number: "8"
weeks: "16-18"
last_status_update: 2026-05-12
---

## For future Claude

This is **Sprint 8** (Weeks 16-18). Restructured 2026-05-12 per [[2026-05-12-uc3-expanded-scope]] to be **Part 1 of the [[UC-3]] v1 wedge** (Foundations + Aveiro vertical slice setup). Replaces the previous "UC-3 MVP Land Development Opportunities" framing. Ships: template extraction (WS1), national OGC migration foundations (NOT in v1 wedge scope — deferred), LiDAR Aveiro ingestion + zonal stats (WS3), parcel_universe + extended silver_geo (WS3), SCE geocoding + silver_sce_buildings start (WS4 Slice B Part 1). [[sprint-09]] completes the wedge with WS4 finish + Atlas Inspector + dev dedup + demo. Developer-interview outreach runs in calendar parallel from Day 1. Engineering effort spans Sprint 8 + Sprint 9 (~6-8 weeks total, with 2-3w outreach overlap). Read this before touching any v1 wedge code.

## Goal

Land the foundations the [[UC-3]] v1 wedge depends on: template extraction patterns, LiDAR ingestion for Aveiro, parcel_universe materialization, density extraction in silver_geo.zoning, SCE address geocoding, and the start of silver_sce_buildings (Slice B). Set the stage for [[sprint-09]] to ship `gold.fn_assess_polygon` + the Atlas Inspector + Slice C LLM extraction + dev dedup + demo.

**Prerequisite (load-bearing, calendar parallel from Day 1):** developer-interview outreach per [[2026-05-12-uc3-expanded-scope]] kill criteria. Three named PT land developers, three real conversations. Outreach via APEMIP, AICCOPN, LinkedIn warm — hit-rate ~5-30% depending on channel. Do not start WS4 Slice B (silver_sce_buildings, the wedge differentiator) until ≥1 interview is scheduled.

**Confirm before WS3 commits**: DGT LiDAR Aveiro tile availability via cdd.dgterritorio.gov.pt ([[2026-05-12-uc3-expanded-scope]] open question 1). Without LiDAR coverage, the slope-contrast demo moment falls back to Copernicus EEA-10 (10m resolution, lower wow).

## Deliverables

### Workstream 1 — Architectural foundations (~1 week, INHERITED from 2026-05-03 Aveiro demo design)

- `pipelines/gis/template/ogcapi_template.py` — `OGCAPIIngestionConfig` dataclass extracted from existing `cadastro_ingestion_dag.py` streaming pagination loop. Reuses `upload_to_minio` helper.
- Refactor [[cadastro]] DAG onto the new template; **row-count parity test** vs. previous run within 1% — added as the first test in v1 wedge CI integration.
- `dbt test` macro `gis_dual_run_count_parity` for future WFS→OGC cutovers (deferred-utility — not load-bearing for v1 wedge demo).
- `pipelines/gis/template/raster_template.py` — tile-manifest CSV → parallel download (Airflow pool concurrency cap N=4) → `rio cogeo create` COG conversion → MinIO upload at `raw/{source}/{version}/cog/{tile_id}.tif` → manifest row insert with EPSG:3763 bbox polygon + checksum.

### Workstream 3 — LiDAR + Aveiro spatial backbone (~2 weeks, INHERITED with one schema rename)

- Copernicus EEA-10 DEM **pilot tile** (~250 MB) to validate `raster_template.py` end-to-end before LiDAR scale.
- DGT LiDAR DTM 2m for **Aveiro tiles only** (manifest filter to Aveiro município bbox via [[caop]] polygon). Tolerate 404s for unpublished NW Portugal tiles. Lands manifests in `bronze_terrain.raw_lidar_mdt_2m_manifest` per existing [[lidar]] source schema.
- `pipelines/gis/lidar/derive_terrain_dag.py` — `gdaldem slope` + `gdaldem hillshade` per DTM tile. Derived COGs at `raw/lidar/{version}/derived/slope_pct/{tile_id}.tif`. Manifests in `bronze_terrain.derived_slope_manifest`.
- `pipelines/gis/lidar/parcel_zonal_stats_dag.py` — for each Aveiro [[cadastro]] / [[bupi]] parcel: intersect bbox with DTM/slope manifest, lazy-read COG windows via rasterio, compute `mean / min / max / p10 / p90`. Writes `bronze_terrain.parcel_terrain_stats(parcel_id, snapshot_date, slope_mean_pct, slope_p90_pct, slope_max_pct, elevation_mean_m, ...)`. Parallelize via Airflow pool concurrency.
- `dbt/models/silver/parcels/parcel_universe.sql` — UNION [[cadastro]] + [[bupi]] for Aveiro, deduplicated, one row per canonical parcel. dbt incremental materialization. **Test #12 from Appendix C of the design doc**: dedup correctness when both sources have the same parcel.
- Extend [[silver_geo.zoning]] with density extraction — parse `max_floors`, `max_density_index`, `max_coverage_ratio` from CRUS `land_designation` text. zone_category defaults where not parseable.
- Extend [[silver_geo.parcel_constraints]] (if not already present) — per-parcel `ST_Intersects` precomputed against [[srup]] RAN / DPH / IC. Severity 0=none, 1=DPH buffer, 2=RAN partial, 3=RAN full, 4=heritage. GIST index on `geom`.

### Workstream 4 Slice B — SCE Unit Aggregation Part 1 (~1.5 weeks, NET-NEW)

- **SCE address normalization spike** (2-3 days): output is the deterministic `normalized_address` function per Appendix A of the design doc. Tested against ~50 sample SCE rows from Aveiro distrito.
- `pipelines/enrichment/sce_geocode_dag.py` — joins [[sce]] `localidade` + `concelho` to **CTT postal-code centroids** (free, INE-published, ~500m geocoding accuracy sufficient for 500m-radius spatial joins). Nominatim local Docker fallback for CTT misses. Writes `bronze_enrichment.raw_sce_geocoded(doc_number, address_lat, address_lng, geocode_source, geocode_confidence)`. **Idempotent on `doc_number`**. New schema: `bronze_enrichment` per [[bronze-permissive]] rule.
- Extend `dbt/models/staging/regulatory/stg_sce_certificates.sql` with `normalized_address` function application + geocoded coordinate join. **Test #1 from Appendix C (MANDATORY REGRESSION)**: row count unchanged after the modification; all existing downstream dbt tests still pass.
- Start of `dbt/models/silver/regulatory/silver_sce_buildings.sql` — schema definition + GIST index creation. Full aggregation logic (DBSCAN + Levenshtein dedup + frac_count + energy_class_dist + cluster_split tiebreak) finishes in [[sprint-09]].

### CI/CD extensions (extending Phase 4 scaffolding, commit `fda6d6c`)

- Add **pgTAP** test step to CI (Postgres+PostGIS container, runs `pg_prove tests/sql/*.sql`). Gates PRs touching `dbt/models/gold/fn_*.sql` in [[sprint-09]].
- Tests #1, #7-#12 from Appendix C of the design doc — wired into existing `make dbt-test` step.
- Tests #13-#15 from Appendix C — wired into existing `make test` step.

## Exit criteria

- `parcel_universe` materialized for Aveiro (~50K rows) with dedup tests passing.
- `silver_geo.zoning` density extraction landed; spot-check 10 Aveiro CRUS rows show parsed `max_floors` / `max_density_index` / `max_coverage_ratio` values.
- `silver_geo.parcel_constraints` materialized with severity classification; spot-check shows known RAN/DPH parcels have expected gates.
- `bronze_terrain.parcel_terrain_stats` populated for Aveiro parcels from real LiDAR (or Copernicus EEA-10 fallback if DGT tiles unavailable). 20-parcel manual spot-check matches QGIS-computed values.
- `bronze_enrichment.raw_sce_geocoded` populated for Aveiro distrito SCE rows. ≥90% of rows have non-null coordinates from CTT or Nominatim fallback.
- `stg_sce_certificates` regression test (test #1) passes.
- CI/CD extended with pgTAP step (running but empty until sprint-09 ships `fn_assess_polygon`).
- ≥1 PT land developer interview SCHEDULED (per the wedge-validation gate). Outreach in flight; kill-criteria pre-committed in design doc.

## Key decisions

- **Workstream 2 (national OGC migration) is DROPPED** from the v1 wedge per [[2026-05-12-uc3-expanded-scope]]. May run as separate infrastructure work in parallel, but NOT a wedge demo deliverable. The 2026-05-03 Aveiro demo design's WS2 was sunk-cost inheritance.
- **No per-parcel materialized `parcel_assessment` table** — wasteful for the draw-polygon UX. Upstream silver tables stay materialized + GIST-indexed; the assessment runs live via `fn_assess_polygon` in [[sprint-09]].
- **SCE geocoding via CTT centroids + Nominatim fallback** (NOT pure Nominatim, which was the previous [[sprint-09]] plan). CTT-first is faster and free; Nominatim is fallback for misses. Saves ~50ms/lookup batched.
- **Aveiro município is the only target** in v1 wedge. National rollout is v2 work.
- **Demo-grade error handling** posture per eng-review D5: fail-fast at boundaries, no retries, no circuit breaker. Production-grade in v2.
- **Idealista-only for Slice C** in v1 wedge per eng-review D1; jll/remax/zome plot extraction lands in v1.5.

## Tests added (per /plan-eng-review Appendix C)

Tests landing in Sprint 8 (the rest land in [[sprint-09]]):

- **#1 (MANDATORY REGRESSION)**: `stg_sce_certificates` row count unchanged after `normalized_address` apply; all existing downstream dbt tests still pass
- **#7-11**: `silver_sce_buildings` aggregation tests (DBSCAN, Levenshtein dedup, frac_count, energy_class_dist, cluster_split)
- **#12**: `parcel_universe` dedup correctness
- **#13-15**: `sce_geocode_dag` tests (CTT lookup, Nominatim fallback, idempotency)

All wired into existing `make dbt-test` / `make test` in CI/CD per Phase 4 scaffolding.

## Status update history

- 2026-04-18: original "UC-3 MVP Land Development Opportunities" declared in README §12; status `planned`
- 2026-05-12: restructured to "UC-3 v1 wedge Part 1 (Foundations + Aveiro Vertical Slice)" per [[2026-05-12-uc3-expanded-scope]]. WS2 (national OGC migration) dropped from v1 wedge. SCE geocoding pulled forward from [[sprint-09]]. Status `planned`.

## See also

- [[2026-05-12-uc3-expanded-scope]] — the ADR driving this sprint's reshape
- [[UC-3]] — use case page (also reframed 2026-05-12)
- [[sprint-09]] — successor sprint (v1 wedge Part 2: completion + demo)
- [[bupi]], [[cos]], [[crus]], [[srup]], [[cadastro]] — spatial backbone sources
- [[sce]] — load-bearing data source for Slice B
- [[lidar]] — DGT LiDAR Aveiro source
- [[caop]] — Aveiro município bbox for tile-manifest filter
- [[medallion-layering]] — silver/gold pattern + new `bronze_enrichment` schema
- [[bronze-permissive]] — enrichment writes to bronze, not silver directly
- Office-hours design doc: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-design-20260512-151500.md`
- /plan-eng-review test plan: `~/.gstack/projects/dacostalindo-House4House/manuellindo-feature-phase-7c-scaffolding-skills-eng-review-test-plan-20260512-155850.md`

## 🏁 Milestone

**Milestone 3 Part 1 (Week 18): UC-3 v1 wedge Foundations LIVE.** Spatial backbone + LiDAR + SCE geocoding in place. Wedge differentiator (Atlas Inspector + dev dedup + Slice C LLM extraction + demo) lands in [[sprint-09]]. Developer interviews in flight.
