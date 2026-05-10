---
title: Eurostat — European Commission Statistics
type: source
last_verified: 2026-05-08
tags: [api, statistics, international, sdmx]
priority: P1
---

## For future Claude

This is a source page about Eurostat, narrowly scoped to a single dataset: PRC_HPI_Q (House Price Index, quarterly, 2015=100). It documents the SDMX 2.1 REST ingest used for cross-EU benchmarking against [[ine]]'s PT-native HPI. Read this page before editing [pipelines/api/eurostat/eurostat_config.py](../../pipelines/api/eurostat/eurostat_config.py) or its DAG.

## Source

- **Official name**: Eurostat — Statistics European Union
- **Owner**: government agency (European Commission)
- **Protocol**: SDMX 2.1 REST (returns SDMX JSON)
- **Base endpoint**: `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/prc_hpi_q`
- **License**: open data
- **Schedule**: quarterly — 1st of Jan/Apr/Jul/Oct at 06:00 UTC (`0 6 5 1,4,7,10 *`); 5-day buffer accommodates Eurostat's typical first-of-quarter publication delay

## Schema

Bronze table: `bronze_statistics.raw_eurostat_hpi` — single dataset, all EU/EEA countries.

- **PRC_HPI_Q**: quarterly house price index, indexed at 2015=100, by country
- All EU/EEA countries included for cross-country benchmarking; PT row extracted in dbt staging for direct comparison against [[ine]]'s HPI series

## Quirks

- **Single dataset, no pagination**: SDMX 2.1 returns the full PRC_HPI_Q payload in one fetch. ~31k observations across 38 EU/EEA countries × 83 quarters. `rate_limit_delay=0`, `request_timeout=120s` (Eurostat is slower than [[ecb]]).
- **No server-side filtering**: the API ignores `geo` and `unit` query params on PRC_HPI_Q — always returns the full ~31k dataset. Filtering happens in dbt staging. Small enough that this isn't a problem.
- **Quarterly cadence + 3-month publication lag**: Eurostat typically publishes a quarter's data ~3 months after the quarter ends. A `2025-Q4` value usually appears in late March 2026. The 5-day buffer in the cron schedule accommodates this.
- **Status flags**: ~1,100 of the ~31k observations carry SDMX status flags — `p` (provisional), `e` (estimated), `b` (broken series), `d` (definition differs), `|C` (confidential). Silver-layer logic preserves the flags so downstream consumers can choose to filter.
- **SDMX 2.1 vs SDMX 2.0** ([[ecb]]): minor structural differences in dimension encoding. dbt staging handles both shapes.
- **Cross-source role**: Eurostat HPI is the canonical cross-EU benchmark. [[ine]]'s HPI is PT-native granularity (concelho-level transaction medians). Reporting that compares "PT housing 30% above 2015" needs the index from one of these two; Eurostat is the right choice for cross-country narrative, INE for PT-internal narrative.
- **Quarterly cadence**: lower-frequency than [[ine]] (monthly) or [[ecb]] (monthly). Phase 5 enrichment / dashboards should respect the cadence — pulling Eurostat HPI hourly or daily produces no new data.
- **Why not also pull Eurostat housing-cost index, energy prices, etc.**: scope discipline. PRC_HPI_Q is the only Eurostat indicator that fills a gap not covered elsewhere. Add more only when a use case demands it.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read).
