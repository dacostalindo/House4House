---
title: ECB — European Central Bank Euribor
type: source
last_verified: 2026-05-08
tags: [api, financial, international, sdmx]
priority: P0
---

## For future Claude

This is a source page about the ECB Statistical Data Warehouse, narrowly scoped to 3 monthly Euribor rate series (3M / 6M / 12M). It documents the SDMX REST JSON ingest used as a benchmark feed for mortgage-affordability modelling. Read this page before editing [pipelines/api/ecb/ecb_config.py](../../pipelines/api/ecb/ecb_config.py) or its DAG.

## Source

- **Official name**: ECB — European Central Bank Statistical Data Warehouse
- **Owner**: government agency (international, eurozone monetary authority)
- **Protocol**: SDMX REST (returns SDMX JSON)
- **Base endpoint**: `https://data-api.ecb.europa.eu/service/data/FM/{series_key}`
- **License**: open data
- **Schedule**: monthly 1st 06:00 UTC (`0 6 1 * *`)

## Schema

Bronze table: `bronze_financial.raw_ecb` — 3 Euribor series, raw SDMX JSON preserved per [[bronze-permissive]].

- **Euribor 3M** monthly average — series key embedded in endpoint
- **Euribor 6M** monthly average
- **Euribor 12M** monthly average — primary mortgage benchmark in PT (most variable-rate mortgages reset against 12M Euribor)

## Quirks

- **Tiny scope**: 3 series total, single fetch each. `rate_limit_delay=0`. The simplest source in our stack.
- **SDMX format**: standardized statistical data exchange format used by ECB, [[eurostat]], and other European institutions. Hierarchical: dataflow → series → observations. Bronze stores raw; staging unpacks observations into a long-format `(date, tenor, rate)` table.
- **Mortgage benchmarking**: Phase 5 listing-affordability calculations need a same-month Euribor reference. Pulling from ECB directly is more authoritative than going through [[bpstat]]'s domain-21 (which is BdP's interpretation/aggregation).
- **No backfill needed**: ECB returns full history on every fetch (no pagination, no incremental window). ~1,158 rows total (386 observations per series, monthly since 1994). dlt write-disposition is full-replace.
- **12M Euribor is the primary mortgage benchmark in PT**: most variable-rate PT mortgages reset against 12M Euribor (3M and 6M are minority products). For affordability modelling, 12M is the headline rate.
- **Cross-source role**: ECB Euribor + [[bpstat]] domain 21 (PT-specific lending rates) + [[ine]] mortgage flows = a complete affordability picture. Each fills a piece the others can't.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read; 3 Euribor series confirmed).
