---
title: Público Rankings — column legend
type: concept
last_verified: 2026-06-06
tags: [education, publico, rankings, schema, legend]
---

## For future Claude

This concept page decodes the 91 cryptic column names in
`bronze_education.raw_publico_rankings`. The decoding is **ground-truthed**
against Público's interactive school card — see "Provenance" below for the
specific row that was matched UI-label-to-DB-value. Read this before writing
dbt silver promotions on the table; every column name is a 1–6 char
abbreviation of a Portuguese education term, and Público ships no
machine-readable legend.

## Provenance

Decoded by matching the school card for **Escola Básica e Secundária
Dr. Ferreira da Silva, Oliveira de Azeméis** (eid=1069, year=2024, kind=sec)
against the screenshots of Público's `publico.pt/ranking-escolas` interactive
page. Every visible UI label in that card was mapped to its source DB column;
the disciplina mapping ground-truthed the dual codebook (1-letter `m/n/r*`
vs 2-letter `rs*`). Empirical envelopes from the 10,288-row corpus filled in
the columns that don't appear on the public card.

## What it is

A row in the bronze table corresponds to one (year × kind × school) tuple. The
columns split into 9 families:

1. **Identity & geography** (`e`, `eid`, `id`, `co`, `c`, `coduo`, `lt`, `ln`, `t`)
2. **Headline ranking principal** (`mt`, `rt`, `nt`)
3. **Ranking da Superação** (`rs`, `rs{XX}`, `v`)
4. **Per-disciplina principal** (`m{X}` / `n{X}` / `r{X}`)
5. **Nota Interna (CIF)** (`nim{X}` / `nip{X}`)
6. **Prior-year carry** (`m21`, `r21`, …)
7. **Contexto socioeconómico** (`hp`, `hm`, `ac`, `im`, `pdq`)
8. **Taxa de retenção** (`tx0`, `tx1`, `tx2`)
9. **Equidade & Equivalência** (`pde`, `pdp`, `pdr`, `eq*`, `re`, `rs`)

## Why

Direct SQL on the unnested bronze needs human-readable column meaning. The
abbreviations follow a regular grammar — `<prefix><discipline_code>` — but the
two discipline codebooks **collide on letter `ma`**: in `m/n/r*` it means
Economia, in `rs*` it means Matemática A. Document once, reference from silver.

## How

### Family 1 — Identity & geography

| Column | Type | Decoded |
|---|---|---|
| `e` | text | **E**scola — full school name |
| `eid` | text PK | Público internal school id (stable across years) |
| `id` | text | Público 4-digit short code (zero-padded). Not a prefix of DGEEC's 6-digit. |
| `co` | text | **CO**ncelho name (no DICOFRE) |
| `c` | text | **C**ontexto do agrupamento: `D` Desfavorável, `F` Favorável, `I` Intermédio, `PRI` privado sem contrato, `PRI_CA` privado com contrato associação, `Açores`, `Madeira` |
| `coduo` | text | **COD**igo da **U**nidade **O**rgânica — DGEEC 6-digit agrupamento código |
| `lt`, `ln` | dp | **L**a**T**itude, **L**o**N**gitude (WGS84) |
| `t` | dp | **T**ipo: `1` privado/coop/IPSS, `2` público |

### Discipline codebook (the collision trap)

**1-letter codebook** — used in `m*`, `n*`, `r*` (principal ranking + Nota Interna):

| Code | Disciplina |
|---|---|
| `m` | Matemática A |
| `p` | Português |
| `b` | Biologia e Geologia |
| `f` | Física e Química A |
| `g` | Geografia A |
| `fl` | Filosofia |
| **`ma`** | **Economia A** ⚠️ |
| **`i`** | **MACS** (Matemática Aplicada às Ciências Sociais) ⚠️ |
| `h` | História A |

**2-letter codebook** — used in `rs*` (Ranking da Superação):

| Code | Disciplina |
|---|---|
| **`ma`** | **Matemática A** ⚠️ |
| `po` | Português |
| `bi` | Biologia e Geologia |
| `fq` | Física e Química A |
| `ge` | Geografia A |
| `fi` | Filosofia |
| `ec` | Economia A |
| `mc` | MACS |

**⚠️ Collision**: `ma` means *opposite* disciplinas in the two codebooks. Silver
promotions MUST disambiguate by prefix — never assume disciplina from suffix alone.

### Ranks are per-partition, not global

Every `ranking_*` column in the bronze table is scoped to its `(year, kind)`
partition. `ranking_exames = 1` means "best in this year's sec or 9ano cohort",
not "best in Portugal across all editions". A naive `SELECT ranking_exames FROM
… WHERE ranking_exames = 1` returns up to 12 rows (one per partition: 7 sec
editions + 5 9ano editions). Always filter by `(year, kind)` before reading a
rank.

**Tie behavior**:

- `ranking_exames` is empirically strictly unique within partition across the
  2018–2024 corpus (verified by `dbt_utils.unique_combination_of_columns`
  test on `(year, kind, ranking_exames)`). `mt` precision is enough to break
  ties.
- `ranking_superacao` ALLOWS TIES via standard competition ranking
  (1, 2, 2, 4 — skipping). Ties cluster at the bottom of the distribution
  where `mt − v` quantizes to limited precision. Example: 2024 9ano has a
  3-way tie at rank 569; the next assigned rank is 572. Silver / gold models
  that depend on unique rank values must dedup or use a `dense_rank()`
  re-projection.

### Family 2 — Headline ranking principal

Ground-truth from screenshot: school Dr. Ferreira da Silva 2024 sec.

| Column | Decoded | DB value | UI label |
|---|---|---|---|
| `mt` | **M**édia **T**otal exames (0–20 sec, 0–5 9ano) | 14.11 | "Média nos Exames" |
| `rt` | **R**anking **T**otal — national position from `mt` | 36 | "Ranking dos Exames: 36.º" |
| `nt` | **N**úmero **T**otal de provas (denominator de `mt`) | 70 | "Número de Provas: 70" |

### Family 3 — Ranking da Superação

Público publishes a 2nd headline ranking each year measuring "how much the
school exceeds its expected average given socioeconomic context". The metric
is `mt − v` (observed minus expected); `rs` ranks schools by that gap.

| Column | Decoded | DB value | UI label |
|---|---|---|---|
| `rs` | **R**anking da **S**uperação — total | 1 | "Ranking de Superação: 1.º" |
| `v` | Média esperada (baseline used to compute Superação) | 11.38 | "Média Esperada: 11,38" |
| `rs{XX}` | Ranking da Superação per disciplina (2-letter codebook) | `rsma=1` | (sub-views in UI) |

Confirmed distinct from `rt`: only 8/1608 schools have `rs = rt`; avg abs diff ≈ 145 positions.

### Family 4 — Per-disciplina principal

Ground-truth from screenshot's "RESULTADOS NOS EXAMES DE CADA DISCIPLINA":

For each disciplina `X` (1-letter code):

| Pattern | Decoded |
|---|---|
| `m{X}` | **M**édia da disciplina (0–20) |
| `n{X}` | **N**úmero de provas na disciplina |
| `r{X}` | **R**anking nacional na disciplina (NULL when sample too small) |

Verified for school 1069 (2024 sec):

| Disciplina | UI N / Média / Pos | DB cols |
|---|---|---|
| Português | 14 / 11.95 / 226.º | `np=14, mp=11.95, rp=226` |
| Matemática A | 16 / 18.16 / 2.º | `nm=16, mm=18.16, rm=2` |
| Biologia e Geologia | 7 / 12.24 / 57.º | `nb=7, mb=12.24, rb=57` |
| Física e Química A | 7 / 9.61 / 484.º | `nf=7, mf=9.61, rf=484` |
| Geografia A | 1 / 17.50 / — | `ng=1, mg=17.5, rg=NULL` (sample < threshold) |
| MACS | 7 / 15.49 / 8.º | `ni=7, mi=15.49, ri=8` |
| Economia A | 5 / 13.98 / 125.º | `nma=5, mma=13.98, rma=125` |
| Filosofia | 13 / 13.94 / 29.º | `nfl=13, mfl=13.94, rfl=29` |

For 9ano only Matemática and Português are reported (`mm`, `mp`, `nm`, `np`, `rm`, `rp`, plus `nt`).

### Family 5 — Nota Interna (CIF)

The school's own internal grading (Classificação Interna de Frequência) for
each disciplina, plus the rank of the gap between CIF and exam — sometimes
called the "inflation index" because privates' CIF inflate vs públicos. Despite
that critique, the columns are populated for both públicos and privados in
recent years (verified on the screenshot school which is `t=2` público).

| Pattern | Decoded | DB value (school 1069) |
|---|---|---|
| `nim{X}` | **N**ota **I**nterna **M**édia na disciplina | `nimm=17.17` (CIF Mat A) |
| `nip{X}` | **N**ota **I**nterna **P**osição (rank by CIF) | `nipm=23` (rank by CIF Mat A) |

16 columns total: `nim/nip × {b, f, fl, g, i, m, ma, p}`.

### Family 6 — Prior-year carry

| Column | Decoded |
|---|---|
| `m21` | Média total no **ano anterior** (despite the `21` suffix) |
| `r21` | Ranking total no ano anterior |
| Older suffixes (`m17`–`m20`, `r17`–`r20`) | Earlier years in older release files |

⚠️ **The `21` suffix is legacy**. In the 2024 file, `m21 = 12.6` and `r21 = 100`
for school 1069 — these correspond to the **2023 edition** (the screenshot
shows "100.º em 2023" and "12,60 em 2023"). The suffix `21` dates back to when
Público first introduced rolling-history columns in the 2021 file and never
renamed them. Always interpret `m21`/`r21` as "previous year's mt/rt" for the
file's vintage.

### Family 7 — Contexto socioeconómico

Composite signals for the agrupamento's environment, ground-truthed from the
"CONTEXTO DO AGRUPAMENTO" panel:

| Column | Decoded | DB value | UI label |
|---|---|---|---|
| `hp` | **H**abilitações **P**ais (anos de escolaridade do pai, média) | 7.77 | "Anos de escolaridade dos PAIS: 7,77" |
| `hm` | **H**abilitações **M**ães (anos de escolaridade da mãe, média) | 9.32 | "Anos de escolaridade das MÃES: 9,32" |
| `ac` | **A**cção Social Escolar — % alunos **SEM** ASE (wealth proxy) | 72 | "SEM Acção Social Escolar: 72%" |
| `im` | **I**dade **M**édia dos alunos no 12.º ano | 17 | "Idade média dos alunos no 12.º: 17" |
| `pdq` | **P**rofessores **D**os **Q**uadros — % corpo docente em quadro | 84.9 | "Número de professores nos quadros: 84,90%" |

⚠️ Prior (wrong) decode in earlier drafts: `pdq` was guessed as "Percursos
Diretos Qualidade"; `hm`/`hp` as histórico; `ac` as Aproveitamento; `im` as
índice mediano; `v` as variância. The screenshot overrides all of those.

### Family 8 — Taxa de retenção

Per-grade retention rates inside the secundário cycle:

| Column | Decoded | DB value | UI label |
|---|---|---|---|
| `tx0` | **T**a**X**a de retenção no **10º** ano | 0 | "10.º Ano: 0%" |
| `tx1` | Taxa de retenção no **11º** ano | 0 | "11.º Ano: 0%" |
| `tx2` | Taxa de retenção no **12º** ano | 8 | "12.º Ano: 8%" |

(For 9ano files these refer to 7º/8º/9º retention respectively — unverified but
the only plausible mapping by analogy.)

### Family 9 — Equidade & Equivalência

The "EQUIDADE" panel in the UI tracks how well a school's ASE-eligible
students complete secundário in 3 years vs the national norm. Empirically all
three `pd*` columns are NULL for school 1069 (matching the screenshot's "—"
placeholders), so the assignment is by structural inference:

| Column | Decoded (inferred from UI structure) |
|---|---|
| `pde` | **P**ercursos **D**iretos **E**scola — % alunos com ASE que concluíram secundário em 3 anos (this school) |
| `pdp` | **P**ercursos **D**iretos do **P**aís — % alunos do país com perfil semelhante que concluíram em 3 anos |
| `pdr` | **P**ercursos **D**iretos — **R**anking da diferença escola vs média nacional comparável |

The Equivalência à Frequência family (for students who can't sit standard exams — IPSS / repeaters / external candidates):

| Column | Decoded |
|---|---|
| `eq1`, `eq2`, `eq3` | Componentes do score de Equivalência (% / %  / signed delta vs norm) |
| `eqnaousar`, `eqnusar` | "**Eq**uivalência **Não Usar**" quality flags (school's eq excluded from ranking) |
| `re` | **R**anking **E**quivalência (rank among schools with eq data) — 303/303 sample-size overlap with `eq1`/`eq2`/`eq3` |

## Verified row dump (Escola Dr. Ferreira da Silva, eid=1069, 2024 sec)

| Family | Columns populated for this row | Verified against |
|---|---|---|
| Identity | e, eid=1069, id=0113, co=Oliveira de Azeméis, c=I (Intermédio), lt, ln, t=2 (público) | School card header |
| Headline principal | mt=14.11, rt=36, nt=70 | "Média nos Exames", "Ranking dos Exames", "Número de Provas" |
| Superação | rs=1, v=11.38 | "Ranking de Superação: 1.º", "Média Esperada: 11,38" |
| Per-disc principal | mm, mp, mb, mf, mg, mfl, mma, mi + nm, np, nb, nf, ng, nfl, nma, ni + rm, rp, rb, rf, rfl, rma, ri (and rg=NULL, sample<threshold) | "Resultados nos exames de cada disciplina" table |
| Per-disc Superação | rsma=1, rspo, rsbi, rsfq, rsfi, rsec, rsmc (rsge=NULL) | (sub-view) |
| Nota Interna | full 16 cols populated | "Notas Internas" panel |
| Prior year | m21=12.6 (=12.60 em 2023), r21=100 | "12,60 em 2023", "100.º em 2023" |
| Contexto | hp=7.77, hm=9.32, ac=72, im=17, pdq=84.9 | "Contexto do agrupamento" panel |
| Taxa retenção | tx0=0, tx1=0, tx2=8 | "Taxa de retenção" 10º/11º/12º |
| Equidade | pde, pdp, pdr all NULL | UI shows "—" for all three |

## See also

- [[publico-rankings]] — source page (URL eras, soft-404, licence, DDL)
- [[bronze-permissive]] — the invariant relaxed by unnesting at bronze
- [[rede-escolar]] — the join target via `coduo`
