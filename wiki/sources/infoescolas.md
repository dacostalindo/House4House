---
title: Infoescolas — DGEEC school quality indicators
type: source
last_verified: 2026-06-06
tags: [education, statistics, government, quality, bulk-file]
priority: P1
---

## For future Claude

This is a source page about **Infoescolas** ([[ine|DGEEC]]/MECI) — per-school national-exam results + an equity (value-added) indicator, used as the **quality attribute** joined onto the [[gesedu]] school points by `Código Escola DGEEC`. Non-spatial; it carries no geometry — geometry comes from [[gesedu]]. Pairs with [[bgri]] (resident attainment, the *other* area signal). Design doc: [[pt-education-amenity-design]]. Read this before editing `pipelines/<education ingest>`.

## Source

- **Official name**: Infoescolas (Resultados escolares por escola/unidade orgânica)
- **Owner**: government agency (DGEEC / MECI)
- **Protocol**: bulk file download (XLSX/ODS), not an API
- **Endpoints**:
  - **Fresh** (through Feb 2025, **no stated licence**): `https://infoescolas.medu.pt/bds.asp` (static `/docs/` directory, *DadosPorEscola* / *DadosPorUO* / *DadosPorRegiao*)
  - **CC BY 4.0** (clean licence, ~2021 snapshot, fallback): `https://dados.gov.pt/api/1/datasets/infoescolas/`
- **License**: bds.asp = unstated (treat as internal-derived, **do not redistribute raw**); dados.gov.pt = CC BY 4.0
- **Schedule**: manual trigger (annual editions)
- **Coverage**: national, public + private; secundário exam metrics (basic-only schools → null by design)

## Schema

Bronze table: `bronze_location.raw_infoescolas_quality` (kept with [[gesedu]] for the cohesive education layer; alternatively `bronze_statistics` as a DGEEC stat — chose `location` for join cohesion).

- `codigo_escola_dgeec` — 6-digit join key = [[gesedu]] `codescme`. (The *DadosPorUO* file also has `codigo_do_agrupamento` + `codigo_da_escola` for agrupamento-grain joins.)
- `nome_escola`, `concelho`
- `exam_avg` — national-exam average (secundário)
- `equity` — Infoescolas value-added / equity indicator
- (carry as separate columns; the user-facing blend is deferred to the surfacing mart)

## Build scope (v1)

- Bulk-file ingest DAG (not the ArcGIS template — plain download → MinIO → bronze): fetch the *DadosPorEscola* XLSX from `bds.asp`, land to `raw/infoescolas/`, load to `bronze_location.raw_infoescolas_quality`.
- `stg_infoescolas_quality.sql` via `/stg-from-bronze` (cast, NULL guards, `not_null` on `codigo_escola_dgeec`).
- Joined to [[gesedu]] points in the surfacing mart on `codescme = codigo_escola_dgeec`; rolled up to freguesia/concelho for the "aggregated school quality" area column.

## Quirks

- **bds.asp has no stated licence** — the live-portal files are fresher than the CC-BY dados.gov.pt copy but legally unmarked. Source from bds.asp for v1 (flag internal-derived); the CC-BY 2021 file is the redistributable fallback.
- **Secundário-only metrics** → basic/pré-escolar schools carry null `exam_avg` by design; the catchment mart's quality bucket keys on "nearest secundário-with-a-score", not "nearest school".
- **código confirmed present (Gate 1, 2026-06-06)** — first column is literally `Código Escola DGEEC`; this is what makes the clean código-spine join possible instead of fuzzy name-matching.
- **Retention/dropout NOT here** — that's Regiões em Números (concelho grain, `estatisticas-educacao.dgeec.medu.pt`), dropped from v1.

## Last verified

2026-06-06 — XLSX downloaded + parsed, `Código Escola DGEEC` column + 6-digit values confirmed; bds.asp file directory through Feb 2025 confirmed live. Not yet built — scoped spec.
