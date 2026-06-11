---
title: News + Market-Intelligence PoC — Sprint Plan
type: plan
last_verified: 2026-06-11
tags: [plan, poc, news, sprint, pr-slicing]
status: planned
last_status_update: 2026-06-11
---

# News + Market-Intelligence PoC — Sprint Plan

## For future Claude

This page is the per-PR breakdown of the News PoC, paired with [[news-pipeline-design|design.md]]. 5 PRs to v1; each PR has explicit scope, acceptance criteria, and the wiki updates it must ship in the same commit (per the project's CLAUDE.md rule). The sequencing is intentional: cheapest source first (Idealista has the highest cadence + clearest URL-path lane prior, making the whole shape visible end-to-end in PR1); DRE is deferred to PR5 because despite being preflight-solved, it's still the source with the most novel adapter shape. Read this page when scoping the PoC into a sprint, picking up mid-build, or judging whether to merge a PR against the planned increment.

Read this when:
- Picking up news-pipeline work mid-build — the PR table tells you what shipped and what's next.
- Deciding whether a PR can ship without its wiki updates (no — they're same-commit, per project rule).
- Sizing the PoC for a real sprint slot (rough estimate per PR below).

## Status snapshot

| PR | Scope | Acceptance | Wiki updates (same commit) | Est. effort |
|---|---|---|---|---|
| **PR1** | Scaffold + Idealista end-to-end | ✅ Pending | 8 pages + index + log | ~2 days |
| **PR2** | Vida + Público adapters | ✅ Pending | 2 source pages + index + log | ~1.5 days |
| **PR3** | Haiku NER + PTdata geo + NIF enrichment + eval gates | ✅ Pending | extend concept + 1 decision page + log | ~2 days |
| **PR4** | Sonnet daily digest + SMTP email + budget guard | ✅ Pending | extend architecture + 1 decision page + log | ~2 days |
| **PR5** | DRE adapter + weekly synthesis + freshness watchdog | ✅ Pending | 1 source page + 1 decision page + log | ~2.5 days |

**Total: ~10 working days of focused effort for v1.** Slot into next available sprint after the in-flight portal-expansion / education-pillar work clears.

## Overall sequencing principle

Front-load the *uncertain* parts (does lane classification work? does PTdata geo actually resolve dicofre cleanly? is the Sonnet digest worth reading?) and back-load the well-understood plumbing. Specifically:

- **PR1 proves the pipeline shape** with one source. If Idealista's sitemap-crawl + URL-path lane prior + dlt → bronze → silver works cleanly end-to-end, every other source slots into the same adapter pattern.
- **PR3 proves the join surface** — geo grounding to dicofre and entity tagging are what make the news rows compose with the rest of the warehouse. If PTdata `geo/search` returns dicofre at <0.80 accuracy on the eval set, geo design needs revisiting before PR4 commits to a digest format keyed on it.
- **PR4 proves the product** — the daily Sonnet digest is the only output an analyst actually reads. If it's not useful after 2 weeks of inbox delivery, no amount of source-list growth in PR6+ fixes that.
- **PR5 closes v1** — DRE comes last because its adapter is the most novel and because regulatory-only digest items don't unblock anything in PR1–4.

## PR1 — Scaffold + Idealista end-to-end

**Scope:**

- `pipelines/news/` scaffold: `config/base.py` (Pydantic `BaseNewsSource`), `config/sources/idealista.py`, `adapters/sitemap_crawl.py`, `extract/trafilatura_html.py`, `resources/` dlt resources, `dags/news_ingest_daily.py` (DAG factory, one task per source).
- MinIO raw write (`news-raw/idealista/<YYYY-MM-DD>/<sha256>.html`) per [[2026-05-10-minio-not-s3]].
- `bronze_news.articles_raw` (append-only via dlt) + `bronze_news.feed_heartbeat` (UPSERT, per [[heartbeat-sidecar]]).
- `dbt/models/news/staging/stg_idealista_articles.sql` with URL canonicalization, lane-prior tagging from URL path segment.
- `dbt/models/news/silver/silver_news__articles.sql` filtered to `source_id = 'idealista'`.
- dbt sources + tests: `not_null` on `article_id`, `url_canonical`, `published_at`; `unique` on `article_id`.

**Acceptance:**

- Daily Airflow task runs, polls `https://www.idealista.pt/news/sitemap-news.xml`, diffs against last-fetched URLs, lands new articles in MinIO + bronze.
- `silver_news.articles` populated with ≥10 idealista rows in the first 24h of operation.
- `bronze_news.feed_heartbeat` row for `idealista` shows recent `last_ok_at`.
- GE expectations + dbt tests green.
- Wiki updates land in the same commit.

**Wiki updates (must ship in this commit, per project CLAUDE.md):**

- `wiki/sprints/sprint-NN.md` (new, number TBD when sprint is slotted) — the working sprint page.
- `wiki/concepts/news-intel.md` — new concept page covering: discovery-style ingest, per-article lane classification, single-LLM-call synthesis, dicofre-as-warehouse-key composability principle.
- `wiki/architecture/news-pipeline.md` — new architecture page covering the 3-adapter pattern + data-model overview.
- `wiki/sources/idealista-news.md` — new source page (distinct from `[[idealista]]` listings source — same domain, different surface).
- `wiki/decisions/2026-06-11-news-pipeline-stack.md` — locks the v3 plan vs v2 decisions.
- `wiki/decisions/2026-06-11-ptdata-as-geo-and-entity-layer.md` — locks PTdata-primary, Nominatim-fallback.
- `wiki/index.md` — add `pipelines/news/` and `dbt/models/news/` rows under §"By area of code"; add new pages to Concepts / Architecture / Sources / Decisions sections.
- `wiki/log.md` — one-line entry.

## PR2 — Vida + Público adapters

**Scope:**

- `config/sources/vida.py` + `config/sources/publico.py`.
- Reuse `adapters/sitemap_crawl.py` for Vida (same shape as Idealista with category-prior map: `juridico`→regulatory, `investimento`/`mercados`→industry).
- New `adapters/json_api.py` for Público (paginate `?page=N`, dedupe on `id`, **neutral UA** — robots blocks `anthropic-ai`/`GPTBot`).
- `dbt/models/news/staging/stg_vida_articles.sql`, `stg_publico_articles.sql`.
- Extend `silver_news__articles.sql` to UNION all three sources.
- Encode the Público excerpt-only constraint: `body_text=NULL`, `excerpt=<descricao>`, `body_available=false` on paywalled rows.
- Great Expectations suite for the staging tier per [[bronze-permissive]].

**Acceptance:**

- All 3 sources populating `silver_news.articles` daily; row count between 21 and 35/day in steady state.
- `body_available=false` correctly flags Público rows; never attempts body scrape.
- Heartbeat row per source, all green.
- GE + dbt tests green across the staging tier.

**Wiki updates:**

- `wiki/sources/vida-imobiliaria.md` — new source page.
- `wiki/sources/publico-imobiliario.md` — new source page; document the headline-only constraint + neutral-UA rule explicitly.
- `wiki/index.md` — add to Sources section.
- `wiki/log.md` — one-line entry.

## PR3 — NER + geo grounding + NIF enrichment + eval gates

**Scope:**

- `pipelines/news/ner.py` — Haiku 4.5 single-shot per-article NER (ORG / PER / LOC / LAW). Schema-validated JSON output.
- `pipelines/news/geo.py` — PTdata `geo/search` with caching (place name → dicofre, district code, NUTS); self-hosted Nominatim fallback for unresolved or low-confidence cases. Confidence numeric written to `silver_news.article_freguesia_xref.confidence`.
- PTdata `companies/{nif}` enrichment hook — fires only when an article explicitly cites a 9-digit NIF; result written to `silver_news.article_entities.resolved_nif` and a denormalized enrichment column.
- `dbt/models/news/silver/silver_news__article_entities.sql` + `silver_news__article_freguesia_xref.sql`.
- Indexes: `(published_at DESC)`, `(source_id, published_at DESC)`, `article_freguesia_xref(dicofre)`.
- Eval harness — `tests/news/evals/gold/lane_labels.jsonl` (30 hand-labelled), `tests/news/evals/gold/place_freguesia.jsonl` (20 place-name → expected-dicofre pairs incl. ambiguous "São Pedro"/"Santo António"/"Marvila"). `make news-evals` target. **Gates: lane accuracy ≥ 0.85, geo resolution accuracy ≥ 0.80.**

**Acceptance:**

- ≥80% of `silver_news.articles` rows have ≥1 entity in `article_entities`.
- ≥60% of LOC entities resolve to a dicofre that joins to `silver_caop_freguesias`.
- `make news-evals` passes both gates.
- Articles with cited NIFs (e.g. fund prospectus mentions) carry the enriched `companies/{nif}` payload.

**Wiki updates:**

- Extend `wiki/concepts/news-intel.md` with the lane-classification + entity-resolution sections.
- `wiki/decisions/2026-MM-DD-news-lane-per-article.md` — lock per-article lane classification + source-prior seeding.
- `wiki/log.md`.

## PR4 — Daily Sonnet synthesis + SMTP email + budget guard

**Scope:**

- `pipelines/news/digest.py` — one Sonnet 4.6 call per day over the day's articles + entities + freguesia mentions. Structured-JSON output: clusters (article_ids + representative_id + lane + importance + summary_short + entities_called_out + freguesias_called_out + long_summary if importance ≥ threshold).
- `gold_news.digest_daily` table: `payload jsonb`, `rendered_html text`, `llm_status text`, `llm_spend_usd numeric`.
- `dags/news_synthesis_daily.py` — fan-in DAG: extract → NER (PR3) → geo (PR3) → digest (PR4) → email (PR4).
- `metadata.news_llm_spend` ledger — Airflow task posts row per LLM call (model, prompt_tokens, completion_tokens, cost_usd, stage).
- **Pre-task budget guard** — sums month-to-date spend, soft-fails the DAG with skip-downstream if projected > monthly cap (default €30/mo).
- SMTP email delivery: jinja2 template rendering `payload` → HTML email; one recipient list config-driven.
- **Graceful degradation paths:**
  - Sonnet daily-digest fails → retry once with smaller context (titles + excerpts only); on second fail, ship "Quiet day — synthesis failed, raw titles below" digest.
  - Empty day → ship digest with "Quiet day" header.
  - Never skip the send.

**Acceptance:**

- Email arrives by 07:00 local Mon–Fri.
- `gold_news.digest_daily.llm_status='ok'` for ≥4 of 5 weekday runs over 2 weeks.
- `metadata.news_llm_spend` accurately records every Sonnet/Haiku call.
- Budget guard fires correctly when manually-induced over-spend test exceeds cap.
- Two failure-injection tests pass (Sonnet 5xx → smaller-context retry; Sonnet 5xx twice → "Quiet day" degraded send).

**Wiki updates:**

- Extend `wiki/architecture/news-pipeline.md` with the synthesis + delivery diagram.
- `wiki/decisions/2026-MM-DD-news-single-daily-sonnet-call.md` — lock the no-embedding-stack architectural choice with the volume justification.
- `wiki/log.md`.

## PR5 — DRE + weekly synthesis + freshness watchdog

**Scope:**

- `pipelines/news/adapters/outsystems_post.py` — DRE-specific adapter implementing the `DataActionGetConteudoByElastic` (keyword search) and `DataActionGetConteudoData` (full diploma) replay pattern from the HAR analysis.
- `config/sources/dre.py` — endpoint URLs, ES query template (RE-keyword OR-set: arrendamento, IMT, IMI, IVA + imóvel, habitação, urbanismo, alojamento local, reabilitação urbana), date-window param.
- **CSRF bootstrap** — weekly cron'd headless GET of `/dr/home` extracts a fresh `x-csrftoken`; persists to a secrets backend; reused across all daily ingests for the week. Manual capture as documented fallback.
- `dbt/models/news/staging/stg_dre_articles.sql` — type cast, drop ELI/PDF URL into `source_metadata`, lane hardcoded `regulatory`.
- Extend `silver_news.articles` UNION to 4 sources.
- **PTdata `legislation/search` citation enrichment** — when a DRE article (or any regulatory-tagged article) cites "artigo N do CIVA/CIMI/etc.", resolve to canonical article text via PTdata; attach to entities table as `LAW` entity with `enrichment_payload`.
- `pipelines/news/digest.py` — weekly variant: one Sonnet call per week over the week's `digest_daily.payload` rows; output → `gold_news.digest_weekly` with `narrative_text` + `watch_items jsonb`.
- `dags/news_synthesis_weekly.py` — runs Monday morning before the daily.
- **Freshness watchdog** — Airflow sensor (or dbt test) that alerts if the latest ingested regulatory-tagged Série-I diploma `published_at` is > 5 days behind today. This is the belt-and-braces alarm for the failure mode that bit `legalize-pt` (silent 4-week drift). Independent of which DRE access path is in use.

**Acceptance:**

- DRE ingest runs daily, landing 0–5 RE-keyword-matched diplomas per typical weekday.
- CSRF bootstrap survives a fresh-token rotation (manually expire current token → next daily run still succeeds via weekly refresh).
- Citation enrichment fires on a manually-crafted test article referencing "artigo 78-E do CIRS" and returns the canonical article text.
- Monday email contains the weekly narrative + watch items.
- Watchdog alerts within 24h of an artificially-induced 6-day gap on the regulatory feed.

**Wiki updates:**

- `wiki/sources/dre.md` — new source page documenting the OutSystems screenservices replay pattern, ES index name (`dre-prd-28102025`), CSRF rotation behaviour, fallback chain.
- `wiki/decisions/2026-MM-DD-dre-via-outsystems-screenservices.md` — locks the direct-HTTPS path over headless / ZenRows / legalize-pt / tretas; references the HAR evidence; documents the CSRF lifetime finding (~days).
- `wiki/log.md`.

## What PR6+ looks like (post-v1)

Driven by analyst demand after v1 is in operation for 4+ weeks. Not in scope of this PoC; listing here so the trajectory is visible:

- Additional sources via existing adapters: INE destaques, ECO, BdP comunicados, AT circulares, Confidencial Imobiliário, Vida Imobiliária weekly newsletter, JN Imobiliário, Observador real estate vertical.
- Secondary delivery surfaces: Telegram bot, Obsidian MCP write, Streamlit "Weekly intel" page with Kepler freguesia heatmap.
- Watchlist UPSERT (Streamlit form) — only if analyst actually asks.
- KG-PoC bridge — once the Knowledge-graph-PoC silver-layer resolver is live, news-emitted ORG spans flow into the resolver; resolved NIFs flow back to news via a join table.
- bizAPIs preflight + integration if it solves brand → entity-cluster resolution at usable accuracy.

## See also

- [[news-pipeline-design|Design doc]] — what + why + architecture summary.
- [`.claude/plans/news-pipeline.md`](../../../../.claude/plans/news-pipeline.md) — authoritative implementation plan with full data-model SQL.
- [`.context/news-sources-preflight.md`](../../../../.context/news-sources-preflight.md) — preflight evidence.

## Last verified

2026-06-11 — sprint plan drafted directly from preflight-grounded design; effort estimates assume one engineer working from this branch; no PR has shipped yet.

## Status update history

- 2026-06-11 — plan drafted, design approved, awaiting sprint slot.
