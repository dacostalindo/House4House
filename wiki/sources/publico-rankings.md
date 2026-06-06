---
title: Público School Rankings — Annual Exam-Score Rankings
type: source
last_verified: 2026-06-06
tags: [education, schools, rankings, json, publico, p1]
priority: P1
---

## For future Claude

This is a source page about Público's annual school rankings, published as static JSON files
on CloudFront-fronted S3 buckets and used as the primary ranking signal for both secundário
(11º+12º exames nacionais) and 3º ciclo (9º ano Provas Finais) in the education amenity
pillar of the warehouse. Read this page before editing
[pipelines/gis/publico_rankings/publico_rankings_config.py](../../pipelines/gis/publico_rankings/publico_rankings_config.py) —
it documents the three-era URL convention, the COVID-cancellation gaps, the soft-404 trap,
and the licence restrictions on the downstream `mt` (média total) field. Sibling sources in
the same pillar: [[rede-escolar]] (KG-secundário register), [[dges-acesso]] (higher-ed
ranking), [[infoescolas]] (3º ciclo cross-check), [[dgeec-ens-sup]] (higher-ed register).

## Source

- **Official name**: Ranking das Escolas — edição {YEAR}
- **Owner**: Público (jornal, commercial). Data derived from IAVE exam-score microdata.
- **Protocol**: anonymous HTTPS GET of static JSON files served from S3/CloudFront. `.js`
  extension is misleading — body is a plain JSON array, no JSONP wrapper.
- **Base endpoints**: see the per-year URL resolver table below; one URL per (year, kind)
  tuple. Three hosting eras in seven years.
- **Required headers**: `Referer: https://www.publico.pt/`, `Origin: https://www.publico.pt`.
  CDN returns 403 on the `/s3/` era buckets without them.
- **Licence**: © Público. Internal analytical use OK; **do not republish raw `mt`/`rt`**;
  cite Público in any user-facing display. The numeric scores are facts (not copyrightable
  in isolation) but the curated list-as-a-whole is editorial product.
- **Schedule**: annual, late March / early April. Probe quarterly Mar-May for new release.
- **Coverage**: continental Portugal + Açores + Madeira; públicos + privados +
  cooperativos + IPSS (anything that registers students for national exams).

### Per-year URL resolver table

Verified live 2026-06-06 (`tests/3ciclo-all-years.har` + curl probe). Sizes are
approximate observed body lengths; the soft-404 sentinel is exactly 22634 bytes.

| Year | sec URL | sec ~size | 9ano URL | 9ano ~size |
|---|---|---|---|---|
| 2018 | `static.publicocdn.com/files/rankings2018/data/listas/rankings2018sec.js` | 322 KB | `…/rankings20189ano.js` | 404 KB |
| 2019 | `static.publicocdn.com/files/rankings2019/data/listas/rankings2019sec.js` | 308 KB | `…/rankings20199ano.js` | 376 KB |
| 2020 | `static.publicocdn.com/files/rankings2020/data/listas/rankings2020sec.js` | 314 KB | **N/A** (COVID) | — |
| 2021 | `static.publico.pt/files/rankings2021/data/listas/rankingssec.js` | 764 KB | **N/A** (COVID) | — |
| 2022 | `static.publico.pt/files/rankings2022/data/listas/rankingssec.js` | 1034 KB | `…/rankings9ano.js` | 1033 KB |
| 2023 | `static.publico.pt/files/rankings2023/data/listas/rankingssec.js` | 583 KB | `…/rankings9ano.js` | 601 KB |
| 2024 | `static.publico.pt/s3/rankings2024/data/listas/rankingssec.js` | 618 KB | `…/rankings9ano.js` | 639 KB |

The 9ano gap in 2020 and 2021 is intentional, not missing data — Provas Finais 9º ano
were cancelled in both years due to COVID. Do NOT add placeholder URLs.

## Schema

### Pipeline split

Two DAGs per the established GIS-source pattern ([[bgri]] + [[osm]] both follow it):

- **`publico_rankings_ingestion`** — downloads + validates + lands the raw `.js`
  bodies at `s3://raw/publico_rankings/{year}/{kind}.json` in MinIO. Network-fragile
  half; re-running burns Público's CDN.
- **`publico_rankings_bronze_load`** — MinIO → `bronze_education.raw_publico_rankings`.
  Discovers blobs, applies the DDL (idempotent), unnests each JSON row into typed
  columns, upserts keyed on `(year, kind, eid)` so replays are safe. If bronze is
  dropped, MinIO is the audit trail — re-trigger this DAG to rebuild without
  re-hitting Público.

### Bronze DDL (unnested, 95 columns, human-readable names)

The bronze loader unnests the JSON AND renames every cryptic source key to a
human-readable Portuguese column name verified against Público's interactive UI:
`mt` → `media_total_exames`, `rt` → `ranking_exames`, `rs` → `ranking_superacao`,
`mm` → `media_matematica_a`, `mma` → `media_economia_a`, etc.

4 partition/audit columns + 5 text identity columns + 86 numeric metric columns.
The raw JSONB blob is intentionally NOT retained — MinIO holds the verbatim audit
trail, so bronze can stay typed. This trades the strict [[bronze-permissive]]
invariant ("keep everything as JSON, type at silver") for SQL ergonomics:
`SELECT media_total_exames FROM …` instead of `(raw->>'mt')::float` everywhere downstream.

The rename map is the single source of truth: `SOURCE_KEY_TO_COLUMN` dict at the
top of `publico_rankings_bronze_dag.py`. DDL, INSERT column list, and UPDATE SET
clause are all derived from it.

```sql
CREATE TABLE bronze_education.raw_publico_rankings (
  year             smallint    NOT NULL,
  kind             text        NOT NULL CHECK (kind IN ('sec','9ano')),
  eid              text        NOT NULL,
  source_loaded_at timestamptz NOT NULL DEFAULT now(),
  -- Identity & geography
  nome text, id_publico text, concelho text,
  contexto_agrupamento text, codigo_uo_dgeec text,
  latitude double precision, longitude double precision,
  tipo double precision,                          -- 1=privado, 2=público
  -- Headline principal
  media_total_exames double precision,            -- mt
  ranking_exames     double precision,            -- rt
  num_provas_total   double precision,            -- nt
  -- Ranking da Superação
  ranking_superacao double precision,             -- rs
  media_esperada    double precision,             -- v
  -- Per-disciplina principal (9 disciplinas × {media, num_provas, ranking})
  media_matematica_a, media_portugues, media_bio_geo, media_fq_a,
  media_geografia_a, media_filosofia, media_historia_a,
  media_economia_a, media_macs,
  num_provas_matematica_a, num_provas_portugues, num_provas_bio_geo, ...
  ranking_matematica_a, ranking_portugues, ranking_bio_geo, ...
  -- Nota Interna (CIF) — 8 disciplinas × {media, ranking}
  cif_media_matematica_a, cif_media_portugues, ..., cif_ranking_matematica_a, ...
  -- Per-disciplina Superação (2-letter codebook: ma=Mat A here, not Economia)
  ranking_superacao_matematica_a, ranking_superacao_portugues, ...,
  ranking_superacao_economia_a, ranking_superacao_macs,
  -- Prior-year carry (suffix = literal source key, semantics = ano anterior)
  media_ano_anterior, ranking_ano_anterior,       -- m21, r21
  media_legacy_y17..y20, ranking_legacy_y17..y20,
  -- Contexto socioeconómico
  habilitacoes_pais, habilitacoes_maes,           -- hp, hm
  pct_sem_ase, idade_media_12ano,                 -- ac, im
  pct_professores_quadros,                        -- pdq
  -- Taxa de retenção (ano0/1/2 = 10º/11º/12º para sec, 7º/8º/9º para 9ano)
  taxa_retencao_ano0, taxa_retencao_ano1, taxa_retencao_ano2,
  -- Equidade
  equidade_pct_ase_3anos, equidade_pct_pais_3anos, equidade_ranking_diferenca,
  -- Equivalência à Frequência
  equivalencia_comp1, equivalencia_comp2, equivalencia_delta,
  equivalencia_flag_nao_usar, equivalencia_flag_nao_usar_v2,
  ranking_equivalencia,                           -- re
  PRIMARY KEY (year, kind, eid)
);
CREATE INDEX raw_publico_rankings_codigo_uo_dgeec
  ON bronze_education.raw_publico_rankings (codigo_uo_dgeec)
  WHERE codigo_uo_dgeec IS NOT NULL AND codigo_uo_dgeec <> '';
```

See [[publico-rankings-column-legend]] for the complete `source_key → renamed_column`
table (91 mappings) including the ground-truth row-dump that validates every name
against Público's UI for eid=1069.

**Value coercion**: source values arrive as a mix of JSON numbers and JSON strings
("13.49" vs `13.49`, sometimes within the same row across years). The loader runs
every non-text field through `_coerce_numeric` which yields `NULL` on parse failure /
empty string / literal `"null"`. NULL means "key absent or unparseable" — the
cross-kind shape gap is expected (sec has 76 keys, 9ano has 40; union = 91 data cols).

**Schema-drift detection**: every load logs a WARNING if any source key falls outside
the union of `TEXT_COLS + NUMERIC_COLS`. Re-load with the new key added to the
appropriate tuple to absorb the drift. Verified 2026-06-06: zero unknown keys across
the full 2018-2024 corpus.

**Column legend**: see [[publico-rankings-column-legend]] for the decoded meaning of
every cryptic 1–6 char column name (mt, rt, mm, mp, rsma, nimm, pde, etc.), the dual
discipline codebook (1-letter in `m/n/r*`, 2-letter in `rs*`), and the empirical
range / sample-size envelopes used to disambiguate the residual unclear columns.

### Row counts (verified 2026-06-06 — full bronze load completed)

| Year | sec rows | 9ano rows |
|---|---|---|
| 2018 | 624 | 1204 |
| 2019 | 625 | 1181 |
| 2020 | 629 | — (COVID) |
| 2021 | 635 | — (COVID) |
| 2022 | 637 | 1166 |
| 2023 | 637 | 1165 |
| 2024 | **624** | **1161** |
| **total** | **4,411** | **5,877** |

Grand total: **10,288 rows** in `bronze_education.raw_publico_rankings`.

### Data-integrity facts verified at load time (2026-06-06)

- `coduo` populated on 921/1161 = **79.3%** of 2024 9ano rows — matches the design-doc
  claim that powers the direct-join strategy to [[rede-escolar]].
- `coduo` populated on **0/4411** sec rows — confirms the fuzzy-join requirement for the
  secundário side of the bridge.
- `mt` (ranking score) populated on **100%** of all 10,488 rows across all years and kinds.

Critical fields (subset of 77 in sec / 40 in 9ano):

| Source key | Type | Meaning |
|---|---|---|
| `eid` | string-int | Público's internal school id (stable across years). |
| `e` | string | School name, accents intact. |
| `id` | string (4-digit zero-padded) | Público short code. **NOT a prefix of DGEEC's 6-digit** — confirmed via spot-check (`id='1314'` vs `coduo='151130'`). Used as Público's URL slug. |
| `coduo` | string (6-digit) | DGEEC agrupamento código. Populated for 921/1161 9ano rows (79.3%); **empty for all sec rows**. The primary join key to [[rede-escolar]]`.CODUOME`. |
| `co` | string | Concelho name (no DICOFRE). |
| `c` | string | Region group: `D`/`F`/`I` (continental), `PRI`/`PRI_CA` (privates), `Açores`, `Madeira`. |
| `t` | int | Natureza: 1 = privado, 2 = público. |
| `mt` | string-float | **Média total exames** — the ranking score. Scale 0-20 for sec; 0-5 for 9ano Provas Finais. |
| `rt` | string-int | Posição global. NULL when sample size too small. |
| `lt`, `ln` | string-float | Lat, lon (WGS84). |
| `mm,mp,mb,mf,mg,mi,mma,mfl` | float | Per-disciplina averages (sec: Mat/Port/Bio/FQ/Geo/Ing/MatA/Fil; 9ano: only `mp`+`mm` = Port+Mat). |

## Quirks

- **`.js` extension, JSON body**: do not feed to a JSONP parser; `json.loads(body)` works
  directly. If a future release wraps the array in a `var x = [...]` prefix, the DAG's
  validation `json.loads` call will fail loudly — that's the canary.
- **Soft-404 returns HTTP 200**: an unknown URL returns the standard Público HTML 404 page
  with body size exactly 22634 bytes. The DAG validates by size (must exceed the per-file
  `expected_min_bytes` floor and must not equal 22634), not status. If you see 22634-byte
  successes, Público has moved a file — update `YEAR_FILE_TABLE` and re-trigger.
- **Three hosting eras in 7 years**: see resolver table. Adding a new year is an
  append-only entry to `YEAR_FILE_TABLE`; never rewrite historical rows (those URLs have
  stable bodies).
- **`id` ↔ DGEEC bridge unsolved**: the 4-digit `id` field is NOT a prefix of the 6-digit
  DGEEC código. For 9ano rows we get a direct join via `coduo` (79%); for secundário rows
  `coduo` is empty and the bridge is fuzzy (`ST_DWithin + similarity(name) + concelho`).
  See [[2026-06-06-pt-education-amenity-design]] for the bridge-table design.
- **9ano gap 2020+2021 is real**: COVID cancellation, not missing data. Do not paper
  over with placeholder URLs.
- **Licence is restrictive**: `mt` and `rt` are the editorial product. Internal use OK;
  any republished view must cite Público and aggregate (e.g. "% of schools in concelho
  X above national median") rather than expose raw per-school scores.
- **Required Referer header**: Era 3 (`/s3/`) returns 403 without it. Eras 1+2 are lax.
  Set in `REQUEST_HEADERS` in the config; the DAG passes them through.

## Last verified

2026-06-06 — full Phase-0 end-to-end run completed:

1. All 12 expected URLs fetched live (HTTP 200, sizes above per-file floor, all parse
   as JSON arrays).
2. Soft-404 sentinel confirmed (HTTP 200 + 22634 bytes for unknown `/files/` paths;
   `/s3/` era returns proper 403 instead — DAG handles both via `raise_for_status` +
   size check).
3. DAG imports + Airflow-parses cleanly under `uv run` (`dag_id=publico_rankings_ingestion`,
   tasks: fanout / download_one / upload_one / summarize, dynamic mapping over the
   12-row resolver).
4. All 12 files landed in MinIO at `s3://raw/publico_rankings/{year}/{kind}.json`.
5. `bronze_education.raw_publico_rankings` created + loaded (unnested, 95 cols, 91 data
   cols): 10,288 rows, integrity facts verified post-unnest (see "Row counts" +
   "Data-integrity facts" above). Zero schema-drift keys across the corpus.

**Caveat for next session**: the Airflow scheduler container mounts the main repo's
`pipelines/`, not the worktree's. The DAG isn't visible in the scheduler's `dags list`
until the files are merged to main (or the compose volume is rebound to the worktree).
Phase-0 verification ran the DAG's logic directly via `uv run`, not via Airflow trigger.
