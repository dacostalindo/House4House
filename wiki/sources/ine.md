---
title: INE — Instituto Nacional de Estatística
type: source
last_verified: 2026-06-02
tags: [api, statistics, government, json-stat]
priority: P0
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

Bronze table: `bronze_ine.raw_indicators` — one fetch per indicator, raw JSON-stat payload flattened per (period × geography × dimensions) tuple at load time. `bronze_ine` schema (NOT `bronze_statistics` — earlier docs had this wrong). As of sprint-09 WS4 (2026-06-02), the bronze loader also writes `indicator_category` per row, sourced from `INE_INDICATORS[code].category` in [`ine_config.py`](../../pipelines/api/ine/ine_config.py) — single source of truth, no dual maintenance in silver.

- **Indicator coverage** (47 total per the README; 33 represent the actively-fetched subset encoded in `INE_INDICATORS` — the remaining 14 are documented but commented out, ready to enable):
  - **Housing**: prices (HPI, transaction medians), transactions (volume, value), rental, construction, mortgage flows
  - **Demographics**: resident population, dependency ratio, NUTS-level breakdowns
  - **Census 2021**: dwelling stock, household composition, housing typology
  - **Tourism**: occupancy, accommodation supply
  - **Economy**: employment, income proxies
  - **Innovation**: small set of regional innovation indicators
- **Dimensions** (vary per indicator): `Dim1` = time period (`T` = all), `Dim2` = geography (`T` = all, `lvl@1`–`lvl@3` for NUTS levels), `Dim3+` = indicator-specific
- **Refresh cadence per indicator**: encoded as enum (`monthly`, `quarterly`, `annual`, `decennial` for Census)

## Silver layer

Two silvers consume INE bronze with different scopes:

- [`silver_market.ine_indicators_long`](../../dbt/models/silver/market/ine_indicators_long.sql) (sprint-09 WS4, shipped 2026-06-02) — long-form table at parish/concelho/NUTS granularity. One row per `(indicator_code, geographic_code, time_period, dim_3-5)`. Handles INE's two coding schemes: (A) CAOP-flat (`'PT'`, 1-2-3 char NUTS, 4-char DTCC concelho, 6-char DTMNFR freguesia incl. letter unions e.g. `0302FD`); (B) NUTS3-prefixed (7-char concelho = NUTS3+DTCC e.g. `11A1312` Porto, 9-char freguesia = NUTS3+DTMNFR e.g. `11A131727` Mafamude). Exposes CAOP-compatible `freguesia_code` (6 chars) + `concelho_code` (4 chars) derived from either scheme, so downstream JOINs to `dim_geography` work uniformly. Best-effort parses `time_period` to `time_period_date`. Passes `indicator_category` through from bronze. Tests per [[silver-dq-baseline]].
- [`silver_geo.census_demographics`](../../dbt/models/silver/geo/census_demographics.sql) (pre-existing) — wide table joining 12 Census 2021 INE indicators to BGRI demographics at freguesia grain. Different shape; serves the hedonic feature-engineering use case.
- See [[silver-dq-baseline]] §"Statistical-source silver topology" for which silver answers which question and why INE is kept separate from [`silver_market.macro_timeseries`](../../dbt/models/silver/market/macro_timeseries.sql) (BPStat+ECB+Eurostat).

## Two endpoints: pindica.jsp + pindicaMeta.jsp

INE exposes two endpoints per indicator:

- **`pindica.jsp`** — DATA. Returns observations as flattened `Dados` blocks. Used by [`pipelines/api/ine/ine_bronze_dag.py`](../../pipelines/api/ine/ine_bronze_dag.py).
- **`pindicaMeta.jsp?varcd=<code>`** — METADATA. Returns the indicator's dimension definitions: for each dim, the list of categories with codes + labels + descriptions. NOT currently fetched in v1.

Example: for indicator `0008273` (Resident population), [`pindicaMeta.jsp`](https://www.ine.pt/ine/json_indicador/pindicaMeta.jsp?varcd=0008273&lang=EN) reveals Dim3 (Sex) has 3 categories — `T → MF → 'Both sexes combined'`, `1 → M → 'Males'`, `2 → F → 'Females'` — where the first column is the code in observations, the second is the displayable label, and the third is the full description. We currently store the first two; the third requires the metadata endpoint.

## `dim_X` vs `dim_X_t` semantics (locked 2026-06-02)

In `pindica.jsp` observations:

- **`dim_X`** = INE category **CODE** within the dimension. Stable convention: `'T'` always = total across this dimension. Other values are indicator-specific (e.g. for Sex: `'1'`/`'2'`; for HPI housing category: `'H1'`/`'H11'`/`'H12'`).
- **`dim_X_t`** = INE **displayable label** (the `t` suffix is INE convention — likely *título* / *texto*). Inconsistently shaped — sometimes a short code (`'M'`, `'F'`), sometimes a full label (`'5 - 9 years'`).

Renamed to `dim_X_label` in [`stg_ine_indicators.sql`](../../dbt/models/staging/ine/stg_ine_indicators.sql) (NOT `_name` — the value is not always a human-readable name). Full descriptions (`'Males'` not `'M'`) require the `pindicaMeta.jsp` endpoint.

**v2 path** (NOT v1): build a `silver_market.ine_dimensions` table populated by a periodic `pindicaMeta` fetch, exposing `(indicator_code, dim_n, code, label, description)`. Lets downstream consumers JOIN to get full descriptions without re-fetching.

## Quirks

- **JSON-stat 1.0 format** (NOT JSON-stat 2.0; [[bpstat]] and [[eurostat]] use 2.0): payload structure is hierarchical with `Dim1` / `value` / `status` blocks. Bronze stores raw; staging unpacks per-indicator into long-format facts.
- **`sinal_conv` missing-data codes**: `'x'` = not available, `'...'` = provisional. Both parsed as NULL in silver-layer normalization. Without this, downstream models would treat `'x'` strings as legitimate values.
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
