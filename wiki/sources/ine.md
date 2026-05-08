---
title: INE — Instituto Nacional de Estatística
type: source
last_verified: 2026-05-08
tags: [api, statistics, government, json-stat]
---

## For future Claude

This is a source page about INE (Statistics Portugal), the National Statistics Institute. It documents the REST JSON-stat ingest covering 33 indicators across housing, demographics, Census 2021, tourism, and economy — all via the public `pindica.jsp` endpoint, no auth required. Read this page before editing [pipelines/api/ine/ine_config.py](../../pipelines/api/ine/ine_config.py) or its DAG.

## Source

- **Official name**: INE — Instituto Nacional de Estatística (Statistics Portugal)
- **Owner**: government agency (national statistical office)
- **Protocol**: REST JSON (no auth, public)
- **Base endpoint**: `https://www.ine.pt/ine/json_indicador/pindica.jsp`
- **License**: open data (CC-BY)
- **Schedule**: monthly 1st 06:00 UTC (`0 6 1 * *`)

## Schema

Bronze table: `bronze_statistics.raw_ine` — one fetch per indicator, raw JSON-stat payload preserved as-is per [[bronze-permissive]].

- **Indicator coverage** (33 total, encoded in `INE_INDICATORS`):
  - **Housing**: prices (HPI, transaction medians), transactions (volume, value), rental, construction, mortgage flows
  - **Demographics**: resident population, dependency ratio, NUTS-level breakdowns
  - **Census 2021**: dwelling stock, household composition, housing typology
  - **Tourism**: occupancy, accommodation supply
  - **Economy**: employment, income proxies
  - **Innovation**: small set of regional innovation indicators
- **Dimensions** (vary per indicator): `Dim1` = time period (`T` = all), `Dim2` = geography (`T` = all, `lvl@1`–`lvl@3` for NUTS levels), `Dim3+` = indicator-specific
- **Refresh cadence per indicator**: encoded as enum (`monthly`, `quarterly`, `annual`, `decennial` for Census)

## Quirks

- **JSON-stat 1.0 format** (NOT JSON-stat 2.0): payload structure is hierarchical with `dimension` / `value` / `status` blocks. Bronze stores raw; staging unpacks per-indicator into long-format facts.
- **Rate limit 1.0s**, request timeout 60s, max_retries 3. Stable endpoint, rarely backpressures.
- **Adding a new indicator**: append an `APIIndicator` entry to `INE_INDICATORS` in `ine_config.py`. Indicator codes can be discovered via:
  1. Browsing `https://www.ine.pt`
  2. Searching `smi.ine.pt/Indicador`
  3. Probing API at `pindica.jsp?op=2&varcd=...`
- **NUTS hierarchy**: PT has NUTS I (the country), NUTS II (regions: Norte, Centro, Lisboa, Alentejo, Algarve + Madeira + Açores), NUTS III (sub-regions). Indicators with geographic dimension support `lvl@1`–`lvl@3`. Below NUTS III, INE switches to municipality (concelho, see [[caop]]) but only some indicators expose that level.
- **Decennial Census 2021 indicators** are static (next refresh is 2031); fetching them every month is harmless but pointless. Could be moved to a manual-trigger DAG later.
- **Cross-source role**: INE is the canonical source for PT macro-housing context. [[eurostat]] provides cross-EU comparison (HPI 2015=100); INE provides PT-native granularity (concelho-level transaction medians).

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read; 33 indicators confirmed in `INE_INDICATORS`).
