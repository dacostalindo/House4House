---
title: SCE buildings clustering — DBSCAN + normalized-address grouping for the silver_sce_buildings model
type: concept
last_verified: 2026-05-17
tags: [sce, buildings, clustering, dbscan, silver, spatial, concept]
---

## For future Claude

This is a concept page about how SCE energy certificates get rolled up into **per-building rows** in [[silver_sce_buildings]]. It locks the v1 design decisions for sprint-09 Slice B: DBSCAN spatial clustering at 30m + within-cluster GROUP BY on `normalized_address`, with no parcel join and no Levenshtein fuzzy matching. Read this before editing the model SQL, the schema YAML, or adding new pgTAP tests. The key v1 simplification: **the model is a same-source within-30m clusterer**, not a probabilistic record linker. Splink / Dedupe / Levenshtein are deferred — empirical 0% leakage at 6k rows from the [[sce|Appendix A]] normalizer makes the deterministic GROUP BY sufficient.

## What it is

`silver_sce_buildings` rolls up [[sce]] energy certificates (one per fraction/apartment) into **one row per physical building**, exposing aggregates that the v1 wedge demo's polygon-assessment surface needs: `frac_count` (≈ units), `energy_class_dist` (JSONB histogram across A+ / A / B / B- / C / D / E / F), `first_emission` / `last_emission` dates, `dominant_state`, `cluster_geocode_confidence`, and `member_doc_numbers` for traceability.

The grain change is real: bronze has ~280k certificates across the loaded distritos; silver has ~12.6k buildings. The mean ~1.66 certificates per building reflects the typical PT condo pattern (several fractions per building).

It's consumed by sprint-09's [[2026-05-12-uc3-expanded-scope|gold.fn_assess_polygon]] via `ST_DWithin(cluster_geom_3763, input_geom, 500)` for the Atlas Site Inspector's "Nearby SCE Developments" panel.

## Why

The polygon-assessment use case needs **building-grained** answers, not certificate-grained. A user draws a polygon over a city block and asks "what's been built here?" The answer "47 certificates" is unintelligible; "12 buildings, 47 units, mostly A-class, built 2018–2024" is the demo. That roll-up is what this model does.

The clustering layer is needed because the raw SCE address text is too noisy to GROUP BY: typographic variance ("Rua Dr. Mário Sacramento" vs "r. dr mario sacramento"), inconsistent fração markers, diacritic differences. The Appendix A normalizer ([pipelines/enrichment/sce_address_norm.py](pipelines/enrichment/sce_address_norm.py)) collapses 44.2% of these mechanically. ST_ClusterDBSCAN handles the residual cases where two certs at the same building have addresses the normalizer can't unify — e.g. "Rua X 12-A" vs "Rua X 12 (R/C)".

## How

The pipeline lives in [dbt/models/silver/regulatory/silver_sce_buildings.sql](dbt/models/silver/regulatory/silver_sce_buildings.sql). Read sequentially through the CTEs:

1. **`nominatim_hits`** — filter `stg_sce_certificates` to `geocode_source = 'nominatim'`. This is the **Decision 1** cut: freguesia-centroid rows share an exact coordinate per parish (~5,800 rows of Aveiro distrito), which DBSCAN(eps=30m) would collapse into a single per-parish "mega-cluster." Those rows are NOT lost — they remain queryable via `stg_sce_certificates` directly and can surface in the Inspector as a separate "parish-level" badge.

2. **`clustered`** — `ST_ClusterDBSCAN(geom_3763, eps := 30, minpoints := 1) OVER ()` assigns a `cluster_id` per row. With `minpoints=1` DBSCAN behaves as single-linkage hierarchical clustering: two points share a cluster iff there's a chain of points within 30m connecting them.

3. **`energy_class_per_building`** + **`energy_class_dist_per_building`** — separate sub-pipeline producing the JSONB histogram. Built before the main `buildings` CTE to keep that one flat: `jsonb_object_agg` of `(energy_class, count)` per `(cluster_id, normalized_address)`. NULL `energy_class` members are excluded (don't inflate any bucket).

4. **`buildings`** — the grain-change. `GROUP BY (cluster_id, normalized_address)`. This is **Decisions 2 + 5** combined:
   - Decision 2: GROUP BY exact normalized_address rather than Levenshtein-ratio ≤ 0.15. The 6k-row leakage scan at Slice B Phase 1 showed 0% leakage — the normalizer is aggressive enough that fuzzy matching is gilding the lily AND adds O(n²) cost per cluster.
   - Decision 5: address-grouping (not pure coord clustering). At 30m eps in dense urban grids, two adjacent-but-distinct buildings ("Rua X 12" + "Rua X 14", 20m apart) can DBSCAN together; the address split rescues them. Trade-off: multi-frontage buildings (one building, two street entrances at the same coord) get incorrectly split into 2 rows. We accept this for v1 because suburban Aveiro adjacent-buildings >> multi-frontage; one-line v1.5 reversal path if dev interviews surface false-splits.

5. **Final SELECT** — `ROW_NUMBER() OVER (ORDER BY cluster_id, normalized_address)` assigns `sce_building_id`. Both geometries are emitted: `cluster_geom_3763` (PT-TM06, for spatial joins) and `cluster_geom_4326` (WGS84, for Kepler.gl display). `MIN(geocode_confidence)` propagates the worst member's confidence to the building level — surfaces fuzzy clusters honestly in the Inspector UI.

### Design Decisions 3 and 4 — what's NOT in the SQL

- **No parcel_id / cluster_split** (Decision 3 / "Option B" retire): the original spec called for joining each SCE point against [[parcel-universe]] via `ST_Within` and tiebreaking via "most rows wins, smaller area, cluster_split=TRUE on ties." Empirical reality: **97.7% of Nominatim-geocoded SCE points fall on street centerlines outside any cadastral parcel** (50-200m typical gap). The semantics of "the parcel this building is on" don't work with street-level geocoding; the spec was wrong. The Atlas Inspector can join `parcel_universe` at query time when it wants per-parcel context. Test #11 was retired with this decision.
- **No Splink / probabilistic record linkage** (Decision 4): the within-30m blocking + 0%-leakage normalizer make probabilistic matching overkill for Slice B's same-source same-distrito problem. Splink is plausibly the right tool for [[2026-05-12-uc3-expanded-scope|silver_sce_building_listing_hints]] (cross-source SCE ↔ idealista dedup) — re-evaluate there.

### Verification

Tests #7-#10 ([tests/sql/sce_buildings_*.sql](tests/sql/)) — pgTAP, self-contained TEMP fixtures + inlined replica of the pipeline. Cover DBSCAN clustering, address dedup, `frac_count` conservation, `energy_class_dist` completeness. Run via [pg_prove on CI](.github/workflows/ci.yml).

Locally: `dbt build --select silver_sce_buildings` against the warehouse (5.11s for 12.6k buildings). dbt's own schema tests (unique + not_null on `sce_building_id`, not_null on geoms / `frac_count` / `cluster_geocode_confidence` / `member_doc_numbers` / `_built_at`) cover the structural invariants.

## See also

- [[sce]] — the source, including Appendix A normalizer spec
- [[parcel-universe]] — the parcel layer we deliberately did NOT join against (street-vs-plot geocoder gap)
- [[2026-05-12-uc3-expanded-scope]] — the v1 wedge decision that frames where `silver_sce_buildings` lives
- [[medallion-layering]] — bronze → staging → silver → gold convention this model follows
- [[bronze-permissive]] — why the geocoding output lives in a sibling `bronze_enrichment` schema rather than mutating `bronze_regulatory.raw_sce_certificates`
- [[sprint-08]] Activity 7 — the geocoding pipeline that produced `bronze_enrichment.raw_sce_geocoded`
- [[sprint-09]] Slice B — the body-fill work this concept page documents
