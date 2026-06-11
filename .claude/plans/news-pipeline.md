# News pipeline for PT real estate — plan (v3, preflight-grounded)

**Status:** implementation-ready, evidence-backed.
**Date:** 2026-06-11.
**Supersedes:** v2 (`Desktop/Apps/House4House/.claude/worktrees/vigorous-sanderson-fd8cfa/.claude/plans/news-pipeline.md`).
**Preflight evidence:** `.context/news-sources-preflight.md` — every source / endpoint below was live-fetched and verified.

## What changed from v2

Four shifts, all driven by preflight evidence:

1. **No RSS factory.** None of the 4 sources have RSS. Three ingest adapters instead: sitemap-crawl (Vida, Idealista), JSON-API (Público), OutSystems-POST (DRE).
2. **No embedding / clustering stack.** Verified volume ≈ 25–35 full-text articles/day. One daily Sonnet call (cluster + rank + tag + summarize) beats TEI/BGE-M3 + GLiNER + HNSW + HDBSCAN on cost, latency, simplicity, and failure surface at this scale.
3. **DRE is direct HTTPS, not headless+PDF.** HAR analysis (`.context/attachments/PrcV4G/diariodarepublica.pt.har`) revealed OutSystems screenservices POSTs that replay with plain `curl` + `x-csrftoken` only — full structured JSON + native Elasticsearch search. No ZenRows, no PDF parsing, no legalize-pt/tretas dependency.
4. **Geo and entity-data via PTdata API.** `api.ptdata.org` is live, free, keyless: `geo/search` → dicofre (3,049 freguesias) replaces Nominatim as primary; `companies/{nif}` enrichment replaces a custom build; `legislation/search` is a free bonus for citing CIVA/CIMI/CIRS articles.

Org-name → NIPC (brand → entity-cluster) is **deferred to the Knowledge-graph-PoC's silver-layer resolver** — not duplicated here.

## Product shape

Internal analyst tool. Two outputs:

- **Daily morning digest** (~07:00 Mon–Fri): yesterday's items clustered + ranked + tagged by entity/freguesia, delivered by **email** (one surface only in v1).
- **Weekly Monday synthesis**: narrative over the week's clusters — emerging themes, regulatory pipeline status, deal-flow rollup.

No real-time alerts. No public surface. No backfill.

## Scope

### Sources (4, all preflight-verified)

| Source | Adapter | Cadence | Lane access | Notes |
|---|---|---|---|---|
| **DRE** | OutSystems screenservices POST + `x-csrftoken` | daily ES query | regulatory (clean) | full structured JSON + body text. Weekly CSRF bootstrap via 1 headless GET. |
| **Vida Imobiliária** | sitemap-crawl (`sitemap.xml`, `<lastmod>` incremental) | ~5/day | mixed (`juridico`/`investimento`/`mercados` URL category = prior) | full text in HTML, no friction. |
| **Idealista/news** | sitemap-news.xml + category/etiquetas pages | ~15–25/day | mixed (URL path = prior: `/financas/fiscalidade`, `/etiquetas/arrendamento`, `/imobiliario/habitacao`) | full text in HTML, no paywall. `/news/` not bot-blocked. |
| **Público** | JSON API `api/list/habitacao` + `api/list/imobiliario` (paginate `?page=N`) | ~1–3 RE/day | mixed, regulatory-leaning (`rubrica`/`tags` = prior) | **headline + ~200-char excerpt + tags + date ONLY**. ~50% bodies paywalled — do not scrape bodies. Use neutral UA (robots blocks `anthropic-ai`/`GPTBot`). |

Lane is **per-article**, classified by the daily Sonnet call, seeded with the source-specific URL/category prior.

### Entity resolution

- **Place → dicofre (freguesia):** `GET https://api.ptdata.org/v1/geo/search?q=<name>` (free, keyless, returns 6-digit dicofre codes that join directly to `silver_caop_freguesias`). Self-hosted Nominatim as fallback for messy/informal place strings.
- **NIF → company enrichment:** `GET https://api.ptdata.org/v1/companies/{nif}` (free, keyless, fuses SICAE+VIES+BASE → canonical name, CAE, address). Called only when an article cites a NIF directly.
- **Org-name → NIPC (brand → entity-cluster):** **deferred** to the Knowledge-graph-PoC's silver-layer resolver. v1 emits raw NER'd ORG spans into `silver_news.article_entities` for downstream linkage; the news pipeline does not solve `Vizta brand → VIZTA 01 CAMELLIA SIC...` itself.
- **Legislation citation enrichment:** `GET https://api.ptdata.org/v1/legislation/search?q=<text>` resolves "artigo 78-E do CIRS" mentions to canonical article text (12 fiscal codes covered). Free, keyless. Added as a low-cost feature; was not in v2.

### Lanes (assigned per-article, not per-source)

`regulatory`, `industry`, `unknown`. Assigned by the daily Sonnet call. DRE = always `regulatory` (deterministic short-circuit).

## Architecture

### Stack (aligned to project conventions)

| Layer | Choice | Notes |
|---|---|---|
| Crawl proxy | **None needed** for v1 sources — direct HTTPS | preflight confirmed: no source needs ZenRows/headless beyond the weekly DRE CSRF refresh. |
| Raw landing | **MinIO** `news-raw/<source>/<YYYY-MM-DD>/<sha256>.{html,json,pdf}` | per existing `[[2026-05-10-minio-not-s3]]`. |
| HTML extract | **Trafilatura** (Vida, Idealista) | F1 0.958. |
| JSON parse | inline (Público, DRE) | no extractor needed. |
| Geo resolution | **PTdata `geo/search`** primary, **Nominatim** fallback | replaces v2's Nominatim-only design. |
| NIF enrichment | **PTdata `companies/{nif}`** | when article cites a NIF. |
| NER (ORG/LOC/LAW) | **Claude Haiku 4.5 single-shot per article** | replaces GLiNER. Haiku is cheaper than running a CPU NER model at 30/day. |
| Daily synthesis | **Claude Sonnet 4.6, ONE call/day** over all articles | replaces embed→cluster→Haiku-per-cluster. Returns clustered + ranked + lane-tagged + summarized structured JSON. |
| Weekly synthesis | **Claude Sonnet 4.6, ONE call/week** | reflective narrative over the week's digests. |
| Orchestration | **Existing Airflow 2.10 + dlt + dbt-postgres + Cosmos** | per project convention. |
| Audit | existing `metadata.pipeline_runs` + new `metadata.news_llm_spend` ledger | pre-task budget guard. |
| Data quality | existing Great Expectations + dbt tests | per `[[bronze-permissive]]`. |
| Delivery | **SMTP email** (single surface in v1) | Telegram/Obsidian/Streamlit explicitly deferred. |

### Why no embedding stack

Verified volume 25–35 articles/day fits comfortably in a single Sonnet context (~80–120k input tokens incl. titles + bodies + excerpts). The cost win of "embed → cluster → one LLM call per cluster" only beats "one LLM call per day" at thousands of articles/day. At 30/day, one Sonnet call ≈ €0.30/day = €9/mo for the full synthesis. The TEI container, HNSW index, GLiNER, HDBSCAN, dim-reduction, cluster-ID-stability mechanism, and 5 eval gates are all solving problems we don't have.

If volume grows 10× or a queryable semantic-search surface enters scope, revisit then.

## Data model

### Bronze — one schema, source-keyed

Article shape is homogeneous across sources, so a per-source-schema layout (v2) is over-engineered. One schema, one append-only table, source-discriminated:

```
bronze_news.articles_raw                    -- dlt append-only
  source_id text,                           -- 'dre' | 'vida' | 'idealista' | 'publico'
  url text, url_canonical text,
  http_status int, fetched_at timestamptz,
  content_type text, content_sha256 text,
  minio_path text,                          -- raw bytes in MinIO, not in Postgres
  source_metadata jsonb,                    -- adapter-specific: sitemap lastmod | rubrica+tags | conteudo_id+ELI
  dlt_load_id, dlt_loaded_at

bronze_news.feed_heartbeat                  -- UPSERT (source_id), per [[heartbeat-sidecar]]
  source_id text, last_seen_at, last_ok_at, consecutive_failures int
```

### Staging — `dbt/models/news/staging/`

One model per source: `stg_dre_articles.sql`, `stg_vida_articles.sql`, `stg_idealista_articles.sql`, `stg_publico_articles.sql`. Per-source validation (URL canon rules differ); standardise to common output columns. Tests: `not_null` on `article_id`, `url_canonical`, `published_at`; `unique` on `article_id`.

### Silver — cross-source consumption (schema: `silver_news`)

```
silver_news.articles
  article_id text PRIMARY KEY,              -- sha256(url_canonical)
  source_id text,
  url_canonical text,
  published_at timestamptz,
  title text,
  body_text text,                           -- NULL for Público (excerpt-only)
  excerpt text,                             -- always present
  body_available boolean,                   -- explicit paywall/excerpt-only signal
  lang text,
  minio_path text,
  ingested_at timestamptz

silver_news.article_entities                -- NER output, denormalized
  article_id text,
  entity_type text,                         -- 'ORG' | 'PER' | 'LOC' | 'LAW'
  entity_text text,
  span_start int, span_end int,
  resolved_dicofre text,                    -- LOC: via PTdata geo/search; NULL if unresolved
  resolved_nif text                         -- only when article explicitly cites a NIF

silver_news.article_freguesia_xref          -- denormalized geo join, indexed
  article_id text,
  dicofre text,                             -- 6-digit, joins to silver_caop_freguesias
  confidence numeric,
  source text                               -- 'ptdata' | 'nominatim'
```

Indexes:
- `silver_news.articles (published_at DESC)`
- `silver_news.articles (source_id, published_at DESC)`
- `silver_news.article_freguesia_xref (dicofre)`

**Deliberately omitted from v1:** `embedding`, `embedding_model_version`, `article_dedup_map`, `watchlist`. URL-canon dedup at staging is sufficient at this volume. Watchlist deferred until an analyst actually asks.

### Gold — `gold_news.*`

```
gold_news.digest_daily
  digest_date date PRIMARY KEY,
  payload jsonb,                            -- Sonnet structured output: clusters + ranking + lane tags + summaries + entities
  rendered_html text,                       -- email body
  llm_status text,                          -- 'ok' | 'sonnet_failed' | 'degraded'
  llm_spend_usd numeric

gold_news.digest_weekly
  iso_week text PRIMARY KEY,
  narrative_text text,
  watch_items jsonb,
  llm_spend_usd numeric
```

No `clusters_daily` table — clusters live inside `payload`. Re-materialise to relations later only if querying clusters cross-day becomes a need.

### LLM spend ledger

```
metadata.news_llm_spend
  ts timestamptz, dag_run_id text, model text,
  prompt_tokens int, completion_tokens int,
  cost_usd numeric, stage text
```

Daily budget guard: pre-task check sums month-to-date and fails the DAG (soft, skip-downstream) if projected > monthly cap. Sonnet ≈ €0.30/day + Haiku NER ≈ €0.10/day ≈ €12/mo expected → cap at €30/mo with explicit alert.

## Configs (per `[[pydantic-not-in-dlt]]`)

```
pipelines/news/
  config/
    base.py                       -- BaseNewsSource(BaseModel)
    sources/dre.py                -- DRESource: outsystems endpoint, csrf bootstrap, ES query template
    sources/vida.py               -- VidaSource: sitemap URL, category map
    sources/idealista.py          -- IdealistaSource: news-sitemap URL, URL-path lane prior map
    sources/publico.py            -- PublicoSource: api endpoints, list paths, UA override
  adapters/
    sitemap_crawl.py              -- shared: Vida + Idealista
    json_api.py                   -- shared: Público (paginate dedupe on id)
    outsystems_post.py            -- DRE-specific
  resources/                      -- dlt resources, dict-based, consume configs
  extract/
    trafilatura_html.py           -- Vida, Idealista
  ner.py                          -- Haiku per-article NER call
  geo.py                          -- PTdata geo/search + Nominatim fallback
  digest.py                       -- Sonnet daily-synthesis call (one for the whole day)
  dags/
    news_ingest_daily.py          -- per-source ingest tasks (DAG factory, one task per source)
    news_synthesis_daily.py       -- fan-in: extract → NER → geo → digest → email
    news_synthesis_weekly.py      -- weekly Sonnet over digests
```

## Failure handling

| Failure | Behavior |
|---|---|
| DRE CSRF token expired | weekly-cron headless re-bootstrap; if mid-week refresh fails, log + skip DRE only; other sources continue |
| Source 404 / malformed (sitemap or API) | log, skip, increment `feed_heartbeat.consecutive_failures`; alert if ≥3 consecutive |
| Trafilatura empty extract | article retained with `body_text=NULL, body_available=false`, flagged |
| PTdata down or rate-limited | fall back to Nominatim for geo; skip `companies/{nif}` enrichment (non-blocking) |
| Haiku NER fails | retain articles, skip entities table for the day, digest still runs (entities are nice-to-have for synthesis, not required) |
| Sonnet daily-digest fails | retry once with smaller context (titles + excerpts only); on second fail, ship "Quiet day — synthesis failed, raw titles below" digest, never skip the send |
| Empty day (nothing crawled) | ship digest with "Quiet day" header |
| Budget guard hit | DAG fails soft, alert, no silent overspend |

## Eval (small, honest)

`tests/news/evals/`:
- `gold/lane_labels.jsonl` — 30 hand-labelled PT articles across 4 sources (lane: regulatory | industry | unknown). Gate: Sonnet lane accuracy ≥ 0.85.
- `gold/place_freguesia.jsonl` — 20 place-name → expected-dicofre pairs (incl. ambiguous "São Pedro"/"Santo António"/"Marvila"). Gate: PTdata `geo/search` resolution accuracy ≥ 0.80 (Nominatim fallback measured separately).
- `make news-evals` runs both.

**Deliberately not built in v1:** GLiNER F1 gate, HDBSCAN V-measure, dedup-precision eval. These belong to the stack we removed. Synthesis quality judged qualitatively by analyst review for the first 2–4 weeks; add a structured rubric only if a problem surfaces.

## Geo resolution: justification

In v1 the digest itself doesn't need dicofre codes — an analyst reads "Marvila" and understands it. The reason geo resolution still ships in v1 is **warehouse composability**: every other table in the project (listings, CAOP, BGRI, schools, permits, developments) is keyed to `dicofre`. News rows must land in the same key space to plug into downstream joins: news × listings ("AL containment in Marvila → highlight affected listings"), news × hedonic features, news × developer KG. PTdata `geo/search` makes this nearly free (one keyless HTTP call per LOC mention), inverting v2's "self-hosted Nominatim → lat/lon → `ST_Contains`" cost calculation. Build now, not v2.

## PR slicing (5, lean)

| PR | Scope | Goal |
|---|---|---|
| **PR1** | Scaffold + wiki bootstrap (`sprint-11.md`, `news-intel.md`, decision pages, architecture page, index update) + Pydantic config base + MinIO raw write + heartbeat sidecar + **Idealista end-to-end** (sitemap-crawl adapter → bronze → stg → `silver_news.articles`) | One source live in silver; pipeline shape proven; chosen because highest cadence + URL-path lane prior makes lane visible. |
| **PR2** | Vida adapter (reuse sitemap-crawl) + Público adapter (JSON-API) → bronze → stg → silver. 3 sources live. GE expectations on staging. | Adapter pattern validated across 2 distinct shapes; silver row count meaningful. |
| **PR3** | Haiku NER per article → `silver_news.article_entities`; PTdata `geo/search` → `silver_news.article_freguesia_xref` (Nominatim fallback); PTdata `companies/{nif}` enrichment hook (only fires when NIF cited); lane+geo eval gates. | Articles geo-grounded + entity-tagged; downstream joins unlocked. |
| **PR4** | Daily Sonnet synthesis call → `gold_news.digest_daily` (clusters+ranks+lane tags+summaries inside `payload`) + LLM spend ledger + budget guard + SMTP email delivery + "Quiet day" + graceful-degrade paths. | Morning digest lands in inbox. |
| **PR5** | DRE source (its own slice: OutSystems POST adapter + weekly CSRF bootstrap headless cron + ES keyword query) + freshness watchdog + weekly Sonnet synthesis → `gold_news.digest_weekly` + PTdata `legislation/search` citation enrichment in regulatory items. | DRE inline; full v1 functionality. |
| **PR6+** (post-v1) | Additional sources (INE, ECO, BdP) via existing adapters; Telegram/Obsidian/Streamlit delivery surfaces; watchlist UPSERT form if asked; KG-PoC bridge if/when their resolver is ready. | Driven by analyst demand. |

## Wiki integration

Each PR ships its own wiki updates in the same commit (per project CLAUDE.md):

- **PR1:** create `wiki/sprints/sprint-11.md` (sprint-10 is taken), `wiki/concepts/news-intel.md`, `wiki/architecture/news-pipeline.md`, `wiki/sources/idealista-news.md`, `wiki/decisions/2026-06-11-news-pipeline-stack.md`, `wiki/decisions/2026-06-11-dre-via-outsystems-screenservices.md`, `wiki/decisions/2026-06-11-ptdata-as-geo-and-entity-layer.md`; add `pipelines/news/` and `dbt/models/news/` rows to `wiki/index.md` §"By area of code"; `wiki/log.md` entry.
- **PR2–5:** extend `news-intel.md`; one source page per new source; log.md entry per PR.

## Cost projection (revised)

| Item | €/mo |
|---|---|
| Sonnet 4.6 (one daily synthesis + weekly) | ~10 |
| Haiku 4.5 (per-article NER) | ~3 |
| PTdata API (free, keyless) | 0 |
| Nominatim (existing self-hosted) | 0 |
| Email delivery | 0 |
| **Total marginal** | **~13** |

Lower than v2's €45–115 because Apify LinkedIn, TEI container, ZenRows, and 3 of 4 delivery surfaces are all out.

## What already exists (reuse, not rebuild)

MinIO raw landing, self-hosted Nominatim (fallback only now), `silver_caop_freguesias`, `metadata.pipeline_runs`, Great Expectations, dlt patterns, DAG factory pattern, Cosmos for dbt-DAG generation.

## Explicitly NOT in scope (v1)

Real-time alerts. Public UI. Backfill (start fresh day 1). Apify LinkedIn. Reddit/Bluesky/Mastodon/Telegram/Twitter. Telegram/Obsidian/Streamlit delivery. Watchlist editor. Org-name → NIPC brand-resolver (KG-PoC owns this). Embedding + clustering stack. PDF parsing. Custom NER model. Multi-language UI.

## Open items (not blockers)

1. **bizAPIs preflight** — claimed free-tier NIF/NIPC/CPRC/IES API with name search (incidental finding during VIZTA/Civilria research). If real, it's input to the KG-PoC resolver, not a news-pipeline call. Worth a 30-min spike before next KG-PoC sprint.
2. **PTdata MCP server** (36 tools, `api.ptdata.org/mcp`) — agentic enrichment path; consider for the weekly synthesis step if it accelerates analyst queries against the digest.
3. **legalize-pt status** — currently stale (~4 weeks); revisit only if the OutSystems screenservices path ever breaks (defensive backup, not primary).

## Resume command for a new session

> Read `.claude/plans/news-pipeline.md` (this file) and `.context/news-sources-preflight.md` for verified source-access evidence. Start PR1: scaffold `pipelines/news/` + wiki bootstrap (`sprint-11.md`, `news-intel.md`, architecture + 3 decision pages + idealista-news source page + index update) + Pydantic config base + MinIO raw write + heartbeat sidecar + Idealista sitemap-crawl adapter end-to-end into `silver_news.articles`.
