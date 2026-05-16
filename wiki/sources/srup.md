---
title: SRUP — Property Constraints (legacy WFS — slimmed to IC + DPH)
type: source
last_verified: 2026-05-13
tags: [gis, regulatory, government, wfs, legacy, slimmed]
priority: P1
---

## For future Claude

This source page documents the legacy WFS path for SRUP (Servidões e Restrições de Utilidade Pública — property constraints), slimmed on 2026-05-13 to the **two categories DGT does not publish via OGC API**: IC (heritage sites) + DPH (public water domain). RAN moved to [[srup-ogc]] the same day. The pipeline at `pipelines/gis/srup/` still exists and runs for IC + DPH. Read this page before editing [pipelines/gis/srup/srup_config.py](../../pipelines/gis/srup/srup_config.py) or before integrating SRUP constraints into [[sprint-08]] Activity 6 (`silver_geo/parcel_constraints`).

## Source

- **Official name**: SRUP — Servidões e Restrições de Utilidade Pública (Public-Utility Easements and Restrictions)
- **Owner**: DGTERRITÓRIO
- **Protocol**: WFS 2.0.0 (GeoJSON output)
- **Base endpoint pattern**: `https://servicos.dgterritorio.pt/SDISNITWFS{SRUP_IC_PT1,SRUP_DPH_PT1}/WFService.aspx`
- **License**: open data
- **Schedule**: manual trigger
- **Status**: active for IC + DPH only. RAN retired 2026-05-13 — now served by [[srup-ogc]] (collection `srup_ran`). All other SRUP layers (REN, áreas protegidas, ZPE, ZEC, defesa militar, perigosidade incêndio rural, SGIFR, etc.) are published exclusively via OGC API and live in [[srup-ogc]].

## Schema

Two bronze tables (post-slim):

- `bronze_regulatory.raw_srup_ic` — Imóveis Classificados (~3,676 heritage sites; ~21 fields including CLASSIFICACAO, DESIGNACAO, LEI_TIPO, TUTELA, SERVIDAO)
- `bronze_regulatory.raw_srup_dph` — Domínio Público Hídrico (~7 features; ~18 fields)

Both: geometry = Polygon / MultiPolygon, EPSG:3763 (PT-TM06).

Retired 2026-05-13:

- `bronze_regulatory.raw_srup_ran` — replaced by `bronze_regulatory.raw_srup_ran_ogc` from [[srup-ogc]]. The legacy table is NOT dropped from PostgreSQL — leave for ad-hoc historical queries. To physically drop: `DROP TABLE bronze_regulatory.raw_srup_ran`.

## Quirks

- **Field normalization**: strip diacritics on ALL field names (`SERVIDÃO` → `SERVIDAO`). Without this, downstream models break (postgres column quoting on accented names is a footgun). Both IC and DPH follow the same convention.
- **DPH is suspiciously small** (~7 features nationally) — may be incomplete relative to the regulator's actual hydric-domain registry. Worth verifying against DGT's portal periodically; if the count jumps significantly between runs, that's the upstream catching up rather than drift in our pipeline.
- **JSONB properties by design**: the dlt resource collapses each WFS feature's attributes into a single JSONB column rather than promoting them to typed columns. Field extraction happens in dbt staging via `properties->>'FIELDNAME'` (post-diacritic-stripping).
- **RAN moved to OGC** (2026-05-13): the OGC schema is lowercase snake_case (`municipios`, `servidao`, `designacao`, `tipologia`, `lei_tipo`, `serv_dr`, `serv_data`, `serv_lei`, `serv_hiperligacao`). Note that the OGC drops the WFS's `DINAMICA` / `RIGOR` / `AUTOR` fields and adds richer constraint metadata. See `stg_srup_ran.sql` for the migrated column projection.
- **Why IC + DPH stayed on WFS**: WebFetch on `ogcapi.dgterritorio.gov.pt/collections` 2026-05-12 confirmed the OGC API does NOT publish `srup_ic` or `srup_dph` collections. Only the legacy WFS endpoints carry them. If DGT adds them to the OGC API in the future, this pipeline can also retire.

## Cross-source role

- **IC** = heritage protection (renovations restricted) — severity 4 in `silver_geo/parcel_constraints`.
- **DPH** = water-domain easement (no construction near rivers) — severity 1 (buffer) or 3 (core).

Joining listings × SRUP via spatial intersection produces "regulatory-flag" features consumed by [[2026-05-08-idealista-enrichment-architecture]] silver/gold pipeline and by [[sprint-08]] Activity 6's per-parcel severity classification.

## Last verified

2026-05-13 (slim to IC + DPH; RAN redirected to [[srup-ogc]]).

## See also

- [[srup-ogc]] — OGC API SRUP layers (RAN + REN + áreas protegidas + ZPE + ZEC + defesa militar + perigosidade incêndio rural + SGIFR + …)
- [[sprint-08]] — Activity 6 wires both into `silver_geo/parcel_constraints`
