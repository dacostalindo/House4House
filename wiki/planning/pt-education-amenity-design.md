---
title: PT Education amenity ingest — design (v1)
type: plan
last_verified: 2026-06-06
tags: [plan, education, amenity, gis, ingest, design]
status: scoped-not-built
---

# PT Education amenity ingest — design (v1)

## For future Claude

This page is the **agreed v1 design** for the Portuguese-education geo-amenity layer — education as a dual signal on every listing (**point-proximity to schools** + **area quality**), national coverage. It came out of an interview + a 6-gate verification pass (2026-06-06). The source-level specs + repo-scoped build plans live on the [[gesedu]] and [[infoescolas]] source pages; this page holds the decision tree, the surfacing spec, and the verification results. **Scoped, not built** — no pipeline has run yet.

Spine = the **DGEEC código de escola** (6-digit), the one stable national key unifying location + all quality sources (verified present + consistent across sources).

> **Headline:** the two heaviest branches we feared — geocoding the national register and scraping GesEdu — both **collapsed**. GesEdu is backed by a public ArcGIS REST FeatureServer returning código + agrupamento + street address + **native lat/lon** in one paginated pull, and the repo's unified template already ships an `ArcgisRestAdapter`. So v1 is **1 API pull + 2 file downloads — no scrapers, no geocoding, no name-crosswalk.**

## Decisions (resolved tree)

| Branch | Decision | Reasoning |
|---|---|---|
| **Purpose** | Both point-proximity **and** area-quality | Two distinct buyer questions; kept as separate signals, never blended |
| **Geo scope** | **National** | [[bgri]] + Infoescolas already national; the API pull is national for free |
| **Point source** | **[[gesedu]] ArcGIS FeatureServer** (was: scrape + geocode) | Returns código + address + lat/lon directly — no scrape, no geocode |
| **Quality metric** | **Exam-avg + equity**, separate columns (retention dropped) | "Carry several, decide the user-facing blend later" — minus retention (see deferred) |
| **Quality grain** | **Per-escola** (código join), no agrupamento fallback | Finest grain; basic-only schools carry null exam scores by design |
| **Quality source** | **[[infoescolas]] `bds.asp` bulk XLSX** (through Feb 2025) | Fresh, no scrape (file download). Licence unstated → internal-derived, do not redistribute raw |
| **Area signals** | **BGRI resident attainment** + **aggregated school quality**, distinct columns | Resident-educated vs good-local-schools are different questions |
| **Surfacing** | **Catchment aggregation**, tiered **1 km + 3 km** | Two buckets: coverage (any school) + quality (secundário-with-score) |
| **Level dimension** | **Scored vs unscored** (via `ENSINOS_MIN`/`CICLO`) | Avoids a full level matrix; keeps the score column meaningful |
| **Crosswalk** | **None needed** | BGRI joins spatially; Infoescolas joins by código; retention (the only name-match) dropped |
| **Geocoder** | **Not needed** ([[2026-05-10-nominatim-osrm-self-hosted|Nominatim]] = fallback only) | FeatureServer ships coordinates |

## Tiers

**Tier 1 — School points (spine).** [[gesedu]] ArcGIS REST FeatureServer → `bronze_location.raw_gesedu_schools`. ~8,670 schools, paginated, `outSR=4326`. Dual-CRS per [[2026-05-10-dual-crs-storage]]. See [[gesedu]] for the full field map + build steps.

**Tier 2 — Quality, per-escola.** [[infoescolas]] `bds.asp` bulk XLSX → `bronze_location.raw_infoescolas_quality`. Join to Tier-1 on `codescme = Código Escola DGEEC`. Carry exam-avg + equity as separate columns. Per-escola → basic-only schools null by design.

**Tier 3 — Area signals (distinct columns, not blended).** [[bgri]] Censos 2021 resident attainment (GeoPackage, direct PostGIS, spatial-join to freguesia/subsecção) + aggregated school quality (Tier-2 rolled up to freguesia/concelho — derived, no new source).

## Surfacing on `fact_listing`

Catchment aggregation, **`ST_DWithin(listing.geom_pt, school.geom_pt, {1000,3000})`** in EPSG:3763 (metric) per [[2026-05-10-dual-crs-storage]]. Two buckets:

- **Coverage (any in-service school):** count within 1 km, count within 3 km, distance to nearest.
- **Quality (secundário-with-score):** count within 1/3 km, distance to nearest scored, best score in radius, distance-weighted mean (exam + equity).
- **Area:** BGRI attainment + aggregated school quality of the containing freguesia.

*Distance metric:* straight-line for v1; OSM-network distance via the self-hosted OSRM is a documented later refinement (heavy precompute, marginal gain at neighborhood scale).

## Verification pass — all 6 gates closed (2026-06-06)

1. **Infoescolas has código** — ✅ `Código Escola DGEEC` (6-digit) is the first column; per-UO file has both agrupamento + escola codes.
2. **GesEdu source** — ✅ + upgrade: public ArcGIS FeatureServer with coords (kills scrape *and* geocode).
3. **Infoescolas freshness/licence** — ✅ `bds.asp` bulk to Feb 2025 (no scrape); ⚠️ no stated licence (CC BY 4.0 dados.gov.pt ~2021 copy is the fallback).
4. **código grain aligns** — ✅ same DGEEC 6-digit family across sources.
5. **Regiões em Números / 308 concelhos** — ✅ confirmed (moot for v1 — retention dropped).
6. **Reorg/URL drift** — ✅ AGSE (DL 99/2025) owns GesEdu; EduQA (DL 105/2025) absorbed IAVE; all endpoints live 2026; add liveness check, don't hardcode `.medu.pt`.

Verified endpoints + field maps are saved to project memory (`pt-education-endpoints`).

## Explicitly out of v1 (deferred)

- **Retention/dropout** (Regiões em Números / PORDATA) — dropped; removes the last scraper + the concelho-name crosswalk + the concelho-broadcast complexity.
- **Higher-ed proximity** (DGEEC point shapefile, CC BY 4.0) — cheap to add later; not in the family-buyer signal.
- **[[osm]] school points** — superseded by the authoritative FeatureServer; available as a coverage cross-check.
- **Agrupamento-fallback** for null scores; **OSM-network** catchment distance; **live-portal** scrape.

## Build order

1. [[gesedu]] FeatureServer ingest (bronze → stg → [[caop]] spatial-validate). 2. [[infoescolas]] `bds.asp` → código join. 3. [[bgri]] load + aggregated rollup. 4. `fact_listing` catchment mart.

## See also

- [[gesedu]] / [[infoescolas]] — source pages with full schemas + build scope
- [[crus-ogc]] — the build template (same `ArcgisRestAdapter` path)
- [[bgri]] — resident-attainment area signal
- [[spatial-strategy]] · [[2026-05-10-dual-crs-storage]] — CRS + catchment conventions
