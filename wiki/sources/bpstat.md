---
title: BPStat — Banco de Portugal Statistical Data
type: source
last_verified: 2026-05-08
tags: [api, financial, government, json-stat]
---

## For future Claude

This is a source page about BPStat, the statistical data warehouse of Banco de Portugal. It documents the JSON-stat 2.0 ingest covering 16 datasets across housing credit, interest rates, and housing prices (3 domains). Read this page before editing [pipelines/api/bpstat/bpstat_config.py](../../pipelines/api/bpstat/bpstat_config.py) or its DAG.

## Source

- **Official name**: BPStat — Banco de Portugal Statistical Data warehouse
- **Owner**: government agency (PT central bank)
- **Protocol**: REST JSON-stat 2.0 (newer format than [[ine]]'s JSON-stat 1.0)
- **Base endpoint**: `https://bpstat.bportugal.pt/data/v1/domains/{domain_id}/datasets/{dataset_id}`
- **License**: open data (CC-BY)
- **Schedule**: monthly 15th 06:00 UTC (`0 6 15 * *`) — mid-month avoids overlap with [[ine]] (1st) and [[ecb]] (1st)

## Schema

Bronze table: `bronze_financial.raw_bpstat` — 16 datasets across 3 domains, raw JSON-stat preserved per [[bronze-permissive]].

- **Domain 186 — Housing credit** (4 datasets): loan volumes, NPL rates, regional flows, average loan size
- **Domain 21 — Interest rates** (10 datasets): fixed-rate mortgages, floating-rate mortgages, mixed-rate mortgages, by tenor and date
- **Domain 39 — Housing prices** (2 datasets): housing price indices, regional breakdown

## Quirks

- **Domain 18 (household debt) NOT included**: ~16,800 series, mostly corporate-flavored debt. The housing-specific subset can be added later if Phase 5 enrichment finds a use case.
- **`code_in_path=True`**: domain and dataset IDs are embedded in the URL path, NOT query params. Standard for BPStat's REST shape.
- **JSON-stat 2.0 format**: structurally similar to JSON-stat 1.0 but with additional `version` + `class` fields and a different dimension-encoding convention. Bronze stores raw; staging models normalize across versions.
- **Rate limit and timeout**: standard (1.0s, 60s).
- **Cross-source role**: BPStat fills the "PT-specific financial" gap that [[ecb]] (Euribor only) and [[eurostat]] (cross-EU HPI only) don't cover. Domain 21 is critical for mortgage-affordability modelling at the listing-level (rates × Euribor benchmark).
- **Series naming**: BPStat uses long, structured codes (e.g., `M.PT.N.A.A20.A.0000.A.A.A.B.A.A.A.A.0.0`). Mapping to human-readable labels lives in the dataset metadata; staging unpacks the codes.

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read; 16 datasets confirmed).
