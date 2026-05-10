---
title: Risk register & mitigation
type: plan
last_verified: 2026-05-10
tags: [planning, risks, mitigation, plan]
---

## For future Claude

This is the **risk register** — 15 identified risks with probability + impact + mitigation, decomposed from README §14. Read this at every sprint close (revisit each risk's status), when a risk's mitigation gets actioned, or when scoping a new sprint that touches a known risk. Risks with `prob=High` AND `impact=High` are sprint-blockers; everything else is monitored.

## What it is

A living risk register. Each row tracks one identified failure mode + its probability + its potential impact + the locked mitigation. Status implicit (no separate column today; see "Mechanic" below for proposed format).

The register is decomposed from README §14 verbatim. As Phase 1-3 work has shipped, some risks have become realized + mitigated (R6 server-failure mitigated by `pg_dump` daily; R5 Nominatim quality observed acceptable in early Phase 1 work) and some have evolved (R9 CRUS coverage limit being addressed by [[crus-ogc]]'s national OGC API path). The register here is the as-of-2026-05-10 state.

## Register

| # | Risk | Prob. | Impact | Mitigation | Status (2026-05-10) |
|---|---|---|---|---|---|
| **R1** | [[idealista]] API rate limits too restrictive | Med | High | Apply for higher tier; cache unchanged listings via [[payload-cache-lifecycle]]; supplement with [[remax]] | **active** — payload cache shipped; listings stable; no rate-limit incidents observed |
| **R2** | Imovirtual blocks scrapers | High | Med | Rotating proxies + user agents; reduce frequency; explore partnership | **deferred** — Imovirtual not in current ingest scope; revisit if added in P3+ |
| **R3** | Hedonic R² < 0.70 without noise/flood features | Med | High | Add interaction terms; try Random Forest; segment by concelho; increase comp weight | **monitored** — Sprint 5 builds the model; this risk gates [[UC-1]] M1 |
| **R4** | CI license too expensive | Med | Low | INE + listing data sufficient for MVP; CI is enrichment | **mitigated** — MVP scope avoids CI; deferred to P3+ if budget opens |
| **R5** | [[osm]]-based Nominatim geocoding quality issues | Low | High | Fallback: Google Maps API; build Portuguese address normalization | **observed acceptable** — Sprint 1 + 2 geocoding ≥ 95% to freguesia; primary risk closed |
| **R6** | Server failure / data loss | Med | High | Daily `pg_dump` + MinIO backup to Hetzner Storage Box | **mitigated** — backups operational from Phase 1 ship; cron in [[orchestration]] schedule |
| **R7** | InfoEscolas JS-heavy, breaks scraper | Med | Low | Education score stays NULL; model handles gracefully | **deferred** — InfoEscolas in P1 / Sprint 7 scope; not yet implemented |
| **R8** | RNAL scraping blocked | Med | Med | Use Inside Airbnb as STR proxy; submit FOI request | **deferred** — RNAL in P1 / Sprint 7 scope; not yet implemented |
| **R9** | [[crus]] coverage limited to 5 municipalities | High | High | Expand CRUS WFS queries to more municipalities; use [[cos]] as fallback for zoning | **partially mitigated** — [[crus-ogc]] national OGC API now ingested for ~236k features; dual-runs for parity; legacy [[crus]] WFS to be decommissioned post-validation |
| **R10** | Sentinel-1 SAR processing complexity + skills gap | Med | Med | Start with building footprints (P1); SAR is enrichment (P2), not blocking. May need remote sensing contractor. | **deferred** — SAR is P3+ scope per [[roadmap-p3-p4]] |
| **R11** | [[bupi]] parcel boundaries are declaration-based (not surveyed) | Med | Low | Acceptable for analytical screening; formal [[cadastro]] (S44) validates specific sites | **acknowledged** — silver-layer cascade strategy (BUPI primary, Cadastro fallback) per [[bupi]] page |
| **R12** | Spatial join performance at scale (3.25M [[bupi]] × 784K [[cos]] × 5M building footprints) | Med | High | Pre-filter BUPI to CRUS municipality extents (~500K parcels); materialize intermediate tables; partition by municipality | **monitored** — [[2026-05-10-postgis-as-warehouse]] + 128 GB RAM design assumes hot working set; re-validate at sprint-04.5 + sprint-08 |
| **R13** | Building footprint false positives/negatives (ML quality) | Med | Med | Acceptable for screening; flag low-confidence matches; specific sites verified via aerial imagery | **deferred** — building footprints in Sprint 9 P1 |
| **R14** | [[cos]] 2023 temporal lag (2-3 years old) | Med | Med | Land classified as vacant in 2023 may already be developed. SAR (P2) partially mitigates; building footprints (P1) provide more recent signal | **acknowledged** — model surfaces "as of COS 2023" caveat; trigger for COS 2028 ingest when available |
| **R15** | [[UC-3]] economics model depends on [[UC-1]] hedonic model | High | High | Sprint 9 economics task blocked until UC-1 complete. Fallback: use INE average €/m² by municipality | **acknowledged** — explicit dependency tracked in [[UC-3]] page Dependencies section |

## Status enum (proposed)

For risk-register maintenance going forward, propose:

- `active` — risk is real today; mitigations are in motion or in steady-state
- `monitored` — risk is plausible but not realized; revisit each sprint
- `deferred` — risk relates to scope not yet entered; revisit when scope opens
- `partially_mitigated` — original mitigation in motion + still progressing
- `mitigated` — risk's primary mitigation is operational; risk closed for current scope
- `acknowledged` — risk is real but accepted (cost of full mitigation > cost of risk realization)
- `realized` — risk has materialized; mitigation activated; track resolution
- `obsolete` — risk no longer applies (scope change, environmental change)

`/wiki-lint` could check that every active/monitored/realized risk has a `last_revisited:` date < 90 days. (Phase 4e or later — captured as candidate enhancement.)

## Mechanic — when does this page get updated?

- **Sprint close** — sweep all rows; flip realized risks; flip mitigated risks; add new rows for risks surfaced during the sprint.
- **Risk realization** — flip status to `realized`; document mitigation activation in the row's status cell.
- **Mitigation completion** — flip status to `mitigated`; trim status cell to single-sentence summary.
- **PR-level** — when a PR closes a risk's primary mitigation, the PR description should reference this page and propose the row update.

## See also

- [[resources]] — companion planning page; effort estimates that some risks could threaten
- [[milestones]] — Go/No-Go criteria where realized risks could trigger hard-fail conditions
- [[roadmap-p3-p4]] — deferred sources where some risks live (R7, R8, R10, R13)
- [[UC-1]], [[UC-2]], [[UC-3]] — use-case pages where R3, R12, R15 land directly
- [[crus-ogc]], [[idealista]], [[bupi]], [[cos]] — sources called out in specific risks
- [[2026-05-10-postgis-as-warehouse]] — the architecture context for R12 (spatial-join performance)
- README §14 — the canonical source for this content
