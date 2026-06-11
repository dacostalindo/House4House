---
title: News + Regulatory-Intelligence Pipeline for PT Real Estate — PoC Design
type: plan
last_verified: 2026-06-11
tags: [plan, poc, news, llm, regulatory-intelligence, uc-3, dre, haiku, sonnet]
status: design-approved
---

# News + Regulatory-Intelligence Pipeline for PT Real Estate — PoC Design

## For future Claude

This page is the **authoritative** design for the news + regulatory-event pipeline: scope, sources, architecture, data model (with full SQL), configs, failure handling, eval gates, costs. It ingests 5 PT real-estate-relevant sources, extracts structured policy/market events into `silver_news.events`, joins them to the existing `dicofre` key space, and materializes a `(dicofre, iso_week, lane, event_type)` panel that feeds [[uc-3-economics|UC-3]]. It supersedes the v3 analyst-digest framing — UC-3 is the single consumer now. A small dev-loop email digest survives as a 4–6 week observability tool with an explicit retirement plan. Preflight evidence is inlined below; there is no separate `.context/news-sources-preflight.md` file. The prior `.claude/plans/news-pipeline.md` is retired to a pointer — this page is the source of truth.

Read this when:
- Sizing or starting any PR on `pipelines/news/` or `dbt/models/news/`.
- Wiring `silver_news.events` / `gold_news.signal_panel` into [[uc-3-economics|UC-3]] econometric modelling.
- Considering adding a new source, a delivery surface, real-time alerts, or brand→NIPC resolution — they were deliberately scoped out (see §NOT in scope).
- Comparing to discovery-style ingest patterns in [[medallion-layering]].

## Goal

Land a structured regulatory + market event panel keyed to `(dicofre, iso_week, lane, event_type)` that [[uc-3-economics|UC-3]] consumes as treatment indicators (event-study / diff-in-diff) and covariate features. News rows live in the same `dicofre` key space as listings, CAOP, BGRI, schools, permits, and developments so downstream joins (news × inventory, news × hedonic features) are a single SQL away.

Two artefacts produced:

1. **`silver_news.events`** — canonical policy/market events with `effective_date`, `event_type` (closed taxonomy), `scope_level`, `scope_codes[]`, provenance, and back-references to source articles. DRE-canonical when ELI present; news-only event clusters allowed but downweighted.
2. **`gold_news.signal_panel`** — rolled-up `(dicofre, iso_week, lane, event_type) → count + salience + dominant_entities` materialization. UC-3's direct input.

Plus one secondary artefact, time-limited:

3. **Daily dev-loop digest email** — a thin Sonnet renderer over today's new events, sent to the developer (you), used to spot extraction errors during the first 4–6 weeks of operation. Explicit retirement plan: promoted to disabled-by-default once `event_recall` ≥0.80 holds for 3 consecutive weeks; replaced by a one-line Airflow ops summary.

No real-time alerts. No public surface. No analyst inbox surface (was v3, demoted). No weekly Sonnet narrative (was v3, dropped — UC-3 doesn't consume prose).

## What changed from v3 (UC-3 reframe)

Six shifts, driven by the UC-3-only priority lock and an interview pass on the v3 plan:

1. **Reframed primary goal: UC-3 signal feature-store, not analyst digest.** Event-shape output (`silver_news.events`) + panel rollup are the deliverables; email demoted to dev-loop observability with retirement plan.
2. **Per-article Haiku extraction replaces one-Sonnet-daily synthesis.** Events are a per-article unit. Backfill, idempotency, prompt-versioning, and reprocessing all require per-article granularity. Sonnet retained as a small surgical nightly *dedup* pass over ELI-less candidates only.
3. **Closed event taxonomy, deferred to post-ingest discovery.** Locked in PR3 after a Sonnet cluster-discovery pass over the PR1–2 corpus. Open-vocabulary `event_type` is useless for econometric treatment indicators.
4. **DRE backfill to 2017-present + fiscal-codes-only spike to 2010.** Per-task budget guard, idempotent on ELI. UC-3 cannot fit treatment effects on forward-only data.
5. **DRE filter by tema, not by keyword.** Live HAR enumeration of `DataActionGetTemas` confirmed the canonical taxonomy. Tema set `{8, 35, 48, 33, 46, 52}` primary, `{4, 39}` PR5 precision spikes. Zero recall risk from keyword drift across the 2017–2026 horizon.
6. **No dlt.** News articles are homogeneous fixed-schema; raw bytes already land in MinIO. dlt's value (schema-contract, schema evolution, heterogeneous-source handling) doesn't apply. Direct `psycopg` INSERT into `bronze_news.articles_raw` with `dag_run_id` provenance.

Brand→NIPC / SPV-cluster resolution is **out of scope entirely** (no longer "deferred to KG-PoC" — KG-PoC isn't shipping). UC-3 keys entity features on brand-string canonicalization via [[entity-aliases]] shared dim.

## Sources (5, prioritized)

| Source | Priority | Adapter | Cadence | Signal density | Notes |
|---|---|---|---|---|---|
| **DRE** | P0 | OutSystems screenservices POST + `x-csrftoken` | daily, tema-filtered | regulatory canonical | full structured JSON + body text via `DataActionGetConteudoData` / `GetPesquisaByTema`. Weekly CSRF bootstrap via 1 headless GET. Tema-filter is the entrance gate. |
| **Vida Imobiliária** | P0 | sitemap-crawl | ~5/day | high (specialist trade press) | full text in server-rendered HTML, no friction, no JS. |
| **Público** (imobiliário + habitação) | P0 | JSON API `api/list/*` (paginate `?page=N`) | ~1–3/day | high (broadsheet journalism) | **headline + ~200-char excerpt + tags + date ONLY** — ~50% bodies paywalled, do not scrape bodies. Neutral UA (robots blocks `anthropic-ai`/`GPTBot`). |
| **Jornal de Negócios** (imobiliário) | P0 | TBD — **preflight blocker before PR2** | TBD | high (business journalism — deal-flow, REITs, M&A) | Cofina group, anti-bot posture unknown, paywall depth unknown. ~1–2h spike scheduled before PR2. |
| **Idealista/news** | P1 | sitemap-news.xml | ~15–25/day | low (SEO/marketing content, listicles) | demoted from v3's P0 anchor. High volume but low signal density per article. Deferred to PR6+. |

Lane is **per-article**, a Haiku output field (secondary attribute, not a primary product axis): `regulatory`, `industry`, `unknown`. DRE short-circuits to `regulatory`.

## Source-access evidence (inline preflight)

Replaces the v3 external `.context/news-sources-preflight.md` reference. Load-bearing claims, verified via HAR capture (`Desktop/diariodarepublica.pt.har`) + direct curl probes during the 2026-06-11 redesign interview. Re-verify before PR5 (DRE) and PR2 (Negócios).

### DRE (verified)

- **Access path:** OutSystems screenservices POST. Endpoints found via HAR:
  - `https://diariodarepublica.pt/dr/screenservices/dr/MenusParaPesquisa/LegislacaoPorTema/DataActionGetTemas` — enumerate tema list.
  - `https://diariodarepublica.pt/dr/screenservices/dr/Pesquisas/PesquisaResultado/DataActionGetPesquisaByTema` — list instruments under a tema.
  - `https://diariodarepublica.pt/dr/screenservices/dr/Pesquisas/PesquisaResultado/DataActionGetCountAreaTematica` — counts per tema.
  - `DataActionGetConteudoData` / `DataActionGetConteudoByElastic` — full diploma body + Elasticsearch-style keyword search (fallback path).
- **Auth:** `x-csrftoken` header; lifetime appears to be days. Weekly cron'd headless GET of `/dr/home` extracts a fresh token.
- **Tema enumeration (full live list — 60+ temas, RE-relevant subset bolded):**
  - **8 Arrendamento** (P0), **33 Turismo** (P0 — AL lives here, not "Habitação"), **35 Urbanismo** (P0), **46 Estrangeiros** (P1 — golden visa / ARI), **48 Fiscal** (P0 — IMI/IMT/AIMI/CIRS-housing), **52 Civil** (P1 — civil-code property provisions).
  - Spikes (precision-test in PR5): **4 Ambiente**, **39 Contratação Pública**.
  - **No `Habitação` tema** exists; housing is fragmented across {Arrendamento, Urbanismo, Fiscal, Turismo} — Mais Habitação will be multi-tagged. **No `Construção` tema**; construction-permit policy lives under Urbanismo.
  - Tema IDs are stable integers — safe to hard-code in `dim_dre_temas` seed.
- **Multi-tema instruments:** `GetPesquisaByTema` returns per-tema; backfill DAG iterates the tema set and dedups on ELI while recording `tagged_temas int[]` on `silver_dre.instruments`.

### Vida Imobiliária (verified)

- **Access path:** `sitemap.xml` with `<lastmod>` incremental polling. Server-rendered HTML, no JS dependency, no anti-bot friction. Trafilatura extraction (F1 0.958).

### Público (verified)

- **Access path:** JSON API at `api/list/habitacao` + `api/list/imobiliario`, paginated `?page=N`.
- **Constraint:** headline + ~200-char excerpt + tags + date ONLY. ~50% bodies paywalled.
- **UA:** robots.txt blocks `anthropic-ai` / `GPTBot`. Use a neutral browser UA.

### Idealista/news (verified, demoted)

- **Access path:** `sitemap-news.xml` + category/etiquetas pages. `/news/` subdomain is not bot-blocked even though the root domain is. Server-rendered, no paywall.

### Jornal de Negócios (NOT verified — PR2 blocker)

- Status: unknown. Cofina group typically aggressive on anti-bot.
- Spike scope (~1–2h before PR2): robots.txt, sitemap availability, paywall depth, anti-bot posture (cf-challenge? Datadome?), best-effort RSS/sitemap-news.xml/JSON-API discovery.
- Fallback plan if preflight reveals headless-only / ZenRows-required access: drop Negócios from v1, ship PR2 as Público-only, defer Negócios to PR6+.

### PTdata API (verified)

- **Status:** live, free, keyless.
- `GET https://api.ptdata.org/v1/geo/search?q=<name>` → dicofre 6-digit codes (3,049 freguesias). Joins directly to `silver_caop_freguesias`.
- `GET https://api.ptdata.org/v1/companies/{nif}` → SICAE+VIES+BASE fused (canonical name, CAE, address).
- `GET https://api.ptdata.org/v1/legislation/search?q=<text>` → canonical article text across 12 fiscal codes (CIVA / CIMI / CIRS / IMT / CIS / EBF / RGIT etc.).
- PTdata MCP server (36 tools, `api.ptdata.org/mcp`) noted but not in v1 critical path.

## Event taxonomy

**Closed set, locked in PR3 after cluster-discovery pass.** Open-vocabulary breaks UC-3 econometrics. Provisional draft (subject to PR3 lock):

- `al_regulation` (Alojamento Local — containment zones, license freezes, relaxations)
- `rent_control` (NRAU updates, lei das rendas)
- `tax_change` (IMI / IMT / AIMI / CIRS art.78-E shifts)
- `housing_program` (Mais Habitação, Porta 65, Renda Acessível, IHRU programs, 1.º Direito)
- `zoning_change` (PDM revisions, AUGI)
- `permit_policy` (RJUE / licenciamento changes)
- `golden_visa` (ARI scope / eligibility)
- `deal_flow` (transactions, fund moves, M&A — brand-keyed, low econometric weight)

Final taxonomy + extraction prompt `v1.0` committed in PR3 alongside the event-recall eval set.

Scope shape: `scope_level text` ∈ {`national`, `nuts2`, `municipio`, `freguesia`} + `scope_codes text[]` (joins to `silver_caop_freguesias` when level=`freguesia`).

## Event identity + provenance

- **ELI-keyed canonical events.** Every DRE legal instrument has a stable ELI URI. Events from DRE rows take ELI as canonical event identity. News articles citing the same ELI attach as `silver_news.event_coverage(article_id, eli, ...)`. Salience = `count(coverage)`.
- **News-only event clusters.** Articles that extract events but cite no ELI flow through a nightly Sonnet dedup pass (small candidate set, ~5–15/night) → either merge into existing ELI events (by event_type + scope + date proximity) or form `provenance='news_only'` clusters. Downweighted in UC-3.
- **ELI extraction from news bodies:** deterministic regex on title + body for qualified citations (`Decreto-Lei N/YYYY`, `data.dre.pt/eli/...` hrefs) + Haiku `legal_instrument_refs[]` field on every extraction call + popular-name dictionary (Mais Habitação, lei das rendas, etc.) bootstrapped by one-shot Sonnet pass over DRE backfill, human-reviewed once during PR5.

## Entity resolution

- **Place → dicofre (freguesia)** — `GET https://api.ptdata.org/v1/geo/search?q=<name>` returns 6-digit dicofre codes joining directly to `silver_caop_freguesias`. Self-hosted Nominatim retained as fallback.
- **Brand-string canonicalization** — `silver_news.article_entities.entity_text_canonical` = lowercased, suffix-stripped (`, S.A.`, `, Lda.`, `SGPS`, `SIC`, etc.), whitespace-collapsed, accent-folded. Alias map at [[entity-aliases]] (`silver_dim.entity_aliases`, shared across pipelines — see "Cross-pipeline composability" below).
- **NIF → company enrichment** — `GET https://api.ptdata.org/v1/companies/{nif}` only when article cites a NIF directly (`resolved_nif` column on `article_entities`). No brand→NIPC resolution — UC-3 doesn't need SPV-level joins for econometric identification.
- **Legislation citation enrichment** — `GET https://api.ptdata.org/v1/legislation/search?q=<text>` resolves "artigo 78-E do CIRS" mentions. Free, keyless. Added in PR5.

## Cross-pipeline composability — `silver_dim.entity_aliases`

The alias map is promoted out of news-PoC ownership into a shared dimension at `silver_dim.entity_aliases`. Both news ingest and any future dev-enrichment LLM (developer-name → web-searched architects/promoters) write to it append-only with conflict-do-nothing on `alias_text`. Both read from it. New variants surfaced by either side propagate. **Limit:** joins work at brand level only, not SPV/NIF level.

## Architecture

| Layer | Choice | Notes |
|---|---|---|
| Crawl proxy | None needed for v1 sources beyond the weekly DRE CSRF headless GET. | Negócios may shift this if preflight finds anti-bot — assess at PR2 spike. |
| Raw landing | MinIO `news-raw/<source>/<YYYY-MM-DD>/<sha256>.{html,json,pdf}` | per [[2026-05-10-minio-not-s3]]. |
| HTML extract | Trafilatura | Vida, Negócios (pending preflight), Idealista (PR6+). |
| JSON parse | inline | Público, DRE. |
| Bronze append | direct `psycopg` INSERT | No dlt — fixed schema + MinIO blob means dlt's contract/evolution machinery is dead weight. See [[2026-06-11-news-pipeline-no-dlt]]. |
| Geo resolution | PTdata `geo/search` primary, Nominatim fallback | replaces v2's Nominatim-only design. |
| NIF enrichment | PTdata `companies/{nif}` | only when article cites a NIF directly. |
| Per-article extraction | Claude Haiku 4.5 single call per article | Output: `events[]`, `entities[]`, `legal_instrument_refs[]`, `freguesia_refs[]`, `lane`. Versioned prompt. MinIO blob cache at `news-llm/extractions/<article_id>/<prompt_version>.json` for cheap re-derivation. |
| Nightly dedup | Claude Sonnet 4.6 single call per night over ELI-less candidates | ~€0.30/mo. |
| Panel materialization | plain dbt SQL over `silver_news.events` × `article_freguesia_xref` → `gold_news.signal_panel` | refreshed daily. |
| Dev-loop digest | thin Sonnet renderer over today's new events → SMTP | retires after 4–6 weeks; explicit `digest_enabled: bool` config flag. |
| Orchestration | existing Airflow 2.10 + dbt-postgres + Cosmos | 6 DAGs (see below). |
| Audit | existing `metadata.pipeline_runs` + `metadata.news_llm_spend` ledger | pre-task budget projection. |
| Data quality | Great Expectations + dbt tests | schema is fixed (not [[bronze-permissive]] — that concept covers schema-evolving sources; news is fixed-shape). |

## Data model (full SQL)

### Bronze — one schema, source-keyed

```sql
CREATE SCHEMA IF NOT EXISTS bronze_news;

CREATE TABLE bronze_news.articles_raw (
  id              bigserial PRIMARY KEY,
  source_id       text NOT NULL,                    -- 'dre' | 'vida' | 'publico' | 'negocios' | 'idealista'
  url             text NOT NULL,
  url_canonical   text NOT NULL,
  http_status     int,
  fetched_at      timestamptz NOT NULL,
  content_type    text,
  content_sha256  text NOT NULL,
  minio_path      text NOT NULL,                    -- raw bytes in MinIO, not in Postgres
  source_metadata jsonb,                            -- adapter-specific: sitemap lastmod | rubrica+tags | conteudo_id+ELI+tagged_temas
  dag_run_id      text NOT NULL,                    -- Airflow's native run id; replaces dlt_load_id
  ingested_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, content_sha256)
);

CREATE INDEX ON bronze_news.articles_raw (source_id, fetched_at DESC);

CREATE TABLE bronze_news.feed_heartbeat (              -- UPSERT per source, per [[heartbeat-sidecar]]
  source_id              text PRIMARY KEY,
  last_seen_at           timestamptz,
  last_ok_at             timestamptz,
  consecutive_failures   int NOT NULL DEFAULT 0
);
```

### Staging — `dbt/models/news/staging/`

One model per source: `stg_vida_articles.sql`, `stg_publico_articles.sql`, `stg_negocios_articles.sql`, `stg_dre_articles.sql` (+ `stg_idealista_articles.sql` at PR6+). Per-source URL canonicalization + metadata extraction; standardised output columns. Tests: `not_null` on `article_id`, `url_canonical`, `published_at`; `unique` on `article_id`.

### Silver — cross-source consumption (`silver_news`)

```sql
CREATE SCHEMA IF NOT EXISTS silver_news;

CREATE TABLE silver_news.articles (
  article_id       text PRIMARY KEY,            -- sha256(url_canonical)
  source_id        text NOT NULL,
  url_canonical    text NOT NULL,
  published_at     timestamptz,
  title            text,
  body_text        text,                        -- NULL for Público (excerpt-only) and other paywalled rows
  excerpt          text,                        -- always present
  body_available   boolean NOT NULL,            -- explicit paywall/excerpt-only signal
  lang             text,
  minio_path       text NOT NULL,
  ingested_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON silver_news.articles (published_at DESC);
CREATE INDEX ON silver_news.articles (source_id, published_at DESC);

CREATE TABLE silver_news.events (
  event_id              text PRIMARY KEY,       -- ELI when DRE-canonical; uuid for news-only
  event_type            text NOT NULL,          -- closed taxonomy locked in PR3
  effective_date        date,
  scope_level           text NOT NULL,          -- 'national' | 'nuts2' | 'municipio' | 'freguesia'
  scope_codes           text[] NOT NULL,        -- 6-digit dicofre when scope_level='freguesia'; municipio code; etc.
  provenance            text NOT NULL,          -- 'dre_canonical' | 'dre_news_coverage' | 'news_only'
  eli                   text,                   -- non-null when provenance like 'dre_*'
  extracted_with        jsonb,                  -- {prompt_version, model, extracted_at}
  created_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON silver_news.events (effective_date DESC);
CREATE INDEX ON silver_news.events USING gin (scope_codes);
CREATE INDEX ON silver_news.events (event_type, effective_date DESC);
CREATE INDEX ON silver_news.events (eli) WHERE eli IS NOT NULL;

CREATE TABLE silver_news.event_coverage (
  article_id     text NOT NULL REFERENCES silver_news.articles(article_id),
  event_id       text NOT NULL,                 -- canonical event_id (post-dedup)
  detected_via   text NOT NULL,                 -- 'regex_eli' | 'haiku_eli' | 'sonnet_dedup' | 'popular_name'
  PRIMARY KEY (article_id, event_id)
);
CREATE INDEX ON silver_news.event_coverage (event_id);

CREATE TABLE silver_news.event_dedup_map (        -- Sonnet nightly output
  candidate_event_id    text NOT NULL,
  canonical_event_id    text NOT NULL,
  decided_at            timestamptz NOT NULL,
  prompt_version        text NOT NULL,
  PRIMARY KEY (candidate_event_id)
);

CREATE VIEW silver_news.events_canonical AS
  SELECT e.* FROM silver_news.events e
  WHERE e.event_id NOT IN (SELECT candidate_event_id FROM silver_news.event_dedup_map);
-- Plus the merged candidates' coverage redirects to canonical_event_id.

CREATE TABLE silver_news.article_entities (
  article_id              text NOT NULL REFERENCES silver_news.articles(article_id),
  entity_type             text NOT NULL,          -- 'ORG' | 'PER' | 'LOC' | 'LAW'
  entity_text             text NOT NULL,          -- raw NER'd span
  entity_text_canonical   text NOT NULL,          -- via silver_dim.entity_aliases lookup + suffix-strip + accent-fold + lowercase
  span_start              int,
  span_end                int,
  resolved_dicofre        text,                   -- LOC: via PTdata geo/search; NULL if unresolved
  resolved_nif            text,                   -- only when article explicitly cites a 9-digit NIF
  extracted_with          jsonb,
  PRIMARY KEY (article_id, entity_type, span_start, span_end)
);
CREATE INDEX ON silver_news.article_entities (entity_text_canonical);

CREATE TABLE silver_news.article_freguesia_xref (
  article_id     text NOT NULL REFERENCES silver_news.articles(article_id),
  dicofre        text NOT NULL,                  -- 6-digit, joins to silver_caop_freguesias
  confidence     numeric,
  source         text NOT NULL,                  -- 'ptdata' | 'nominatim'
  PRIMARY KEY (article_id, dicofre)
);
CREATE INDEX ON silver_news.article_freguesia_xref (dicofre);
```

### Silver — DRE canonical (`silver_dre`)

```sql
CREATE SCHEMA IF NOT EXISTS silver_dre;

CREATE TABLE silver_dre.instruments (             -- a.k.a. dim_legal_instruments
  eli              text PRIMARY KEY,             -- e.g. https://data.dre.pt/eli/dec-lei/33/2026/...
  instrument_type  text NOT NULL,                 -- 'Decreto-Lei' | 'Lei' | 'Portaria' | 'Decreto Regulamentar' | 'Resolução do CM'
  numero           text,                          -- e.g. '33/2026'
  effective_date   date,
  title            text,
  popular_names    text[],                        -- ['Mais Habitação', 'lei do AL'] — bootstrapped by Sonnet pass + human review
  tagged_temas     int[] NOT NULL,                -- DRE tema IDs that surfaced this instrument
  source_minio_path text NOT NULL,
  ingested_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON silver_dre.instruments (effective_date DESC);
CREATE INDEX ON silver_dre.instruments USING gin (tagged_temas);
CREATE INDEX ON silver_dre.instruments USING gin (popular_names);

CREATE TABLE silver_dre.filter_versions (         -- tema-set + instrument-type set per backfill batch, semver-tagged
  version          text PRIMARY KEY,             -- 'v1.0.0'
  tema_ids         int[] NOT NULL,
  instrument_types text[] NOT NULL,
  description      text,
  applied_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE silver_dre.dim_temas (               -- seed data — 60+ rows from DataActionGetTemas
  tema_id    int PRIMARY KEY,
  tag        text NOT NULL,
  is_re_relevant boolean NOT NULL DEFAULT false,  -- true for {8, 35, 48, 33, 46, 52} + {4, 39} after PR5 spike
  active     boolean NOT NULL DEFAULT true
);
```

### Silver — shared dim (`silver_dim`)

```sql
CREATE SCHEMA IF NOT EXISTS silver_dim;

CREATE TABLE silver_dim.entity_aliases (          -- shared cross-pipeline
  alias_text       text PRIMARY KEY,              -- canonicalized form of any variant
  canonical_brand  text NOT NULL,                 -- 'vizta'
  source_pipeline  text NOT NULL,                 -- 'news' | 'dev_enrichment' | 'manual'
  added_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON silver_dim.entity_aliases (canonical_brand);
```

### Gold — `gold_news.*`

```sql
CREATE SCHEMA IF NOT EXISTS gold_news;

CREATE TABLE gold_news.signal_panel (             -- UC-3's direct input
  dicofre       text NOT NULL,
  iso_week      text NOT NULL,                    -- 'YYYY-Www'
  lane          text NOT NULL,                    -- 'regulatory' | 'industry' | 'unknown'
  event_type    text NOT NULL,
  event_count   int NOT NULL,
  salience      numeric NOT NULL,                 -- sum of coverage across the event_count events that week
  dominant_entities text[],                       -- top-N canonical_brand by mention frequency
  refreshed_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (dicofre, iso_week, lane, event_type)
);
CREATE INDEX ON gold_news.signal_panel (iso_week DESC);
CREATE INDEX ON gold_news.signal_panel (dicofre, iso_week DESC);

CREATE TABLE gold_news.digest_daily (             -- dev-loop only, retiring post-validation
  digest_date       date PRIMARY KEY,
  payload           jsonb,                        -- thin Sonnet renderer output: today's events with summaries
  rendered_html     text,
  llm_status        text NOT NULL,                -- 'ok' | 'sonnet_failed' | 'disabled' | 'quiet_day'
  llm_spend_usd     numeric,
  digest_enabled    boolean NOT NULL              -- false after retirement
);
```

### Metadata

```sql
CREATE TABLE metadata.news_llm_spend (
  ts                 timestamptz NOT NULL,
  dag_run_id         text NOT NULL,
  model              text NOT NULL,
  prompt_tokens      int NOT NULL,
  completion_tokens  int NOT NULL,
  cost_usd           numeric NOT NULL,
  stage              text NOT NULL                -- 'extraction' | 'dedup' | 'digest_render' | 'taxonomy_discovery' | 'popular_name_bootstrap'
);
CREATE INDEX ON metadata.news_llm_spend (ts DESC);
CREATE INDEX ON metadata.news_llm_spend (stage, ts DESC);

CREATE TABLE metadata.news_prompts (
  prompt_version     text PRIMARY KEY,            -- 'v1.0.0'
  prompt_sha256      text NOT NULL,
  stage              text NOT NULL,               -- 'extraction' | 'dedup' | 'digest_render'
  prompt_text        text NOT NULL,
  deployed_at        timestamptz NOT NULL,
  retired_at         timestamptz
);
```

Indexes called out above; pg_stat_statements + dbt's `incremental` strategy applied where appropriate.

## Configs / file layout

Per [[pydantic-not-in-dlt]] (Pydantic configs consumed by plain adapter classes — no dlt to keep them out of, but the discipline of typed config carries).

```
pipelines/news/
  config/
    base.py                       BaseNewsSource(BaseModel)
    sources/
      dre.py                      DRESource: outsystems endpoints, csrf bootstrap, tema_ids list, instrument_types list, date_window
      vida.py                     VidaSource: sitemap URL, category map
      publico.py                  PublicoSource: api endpoints, list paths, neutral UA override
      negocios.py                 NegociosSource: TBD post-preflight
      idealista.py                IdealistaSource: PR6+
    event_taxonomy.py             closed event_type enum + scope_level enum + per-type description for the extraction prompt
  prompts/
    extraction_v1_0.txt           per-article Haiku extraction prompt — committed as a file, tracked in metadata.news_prompts
    dedup_v1_0.txt                Sonnet nightly dedup prompt
    digest_render_v1_0.txt        dev-loop digest renderer prompt
    taxonomy_discovery_v0_1.txt   one-shot Sonnet cluster-discovery prompt (PR3, ahead of extraction lock)
    popular_name_bootstrap_v0_1.txt one-shot Sonnet pass over DRE backfill (PR5)
  adapters/
    sitemap_crawl.py              shared: Vida (+ Negócios if applicable + Idealista at PR6+)
    json_api.py                   shared: Público
    outsystems_post.py            DRE-specific
  bronze/
    insert.py                     direct psycopg INSERT into bronze_news.articles_raw (replaces dlt resources)
    heartbeat.py                  UPSERT into bronze_news.feed_heartbeat
  extract/
    trafilatura_html.py           Vida, Negócios pending, Idealista PR6+
    haiku.py                      per-article extraction call; cache reads/writes via news-llm/extractions/ MinIO path
    eli_regex.py                  deterministic ELI extraction pre-pass
  dedup/
    sonnet.py                     nightly dedup call
  geo.py                          PTdata geo/search + Nominatim fallback
  alias.py                        silver_dim.entity_aliases lookup + write-on-miss
  digest.py                       dev-loop renderer (Sonnet thin pass + SMTP)
  panel.py                        signal_panel materialization invoker (mostly dbt SQL; this wraps refresh + spend ledger updates)
  dags/
    news_ingest_daily.py          per-source ingest tasks
    news_extract_daily.py         per-article Haiku extraction
    news_dedup_daily.py           Sonnet nightly dedup
    news_panel_refresh_daily.py   SQL materialization + optional digest + SMTP
    news_dre_backfill.py          parameterized one-shot
    news_reprocess.py             parameterized one-shot (prompt_version, article filter)
```

## DAGs (6 total)

1. `news_ingest_daily` (~06:00 UTC) — per-source ingest, MinIO land, bronze append, heartbeat.
2. `news_extract_daily` (~06:30 UTC) — per-article Haiku extraction → silver events/entities/xref.
3. `news_dedup_daily` (~06:45 UTC) — Sonnet nightly dedup over today + last 14d ELI-less candidates.
4. `news_panel_refresh_daily` (~07:00 UTC) — SQL materialization of `signal_panel` + optional dev-loop digest render + SMTP.
5. `news_dre_backfill` (manual, parameterized) — one-shot per filter version.
6. `news_reprocess` (manual, parameterized) — prompt-version reprocess.

Sequenced via Airflow Datasets, not explicit upstream task deps across DAGs (more failure-resilient). Convention: PR title prefix `news-prompt:` for any prompt change. No auto-fire reprocess on prompt-version bump — explicit human gate.

## Backfill

- **DRE 2017-present primary**, tema-filtered, idempotent on ELI. Per-task budget projection. Backfilled rows carry `provenance='dre_canonical'` (no news coverage join populated).
- **Fiscal-codes-only spike to 2010**, restricted to `tema=Fiscal` AND instrument-type ∈ {Lei, Decreto-Lei} that amend CIRS/CIMI/IMT/IVA. Extends pre-period for tax-event treatments without broader pre-2017 noise.
- **News content backfill:** explicitly out — Wayback/sitemap depth too lossy. Feasibility spike permitted but not committed.

## Reprocessing

Per-article extraction is cache-keyed on `(article_id, prompt_version, model)` with MinIO blob storage at `news-llm/extractions/<article_id>/<prompt_version>.json`. Three reprocess triggers expected in v1:
1. Taxonomy lock at PR3 — re-extract all PR1–PR2 articles at `v1.0`.
2. Popular-name dictionary updates — re-run ELI extraction over articles flagged `provenance='news_only'`.
3. Prompt iteration during the 4–6 week dev-loop validation window — re-extract affected article subset.

`news_reprocess` DAG triggered manually, parameterized, with budget projection. Cache hits skip Haiku re-call.

## Failure handling

| Failure | Behavior |
|---|---|
| DRE CSRF token expired | Weekly headless re-bootstrap. If mid-week refresh fails, log + skip DRE only; other sources continue; heartbeat consecutive_failures increments. |
| Source 404 / malformed (sitemap or API) | Log, skip, increment `feed_heartbeat.consecutive_failures`; alert if ≥3 consecutive. |
| Trafilatura empty extract | Article retained with `body_text=NULL`, `body_available=false`, flagged. |
| PTdata down or rate-limited | Fall back to Nominatim for geo; skip `companies/{nif}` enrichment (non-blocking, retry next run). |
| Haiku per-article extraction fails on a single article | Retry 1× with smaller context; on second fail, retain article with no events/entities row, flagged `extraction_failed=true`; downstream extraction DAG completes. |
| Haiku rate-limit / outage | Extraction DAG fails soft, alert. Articles ingested in bronze remain; extraction retries next run. |
| Sonnet nightly dedup fails | Panel ships with `dedup_pending` flag on affected event rows; alert; no blocking retry. Stale dedup decisions carry forward — UC-3 query layer should respect the flag. |
| Sonnet dev-loop digest fails | Skip the send. One-line Airflow ops summary fires regardless. Never block the panel refresh. |
| Empty day (nothing crawled) | Panel refresh still runs; digest emits "Quiet day" if enabled. |
| Budget guard hit | DAG fails soft, alert, no silent overspend. Per-task projection checks month-to-date before each LLM call. |
| Backfill DAG mid-run failure | Idempotent on ELI — re-trigger from last successful date offset. Per-tema iteration tracked in DAG state. |
| Reprocess DAG triggered with unknown prompt_version | Validation fails at DAG start with explicit error referencing `metadata.news_prompts`. |

## Eval gates

| Eval | Size | Built in | Gate |
|---|---|---|---|
| `dre_relevance` (tema-set completeness) | 40 hand-curated known-RE-relevant ELIs | PR5 pre-backfill | ≥95% recall |
| `event_recall` (per-article event extraction) | 30 hand-annotated articles across 4 sources | PR3 (post-taxonomy-lock) | ≥0.80 recall, ≥0.85 precision |
| `event_typing` (taxonomy correctness) | reuses `event_recall` set | PR3 | ≥0.85 type-match conditional on recall |
| `place_freguesia` (geo accuracy) | 20 place→dicofre pairs | PR3 | ≥0.80 |
| `dedup_correctness` (Sonnet nightly dedup) | 15 should-merge / should-NOT-merge pairs | PR4 | precision ≥0.90 on "should merge" |

Each gate hard-blocks the relevant PR. `make news-evals` runs all. Plus implicit human eval during the 4–6 week dev-loop window.

**Explicitly NOT built in v1:** GLiNER F1 gate, HDBSCAN V-measure, dedup-precision-by-embedding-distance, lane-accuracy gate (lane demoted from primary output to incidental Haiku field). These belong to the stack we removed.

## Cost projection

| Stage | €/mo steady | One-time |
|---|---|---|
| Haiku per-article extraction (~30/day) | ~1 | — |
| Sonnet nightly dedup (~5–15 candidates) | ~0.30 | — |
| Sonnet dev-loop digest renderer (~6wk) | ~1.50, then 0 | — |
| PTdata / Nominatim / SMTP | 0 | — |
| DRE backfill 2017-present | — | ~5 |
| Fiscal-codes-only spike 2010-2016 | — | ~2 |
| Reprocess pass (per full re-run) | — | ~5 |
| **Total** | **~3 steady (~5 during validation)** | **~7–12 at PR5, ~5/reprocess** |

Budget guard: €15/mo monthly steady cap, alert at €10. One-time backfill DAGs carry their own per-task projection; reprocess DAG same.

Down from v3's €13 projection because Sonnet-as-corpus-summary (the dominant cost) is gone.

## What already exists (reuse, not rebuild)

MinIO raw landing, self-hosted Nominatim (fallback only now), `silver_caop_freguesias`, `metadata.pipeline_runs`, Great Expectations, dbt + Cosmos, Airflow 2.10 + dataset wiring patterns.

## NOT in scope (v1)

Real-time alerts. Public-facing UI / SEO. News-content backfill. Apify LinkedIn. Reddit / Bluesky / Mastodon / Telegram / Twitter social lanes. Telegram / Obsidian / Streamlit delivery surfaces. Watchlist editor. Brand → NIPC / SPV-cluster resolver (no consumer). Weekly Sonnet narrative synthesis. Analyst-inbox digest as primary surface. Embedding + clustering stack. PDF parsing. Custom NER model. Multi-language UI. dlt resources for news bronze.

## Open items / blockers

- **Negócios preflight** (~1–2h) — robots, paywall depth, sitemap/RSS/API path, anti-bot posture. **Blocker for PR2 scope.** Cofina group is typically aggressive on anti-bot.
- **bizAPIs preflight** — claimed free-tier NIF/NIPC/CPRC/IES API with name search. Out of news-PoC scope; noted only.
- **PTdata MCP server** (36 tools at `api.ptdata.org/mcp`) — agentic enrichment path; not in v1 critical path.

## Resume command for a new session

> Read this page (`wiki/planning/PoCs/news-pipeline/design.md`) and `wiki/planning/PoCs/news-pipeline/sprint-plan.md`. Start PR1: scaffold `pipelines/news/` + wiki bootstrap (`sprint-11.md`, `news-intel.md`, architecture page, 3 decision pages, vida-imobiliaria source page, index + area-routing updates) + Pydantic config base + MinIO raw write + heartbeat sidecar + Vida sitemap-crawl adapter end-to-end into `silver_news.articles`. No dlt — direct `psycopg` INSERT.

## See also

- [[news-pipeline-sprint-plan|Sprint plan]] — per-PR scope, acceptance criteria, sequencing.
- [[heartbeat-sidecar]], [[medallion-layering]] — load-bearing concepts referenced throughout.
- [[2026-05-10-minio-not-s3]] — raw-landing decision.
- [[2026-06-11-news-pipeline-no-dlt]] — bronze-without-dlt decision (created in PR1).
- [[entity-aliases]] — shared dimension for cross-pipeline brand canonicalization (created in PR2).

## Last verified

2026-06-11 — design rewritten from v3 after UC-3 reframe interview pass. Promoted to authoritative — preflight evidence inlined, full SQL data model embedded, file layout + failure handling sections added. The prior `.claude/plans/news-pipeline.md` is retired to a pointer back at this page. Implementation not yet started.
