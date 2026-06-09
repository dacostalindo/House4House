---
title: PT Education — Geo Amenity Pillar (planning + tracking)
type: plan
last_verified: 2026-06-06
tags: [planning, education, schools, geo-amenity, pillar]
---

## For future Claude

This is the live planning + tracking page for the **Portuguese education
geo-amenity pillar** — a 5-source ingest that will add schools (KG →
university, públicos + privados) as a distance/score amenity dimension to
property listings. Read this before touching anything under
`pipelines/gis/{publico_rankings,rede_escolar,dges_acesso,infoescolas,dgeec_ens_sup}/`
or `dbt/models/staging/education/`. Section §0 (Status) is the
single-page progress dashboard; the rest of the doc is the locked design
underpinning it.

Sibling reference pages (read these alongside, NOT instead):
- [[publico-rankings]] — source page for the 1st pillar source (the only one shipped so far)
- [[publico-rankings-column-legend]] — 91-column ground-truthed legend with UI-screenshot provenance
- [[dbt-source-column-descriptions]] — the column-description convention this pillar pioneered

## 0. Status (live tracking dashboard)

| # | Source | Type | Bronze table | Status | PR |
|---|---|---|---|---|---|
| 1 | [[publico-rankings]] | annual rankings JSON | `bronze_education.raw_publico_rankings` (95 cols, 10,288 rows) | ✅ **Shipped** (2 DAGs + bronze + legend + tests) | [#52](https://github.com/dacostalindo/House4House/pull/52) |
| 2 | [[rede-escolar]] | KG → sec register (paginated ArcGIS REST) | `bronze_education.raw_rede_escolar` (46 cols, 8,670 rows / 90.47% with geom) | ✅ **Shipped + end-to-end verified** (live Airflow + bronze query) | this PR |
| 3 | [[dgeec-ens-sup]] | DGEEC shapefile — higher-ed register | `bronze_education.raw_dgeec_ens_sup` (21 cols, 321 rows / 100% with geom, 321 unique UO codes) | ✅ **Shipped + end-to-end verified** (live Airflow + bronze query) | this PR |
| 4 | [[dges-acesso]] | higher-ed ranking — 36 source files (XLSX/XLS/ODS), 2014–2025 × 3 phases | `bronze_education.raw_dges_acesso` (22 cols, ~40k rows expected) + silver `silver_dges_acesso_uo` (vagas-weighted, per UO/year/phase) | ✅ **Shipped** (3 DAGs + bronze + stg + silver + 36-URL dict + cross-format parser); E2E Airflow run pending | this PR |
| 5 | `infoescolas` (XLSX) | 3º ciclo cross-check | `bronze_education.raw_infoescolas` | 🔲 Endpoint verified; demoted to fallback after Público 9ano discovery | — |

### Phase 0 — bootstrap (current sprint)

- [x] Lock all 18 decisions (§2 below)
- [x] Verify all source endpoints with real fetches
- [x] Bootstrap source #1 (`publico_rankings`):
  - [x] Ingestion DAG (web → MinIO, 12 blobs)
  - [x] Bronze loader DAG (MinIO → Postgres, 10,288 rows)
  - [x] Unnest + rename to 91 human-readable Portuguese columns
  - [x] Ground-truth column legend (verified vs Público UI for eid=1069)
  - [x] dbt sources YAML — all 95 cols documented, 18/18 tests pass
  - [x] Wiki source page + concept legend + column-description convention page
- [x] Bootstrap source #2 ([[rede-escolar]]) — paginated ArcGIS REST custom DAG:
  - [x] Config module (endpoint + count probe + sanity bands + headers)
  - [x] Ingestion DAG (probe_and_fanout → download_page.expand → upload_page.expand → summarize; pre-computed offsets @ 2000 stride; `@monthly`)
  - [x] Bronze loader DAG (discover_latest_run → fanout_pages → ensure_table → load_page.expand → summarize; dual-CRS geom 4326+3763 per [[2026-05-10-dual-crs-storage]])
  - [x] Rename 42 ArcGIS field names → readable Portuguese columns
  - [x] dbt sources YAML — 46 cols documented + unique (run_date, codigo_escola) test
  - [x] Wiki source page with pagination verification table
  - [x] Live-verified field set matches rename map exactly (zero drift, 2026-06-06)
  - [x] End-to-end Airflow run on the live stack: ingestion 9s (5 pages → MinIO), bronze load 5s, 8,670 rows in `bronze_education.raw_rede_escolar`, 0 PK duplicates, probed school `614798` round-trips identically
- [x] Bootstrap source #3 ([[dgeec-ens-sup]]) — shapefile bundle via custom DAG (template auto-extract destroys sidecars):
  - [x] Config module (URL + size/feature bands + sidecar list + layer name)
  - [x] Ingestion DAG (download_and_validate → upload_to_minio → summarize; ZIP stored intact at `s3://raw/dgeec_ens_sup/{run_date}/Estab_Ens_Sup_Portugal.zip`)
  - [x] Bronze loader DAG (discover_latest_run → ensure_table → load → summarize; pyogrio.raw.read + manual Point WKB decode → dual-CRS geom 4326+3763 per [[2026-05-10-dual-crs-storage]])
  - [x] Rename 16 DBF (10-char truncated) field names → readable Portuguese; `Código do Estabelecimento` deliberately renamed `codigo_instituicao` (non-unique; means "parent institution", not "building")
  - [x] dbt sources YAML — 21 cols documented + unique (run_date, codigo_unidade_organica) test
  - [x] Wiki source page with live probe table + DBF-truncation trap + estabelecimento-vocabulary trap
  - [x] Live-verified field set matches rename map exactly (zero unknown keys, 2026-06-07)
  - [x] End-to-end Airflow run: ingestion 3s (1 ZIP → MinIO), bronze load 5s, 321 rows in `bronze_education.raw_dgeec_ens_sup`, 321 unique PKs, 0 NULL geom, sample UO `0100` (Universidade dos Açores) round-trips identically
- [x] Bootstrap source #4 ([[dges-acesso]]) — 36-file XLSX/XLS/ODS mix with vagas-weighted aggregation:
  - [x] Config (36-entry YEAR_PHASE_URLS dict — no pattern; 12 years × 3 phases; 8 .xlsx + 19 .xls + 9 .ods)
  - [x] Ingestion DAG (param `{year, phase}` lookup → size + row-count band-check → MinIO `raw/dges_acesso/{year}/fase_{n}/{filename}`)
  - [x] Backfill DAG (one task per (year, phase) for clean failure isolation across 36 files)
  - [x] Bronze loader DAG (walks ALL MinIO blobs each run; multi-format parser via openpyxl/xlrd/odfpy routed by URL suffix; SOURCE_LABEL_TO_COLUMN collapses synonyms across phases AND format variants; PK = (year, phase, codigo_instit, codigo_curso); 2018 .ods (1)(2)... annotation row filtered generically)
  - [x] dbt sources YAML — 22 cols documented + unique (year, phase, codigo_instit, codigo_curso) test
  - [x] dbt staging `stg_dges_acesso` (1:1 typed cleanup) + silver `silver_dges_acesso_uo` (vagas-weighted nota per UO/year/phase, NULL-nota excluded from both num+denom, LEFT JOIN to latest dgeec_ens_sup with unmatched_uo flag)
  - [x] Wiki source page ([[dges-acesso]]) with 3-trap doc (Família A, URL-pattern lie, code-subset)
  - [x] Parser locally verified against 5 representative files (2025 F1/F2/F3 .xlsx + 2022 F1 .xls + 2018 F1 .ods) — zero unknown labels in any
  - [ ] E2E Airflow run on the live stack (deferred to next session — Airflow not running in this worktree)
- [ ] Bootstrap source #5 (`infoescolas`) — XLSX as fallback for 3º ciclo

### Phase 1 — silver promotions (staging tier complete 2026-06-09; gold-mart prerequisites next)

- [x] `stg_publico_rankings_sec.sql` — 1:1 typed view, ~35 cols, dual-CRS geom. Joins deferred to silver per layer-separation principle. ✅ (PR-B 2026-06-09)
- [x] `stg_publico_rankings_9ano.sql` — 1:1 typed view, ~25 cols, PT bbox filter (drops 18 bad-coord rows), `codigo_uo_dgeec` passed through. ✅ (PR-B 2026-06-09)
- [x] `stg_rede_escolar.sql` — typed register, filter `situacao = 'Em funcionamento'` + drop NULL geoms, ~17 canonical cols + dual-CRS geoms ✅ (PR-A 2026-06-09)
- [x] `stg_dgeec_ens_sup.sql` — typed higher-ed register, latest-snapshot filter, dual-CRS geoms ✅ (PR-A 2026-06-09)
- [x] `stg_dges_acesso.sql` — vagas-weighted nota último colocado aggregation per UO ✅ (already shipped with source #4 / PR #56)
- [x] `silver_dges_acesso_curso.sql` (NEW) — per-curso sibling to `silver_dges_acesso_uo`, keeps `nome_curso` + `nome_instituicao` + `grau`; 38,922 rows ✅ (PR-A 2026-06-09)
- [x] `silver_dges_acesso_uo` CTE swap — inline `dgeec_latest_run` CTE replaced with `ref('stg_dgeec_ens_sup')` ✅ (PR-A 2026-06-09)

### Phase 2 — gold marts (started 2026-06-09)

- [x] `silver_publico_rankings_sec` — latest-year-per-school rollup, 661 schools, 0-20 score ✅ (PR-C 2026-06-09)
- [x] `silver_publico_rankings_9ano` — latest-year-per-school rollup, 1,313 schools, 0-5 score ✅ (PR-C 2026-06-09)
- [x] `xref_publico_dgeec` — Público eid → DGEEC codigo_escola bridge, 1,874/1,974 matched (94.9%); 2-stage ensemble algorithm with sim+distance sanity guards: Stage 1 direct_uo_fuzzy (9ano UO-restricted, 921) + Stage 2 ensemble (sec + 9ano residual; trigram + Levenshtein + Jaccard + phonetic vote within concelho-or-2km window). Post-vote guards: sim≥0.7 AND dist≤3km. Tier breakdown: high=1,802, medium=42, low=30, unmatched=100. ✅ (PR-D 2026-06-09 commits 3+4)
- [x] `dim_school` — canonical school dim, all 5 levels, `codigo_dgeec` text PK accepting both 4-digit higher-ed UO + 6-digit basic/sec CODESCME (disjoint code spaces, 0 collisions). 8,117 rows = 7,796 basic_sec + 321 higher_ed. Identity + geometry + harmonized `natureza_publico_privado` + level flags (`has_kg`/`has_basic_1..3`/`has_sec`/`has_higher_ed`). Rankings moved to sibling fact. ✅ (PR-E 2026-06-09)
- [x] `fact_school_ranking` — time-series ranking mart, 15,716 rows (sec 4,257 over 2018-2024 + 9ano 5,639 over 2018-19/2022-24 + higher_ed 5,820 over 2014-2025 × 3 fases). PK = (codigo_dgeec, kind, year, phase). Joins to dim_school on codigo_dgeec. ✅ (PR-E commit 2 / 2026-06-09)
- [ ] `schools_kg|primary|middle|secondary|higher_ed` — per-level views
- [ ] `listing_school_features` — per-listing nearest-school + best-score features

### Open Qs to resolve before silver

- [ ] **CAOP-Açores + CAOP-Madeira** sourcing (mainland CAOP doesn't cover islands; ~210 freguesias). See §9 Q6.
- [ ] **`id` (Público 4-digit) ↔ DGEEC bridge** for secundário (5 manual lookups to design the fuzzy join thresholds). See §9 Q2.
- [ ] **`dim_school` PK strategy**: discriminator col vs split tables (6-digit basic/sec vs 4-digit higher-ed). See §9 Q5.

**Legend**: ✅ shipped & verified · ⏳ in progress · 🔲 not started · ⚠️ blocked

---

## 1. Goal & success criteria

Add **schools** as a geo amenity dimension to property listings, with quality signal where defensible.

A v1 ship is correct if:
- Every active school in continental + island Portugal (KG → university, public + private) has a row with `(lat, lon, código DGEEC, nome, level, natureza, agrupamento_codigo, distrito, concelho, address)`.
- Every secondary school with national-exam data has a `ranking_score` (Público média total, 2023/24 academic year).
- Every 3º ciclo school has a `ranking_score` (Infoescolas "Percursos Diretos de Sucesso", 2022/23 academic year).
- Every higher-ed institution (public, concurso nacional) has a `ranking_score` (DGES vagas-weighted nota último colocado, current 1ª fase).
- A property listing can be enriched with `nearest_school_within_500m_by_level` and `best_score_within_2km_by_level` via PostGIS in <50ms.

Out of scope for v1: per-disciplina raw exam scores, historical trend (>1 year), A3ES accreditation status, IAVE microdata, freguesia-level rollups of attainment (covered by separate BGRI/Censos source).

---

## 2. Locked decisions

| # | Question | Decision |
|---|---|---|
| 1 | Schema shape | **5 per-level tables**: `schools_kg`, `schools_primary`, `schools_middle`, `schools_secondary`, `schools_higher_ed`. Indicators inline (denormalized agrupamento). |
| 2 | Warehouse integration | **Full bronze → silver → gold dbt source**, one per data source, mirrors existing 17 GIS sources pattern. |
| 3 | Ranking metric (secundário) | **Per-school média total exames nacionais**, latest year only (v1). |
| 4 | Time scope | **Latest year + full historical Público backfill (2018–2024)** — verified via `3ciclo-all-years.har` 2026-06-06. Filename/host conventions changed 3× over 7 years; backfill needs a per-year URL resolver table (see §3.2). |
| 5 | Register source — basic/sec | **ArcGIS Online FeatureServer** (`RedeEscolar_mapa` + `UnidadesOrganicas_mapa`). NOT GesEdu HTML. |
| 6 | Ranking source — secundário | **Público S3 JSON** (`rankingssec.js`). No paywall, no auth. |
| 7 | Geocoding | **Not needed.** ArcGIS + Público both ship lat/lon. Nominatim dropped. |
| 8 | KG / primary ranking | **NULL** — register only. |
| 9 | Higher-ed ranking | **DGES `fase1aYY_site.xlsx`**, vagas-weighted nota último colocado, 1ª fase, current year. |
| 10 | 3º ciclo (9º ano) ranking | **Público `rankings9ano.js`** (primary, raw Mat+Port averages, 1,161 schools, Açores+Madeira included). Infoescolas XLSX kept as fallback / cross-check. |
| 11 | Canonical PK | **DGEEC 6-digit `código de escola`** for basic/sec. **DGEEC 4-digit `Código da Unidade Orgânica`** for higher-ed. |
| 12 | Refresh cadence | **Annual**, April-anchored (after Público publishes). DGES + 1ª fase landing in late August separate trigger. |
| 13 | Schema columns | Lean 11+2: `codigo_dgeec, nome, level, natureza, agrupamento_codigo, agrupamento_nome, dicofre, distrito, concelho, address, lat, lon, ranking_score, ranking_year`. |
| 14 | Agrupamento model | **Denormalized** — agrupamento codigo + nome stored on each school row (FK to `agrupamentos` table optional). |
| 15 | Higher-ed location | DGEEC `Estabelecimentos do Ensino Superior` shapefile, INSPIRE ATOM (CC BY 4.0). 321 records, verified downloaded. |
| 16 | Identity reconciliation | DGEEC 6-digit is authoritative for basic/sec. Público → DGEEC bridge via fuzzy (nome+concelho+ST_DWithin 200m). Higher-ed: DGES 4-digit codes already match DGEEC shapefile. |

---

## 3. The four data sources

### 3.1 ArcGIS Online — Rede Escolar (KG → secundário register)

**Authority**: AGSE/DGEEC, hosted on `agseip.maps.arcgis.com`.
**Endpoint**:
```
GET https://services-eu1.arcgis.com/pXkWEYl9JkoX4UHe/arcgis/rest/services/RedeEscolar_mapa/FeatureServer/0/query
  ?f=json
  &where=1=1
  &outFields=*
  &resultOffset=N
  &resultRecordCount=2000
  &returnGeometry=true
  &outSR=4326
```
Companion: `…/UnidadesOrganicas_mapa/FeatureServer/0/query` for agrupamentos.

**Auth**: none. Public ArcGIS Online layer.
**Pagination**: 2000/req default (4× factor → 8000 possible). ~2 GETs for full PT.
**Licence**: not explicitly stated; ArcGIS Online "no fees" terms; treat as © DGEEC, internal use defensible.

**Schema (42 fields, subset that matters)**:
| Field | Type | Maps to |
|---|---|---|
| `DGEEC` | string | **`codigo_dgeec`** ← PK |
| `NOME` | string | `nome` |
| `CODUOME` | string | `agrupamento_codigo` |
| `NOMEUO` | string | `agrupamento_nome` |
| `NIFUO` | string | (skip) |
| `CICLO_COD`, `CICLO` | string | `level` (pre/1c/2c/3c/sec/prof) |
| `NATUREZAINSTITUCIONAL_DESC`, `TUTELA_DESC`, `GRUPONATUREZAINST` | string | `natureza` |
| `COD_DISTRITO`, `DISTRITO` | string | `distrito` |
| `COD_CONCELHO`, `CONCELHO` | string | `concelho` |
| `MORADA`, `CP4`, `CP3`, `LOCALIDADE` | string | `address` (concat) |
| `LATITUDE`, `LONGITUDE` | double | `lat`, `lon` (also `geometry` in 102100 Web Mercator) |
| `SITUACAOESCOLA`, `ESCOLA_EXTINGUIR` | string/flag | filter — only ingest active |
| `URL`, `EMAIL`, `TELEFONE` | string | (optional, v2) |

**Gaps**: freguesia/DICOFRE missing — derive via `ST_Within(geom, caop_freguesias)` against the existing CAOP source.

**Gotchas**:
- Use `f=json` not `f=pbf` for readability.
- Reproject geom 102100 → 4326 (or just trust `LATITUDE`/`LONGITUDE` columns).
- Filter `SITUACAOESCOLA = activa` and `ESCOLA_EXTINGUIR != 1`.
- Use `_mapa` layer (42 cols, has DGEEC + geom). Skip `_tab` (19 cols, no DGEEC, no geom).
- Throttle ~250ms between requests; respect `cacheHint=true`.

---

### 3.2 Público S3 — Ranking das Escolas (secundário ranking)

**Authority**: Público (commercial editorial), data derived from IAVE.
**Endpoints** — verified per-year URL table (from `3ciclo-all-years.har`, fetched 2026-06-06):

| Year | sec URL | sec size | 9ano URL | 9ano size |
|---|---|---|---|---|
| 2018 | `https://static.publicocdn.com/files/rankings2018/data/listas/rankings2018sec.js` | 322 KB | `…/rankings20189ano.js` | 404 KB |
| 2019 | `https://static.publicocdn.com/files/rankings2019/data/listas/rankings2019sec.js` | 308 KB | `…/rankings20199ano.js` | 376 KB |
| 2020 | `https://static.publicocdn.com/files/rankings2020/data/listas/rankings2020sec.js` | 314 KB | **N/A** (COVID — Provas Finais 9º ano cancelled) | — |
| 2021 | `https://static.publico.pt/files/rankings2021/data/listas/rankingssec.js` | 764 KB | **N/A** (COVID — cancelled) | — |
| 2022 | `https://static.publico.pt/files/rankings2022/data/listas/rankingssec.js` | 1034 KB | `…/rankings9ano.js` | 1033 KB |
| 2023 | `https://static.publico.pt/files/rankings2023/data/listas/rankingssec.js` | 583 KB | `…/rankings9ano.js` | 601 KB |
| 2024 | `https://static.publico.pt/s3/rankings2024/data/listas/rankingssec.js` | 618 KB | `…/rankings9ano.js` | 639 KB |

Headers required: `Referer: https://www.publico.pt/`, `Origin: https://www.publico.pt`.
**Auth**: none. CloudFront-backed S3.
**Hosting eras** (3 transitions in 7 years):
- 2018–2020: host `static.publicocdn.com`, path `/files/`, filename embeds year (`rankings{Y}sec.js`, `rankings{Y}9ano.js`).
- 2021–2023: host `static.publico.pt`, path `/files/`, filename drops year (`rankingssec.js`, `rankings9ano.js`).
- 2024+: host `static.publico.pt`, path `/s3/`, filenames unchanged.
**Gotcha**: HTTP 200 with body size = 22634 bytes = the standard Público HTML 404 page (soft-404). Validate by size or content sniff, not status code.
**Refresh**: next release expected `rankings2025/` Apr 2026; assume `/s3/` path persists; probe quarterly Mar–May.

**Schema** (40 fields in 9ano, 77 in secundário — superset; key subset shown):
| Field | Type | Maps to |
|---|---|---|
| `eid` | string-int | Público internal id |
| `e` | string | `nome` |
| `id` | string (4-digit zero-padded, always present) | Público short code; relationship to DGEEC TBD — but join is solved via `coduo` for 9ano (79%) |
| **`coduo`** | string (6-digit) | **agrupamento código DGEEC** — populated for 921/1,161 9ano rows (79.3%), EMPTY for all 624 secundário rows |
| `co` | string | `concelho` (name only) |
| `c` | string | region group: `D`/`F`/`I` (continental), `PRI`/`PRI_CA` (privates), `Açores`, `Madeira` |
| `t` | int | `natureza`: 1=privado, 2=público |
| `mt` | string-float | **média total exames** = `ranking_score` (scale 0–20 for sec; 0–5 for 9ano Provas Finais) |
| `rt` | string-int | posição global (NULL when sample too small) |
| `lt`, `ln` | string-float | `lat`, `lon` (WGS84) |
| `mm`, `mp`, `mb`, `mf`, `mg`, `mi`, `mma`, `mfl` | float | per-disciplina (sec: Mat, Port, Bio, FQ, Geo, Ing, MatA, Fil; 9ano: only `mp`+`mm` = Port+Mat) |
| `m21`, `r21`, `rs` | float/int | prior year delta |

**Coverage**:
- Secundário: 518 público + 106 privado, includes Açores+Madeira, 274 concelhos.
- 9º ano: 982 público + 179 privado (1,161 total), Açores (33) + Madeira (23) + continental + 153 priv + 26 priv_CA.

**Joinability strategy** (different per file):
- **9ano**: 79.3% of rows ship `coduo` (6-digit DGEEC agrupamento código) → direct join to ArcGIS `CODUOME`. The remaining ~21% (mostly privados/IPSS without UO grouping) → fuzzy `ST_DWithin + name + concelho`.
- **Secundário**: `coduo` is empty for all rows → fuzzy join is the only path. Approach:
  1. Try `LEFT(DGEEC, 4) = LPAD(id, 4)` for cheap prefix match (validate on 5 schools first).
  2. Fall back to: `ST_DWithin(publico.geom, dgeec.geom, 200m) AND similarity(unaccent(nome), unaccent(e)) > 0.6 AND concelho_match`.
  3. Manual reconciliation of unmatched (~5–10% expected).
- Bridge table `xref_publico_dgeec(publico_eid, codigo_dgeec, match_method, match_score)` resolves both per yearly refresh.

**Licence**: data is © Público. **Internal analytical use OK**; **do not republish raw `mt`/`rt`**. Cite Público in any user-facing display.

**Sibling files** (resolved via second HAR + confirmed):
- ✅ `…/rankings9ano.js` — 3º ciclo Provas Finais (verified, 1,161 rows, see schema above).
- 🔲 `…/rankings2025/…` — next year, not yet published as of 2026-06-06 — probe quarterly.
- 🔲 `…/rankings{2020..2023}/…` — historical, in scope per user — probe + backfill.
- ℹ️ `…/pt_pt.js` — concelho SVG choropleth (52 KB, has DICOFRE codes — useful sidecar for concelho name ↔ DICOFRE lookup).

---

### 3.3 DGES — Acesso ao Ensino Superior (higher-ed ranking)

**Authority**: DGES (Ministério da Ciência, Tecnologia e Ensino Superior).
**Endpoint**:
```
GET https://wwwcdn.dges.gov.pt/sites/default/files/fase1a25_site.xlsx   (latest 2025/26 1ª fase)
GET https://wwwcdn.dges.gov.pt/sites/default/files/fase1_24.xlsx        (2024/25 1ª fase)
```
File-name convention: `fase{1,2,3}[_a]?_{YY}.xlsx`. Historical 1997–2025 all present.

**Auth**: none. Static XLSX on Drupal CDN.
**Parse**: `pandas.read_excel(..., sheet_name='Mínimas', header=4)`.
**Size**: ~90 KB, ~1,132 rows per phase.

**Schema (sheet `Mínimas`)**:
| Col | Field | Notes |
|---|---|---|
| B | `Código Instit.` | **4-digit, joins DGEEC shapefile `Código da Unidade Orgânica`** |
| C | `Código Curso` | 4-digit |
| D | `Nome da Instituição` | |
| E | `Nome do Curso` | |
| F | `Grau` | L1 / MI / PL / PM |
| G | `Vagas Iniciais` | |
| H | `Colocados` | |
| L | **`Nota do últ. colocado (cont. geral)`** | 0–200 scale; null when course didn't fill |

**Coverage**: 170 unidades orgânicas (vs 321 in DGEEC shapefile — gap = privates + militar/policial use concursos próprios, not concurso nacional). This is **intentional**, not a bug.

**Aggregation → `ranking_score`** (per unidade orgânica):
```sql
SELECT
  codigo_instit,
  SUM(nota_ultimo_colocado * vagas) / NULLIF(SUM(vagas), 0) AS ranking_score
FROM dges_fase1
WHERE grau IN ('L1', 'MI')
  AND nota_ultimo_colocado IS NOT NULL
GROUP BY codigo_instit;
```
Vagas-weighted mean across L1+MI courses, 1ª fase, current year. Excludes PL/PM (preparatórios over-23s, different scale) and unfilled courses (no signal).

**Join to higher-ed register**:
```sql
schools_higher_ed.codigo_dgeec_orgânica = LPAD(dges_fase1.codigo_instit, 4, '0')
```

---

### 3.4 Infoescolas — 3º Ciclo (FALLBACK / cross-check only)

> **Demoted from primary**: Público `rankings9ano.js` is now the primary source for 3º ciclo ranking (raw Mat+Port Provas Finais averages, 1,161 schools, Açores+Madeira included). Infoescolas kept as cross-check (continente-only, 434 schools, composite "Percursos de Sucesso" metric — useful as a sanity check on Público's `mt`).

**Authority**: DGEEC/MECI, official Infoescolas portal.
**Endpoint**:
```
GET https://infoescolas.medu.pt/docs/2024/InfoEscolas2024_3Ciclo_DadosPorEscola.xlsx
Archive index: https://infoescolas.medu.pt/bds.asp
```
**Auth**: none.
**Size**: 820 KB, 7 sheets, 434 schools (continente only).

**Critical schema** (sheet `PercursosDiretosSucesso`):
| Col | Field | Notes |
|---|---|---|
| A | **`Código Escola DGEEC`** | 6-digit, joins basic/sec register directly |
| B | `Nome da Escola` | |
| C | `Município` | |
| D+ | `% alunos com positiva em Provas Nacionais 9º ano após percurso sem retenções` | composite metric → `ranking_score` |
| later | `Categoria da Escola` | DGEEC equity tier |

**Coverage**: públicos + privados, continente only (no Açores/Madeira).

**Caveat**: This is a **composite "percursos de sucesso"** rate, NOT raw per-disciplina provas-finais averages. For raw scores we'd need IAVE microdata (excluded by user). For v1 amenity scoring, composite is more interpretable anyway.

**Refresh**: annual, files dated 2025-01-10 for the 2024 edition (covering AY 2022/23).

---

### 3.5 DGEEC — Estabelecimentos do Ensino Superior (higher-ed register)

**Status**: ✅ Shipped + end-to-end verified 2026-06-07. See [[dgeec-ens-sup]] for the
authoritative source page; this section is the planning record and is kept for archaeology.

**Authority**: DGEEC, via SNIG/DGTerritorio.

**Endpoint**: `http://geo2.dgterritorio.gov.pt/ATOM-download/DGEEC/Estab_Ens_Sup_Portugal.zip`
**Licence**: CC BY 4.0.
**Format**: Shapefile (EPSG:4326), 321 records, point geometry, UTF-8 encoded.

**Schema (planning-time draft was WRONG on two counts — corrected by the 2026-06-07 live probe):**

1. **Field count is 16, not 14.** Planning draft missed `Outro telefone` + `Fax`. Full list:
   `Código do Estabelecimento`, `Estabelecimento`, `Código da Unidade Orgânica`,
   `Unidade Orgânica`, `Natureza e Tipo` (6 categories), `Website`, `Email`, `Morada`,
   `Código Postal`, `Distrito`, `Concelho`, `Telefone`, `Outro telefone`, `Fax`,
   `Latitude`, `Longitude`.
2. **DGEEC's "Estabelecimento" is the parent institution, NOT a physical building.**
   `Código do Estabelecimento` is non-unique (101 distinct values across 321 rows — e.g.
   all UOs of Universidade do Porto share `1100`). The shapefile's grain is **Unidade
   Orgânica** (faculdade/escola-level); the natural PK is `Código da Unidade Orgânica`
   (321/321 unique). This aligns with decision #11; the bronze rename map calls the
   parent-institution column `codigo_instituicao` to defuse DGEEC's confusing
   vocabulary.

**Ingest**: custom DAG (NOT `ogr2ogr` direct; NOT the GIS template). The GIS template
auto-extracts ZIPs to a single inner file and deletes the ZIP, which destroys shapefile
sidecar bundles — no existing source in the repo actually uses `expected_format='shp'`.
The bronze loader uses `pyogrio.raw.read()` + manual Point WKB decode (no
geopandas/shapely deps required) and dual-CRS storage (`geom` 4326 + `geom_pt` 3763) per
[[2026-05-10-dual-crs-storage]], mirroring the pattern shipped by [[rede-escolar]]. Both
4-digit codes (`codigo_instituicao`, `codigo_unidade_organica`) are stored TEXT zero-padded
to width 4 so silver joins to DGES rankings work without re-padding. Joins to
[[dges-acesso]] via `codigo_unidade_organica`.

---

## 4. Output schema

### 4.1 Per-level tables (gold layer)

All 5 tables share the same columns. Differ only by populated indicator scope.

```sql
CREATE TABLE marts.schools_<level> (
  codigo_dgeec        text PRIMARY KEY,           -- DGEEC 6-digit (4-digit for higher_ed)
  nome                text NOT NULL,
  level               text NOT NULL,              -- kg | primary | middle | secondary | higher_ed
  natureza            text NOT NULL,              -- publico | privado | cooperativo | ipss | militar
  agrupamento_codigo  text,                       -- nullable for higher_ed
  agrupamento_nome    text,
  dicofre             char(6),                    -- derived via ST_Within(geom, caop_freguesias)
  distrito            text NOT NULL,
  concelho            text NOT NULL,
  address             text,
  lat                 double precision NOT NULL,
  lon                 double precision NOT NULL,
  geom                geometry(Point, 3763),      -- ETRS89/PT-TM06, matches warehouse SRID
  ranking_score       double precision,           -- NULL for kg, primary
  ranking_year        smallint,                   -- e.g. 2024
  ranking_source      text,                       -- 'publico' | 'infoescolas' | 'dges'
  ranking_method      text,                       -- 'media_total_exames' | 'percursos_diretos_sucesso' | 'vagas_weighted_nota_ult_colocado'
  source_ingested_at  timestamptz NOT NULL,
  CONSTRAINT chk_natureza CHECK (natureza IN ('publico','privado','cooperativo','ipss','militar')),
  CONSTRAINT chk_level    CHECK (level IN ('kg','primary','middle','secondary','higher_ed'))
);
CREATE INDEX schools_<level>_geom_gist ON marts.schools_<level> USING GIST (geom);
CREATE INDEX schools_<level>_concelho  ON marts.schools_<level> (concelho);
```

### 4.2 Optional ancillary tables

```sql
-- Agrupamentos table (one-to-many with basic/sec schools)
CREATE TABLE marts.agrupamentos (
  codigo        text PRIMARY KEY,
  nome          text NOT NULL,
  sede_concelho text,
  num_escolas   smallint,
  ...
);

-- Identity bridge: Público eid ↔ DGEEC codigo_dgeec
CREATE TABLE marts.xref_publico_dgeec (
  publico_eid      integer PRIMARY KEY,
  codigo_dgeec     text NOT NULL,
  match_method     text NOT NULL,        -- 'id_prefix' | 'geo_name' | 'manual'
  match_score      double precision,
  reviewed_by      text,
  reviewed_at      timestamptz
);
```

---

## 5. Pipeline architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│ BRONZE                                                                │
├───────────────────────────────────────────────────────────────────────┤
│ rede_escolar_arcgis   ← Airflow @daily/never, dlt JSON paginator      │
│ unidades_organicas    ← (same DAG, sibling)                           │
│ publico_rankings_sec  ← Airflow @yearly Apr, dlt single fetch         │
│ publico_rankings_3c   ← (same DAG if sibling URL confirmed)           │
│ dges_acesso_fase1     ← Airflow @yearly Sep, dlt single XLSX          │
│ infoescolas_3c        ← Airflow @yearly Jan, dlt single XLSX          │
│ dgeec_ens_sup_shp     ← Airflow manual, pyogrio + dual-CRS psycopg2   │
├───────────────────────────────────────────────────────────────────────┤
│ SILVER (dbt staging)                                                  │
├───────────────────────────────────────────────────────────────────────┤
│ stg_rede_escolar         (typed, geom 3763, freguesia via CAOP join)  │
│ stg_unidades_organicas                                                │
│ stg_publico_rankings_sec (typed, geom 3763)                           │
│ stg_dges_acesso          (typed, vagas-weighted aggregation)          │
│ stg_infoescolas_3c                                                    │
│ stg_dgeec_ens_sup                                                     │
├───────────────────────────────────────────────────────────────────────┤
│ GOLD (dbt marts)                                                      │
├───────────────────────────────────────────────────────────────────────┤
│ dim_school                  (canonical school dim, all levels)        │
│ xref_publico_dgeec          (bridge)                                  │
│ schools_kg                  (level filter on dim_school)              │
│ schools_primary             (idem)                                    │
│ schools_middle              (+ ranking from infoescolas_3c)           │
│ schools_secondary           (+ ranking from publico via xref)         │
│ schools_higher_ed           (+ ranking from dges)                     │
│ agrupamentos                                                          │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 6. Scoring formula (gold → property amenity)

Per listing, computed in gold mart `listing_school_features`:

```sql
SELECT
  l.listing_id,
  -- count of schools within 500m, by level
  COUNT(*) FILTER (WHERE s.level='kg'        AND ST_DWithin(l.geom, s.geom, 500)) AS n_kg_500m,
  COUNT(*) FILTER (WHERE s.level='primary'   AND ST_DWithin(l.geom, s.geom, 500)) AS n_primary_500m,
  COUNT(*) FILTER (WHERE s.level='middle'    AND ST_DWithin(l.geom, s.geom, 500)) AS n_middle_500m,
  COUNT(*) FILTER (WHERE s.level='secondary' AND ST_DWithin(l.geom, s.geom, 500)) AS n_secondary_500m,
  COUNT(*) FILTER (WHERE s.level='higher_ed' AND ST_DWithin(l.geom, s.geom, 2000))AS n_higher_ed_2km,
  -- best ranking_score within 2km, by level
  MAX(s.ranking_score) FILTER (WHERE s.level='secondary' AND ST_DWithin(l.geom, s.geom, 2000)) AS best_sec_score_2km,
  MAX(s.ranking_score) FILTER (WHERE s.level='middle'    AND ST_DWithin(l.geom, s.geom, 2000)) AS best_mid_score_2km,
  -- distance to nearest secondary with score in top decile
  MIN(ST_Distance(l.geom, s.geom)) FILTER (WHERE s.level='secondary' AND s.ranking_score > <p90>) AS dist_to_top10pct_sec
FROM marts.listings l
LEFT JOIN dim_school s ON ST_DWithin(l.geom, s.geom, 5000)
GROUP BY l.listing_id;
```

---

## 7. Implementation roadmap

**Phase 0 — bootstrap (current sprint)**:
- [x] Lock all decisions (this doc).
- [x] Verify all 4 endpoints with real fetches.
- [x] Probe `rankings2025/` + historical Público URLs (2026-06-06: 2018–2024 all available, 3 host eras, COVID gap in 9ano for 2020+2021 — see §3.2).
- [x] Bootstrap source #1 — `publico_rankings` shipped end-to-end (2 DAGs, 95-col unnested bronze, 10,288 rows verified, column legend ground-truthed against UI). See PR #52.
- [ ] Bootstrap remaining 4 sources (rede_escolar, dgeec_ens_sup, dges_acesso, infoescolas).

**Phase 1 — ingest skeletons (next session, ~2 days)**:
- Bronze DAGs for all 5 sources.
- Bronze tests: schema match, row count > thresholds.

**Phase 2 — staging (silver) (~2 days)**:
- dbt staging models with types, geom reprojection, freguesia join, deduplication.
- Build `xref_publico_dgeec` with `id`-prefix hypothesis verification.

**Phase 3 — marts (gold) (~3 days)**:
- `dim_school` + 5 per-level views.
- `listing_school_features` mart for property enrichment.

**Phase 4 — wiki + handoff (~half day)**:
- 4 new `wiki/sources/{name}.md` pages.
- Update `wiki/index.md` §"By area of code" — add `pipelines/gis/{rede_escolar,publico_rankings,dges_acesso,infoescolas}/` routing.
- Update `wiki/concepts/` with `geo-amenity-scoring.md` if not present.

---

## 8. `add-gis-source` bootstrap params

Four invocations of the skill, with all params pre-filled here.

### 8.1 `rede_escolar`
- Source name: `rede_escolar`
- Authority: AGSE / DGEEC
- Format: ArcGIS REST FeatureServer (JSON)
- Endpoint: `https://services-eu1.arcgis.com/pXkWEYl9JkoX4UHe/arcgis/rest/services/RedeEscolar_mapa/FeatureServer/0/query`
- Companion: `…/UnidadesOrganicas_mapa/FeatureServer/0/query`
- Pagination: `resultOffset` + `resultRecordCount=2000`
- SRID: 4326 (reproject to 3763 in silver)
- Refresh: monthly (school network changes mid-year)
- Licence: ArcGIS Online "no fees", treat as © DGEEC

### 8.2 `publico_rankings`
- Source name: `publico_rankings`
- Authority: Público (commercial)
- Format: JSON (served as `.js` from S3)
- Endpoints (both verified):
  - `https://static.publico.pt/s3/rankings{YEAR}/data/listas/rankingssec.js` (secundário)
  - `https://static.publico.pt/s3/rankings{YEAR}/data/listas/rankings9ano.js` (3º ciclo)
  - sidecar: `https://static.publico.pt/s3/rankings{YEAR}/data/pt_pt.js` (concelho/DICOFRE)
- Historical backfill: **AVAILABLE 2018–2024** — verified 2026-06-06 via `3ciclo-all-years.har`. Per-year URL resolver table above. 2025 not yet published (probe quarterly). 9ano files do NOT exist for 2020 & 2021 (COVID — Provas Finais cancelled).
- Headers: `Referer: https://www.publico.pt/`, `Origin: https://www.publico.pt`
- Refresh: yearly April (probe Feb–May)
- Licence: © Público — internal use only, no republish

### 8.3 `dges_acesso`
- Source name: `dges_acesso`
- Authority: DGES
- Format: XLSX
- Endpoint pattern: `https://wwwcdn.dges.gov.pt/sites/default/files/fase{1,2,3}[_a]?_{YY}.xlsx`
- Sheet: `Mínimas`, header row 5
- Refresh: yearly August (1ª fase), September (2ª), October (3ª)
- Licence: DGES open data

### 8.4 `infoescolas`
- Source name: `infoescolas`
- Authority: DGEEC/MECI
- Format: XLSX
- Endpoints:
  - `https://infoescolas.medu.pt/docs/2024/InfoEscolas2024_3Ciclo_DadosPorEscola.xlsx`
  - sibling: `…_2Ciclo_DadosPorEscola.xlsx`, `…_1Ciclo_…`, `…_Secundario_…`
- Refresh: yearly January (latest edition published mid-month)
- Licence: CC BY 4.0 (consistent with the dados.gov.pt sibling)

---

## 9. Open questions for the next session

1. ✅ **RESOLVED** — Público 3º ciclo file is `rankings9ano.js` (not `rankings3c.js`). 1,161 schools, 79.3% have `coduo` agrupamento código.
2. ✅ **RESOLVED 2026-06-09** — Público `id` is its own short code, unrelated to any DGEEC key (LEFT(codigo_escola,4)=LPAD(id_publico,4) probe yields 0/661 sec matches). Final bridge algorithm is a 2-stage ensemble: Stage 1 `direct_uo_fuzzy` for 9ano with `codigo_uo_dgeec` (921 schools at avg sim 0.992); Stage 2 ensemble of 4 algorithms (trigram + Levenshtein + Jaccard + phonetic dmetaphone) voting on the best codigo_escola within a "same normalized concelho OR within 2km" candidate window — `ensemble_high` when ≥3 agree, `ensemble_medium` when 2 agree. Bridge at `gold_analytics.xref_publico_dgeec`; 1,874/1,974 (94.9%) matched (1,839 high + 35 medium). See [[log#2026-06-09 gold | Phase 2 PR-D]].
3. ✅ **PARTIALLY RESOLVED** — CAOP is **continente-only** (confirmed by user). For Açores/Madeira schools (Público 9ano: 56 rows; secundário: 35 rows; ArcGIS: many more), we need:
   - **Option A (recommended)**: ingest CAOP-Açores (DRRT/SREA) + CAOP-Madeira (DRIGOT) as **separate sibling sources**, union into a single `freguesias_pt` view.
   - **Option B**: leave `dicofre` NULL for non-continente schools, keep only `distrito` + `concelho`. Acceptable for v1 if Açores/Madeira listings are a small share.
   - Defer to dedicated open question — see Q6.
4. ✅ **RESOLVED** — historical Público **in scope** per user. Add `YEAR ∈ {2020..2024}` backfill to bronze DAG.
5. ✅ **RESOLVED 2026-06-09** — single-table design with `school_type` discriminator + `codigo_dgeec` text PK accepting both code spaces. Empirically verified the 6-digit basic/sec codes and 4-digit higher-ed UO codes are disjoint by length (0 collisions across 8,117 rows). Lives at `gold_analytics.dim_school`. See [[log#2026-06-09 gold | Phase 2 PR-E]].
6. **CAOP-Açores + CAOP-Madeira sourcing** — find the canonical DRRT/SREA + DRIGOT freguesia datasets (or fall back to OSM admin boundaries). Roughly: 156 freguesias on Açores, 54 on Madeira. Confirm with user before bootstrapping a 4th `add-gis-source`.

---

## 10. Verified artefacts

In `/tmp/pt-edu-probe/`:
- `dgeec.zip` (40 KB) — higher-ed shapefile, 321 records, schema confirmed.
- `dgeec_shp/Estab_Ens_Sup_Portugal.*` — extracted.

In `tests/`:
- `www.gesedu.pt.har` (20 MB) — proves ArcGIS FeatureServer backend.
- `www.publico.pt.har` (1 MB) — proves no paywall, exposes `rankingssec.js` S3 URL.
- `3ciclo.har` (1.8 MB) — exposes `rankings9ano.js` S3 URL + confirms `coduo` agrupamento código is populated for 79% of 9ano rows.
- `3ciclo-all-years.har` — confirms historical Público backfill 2018–2024, exposes 3 host/path conventions and per-year filename variants. Verified live 2026-06-06 (all 12 expected URLs return 200 with non-soft-404 sizes).

HAR analysis reports retained in agent transcripts (4 parallel agents, ~150KB context each):
- A1 GesEdu/ArcGIS forensics
- A2 Público S3 forensics
- A3 DGES research
- A4 Infoescolas live research
