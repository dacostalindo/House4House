---
title: Sprint 9 — Enhancements + Production Hardening
type: plan
last_verified: 2026-05-09
tags: [sprint, plan, hardening, monitoring, weeks-19-20]
status: planned
sprint_number: "9"
weeks: "19-20"
last_status_update: 2026-05-09
---

## For future Claude

This is the **Sprint 9** page (Weeks 19-20): production hardening + the deferred items from earlier sprints. Brings in Imovirtual (deferred from Sprint 3), RNAL, INE Building Permits, REN (SRUP Phase 2), ARU boundaries; recalibrates hedonic + UC-3 with the new features; geocodes [[sce]] addresses via Nominatim (replacing fuzzy text matching with proper spatial joins); ships data-quality monitoring + documentation.

## Goal

Close out the loose ends. Add the second listing portal ([[idealista]] is the only one in scope before Sprint 4.5; Imovirtual scraper, separate from the dlt-driven [[remax]]/[[zome]]/[[jll]] portals, was deferred from Sprint 3). Add ARU + REN + building permits as feature inputs. Retrain hedonic + UC-3 models with the additional inputs. Geocode [[sce]] for spatial joins. Stand up data-quality monitoring + documentation.

## Deliverables

- ARU boundaries (S20) — Urban Rehabilitation Areas → spatial overlay with listings + development sites. `silver_geo.zoning` gets `is_aru` flag; `gold_analytics.development_sites` gets `aru_overlap_pct`
- Imovirtual scraper (S05) → second listing portal live → `bronze_listings.raw_imovirtual`
- Cross-portal dedup: hash(address + area + typology) matching, fuzzy fallback → `silver_properties.unified_listings.property_hash`, `silver_properties.listing_matches`
- RNAL scraping (S14) — AL license registry → `bronze_listings.raw_rnal`
- INE Building Permits (S21) — permit data → active construction validation for UC-3 → `bronze_ine.raw_building_permits`, `stg_building_permits`
- REN ingestion (SRUP Phase 2 via [[srup-ogc]]) — Ecological Reserve → `ren_flag` on sites → `bronze_regulatory.raw_srup_ren`, `stg_srup_ren`
- Recalibrate hedonic model v2: add OSRM travel times (from Sprint 8) + ARU flag to feature vector; retrain → refreshed `gold_analytics.hedonic_features`, `property_valuation`
- UC-3 model recalibration: incorporate ARU + REN + permits into `opportunity_score` → refreshed `gold_analytics.development_sites`
- CI data integration (if license obtained, S02): transaction prices → validate hedonic predictions, calibrate gap %
- [[sce]] geocoding via Nominatim: geocode distinct SCE addresses through Nominatim → add coordinates to `sce_certificates`. Enables direct spatial joins (eliminates fuzzy text matching). New Airflow DAG `sce_geocode_dag`. Dramatically improves SCE-to-listing match rate. Adds `latitude`, `longitude`, `geom`, `geom_pt` to `silver_properties.sce_certificates`
- [[sce]]-to-listing match quality audit: sample-based validation of fuzzy address matching (match rate by municipality, false-positive analysis, similarity-score distribution). Informs threshold tuning for `unified_listings` enrichment
- Data quality monitoring: dbt tests + source freshness alerts + row count anomaly detection on every model
- Documentation: data dictionary + user guide + lineage diagrams

## Exit criteria

Second listing portal live; hedonic model v2 deployed; UC-3 enriched with ARU + REN + permits; SCE geocoded with spatial joins replacing text matching; production monitoring in place.

## Key decisions

- Imovirtual ships LAST among portals — JLL/RE/MAX/Zome/Idealista are the canonical 4; Imovirtual was originally planned earlier but pushed because its non-API scraping shape (Selenium/HTML-only) is high-friction relative to the dlt-driven portals
- Hedonic v2 retrain triggered by OSRM drive-times + ARU; not a fundamental architecture change, just a feature-vector expansion
- [[sce]] geocoding upgrade (text matching → spatial join) is a quality-of-life improvement; deferred from Sprint 4 because text matching was sufficient for Aveiro pilot
- CI data integration is licensee-gated; if commercial license fails, stays as a "deferred indefinitely" gap

## Status update history

- 2026-04-18: declared in README §12; status `planned`

## See also

- [[idealista]], [[sce]], [[srup]], [[srup-ogc]], [[osm]], [[ine]] — sources
- [[medallion-layering]], [[scd2-row-hash]], [[bronze-permissive]] — concepts applied
- [[sprint-08]] — predecessor (OSRM drive-time landed there; ARU/REN/permits queued for here)
- Phase 4 (gstack dev-tooling roadmap, see [[sprint-dev-tooling]]) — `wiki_health.py` + CI/CD work overlaps with this sprint's data-quality monitoring
