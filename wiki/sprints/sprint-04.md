---
title: Sprint 4 — Image Classification + Location Scores
type: plan
last_verified: 2026-05-09
tags: [sprint, plan, image-classification, location-scores, sce, weeks-7-8]
status: in_progress
sprint_number: "4"
weeks: "7-8"
last_status_update: 2026-05-09
---

## For future Claude

This is the **Sprint 4** page (Weeks 7-8): Claude Vision-based image classification (rendered/needs-renovation/habitable + finish quality), floor-plan extraction, transport + POI proximity scoring (crow-flies), and the [[sce]] energy-certificate pipeline (only nodriver scraper in stack). In progress: Aveiro municipality classified (1,330 listings); production scale-up to all municipalities pending. Read this page when you need to know how the listing-enrichment + location-feature work was done before hedonic modelling (Sprint 5).

## Goal

Build out two independent feature sets on top of `silver_properties.unified_listings`: (1) Claude Vision classification of listing images (condition, finish quality) + floor-plan room extraction; (2) location-proximity scores (transport, POI amenities, crow-flies KNN). Plus build the [[sce]] energy-certificate pipeline + silver model as ground-truth unit-count source. OSRM drive-time integration deferred — crow-flies proximity is sufficient for MVP hedonic.

## Deliverables

- ✅ Transport stops model: [[osm]] fclass → `stop_type` (50K rows from point + polygon layers), spatial join → `geo_key`, source/source_id columns, reproject to EPSG:3763 → `silver_location.transport_stops`
- ✅ OSM POIs model: group fclass → `category` (food, health, education, ...), spatial join → `geo_key` (304K rows from point + polygon layers) → `silver_location.pois`
- ✅ Model comparison: Haiku vs Sonnet on 6 sample images. Sonnet selected for all features (better at condition/finish nuance). Haiku adequate only for render detection
- ✅ Image classification — Aveiro municipality (1,330 listings). Sonnet, 3 images per listing (tag-based selection: kitchen/bathroom → facade → livingRoom). Distribution: renovated 75%, habitable 9%, needs_renovation 16%. Confidence floor 0.70 → `bronze_listings.image_classifications`
- ✅ Floor-plan extraction — Aveiro municipality (1,056 plans, 625 properties). Room names standardized in Portuguese (sala, quarto_1, cozinha, wc_1, etc.) → `bronze_listings.floor_plan_extractions`
- ✅ Human validation survey: Portuguese HTML survey for 50 random classified listings. `analyze_survey.py` for evaluator-vs-truth comparison. `prompt_engineer.py` agent analyzing edge cases
- ✅ Prompt engineering initial pass: 15 edge cases analyzed; habitable/renovated boundary confusion + standard/premium ambiguity flagged. `revised_prompt.txt` saved (pending survey results before applying)
- ✅ dbt integration — CV classifications: `stg_image_classifications` view + LEFT JOIN in `unified_listings` → 7 cv_* columns. Replaced regex `is_new_development` with `is_new_development_combined` (= `cv_is_render`, source of truth) — reclassified 413 listings
- ✅ dbt integration — floor plan rooms: `stg_floor_plans` + `silver_properties.floor_plan_rooms` star schema (one row per room per plan image, 2,454 rows). `room_category` mapping (bedroom, bathroom, living_room, kitchen, hallway, balcony, storage, garage, office). Removed denormalized columns; join via `property_id = source_listing_id`
- ✅ [[sce]] scraping framework: reusable scraping ingestion template (nodriver backend + BrowserContext + adaptive circuit breaker). `sce_scraper.py` with in-browser JS extraction, parish-level query partitioning, Cloudflare Turnstile bypass
- ✅ [[sce]] pipeline + config: 3 regions (Aveiro, Coimbra, Leiria), bronze table schema, JSONL → PostgreSQL dedup, MinIO integration, downstream DAG triggering
- ✅ [[sce]] dbt staging: `stg_sce_pce` (deduplicated by `doc_number`, parsed dates, normalized municipality/parish, `is_pce` flag for pre-certificates vs final)
- ✅ [[sce]] ingestion (3 districts): 135,785 PCE records → `bronze_regulatory.raw_sce_pce`
- Pending: [[sce]] extend scraper to ingest Certificados (CE). Change `DOC_TYPE_PCE` → `DOC_TYPE_ALL`. Captures CEs (construction-complete dates) + DCRs alongside PCEs. CE `issued_date` enables `construction_duration_months` in `development_lifecycle`. +30-50K records expected
- Pending: prompt iteration v2 — apply revised prompt after survey feedback, bump `CURRENT_PROMPT_VERSION` to 2, re-trigger DAG, `dbt build --full-refresh`
- Pending: scale classification to all municipalities. `TARGET_CONCELHOS = None`, ~14K remaining listings across Aveiro/Coimbra/Leiria. Estimated cost ~$350 (Sonnet) + ~$162 (floor plans). Run time ~8-10h
- Pending: transport proximity scores (crow-flies) — 5× LATERAL KNN joins on `transport_stops`, exponential decay with per-mode variable decay → `gold_analytics.property_location_scores`
- Pending: POI amenity proximity scores — LATERAL joins on `pois` (nearest school/hospital/supermarket/park within 500m/1km; POI density as walkability proxy)
- Pending: composite `overall_location_score` (weighted transport + amenity)
- Deferred to Sprint 8: drive-time via [[osm]] OSRM (batch routing listing → city center / airport / hospital). Crow-flies sufficient for MVP hedonic
- Pending: Kepler.gl data explorer prototype (`apps/pages/1_investment_map.py`) — wire to real warehouse data, 4 layers (sale listings colored by €/m², PDM zoning, [[bupi]] parcel outlines, [[cos]] level-1 land-use). Municipality dropdown filter, ~3K features/layer, `ST_SimplifyPreserveTopology`. Shared `apps/db.py` connector

## Exit criteria

Image classification pipeline operational with Claude Vision; cv_* columns populated in `unified_listings`. Transport + amenity proximity scores computed for all listings. Floor plan room dimensions extracted. [[sce]] pipeline built and silver models (`sce_certificates`, `new_developments`) operational with ground-truth unit counts per development.

## Key decisions

- **Render = source of truth for new development.** CV `is_render` replaces [[idealista]]'s regex-based `is_new_development` flag. 413 listings reclassified (31% of classified sample). Combined as `is_new_development_combined`.
- **Floor plans as star schema detail table.** `floor_plan_rooms` is standalone (not embedded in `unified_listings`) because plans are 1:N per property. Idealista fields remain source of truth for property-level attributes (typology, num_rooms, area).
- **No confidence threshold needed.** Model confidence floor is 0.70, median 0.90/0.85. No filtering required.
- **Incremental strategy unchanged.** Use `dbt build --full-refresh` after prompt version bumps (not worth adding incremental filter complexity for a manual workflow).
- **Aveiro municipality first.** Scoped initial run to 1,330 listings to validate pipeline before scaling to all 3 districts (~15K).
- **[[sce]] as ground-truth unit count source.** Each PCE = one fraction/apartment. Grouping by normalized address gives accurate unit count per development — replaces listing-cluster estimation in `competitive_developments` (Sprint 7). [[sce]] also provides construction-to-market lifecycle: PCE date (start) → CE date (complete) → listing appearance (on market).
- **[[sce]] geographic join via text matching.** SCE portal dropdown codes are not DTMNFR codes. Geographic assignment uses `UPPER(TRIM(municipality))` text match to `dim_geography.concelho_name`. Geocoding via Nominatim deferred to Sprint 9 for spatial-join upgrade.

## Status update history

- 2026-Q1: declared in README §12; status `planned`
- 2026-Q2: `planned` → `in_progress` (transport stops + POIs models shipped; Aveiro pilot started)
- 2026-Q2: still `in_progress` (Aveiro classification + floor-plan extraction shipped; [[sce]] pipeline live; production scale-up + proximity scores + Kepler.gl pending)

## See also

- [[osm]], [[idealista]], [[sce]], [[bupi]], [[cos]] — sources used
- [[zenrows-universal-vs-re-api]], [[payload-cache-lifecycle]] — relevant for [[idealista]] image-fetching
- [[medallion-layering]] — silver/gold pattern this sprint extends
- [[sprint-03]] — predecessor (silver layer + UC-3 GIS foundation)
- [[sprint-04.4]] — successor (Pre-Sprint-4.5 prep, ran in parallel)
- [[sprint-05]] — downstream consumer (hedonic model needs cv_* + location scores + SCE)
