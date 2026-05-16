---
title: CRUS — Carta do Regime de Uso do Solo (per-município WFS — RETIRED)
type: source
last_verified: 2026-05-13
tags: [gis, regulatory, government, landuse, wfs, legacy, retired]
priority: P2
status: retired
superseded_by: crus-ogc
---

## For future Claude

This source page documents the **retired** legacy per-município WFS path for CRUS. The pipeline `pipelines/gis/crus/` was deleted on 2026-05-13 after the DGT OGC API was confirmed to publish the same data nationally (collection `crus`). Use [[crus-ogc]] for all new work. This page is preserved as historical record for anyone reading old wiki entries / log lines that reference the WFS endpoints or the per-município normalization quirks.

## Retired 2026-05-13

The pipeline was deleted in the [[sprint-08]] Activity 2 cleanup pass. Reasons:

- **OGC coverage is national** (~236k polygons) vs. WFS's 5 municipalities (Aveiro / Lisboa / Porto / Coimbra / Leiria).
- **OGC schema is richer** — adds `situacao_pdm` and `registo_ou_deposito` columns the WFS path lacked.
- **WFS path had quirky workarounds** (no STARTINDEX pagination, per-município field renames, Porto's ID1→ID rebinding) — all moot post-migration.

Downstream impact at retirement time:

- `dbt/models/staging/regulatory/stg_crus_ordenamento.sql` redirected from `source('bronze_regulatory', 'raw_crus_ordenamento')` → `source('bronze_regulatory', 'raw_crus_national_ogc')`. Column names match 1:1 for the fields the staging model consumes; the two new OGC columns are not yet consumed.
- `silver_geo.zoning` reads `stg_crus_ordenamento` and was unchanged.
- `tests/configs/test_config_equivalence.py` lost its `crus` parametrize entry; the fixture moved to `tests/configs/fixtures/_retired/crus.json` for historical record.
- `bronze_regulatory.raw_crus_ordenamento` PostGIS table NOT dropped — leave for any ad-hoc historical query. To physically drop: `DROP TABLE bronze_regulatory.raw_crus_ordenamento`.

## Historical source spec (pre-retirement)

- **Official name**: CRUS — Carta do Regime de Uso do Solo (legacy per-municipality WFS)
- **Owner**: DGTERRITÓRIO
- **Protocol**: WFS 2.0.0 (per-municipality endpoints, GeoJSON output)
- **Base endpoint pattern**: `https://servicos.dgterritorio.pt/SDISNITWFSCRUS_{code}_1/WFService.aspx`
- **License**: open data
- **Schedule**: manual trigger
- **Coverage**: 5 municipalities only — Aveiro, Lisboa, Porto, Coimbra, Leiria

### Historical schema (`bronze_regulatory.raw_crus_ordenamento`)

- **ID, DTCC, Municipio, Classe, Categoria** — administrative + classification fields
- **Area_Ha** — polygon area in hectares
- **Designacao_PlantaOrdenamento** — designation per municipal master plan
- **Data_PublicacaoPDM** — date the PDM was published
- **Fonte, Autor** — provenance fields
- **geometry** — Polygon / MultiPolygon, EPSG:3763 (PT-TM06)

### Historical quirks

- **No STARTINDEX pagination**: this WFS implementation ignored `STARTINDEX` and always returned the same first-N features. Workaround: each municipality had < 2k features, so a single un-paginated request sufficed.
- **Field-name normalization**: strip diacritics from ALL field names (`DESIGNAÇÃO` → `DESIGNACAO`); explicit rename of Porto's `ID1` → `ID` to match the other 4 municipalities.
- **Cross-source role**: CRUS was the regulatory classification of land use per the municipal PDM. [[cos]] tells what the satellite observed; CRUS told what the rules said. That role is now served by [[crus-ogc]].

## See also

- [[crus-ogc]] — the OGC API replacement (national coverage)
- [[cos]] — what the satellite saw (sibling source)
- [[sprint-08]] — the sprint that retired this path
- [[medallion-layering]] — silver/gold pattern

## Last verified

2026-05-13 (retirement; pipeline deleted, page preserved as historical record).
