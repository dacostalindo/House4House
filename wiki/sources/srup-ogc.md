---
title: SRUP OGC API — Constraints & Drivers (modern path)
type: source
last_verified: 2026-05-08
tags: [gis, regulatory, government, ogc-api, multi-layer]
priority: P1
---

## For future Claude

This is a source page about the OGC API Features path for SRUP (Servidões e Restrições de Utilidade Pública), the modern successor to [[srup]]'s legacy per-category WFS. It documents the WS2a + WS2b layer registry (22 layers total), the per-layer page_size/timeout overrides for huge-polygon layers, and the role taxonomy (gate / soft / attr_split / risk / driver). Read this page before editing [pipelines/gis/srup_ogc/srup_ogc_config.py](../../pipelines/gis/srup_ogc/srup_ogc_config.py).

## Source

- **Official name**: SRUP OGC API — Property Constraints + SGIFR Wildfire Drivers via OGC API Features
- **Owner**: government agency (DGTERRITÓRIO)
- **Protocol**: OGC API Features REST (paginated GeoJSON)
- **Base endpoint pattern**: `https://ogcapi.dgterritorio.gov.pt/collections/{srup_*,sgifr_*}/items`
- **License**: open data (CC-BY)
- **Schedule**: manual trigger
- **Status**: modern path; supersedes most of [[srup]]; RAN dual-runs with legacy WFS for parity validation

## Schema

22 bronze tables in `bronze_regulatory` (one per OGC collection):

**WS2a (12 layers, the first wave):**
- `raw_srup_ren_areal`, `raw_srup_ren_linear` — Reserva Ecológica Nacional (areal + linear features)
- `raw_srup_areas_protegidas` — protected natural areas
- `raw_srup_zpe`, `raw_srup_zec` — Zonas de Proteção Especial / Especial Conservação (Natura 2000 sites)
- `raw_srup_defesa_militar`, `raw_srup_defesa_militar_zonas` — military defense + their buffer zones
- `raw_srup_perigosidade_inc_rural` — rural-fire hazard (~410k national features, the biggest layer)
- `raw_srup_sgifr_areas`, `raw_srup_sgifr_linhas`, `raw_srup_sgifr_pontos` — SGIFR wildfire-management features (areal/linear/point)
- `raw_srup_ran_ogc` — RAN dual-run mirror against legacy [[srup]]

**WS2b (10 more layers):**
- `raw_srup_arvores_areal`, `raw_srup_arvores_point` — protected-tree areas + individual trees
- `raw_srup_marcos_geod` — geodesic markers
- `raw_srup_aeronautica` — aeronautical-protection zones
- `raw_srup_aquiferos` — protected aquifers (subset of [[lneg]]'s national aquifer layer)
- `raw_srup_albufeiras` — reservoir-protection zones
- `raw_srup_rede_viaria`, `raw_srup_rede_ferroviaria`, `raw_srup_rede_ferroviaria_estacoes` — road / rail / station network drivers
- `raw_srup_rede_eletrica` — electrical-grid driver

All: EPSG:3763 native; geometry varies (Polygon for areal layers, LineString for linear, Point for point layers).

## Quirks

- **Layer roles** (encoded as a config field):
  - **gate**: hard constraint (RAN, military defense, REN areal/linear) — listing inside is a hard regulatory blocker
  - **soft**: Layer 3 / advisory (some protected-area subsets)
  - **attr_split**: mixed (gate vs. soft depends on attributes)
  - **risk**: wildfire (perigosidade_inc_rural, SGIFR layers) — risk feature, not a hard gate
  - **driver**: network / utility infrastructure (road, rail, electricity) — used as proximity features rather than constraints
- **Per-layer page_size / timeout overrides**:
  - REN areal/linear and RAN have HUGE polygons (~5+ MB per feature). `page_size=10–20`, `timeout=300s` for these — default `page_size=200` causes OOM on the OGC server side.
  - Other layers use defaults (page_size=200, timeout=120s).
- **perigosidade_inc_rural is the largest single layer** (~410k national features). Other layers typically <10k.
- **RAN dual-run with legacy [[srup]]**: bronze tables coexist (`raw_srup_ran` from WFS, `raw_srup_ran_ogc` from this pipeline). dbt parity macro at `dbt/macros/gis_dual_run_count_parity.sql` compares counts and bounding boxes. Once parity holds, legacy WFS path decommissioned.
- **SGIFR layers** are separate from the SRUP framework strictly speaking (Sistema de Gestão Integrada de Fogos Rurais = wildfire-management system) but DGTERRITÓRIO co-publishes them under the same OGC API. Listing-feature engineering for fire risk uses these alongside `perigosidade_inc_rural`.
- **Cross-source role**: see [[srup]]. OGC version is the strategic future — broader coverage (22 layers vs WFS's 3), cleaner pagination, per-layer tuning. WFS will be retired post-parity.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read; 22-layer registry confirmed; new pipeline post-PR 1 work).
