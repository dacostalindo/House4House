---
title: Nominatim + OSRM self-hosted (not Google Maps APIs)
type: decision
last_verified: 2026-05-10
tags: [geocoding, routing, nominatim, osrm, decision]
confidence: high
---

## For future Claude

This is a decision record about self-hosting Nominatim (geocoder) + OSRM (routing engine), rejecting Google Maps Geocoding + Distance Matrix APIs. Both run as Docker services derived from the same [[osm]] PT extract. Read this before adding a new geocoded source, scoping a routing-heavy feature, or considering a GDPR / cost migration.

## Decision

Geocoding via **Nominatim 4.4** (Docker container, port `8088`), routing via **OSRM** (3 profiles on ports `5050` / `5051` / `5052` for car / walking / cycling). Both built from the same `portugal-latest.osm.pbf` extract. Self-hosted on the same Hetzner box as Postgres + MinIO (per [[infra]]).

## Why

1. **Cost — the load-bearing claim.** Bulk geocoding ~500k listings via Google Maps Geocoding API: ~$5/1000 = ~$2,500. Daily re-geocoding of new listings + UC-3 parcel reverse-geocoding: ~$200/month. Bulk drive-time isochrone queries via Distance Matrix: ~$5/1000 trips × thousands per UC-1 location-score recompute = ~$50-200/run. Total annualized: ~$3,000-5,000. Self-hosted: ~€0 incremental.
2. **No API-rate-limit drama.** Nominatim self-hosted: unlimited (rate-limited only by our own CPU). OSRM self-hosted: same. Google Maps APIs: per-second + per-day quotas that complicate batch operations + force backoff/retry logic in pipelines.
3. **GDPR-clean.** Listings + parcel addresses are personal-data-adjacent (residential properties). Sending them to Google Maps APIs creates a third-party data-flow that requires DPA + processing-record updates. Self-hosted = no third party.
4. **OSM-native means same source as [[osm]].** [[osm]]'s POIs / roads / buildings layers and Nominatim's geocoding both come from the same Geofabrik PT extract. Cross-consistency is automatic; we don't have to reconcile "Google says address X is at lat/lon Y but our parcel-spatial-join uses OSM geometry that puts X at Y'."

## Options considered

1. **Nominatim + OSRM self-hosted** (chosen).
2. **Google Maps Geocoding + Distance Matrix** — rejected on cost + GDPR + rate-limits.
3. **MapBox Geocoding + Directions** — same shape as Google. Cheaper but still per-request. Rejected for similar reasons.
4. **Pelias** (open-source geocoder, OSM-derived) — alternative to Nominatim. More features (autocomplete, fuzzy address matching) but heavier ops footprint. Nominatim 4.4 covers our needs; rejected as overkill.
5. **Valhalla** (open-source routing, alternative to OSRM) — OpenStreetMap-derived, similar shape. OSRM has more mature `mld` algorithm + simpler ops; Valhalla's truck-routing features irrelevant for residential use cases. Rejected for now.

## Consequences

- Nominatim first import takes ~30-45 minutes on a fresh PT extract (per [[osm]]). Subsequent restarts are fast (data persisted on `nominatim_data` Docker volume).
- OSRM build takes ~10-15 minutes per profile (`osrm-extract` + `osrm-partition` + `osrm-customize` + `osrm-contract`). Three profiles run in parallel; total ~20 min.
- Both services rebuilt monthly when [[osm]] ingest pulls a new PBF.
- Pipeline integration: Airflow `dag_geocoding` queries Nominatim on `:8088`; UC-1 location-scoring DAG queries OSRM on `:5050-5052`. Both via internal Docker network — no external traffic.
- A future migration to a managed geocoder is a config-change (point `NOMINATIM_BASE_URL` at the new endpoint); reversibility is preserved.
- Single-server failure mode: if the host dies, geocoding + routing stop. Acceptable for current operations posture; no SLA requirement.

## Status

`accepted` — Phase 1 baseline holds; Nominatim + OSRM both stable through Phase 2 + 3 work.

## See also

- [[2026-05-10-single-server-self-hosted]] — the broader self-hosted posture
- [[osm]] — the source extract that feeds both services
- [[ingest-flows]] — Flow-B + Flow-D both depend on Nominatim
- [[orchestration]] — `dag_geocoding` + UC-1 location-score DAG cadence
- [[infra]] — Docker Compose service map (Nominatim + OSRM)
- [[tech-stack]] — primary stack table
- README §3.1 + §3.2 — the canonical source for this content
