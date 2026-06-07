---
title: DGES Concurso Nacional de Acesso — per-(year, phase) higher-ed rankings (XLSX/XLS/ODS)
type: source
last_verified: 2026-06-07
tags: [education, higher_ed, schools, dges, rankings, xlsx, p1]
priority: P1
---

## For future Claude

Source page for DGES's Concurso Nacional de Acesso (CNA) per-(year, phase, curso/instituição) results — the canonical PT higher-ed entrance signal. This is source #4 of the 5-source PT education amenity pillar; it joins to [[dgeec-ens-sup]] via `codigo_unidade_organica` and provides `nota_ult_colocado` (the 0-200 contingente-geral entrance threshold) as the higher-ed quality signal in the silver layer. Read this page before editing [pipelines/gis/dges_acesso/](../../pipelines/gis/dges_acesso/) — it documents the **three traps** the live probe exposed (Family A reference-card confusion, three different file formats, and the codigo_instit ≈ codigo_uo subset relationship).

## Source

- **Official name**: Concurso Nacional de Acesso ao Ensino Superior — Resultados por Fase
- **Owner**: DGES (Direção-Geral do Ensino Superior).
- **Protocol**: anonymous HTTPS GET, one file per `(year, phase)`. 12 years × 3 phases = **36 source files** (2014–2025) in the manifest.
- **Manifest source of truth**: the DGES historical-data page at <https://www.dges.gov.pt/pt/pagina/regime-geral-ensino-superior-publico-concurso-nacional-de-acesso>. Every URL is hard-coded in `YEAR_PHASE_URLS` (see [`dges_acesso_config.py`](../../pipelines/gis/dges_acesso/dges_acesso_config.py)) — DGES does NOT follow a URL pattern (see §"URL trap").
- **License**: open data, attribution to DGES.
- **Live probe (2026-06-07)**: all 36 URLs return HTTP 200; sizes 40k–230k bytes per file; ~1100 rows per file; 36 × ~1100 ≈ 40k bronze rows total.

## Why a custom DAG (not the template)

The GIS ingestion template expects a single download → unzip → load. We have **three** divergences:

1. **Parametrised (year, phase) input** — operator triggers `dges_acesso_ingestion` with `{"year": YYYY, "phase": N}` conf; full backfill via the sibling `dges_acesso_backfill` DAG which iterates the 36 entries with one task per file.
2. **Three formats per source** — 8 `.xlsx` + 19 `.xls` + 9 `.ods` files. Bronze loader routes by URL suffix to `openpyxl` / `xlrd` / `odfpy` via `pandas.read_excel(engine=...)`.
3. **Cross-phase + cross-year schema drift** — column labels rename across phases (F1 has `"Nota do últ. colocado (cont. geral)"`, F2/F3 drop the parenthetical; `"Sobras para 2ª fase"` becomes `"Vagas Sobrantes"`), and 2022 F1 has an extra `"Vaga adic. (vagas autónomas)"` column. The bronze loader uses a label→canonical-column rename map (`SOURCE_LABEL_TO_COLUMN`) that collapses synonyms, mirroring the [[dbt-source-column-descriptions]] convention.

Templatising acesso-shaped sources is parked until N≥2 sibling sources arrive.

## Traps

### 1. Família A vs Família B — only Família B is the truth

DGES publishes TWO XLSX families that look superficially similar:

- **Família A**: per-year "reference card" published in February, named like `dges_vagascna_nota_ult_colocado_1afase{Y}_{Y+1}_*.xlsx`. Contains *next year's* vagas + *prior year's* nota último colocado, denormalised across one row per curso. Has two sheets (`Nacional` + `Local`) and includes an `Área Científica` column.
- **Família B**: per-(year, phase) "results" files, named like `fase{n}_{YY}.xlsx`, `cna{YY}_{n}f_resultados.xls`, or `cna{YY}_{n}f_resultados.ods`. Contains the actual fase results (vagas iniciais, colocados, nota último colocado, sobras).

**This source ingests Família B only.** Família A is explicitly NOT ingested — it duplicates Família B's data with a publish-date-axis ambiguity (the 2024-2025 reference card published Feb 2025 reports 2024's nota, not 2025's). If `Área Científica` becomes needed downstream, ingest Família A as a separate source then; don't conflate.

### 2. URL pattern is a lie

Filename conventions across years and even within years are inconsistent: 2024 has `fase1_24.xlsx` + `fase2_24.xls` + `fase3_24.xlsx`; 2022 is `cna22_{n}f_resultados.xls`; 2018 is `cna18_{n}f_resultados.ods`; 2019 is `site_cna19_{n}f_resultados.{xls,xlsx}`; one outlier is `fase1a25_site.xlsx`. **Every URL is a snowflake.** `YEAR_PHASE_URLS` is a literal `dict[(int, int), str]` — there is NO pattern. To add a new year:

1. Open the [DGES historical-data page](https://www.dges.gov.pt/pt/pagina/regime-geral-ensino-superior-publico-concurso-nacional-de-acesso).
2. Copy the actual download URLs for each phase (right-click → "Copy link address").
3. Add three entries to `YEAR_PHASE_URLS`.
4. Trigger `dges_acesso_ingestion` once per `(year, phase)`, then `dges_acesso_bronze_load` once.

### 3. `Código Instit.` is a strict subset of [[dgeec-ens-sup]] UO codes

Live probe 2026-06-07: across all 3 phases of 2025, DGES exposes 170 distinct `Código Instit.` values. Of those, **162 (95.3%) match an [[dgeec-ens-sup]] `codigo_unidade_organica`**; only 7 (4.1%) match [[dgeec-ens-sup]]'s `codigo_instituicao` (the parent institution). So DGES tracks UO-grain, same as DGEEC.

The remaining 8 DGES codes (`0521, 3036, 3124, 3125, 6810, 7016, 7240, 7270`) have no match — likely UOs added since DGEEC's 2023-03-15 snapshot, or special cases. The silver join is a LEFT JOIN: unmatched rows survive with `unmatched_uo = true` so they can be surfaced as a drift sentinel. When DGEEC refreshes, expect that count to drop.

### 4. `Código Curso` can contain letters

Curso codes look like `9500`, `8086` mostly — 4-digit numeric strings. But some Música variants ship as `L184`, `L344` etc. Bronze stores `codigo_curso` as `text` (NO zfill, NO integer cast). The PK regex `^[0-9A-Za-z]{2,5}$` covers both shapes.

## Schema (superset across 3 phases, 22 bronze columns)

Verified live 2026-06-07 via parse of fase1/2/3 2025 + fase1 2022 (.xls) + fase1 2018 (.ods). Bronze loader normalises whitespace (`"Sobras para\n2ª fase"` → `"Sobras para 2ª fase"`) and collapses synonyms to the canonical bronze column.

| Source label (verbatim) | Bronze column | Type | Present in |
| --- | --- | --- | --- |
| `Código Instit.` | `codigo_instit` (PK) | text | all phases |
| `Código Curso` | `codigo_curso` (PK) | text | all phases |
| `Nome da Instituição` | `nome_instituicao` | text | all phases |
| `Nome do Curso` | `nome_curso` | text | all phases |
| `Grau` | `grau` | text | all phases |
| `Vagas Iniciais` / `Vagas Iniciais 3F` | `vagas_iniciais` | integer | all phases (label drift in F3 2025+) |
| `Vagas de recolocação` | `vagas_recolocacao` | integer | F2 + F3 only |
| `Colocados` | `colocados` | integer | all phases |
| `Colocados (desemp.)` | `colocados_desemp` | integer | post-2018 |
| `Colocados (sem class. final)` | `colocados_sem_class` | integer | post-2018 |
| `Vaga adic. (sem class. final)` | `vaga_adic_sem_class` | integer | post-2018 |
| `Vaga adic. (vagas autónomas)` | `vaga_adic_autonomas` | integer | F1-2022 only (observed) |
| `Vaga adic. (alíneas c) e e) do artº 10º)` | `vaga_adic_alineas_c_e` | integer | F2 only |
| `Nota do últ. colocado (cont. geral)` / `Nota do últ. colocado` | `nota_ult_colocado` | numeric | all phases (F2/F3 drop "(cont. geral)") |
| `Sobras para 2ª fase` / `Sobras para2ª fase` / `Vagas Sobrantes` | `vagas_sobrantes` | integer | all phases (label drift across phases AND 2018 .ods typo) |
| `Sobras 2F` | `sobras_2f` | integer | F3 only |
| `Não Matric 2F` | `nao_matric_2f` | integer | F3 only |
| `Não Matric 2F (sem class. final)` | `nao_matric_2f_sem_class` | integer | F3 only |
| `Sobras Retiradas` | `sobras_retiradas` | integer | F3 only |

Plus partition/audit: `year`, `phase`, `source_loaded_at`. Full column descriptions live in [`dbt/models/staging/education/_staging_education__sources.yml`](../../dbt/models/staging/education/_staging_education__sources.yml).

### Bronze DDL (preview)

```sql
CREATE TABLE bronze_education.raw_dges_acesso (
  year             integer NOT NULL,
  phase            integer NOT NULL,
  codigo_instit    text    NOT NULL,
  codigo_curso     text    NOT NULL,
  source_loaded_at timestamptz NOT NULL DEFAULT now(),
  nome_instituicao text, nome_curso text, grau text,
  vagas_iniciais   integer, vagas_recolocacao integer,
  colocados        integer, colocados_desemp integer, colocados_sem_class integer,
  vaga_adic_sem_class integer, vaga_adic_autonomas integer, vaga_adic_alineas_c_e integer,
  nota_ult_colocado numeric, vagas_sobrantes integer,
  sobras_2f integer, nao_matric_2f integer,
  nao_matric_2f_sem_class integer, sobras_retiradas integer,
  PRIMARY KEY (year, phase, codigo_instit, codigo_curso)
);
```

### File-shape probe (2026-06-07)

| Year | Phase | Format | Bytes  | Sheet     | Header @ | Rows | Cols | Notes |
|------|-------|--------|--------|-----------|----------|------|------|-------|
| 2025 | 1     | .xlsx  |  92034 | Mínimas   | row 4    | 1132 | 12   | F1 canonical |
| 2025 | 2     | .xlsx  | 101856 | Pares     | row 4    | 1132 | 14   | +recolocação +alíneas |
| 2025 | 3     | .xlsx  | 107523 | Pares     | row 4    | 1132 | 17   | +sobras_2f/etc |
| 2022 | 1     | .xls   | 226304 | Mínimas   | row 4    | 1103 | 13   | +vagas_autónomas |
| 2018 | 1     | .ods   |  67156 | Mínimas   | row 4    | 1068 | 9    | annotation row at idx 5; "Sobras para2ª fase" typo |

Row 5 in older .ods files contains an annotation row (`(1) (2) ... (9)`) between header and data; the loader filters generically by `codigo_instit ∈ ^[0-9A-Za-z]{2,5}$` so blanks, annotations, and trailing summary rows all drop out.

## Silver model

[silver_dges_acesso_uo](../../dbt/models/silver/education/silver_dges_acesso_uo.sql) aggregates per `(codigo_unidade_organica, year, phase)`:

- `nota_ult_colocado_weighted = SUM(vagas_iniciais * nota) / NULLIF(SUM(vagas_iniciais), 0)` — weighted only over cursos with non-NULL nota (NULL-nota cursos excluded from BOTH numerator and denominator).
- `vagas_total`, `colocados_total`, `n_cursos`, `n_cursos_with_placement`.
- LEFT JOIN to the latest [[dgeec-ens-sup]] snapshot — unmatched DGES codes surface with `unmatched_uo = true`.

There is no `stg_dgeec_ens_sup` model yet; silver inlines the "latest run_date" filter as a CTE. When DGEEC gets a staging model, swap the CTE for a `ref`.

## DAGs

- `dges_acesso_ingestion` — manual, conf `{"year": YYYY, "phase": N}`. Looks up the URL, downloads (size + row-count band-check), uploads to `s3://raw/dges_acesso/{year}/fase_{n}/{filename}`.
- `dges_acesso_backfill` — manual one-shot bootstrap. One task per (year, phase) for clean failure isolation: a broken 2018 .ods doesn't stop the other 35.
- `dges_acesso_bronze_load` — manual. Walks ALL MinIO blobs under `raw/dges_acesso/`, parses each with the right engine, upserts on `(year, phase, codigo_instit, codigo_curso)`. Idempotent; rerun after the ingestion DAG adds a new file.

All three live under [`pipelines/gis/dges_acesso/`](../../pipelines/gis/dges_acesso/).

## Quirks

- **DGES → IES institutional transition** — at least one DGES page hints at "functions integrated into IES, I.P." If URLs move in 2026+, `YEAR_PHASE_URLS` is the single dict to update; no logic change required.
- **2ª fase / 3ª fase publication dates are irregular** — typically mid-September and early October but DGES has slipped weeks. Manual trigger discipline avoids spurious cron failures.
- **The 8 unmatched DGES UO codes** (`0521, 3036, 3124, 3125, 6810, 7016, 7240, 7270`) are not researched yet. Silver flags them; manual resolution deferred until a use case needs it.
- **`nota_ult_colocado` is NULL when colocados=0** — a curso that filled no candidates this phase has nothing to report. Silver excludes these from the weighted mean (both numerator and denominator).
- **`Código Curso` letters** — about 30 cursos in the 2025 corpus have codes like `L184`, `L344` (Música variants). Stored verbatim; do NOT cast to integer in silver.

## Last verified

2026-06-07 — all 36 URLs returned HTTP 200 via `curl HEAD`. Parser verified locally against 5 representative files (2025 fase 1/2/3 .xlsx + 2022 fase 1 .xls + 2018 fase 1 .ods); zero unknown labels in any file. End-to-end Airflow ingestion + backfill + bronze load deferred to next session (Airflow stack not running in this worktree).
