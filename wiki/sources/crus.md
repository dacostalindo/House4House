---
title: CRUS — Carta do Regime de Uso do Solo (per-município WFS)
type: source
last_verified: 2026-05-08
tags: [gis, regulatory, government, landuse, wfs, legacy]
---

## For future Claude

This is a source page about the legacy per-município WFS path for CRUS (regulatory land-use classification per PDM). It documents the 5-municipality config (Aveiro/Lisboa/Porto/Coimbra/Leiria), the field-normalization quirks (diacritics + Porto's ID1→ID rename), and the planned deprecation in favor of [[crus-ogc]] once dual-run parity validates. Read this page before editing [pipelines/gis/crus/crus_config.py](../../pipelines/gis/crus/crus_config.py).

## Source

- **Official name**: CRUS — Carta do Regime de Uso do Solo (legacy per-municipality WFS)
- **Owner**: government agency (DGTERRITÓRIO)
- **Protocol**: WFS 2.0.0 (per-municipality endpoints, GeoJSON output)
- **Base endpoint pattern**: `https://servicos.dgterritorio.pt/SDISNITWFSCRUS_{code}_1/WFService.aspx`
- **License**: open data
- **Schedule**: manual trigger
- **Status**: LEGACY — being replaced by [[crus-ogc]] (national OGC API path); deprecation pending dual-run parity validation

## Schema

Bronze table: `bronze_regulatory.raw_crus_ordenamento`.

- **ID, DTCC, Municipio, Classe, Categoria** — administrative + classification fields
- **Area_Ha** — polygon area in hectares
- **Designacao_PlantaOrdenamento** — designation per municipal master plan
- **Data_PublicacaoPDM** — date the PDM was published (varies by municipality, important for currency)
- **Fonte, Autor** — provenance fields
- **geometry** — Polygon / MultiPolygon, EPSG:3763 (PT-TM06)

## Quirks

- **5 municipalities only**: Aveiro, Lisboa, Porto, Coimbra, Leiria. Configurable in `crus_config.py`. Each has its own WFS endpoint (per-município, NOT a national index).
- **Field normalization is non-trivial**:
  - Strip diacritics from ALL field names (`DESIGNAÇÃO` → `DESIGNACAO`, `PLANTA_ORDENAMENTO` → unchanged but its label has accents).
  - Explicit rename: Porto's `ID1` → `ID` to match the other 4 municipalities. Without this, downstream models break on the join.
- **No STARTINDEX pagination**: this WFS implementation ignores `STARTINDEX` and always returns the same first-N features. Workaround: each municipality has < 2k features, so a single un-paginated request suffices.
- **Dual-run with [[crus-ogc]]** in progress: bronze tables coexist (`raw_crus_ordenamento` for WFS, `raw_crus_national_ogc` for OGC API). Parity validation in dbt — `dbt/macros/gis_dual_run_count_parity.sql` (per the recent commit) compares feature counts and bounding boxes. Once parity holds, this WFS pipeline is decommissioned.
- **Cross-source role**: CRUS is the regulatory classification of land use per the municipal PDM. It tells you what the local zoning rules say; [[cos]] tells you what the satellite observed. Mismatches between CRUS and COS = regulatory red flags (e.g., residential listing on CRUS-protected land).

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read; dual-run-parity macro present in dbt/macros/).
