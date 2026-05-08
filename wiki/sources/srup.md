---
title: SRUP — Property Constraints (legacy WFS)
type: source
last_verified: 2026-05-08
tags: [gis, regulatory, government, wfs, legacy]
---

## For future Claude

This is a source page about the legacy WFS path for SRUP (Servidões e Restrições de Utilidade Pública — property constraints). It documents the Phase 1 categories (IC heritage / RAN agricultural reserve / DPH water domain), the field-normalization quirks (diacritic stripping), and the upcoming migration to [[srup-ogc]]. Read this page before editing [pipelines/gis/srup/srup_config.py](../../pipelines/gis/srup/srup_config.py).

## Source

- **Official name**: SRUP — Servidões e Restrições de Utilidade Pública (Public-Utility Easements and Restrictions)
- **Owner**: government agency (DGTERRITÓRIO)
- **Protocol**: WFS 2.0.0 (GeoJSON output)
- **Base endpoint pattern**: `https://servicos.dgterritorio.pt/SDISNITWFS{SRUP_IC_PT1,SRUP_RAN_PT1,SRUP_DPH_PT1}/WFService.aspx`
- **License**: open data
- **Schedule**: manual trigger
- **Status**: LEGACY — Phase 2 categories (REN, etc.) live in [[srup-ogc]]; RAN dual-runs against srup-ogc for parity validation; full migration when parity holds

## Schema

Three bronze tables, one per Phase 1 category:

- `bronze_regulatory.raw_srup_ic` — Imóveis Classificados (~3,676 heritage sites; ~21 fields including CLASSIFICACAO, DESIGNACAO, LEI_TIPO, TUTELA, SERVIDAO)
- `bronze_regulatory.raw_srup_ran` — Reserva Agrícola Nacional (~268 features; 7 fields including DINAMICA — note the diacritic-stripped form)
- `bronze_regulatory.raw_srup_dph` — Domínio Público Hídrico (~7 features; ~18 fields)

All: geometry = Polygon / MultiPolygon, EPSG:3763 (PT-TM06).

## Quirks

- **Field normalization**: strip diacritics on ALL field names (`DINÂMICA` → `DINAMICA`, `SERVIDÃO` → `SERVIDAO`). Without this, downstream models break (postgres column quoting on accented names is a footgun).
- **RAN response is huge**: ~360 MB payload despite only 268 features (large polygons, complex geometry). `WFS_REQUEST_TIMEOUT=300s` to accommodate. If you hit 504s, increase the timeout, don't try to paginate (this WFS doesn't support STARTINDEX reliably — same quirk as [[crus]]).
- **Phase 1 = full national fetch**: IC, RAN, DPH all return national results in one request each.
- **DPH is suspiciously small** (~7 features nationally) — may be incomplete relative to the regulator's actual hydric-domain registry. Worth verifying against DGT's portal periodically; if the count jumps significantly between runs, that's the upstream catching up rather than drift in our pipeline.
- **JSONB properties by design**: the dlt resource collapses each WFS feature's attributes into a single JSONB column rather than promoting them to typed columns. Avoids schema coupling to upstream's per-category attribute drift. Field extraction happens in dbt staging via `properties->>'FIELDNAME'` (post-diacritic-stripping).
- **Phase 2 categories not implemented in this WFS pipeline**: REN (Reserva Ecológica Nacional) requires BBOX filtering for regional endpoints (unlike Phase 1's national endpoints). Phase 2 work moved to [[srup-ogc]] which handles paging more cleanly.
- **Cross-source role**: SRUP is the canonical "what regulatory constraints apply to this parcel?" layer. IC = heritage protection (renovations restricted); RAN = agricultural reserve (cannot be developed for housing); DPH = water-domain easement (no construction near rivers). Joining listings × SRUP via spatial intersection produces a "regulatory-flag" feature for [[2026-05-08-idealista-enrichment-architecture]] silver/gold pipeline.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read).
