---
title: News + Market-Intelligence Pipeline for PT Real Estate — PoC Design
type: plan
last_verified: 2026-06-11
tags: [plan, poc, news, llm, regulatory-intelligence, sonnet, haiku, ptdata, dre]
status: design-approved
---

# News + Market-Intelligence Pipeline for PT Real Estate — PoC Design

## For future Claude

This page is the wiki-shaped design for a daily news + regulatory-intelligence pipeline that ingests 4 PT real-estate-relevant sources, geo-grounds and entity-tags every article, and emits an internal-analyst email digest (daily) + Sonnet narrative (weekly). It supersedes the unmerged v2 draft in the `vigorous-sanderson-fd8cfa` worktree; the authoritative implementation plan with full data-model SQL lives in [`.claude/plans/news-pipeline.md`](../../../../.claude/plans/news-pipeline.md), and every source/endpoint claim below was live-verified in [`.context/news-sources-preflight.md`](../../../../.context/news-sources-preflight.md). Read this when scoping the news PoC, sizing it for sprint planning, or revisiting why the embedding/clustering stack was cut.

Read this when:
- Sizing or starting any PR on `pipelines/news/` or `dbt/models/news/`.
- Considering whether to add real-time alerts, a new delivery surface, or social-media lanes — they were deliberately scoped out, see §NOT in scope.
- Wiring news rows into downstream warehouse joins (listings × news, hedonic features × regulatory events, [[uc-3-economics|UC-3]] inputs, the developer KG).
- Comparing to similar discovery-style ingest patterns in [[medallion-layering]].

## Goal

Produce a single internal-analyst surface that compresses ~25–35 PT real-estate-relevant articles per day into a ranked, geo-grounded morning email — and folds the week's signal into a Monday narrative. The pipeline lands news in the same `dicofre` key space as listings, CAOP, BGRI, schools, permits, and developments so that downstream joins (news × inventory, news × hedonic features, news × developer entities) become a single SQL away.

Two outputs:

1. **Daily morning digest** (~07:00 Mon–Fri) — yesterday's articles clustered, ranked by importance, lane-tagged, entity-tagged, delivered by email.
2. **Weekly Monday synthesis** — narrative over the week's clusters: emerging themes, regulatory pipeline status, deal-flow rollup.

No real-time alerts. No public surface. No backfill. No buyer-facing content.

## What changed from v2 (preflight-driven)

Four shifts justified directly by live-verified evidence in [`.context/news-sources-preflight.md`](../../../../.context/news-sources-preflight.md):

1. **No RSS factory.** None of the 4 sources have RSS. Three adapter shapes instead: sitemap-crawl, JSON-API, OutSystems-POST.
2. **No embedding/clustering stack.** Verified volume ~25–35 full-text articles/day. One daily Sonnet call beats TEI/BGE-M3 + GLiNER + HNSW + HDBSCAN on cost, latency, simplicity, and failure surface at this scale.
3. **DRE is direct HTTPS, not headless + PDF.** HAR analysis of `diariodarepublica.pt` revealed OutSystems screenservices POSTs that replay with plain `curl` + `x-csrftoken` — full structured JSON + native Elasticsearch search. No [[zenrows-universal-vs-re-api|ZenRows]], no PDF parsing, no `legalize-pt` dependency.
4. **Geo + entity-data via PTdata API.** `api.ptdata.org` is live, free, keyless: `geo/search` returns 6-digit dicofre codes that join straight to `silver_caop_freguesias`; `companies/{nif}` enrichment fuses SICAE+VIES+BASE; `legislation/search` is a free bonus for citing CIVA/CIMI/CIRS articles. Replaces a self-hosted Nominatim-only design.

Brand → entity-cluster resolution (e.g. `Vizta brand → VIZTA 01 CAMELLIA SIC...`) is **deferred to the Knowledge-graph-PoC's silver-layer resolver** — not duplicated here.

## Sources (4, all live-verified)

| Source | Adapter | Cadence | Lane access | Notes |
|---|---|---|---|---|
| **DRE** | OutSystems screenservices POST + `x-csrftoken` | daily ES query | regulatory (clean) | full structured JSON + body text via `DataActionGetConteudoData` and `DataActionGetConteudoByElastic`. Weekly CSRF bootstrap via 1 headless GET. |
| **Vida Imobiliária** | sitemap-crawl (`sitemap.xml`, `<lastmod>` incremental) | ~5/day | mixed (URL category prior: `juridico` ≈ pure regulatory; `investimento`/`mercados` = deal-flow) | full text in server-rendered HTML, no friction, no JS. |
| **Idealista/news** | sitemap-news.xml + category/etiquetas pages | ~15–25/day | mixed (URL-path prior: `/financas/fiscalidade`, `/etiquetas/arrendamento`, `/imobiliario/habitacao`) | full text in server-rendered HTML, no paywall. `/news/` is not bot-blocked even though the root domain is. |
| **Público** | JSON API `api/list/habitacao` + `api/list/imobiliario` (paginate `?page=N`) | ~1–3 RE/day | mixed, regulatory-leaning (`rubrica`/`tags` prior) | **headline + ~200-char excerpt + tags + date ONLY**; ~50% bodies paywalled — do not scrape bodies. Use neutral UA (robots blocks `anthropic-ai`/`GPTBot`). |

Lane is **per-article**, classified by the daily Sonnet call, seeded with the source-specific URL/category prior. DRE short-circuits to `regulatory`.

## Entity resolution

- **Place → dicofre (freguesia)** — `GET https://api.ptdata.org/v1/geo/search?q=<name>` returns 6-digit dicofre codes that join directly to `silver_caop_freguesias`. Free, keyless, single HTTP call per LOC mention. Self-hosted Nominatim retained as fallback for messy/informal strings. This replaces v2's "Nominatim → lat/lon → `ST_Contains`" design — the cost of geo dropped to nearly zero.
- **NIF → company enrichment** — `GET https://api.ptdata.org/v1/companies/{nif}` fuses SICAE+VIES+BASE → canonical name, CAE, address. Called only when an article explicitly cites a NIF.
- **Org-name → NIPC (brand → entity-cluster)** — deferred to the Knowledge-graph-PoC's silver-layer resolver. v1 emits raw NER'd ORG spans into `silver_news.article_entities`; the news pipeline does not solve `Vizta brand → SPV-NIF` itself.
- **Legislation citation enrichment** — `GET https://api.ptdata.org/v1/legislation/search?q=<text>` resolves "artigo 78-E do CIRS" mentions to canonical article text across 12 fiscal codes. Free, keyless. Added because preflight surfaced it; was not in v2.

### Why geo resolution is in v1 even though the digest doesn't strictly need it

The digest itself reads fine with raw place strings — an analyst understands "Marvila" without dicofre `110645`. Geo lands in v1 anyway because **every other table in this project is keyed to dicofre**: listings, CAOP, BGRI, schools, permits, developments. News rows must join the same key space to unlock the downstream surface — news × listings ("AL containment in Marvila → highlight affected inventory"), news × hedonic features, news × developer KG. PTdata makes this nearly free; the calculus that justified deferring it in v2 no longer holds.

## Architecture summary

Full stack table is in [`.claude/plans/news-pipeline.md`](../../../../.claude/plans/news-pipeline.md). Headlines:

- **Raw landing:** MinIO `news-raw/<source>/<YYYY-MM-DD>/<sha256>.{html,json,pdf}` per [[2026-05-10-minio-not-s3]].
- **HTML extract:** Trafilatura (Vida, Idealista). JSON parse inline (Público, DRE).
- **NER:** Claude Haiku 4.5 single-shot per article. Replaces GLiNER (cheaper at 30/day than running a CPU NER model).
- **Daily synthesis:** Claude Sonnet 4.6, **one call per day** over the full set — returns clustered + ranked + lane-tagged + summarized structured JSON. Replaces embed→cluster→Haiku-per-cluster (volume justifies single-call).
- **Weekly synthesis:** Sonnet, one call per week over the daily payloads.
- **Orchestration:** existing Airflow 2.10 + dlt + dbt-postgres + Cosmos.
- **Audit:** existing `metadata.pipeline_runs` + new `metadata.news_llm_spend` ledger with pre-task budget guard.
- **Data quality:** Great Expectations + dbt tests per [[bronze-permissive]].
- **Delivery:** **SMTP email only** in v1. Telegram, Obsidian MCP, Streamlit explicitly deferred.

## Data model summary

Full SQL in the authoritative plan. Headlines:

- **Bronze:** single `bronze_news` schema, source-discriminated (articles are homogeneous; per-source schemas would over-engineer the GIS pattern). `bronze_news.articles_raw` (append-only via dlt) + `bronze_news.feed_heartbeat` (UPSERT) per [[heartbeat-sidecar]].
- **Staging:** one model per source (`stg_dre_articles.sql`, `stg_vida_articles.sql`, `stg_idealista_articles.sql`, `stg_publico_articles.sql`) — per-source URL canon rules and metadata extraction, standardised output columns.
- **Silver (`silver_news`):** `articles` (PK = `sha256(url_canonical)`), `article_entities` (denormalized NER output with `resolved_dicofre` + `resolved_nif`), `article_freguesia_xref` (indexed geo join). No embeddings, no dedup map, no watchlist in v1.
- **Gold (`gold_news`):** `digest_daily` (Sonnet structured output in `payload` jsonb + rendered email body), `digest_weekly` (narrative + watch items). No `clusters_daily` table — clusters live inside the digest payload.

## Cost projection

| Item | €/mo |
|---|---|
| Sonnet 4.6 (one daily synthesis + weekly) | ~10 |
| Haiku 4.5 (per-article NER) | ~3 |
| PTdata API (free, keyless) | 0 |
| Nominatim (existing self-hosted) | 0 |
| Email delivery | 0 |
| **Total marginal** | **~13** |

Down from v2's projected €45–115/mo, primarily by dropping Apify LinkedIn, the TEI/BGE-M3 container, ZenRows incremental usage, and 3 of 4 delivery surfaces.

## NOT in scope (v1)

Real-time push alerts. Public-facing UI / SEO / buyer pages. Backfill of any kind. Apify LinkedIn lane. Reddit / Bluesky / Mastodon / Telegram / Twitter social lanes. Telegram / Obsidian / Streamlit delivery surfaces. Watchlist editor. Org-name → NIPC brand resolver (Knowledge-graph-PoC owns this). Embedding + clustering stack. PDF parsing. Custom NER model. Multi-language UI.

## Open items (not blockers)

- **bizAPIs preflight** — claimed free-tier NIF/NIPC/CPRC/IES API with name search (incidental finding during VIZTA/Civilria research). If real, it's input to the KG-PoC resolver, not a news-pipeline call. Worth a 30-min spike before next KG-PoC sprint.
- **PTdata MCP server** (36 tools at `api.ptdata.org/mcp`) — agentic enrichment path; consider for the weekly synthesis step.
- **`legalize-pt` status** — currently stale ~4 weeks; revisit only if the OutSystems screenservices path ever breaks (defensive backup, not primary).

## See also

- [[news-pipeline-sprint-plan|Sprint plan]] — per-PR scope, acceptance criteria, sequencing.
- [`.claude/plans/news-pipeline.md`](../../../../.claude/plans/news-pipeline.md) — authoritative implementation plan with full data-model SQL and config layout.
- [`.context/news-sources-preflight.md`](../../../../.context/news-sources-preflight.md) — live-verified source-access evidence per source / endpoint.
- [[bronze-permissive]], [[heartbeat-sidecar]], [[medallion-layering]] — load-bearing concepts referenced throughout the design.
- [[2026-05-10-minio-not-s3]] — raw-landing decision.

## Last verified

2026-06-11 — design re-grounded against live preflight of all 4 sources, PTdata API, DRE HAR analysis, legalize-pt + tretas comparison. Implementation not yet started.
