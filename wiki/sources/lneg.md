---
title: LNEG — Geology & Hydrogeology
type: source
last_verified: 2026-05-08
tags: [gis, regulatory, government, geology, hydrogeology, arcgis-rest]
---

## For future Claude

This is a source page about LNEG (Laboratório Nacional de Energia e Geologia), narrowly scoped to the 1:500k geology layer (CGP500k) and the national aquifers layer. It documents the ArcGIS REST MapServer ingest with server-side reprojection, the deliberate scope at 1:500k due to higher-resolution gaps, and the self-signed SSL cert workaround. Read this page before editing [pipelines/gis/lneg/lneg_config.py](../../pipelines/gis/lneg/lneg_config.py).

## Source

- **Official name**: LNEG — Laboratório Nacional de Energia e Geologia
- **Owner**: government agency (national geological + energy laboratory)
- **Protocol**: ArcGIS REST MapServer (server-side reprojection to EPSG:3763)
- **Base endpoint pattern**: `https://sig.lneg.pt/server/rest/services/{CGP500k,RecursosHidro}/MapServer/2`
- **License**: open data
- **Schedule**: manual trigger

## Schema

Two bronze tables:

- `bronze_geology.raw_lneg_geology_500k` — Geologia 1:500k, 282 polygons national, hierarchical lithology classes (e.g., `C3` = Arenitos e argilas de Aveiro = Aveiro sandstones and clays)
- `bronze_hydrology.raw_lneg_aquiferos` — Aquíferos (aquifer systems), 63 polygons national. Fields: CodigoInag, NomeCompleto, SistemaAquifero, Idade

Both: geometry = Polygon, EPSG:3763 (PT-TM06, server-reprojected).

## Quirks

- **1:500k is the available resolution**: higher-resolution geology layers (CGP200k, CGP50k INSPIRE harmonised) have gaps:
  - **CGP200k**: Folha 5 (Beira Litoral, includes Aveiro) UNPUBLISHED. Cannot use.
  - **CGP50k INSPIRE**: 31,285 polygons total but only 30 of ~175 folhas published, ALL in northern PT. Aveiro is NOT covered.
  Hence, 500k is the only layer that gives PT-wide Aveiro coverage. When DGT publishes the missing folhas, revisit.
- **Self-signed SSL cert on sig.lneg.pt**: current workaround is `verify=False` in the requests session. **TODO** (Phase 7+ candidate): pin the cert to avoid silently accepting MITM on a regulatory data source. Until then, if you see `CertificateError`, that's the symptom of upstream rotating their cert.
- **PAGE_SIZE=1000, rate_limit=0.5s, request_timeout=180s**. Both layers are small (≤282 features) so a single request fetches each.
- **Lithology codes hierarchical**: the geology layer's `Idade_Litologia` field encodes age + composition in a structured code. Downstream silver-layer logic decodes the prefix (e.g., `C` = Cretácico era) for grouping.
- **Cross-source role**: geology + aquifers feed listing-feature engineering for "is this listing on stable bedrock?" (geology) and "what's the aquifer-recharge sensitivity here?" (aquifers, relevant for water-availability and pollution-risk assessments). [[srup-ogc]]'s aquíferos layer is a PROTECTED-zone subset of LNEG's national aquifers; the two are complementary (LNEG = "where are aquifers", SRUP = "which ones are protected").

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read).
