---
title: News + Regulatory-Intelligence PoC — Sprint Plan
type: plan
last_verified: 2026-06-11
tags: [plan, poc, news, sprint, pr-slicing, uc-3]
status: planned
last_status_update: 2026-06-11
---

# News + Regulatory-Intelligence PoC — Sprint Plan

## For future Claude

This page is the per-PR breakdown of the News PoC, paired with [[news-pipeline-design|design.md]]. 5 PRs to v1; each PR has explicit scope, acceptance criteria, eval gates, and the wiki updates it must ship in the same commit (per the project's CLAUDE.md rule). The sequencing changed materially from the v3 cut after the UC-3 reframe: Vida replaces Idealista as the PR1 anchor (simpler adapter + higher signal density); PR3 inserts a taxonomy-discovery step before per-article Haiku extraction; PR4 swaps daily Sonnet synthesis for a Sonnet nightly dedup pass + dbt SQL panel materialization; PR5 adds the DRE backfill DAG. Read this when scoping the PoC into a sprint, picking up mid-build, or judging whether to merge a PR against the planned increment.

Read this when:
- Picking up news-pipeline work mid-build — the PR table tells you what shipped and what's next.
- Deciding whether a PR can ship without its wiki updates (no — they're same-commit, per project rule).
- Sizing the PoC for a real sprint slot.

## Status snapshot

| PR | Scope | Acceptance | Wiki updates (same commit) | Est. effort |
|---|---|---|---|---|
| **PR1** | Scaffold + wiki bootstrap + **Vida** end-to-end (sitemap → bronze → silver) | ✅ Pending | 8 pages + index + log | ~2 days |
| **PR2** | **Público** (JSON-API) + **Negócios** (post-preflight) + `silver_dim.entity_aliases` seed | ✅ Pending — *blocked on Negócios preflight* | 2 source pages + 1 shared-dim concept + index + log | ~2 days |
| **PR3** | Taxonomy-discovery → per-article **Haiku extraction** → events / entities / freguesia + 3 eval gates + reprocess DAG scaffold | ✅ Pending | extend concept + 1 decision page + log | ~3 days |
| **PR4** | **Sonnet nightly dedup** + spend ledger + budget guard + `gold_news.signal_panel` materialization + optional dev-loop digest renderer | ✅ Pending | extend architecture + 1 decision page + log | ~2 days |
| **PR5** | **DRE** adapter + tema-filter set + DRE backfill DAG (2017+ + fiscal-codes spike to 2010) + popular-name dict bootstrap + `dre_relevance` gate | ✅ Pending | 1 source page + 2 decision pages + log | ~3 days |

**Total: ~12 working days of focused effort for v1**, plus ~1–2h Negócios preflight before PR2.

## Overall sequencing principle

Front-load the *uncertain* parts (does Haiku per-article extraction hit the recall/precision gates? does the closed taxonomy survive contact with real PT articles? does tema-filtering recall the 40-ELI known-relevant set?) and back-load the well-understood plumbing. Specifically:

- **PR1 proves the pipeline shape** with one P0 source. Vida is the simplest adapter (sitemap-crawl, full HTML, no paywall, no JS) — if it works end-to-end, Público + Negócios + Idealista all slot into the same pattern.
- **PR3 proves the extraction surface** — events + entities + geo are the deliverables UC-3 actually consumes. If the taxonomy doesn't survive cluster-discovery, or if `event_recall` < 0.80, the entire downstream pipeline is unfittable for UC-3. Gates are hard.
- **PR4 proves the panel + dev-loop observability** — `signal_panel` is UC-3's direct input; the digest is the qualitative-eval feedback loop during validation.
- **PR5 closes v1** with the DRE backfill — the most-novel adapter shape, the largest one-time data load, and the legislation-citation enrichment that makes regulatory events first-class.

## PR1 — Scaffold + wiki bootstrap + Vida end-to-end

**Scope:**

- `pipelines/news/` scaffold: `config/base.py` (Pydantic `BaseNewsSource`), `config/sources/vida.py`, `adapters/sitemap_crawl.py`, `extract/trafilatura_html.py`, `dags/news_ingest_daily.py` (DAG factory, one task per source — only `vida` activated in this PR).
- MinIO raw write (`news-raw/vida/<YYYY-MM-DD>/<sha256>.html`) per [[2026-05-10-minio-not-s3]].
- `bronze_news.articles_raw` — created via Alembic/SQL migration, **not dlt**. Direct `psycopg` INSERT from the Airflow task. `(source_id, content_sha256)` unique constraint. `dag_run_id` + `ingested_at` provenance columns.
- `bronze_news.feed_heartbeat` UPSERT per source per [[heartbeat-sidecar]].
- `dbt/models/news/staging/stg_vida_articles.sql` with URL canonicalization, category-prior tagging from URL path.
- `dbt/models/news/silver/silver_news__articles.sql` filtered to `source_id = 'vida'`.
- dbt sources + tests: `not_null` on `article_id`, `url_canonical`, `published_at`; `unique` on `article_id`.
- **Recreate `.context/news-sources-preflight.md`** stub from existing evidence inline in the wiki + HAR, or remove references throughout if not recreating.

**Acceptance:**

- Daily Airflow task runs, polls `https://vidaimobiliaria.com/sitemap.xml` (or actual URL — verify in PR1), diffs against last-fetched URLs, lands new articles in MinIO + bronze.
- `silver_news.articles` populated with ≥3 Vida rows in the first 24h.
- `bronze_news.feed_heartbeat` row for `vida` shows recent `last_ok_at`.
- dbt tests green.
- Wiki updates land in the same commit.

**Wiki updates (must ship in this commit, per project CLAUDE.md):**

- `wiki/sprints/sprint-11.md` (new) — the working sprint page.
- `wiki/concepts/news-intel.md` — new concept page covering: event-shape extraction, dicofre-as-warehouse-key composability principle, brand-string canonicalization, UC-3 as sole consumer.
- `wiki/architecture/news-pipeline.md` — new architecture page covering the 6-DAG layout + data-model overview.
- `wiki/sources/vida-imobiliaria.md` — new source page, priority P0.
- `wiki/decisions/2026-06-11-news-pipeline-stack.md` — locks the v4 plan (UC-3 reframe, per-article Haiku, no dlt, no embeddings, no weekly synthesis, brand-string-only).
- `wiki/decisions/2026-06-11-news-pipeline-no-dlt.md` — locks the no-dlt decision with rationale (fixed schema + MinIO blob = dlt machinery is dead weight here).
- `wiki/decisions/2026-06-11-ptdata-as-geo-and-entity-layer.md` — locks PTdata-primary, Nominatim-fallback.
- `wiki/index.md` — add `pipelines/news/` and `dbt/models/news/` rows under §"By area of code"; add new pages to Concepts / Architecture / Sources / Decisions sections.
- `wiki/log.md` — one-line entry.

## PR2 — Público + Negócios + entity-aliases seed

**Blocker:** Negócios preflight spike (~1–2h) must complete and be documented inline before this PR is scoped. Robots, paywall depth, sitemap/RSS/API access path, anti-bot posture. Cofina group is typically aggressive — if preflight reveals headless-only or ZenRows-required access, the PR scope contracts to Público-only and Negócios moves to PR6+.

**Scope:**

- `config/sources/publico.py` + `config/sources/negocios.py`.
- New `adapters/json_api.py` for Público (paginate `?page=N`, dedupe on `id`, **neutral UA** — robots blocks `anthropic-ai`/`GPTBot`).
- Negócios adapter shape TBD post-preflight (likely sitemap-crawl reusing PR1's adapter; potentially JSON-API).
- `dbt/models/news/staging/stg_publico_articles.sql`, `stg_negocios_articles.sql`.
- Extend `silver_news__articles.sql` to UNION all three sources.
- Encode Público's excerpt-only constraint: `body_text=NULL`, `excerpt=<descricao>`, `body_available=false` on paywalled rows.
- `silver_dim.entity_aliases` table created via migration, seeded with ~20 PT real-estate operator brand variants (Vizta, Solyd, Habitat Invest, Stone Capital, Civilria, Krest, etc.). Append-only with conflict-do-nothing on `alias_text`.
- Great Expectations suite for the staging tier.

**Acceptance:**

- All 3 sources populating `silver_news.articles` daily; row count between 10 and 25/day in steady state (volume lower than v3's Idealista-led ~30/day estimate, but higher signal density).
- `body_available=false` correctly flags Público rows; never attempts body scrape.
- Heartbeat row per source, all green.
- `silver_dim.entity_aliases` accessible and seeded.
- GE + dbt tests green.

**Wiki updates:**

- `wiki/sources/publico-imobiliario.md` — new source page; document the headline-only constraint + neutral-UA rule explicitly. Priority P0.
- `wiki/sources/jornal-de-negocios-imobiliario.md` — new source page; document the preflight findings + adapter shape. Priority P0.
- `wiki/concepts/entity-aliases.md` — new shared-dim concept page covering: cross-pipeline brand canonicalization, append-only with conflict-do-nothing, brand-level (not SPV/NIF-level) joins, future dev-enrichment consumer pattern.
- `wiki/index.md` — add to Sources + Concepts sections.
- `wiki/log.md` — one-line entry.

## PR3 — Taxonomy discovery + per-article Haiku extraction + eval gates

**Scope (sequenced internally):**

1. **Taxonomy discovery pass** (offline) — one-shot Sonnet call over the PR1–PR2 corpus accumulated so far (~14 days × ~15 articles ≈ 200 articles). Prompt: "discover the natural event types in these PT real-estate articles." Output: candidate taxonomy + frequency. Human review, lock final closed taxonomy (~8 event types) into `pipelines/news/config/event_taxonomy.py`. Commit extraction prompt `v1.0` to `pipelines/news/prompts/extraction_v1_0.txt`. Record in `metadata.news_prompts` (semver + sha256 + deployed_at).
2. **Per-article Haiku extraction** — `pipelines/news/extract/haiku.py`. Single Haiku 4.5 call per article. Schema-validated structured output: `events[]` (type, scope_level, scope_codes, effective_date, confidence), `entities[]` (type, text, span), `legal_instrument_refs[]` (cited_text, eli_or_null, confidence), `freguesia_refs[]`, `lane`. Records `extraction_prompt_version` + `extraction_model` on every row.
3. **MinIO blob cache** at `news-llm/extractions/<article_id>/<prompt_version>.json`. Re-derivation reads cache, no Haiku re-call.
4. **Deterministic ELI extraction** — regex pass on title + body before Haiku call for qualified citations + `data.dre.pt/eli/...` href extraction. Haiku gets the regex results as context.
5. **PTdata `geo/search`** with caching → `silver_news.article_freguesia_xref`. Self-hosted Nominatim fallback.
6. **Alias-map canonicalization** — every NER'd ORG span gets `entity_text_canonical` via `silver_dim.entity_aliases` lookup; new variants auto-appended.
7. **`news_reprocess` DAG scaffold** — parameterized by `prompt_version` + article filter; per-task budget projection. No auto-trigger.
8. **Eval harness:**
   - `tests/news/evals/gold/event_recall.jsonl` — 30 hand-annotated articles across 4 sources (~3h labelling). Each article has expected `events[]`. Gate: ≥0.80 recall, ≥0.85 precision.
   - `tests/news/evals/gold/event_typing.jsonl` — reuses the same 30 articles; type-match accuracy gate ≥0.85 conditional on recall.
   - `tests/news/evals/gold/place_freguesia.jsonl` — 20 place→dicofre pairs incl. ambiguous "São Pedro"/"Marvila". Gate: ≥0.80.
   - `make news-evals` runs all three.

**Acceptance:**

- All 3 gates pass on `make news-evals`.
- ≥80% of `silver_news.articles` rows have ≥1 row in `article_entities`.
- ≥60% of LOC entities resolve to a dicofre that joins to `silver_caop_freguesias`.
- `silver_news.events` populated with ≥1 event/article on average across the corpus.
- Reprocess DAG manually triggered against a prior `prompt_version='v0.9.0'` (the pre-lock draft) successfully re-extracts a 50-article sample.

**Wiki updates:**

- Extend `wiki/concepts/news-intel.md` with: taxonomy-discovery pattern, per-article extraction shape, alias-map canonicalization flow, reprocess discipline.
- `wiki/decisions/2026-MM-DD-news-event-taxonomy.md` — locks the closed 8-type taxonomy, references the cluster-discovery evidence.
- `wiki/log.md`.

## PR4 — Sonnet dedup + panel materialization + dev-loop digest

**Scope:**

- `pipelines/news/dedup.py` — Sonnet 4.6 nightly call over ELI-less event candidates from today + the last 14 days. Input: candidate events with type / scope / date / source-article-id. Output: merge graph (`{candidate_id: canonical_event_id}`). Failure → flag candidates `dedup_pending` in panel; never crash.
- `silver_news.event_dedup_map` table + dedup-applied view `silver_news.events_canonical` materializing the resolution.
- `dbt/models/news/gold/gold_news__signal_panel.sql` — `(dicofre, iso_week, lane, event_type) → count + salience + dominant_entities`. Pure SQL over `events_canonical` × `article_freguesia_xref` × `event_coverage`. Refreshed daily.
- `metadata.news_llm_spend` ledger — every LLM call records `model`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `stage`.
- **Pre-task budget guard** — sums month-to-date spend, soft-fails the DAG with skip-downstream if projected > €15/mo cap (alert at €10).
- **Optional dev-loop digest renderer** — thin Sonnet pass over today's new events (~5–15 events typically), emits a one-page HTML email. SMTP delivery to single configured recipient. Explicitly time-limited: a `digest_enabled: bool` config flag in `dre.py`/site-config defaults to true at PR4 ship, retired after `event_recall` ≥0.80 holds for 3 consecutive weeks. Replaced by one-line Airflow ops summary at that point.
- **Graceful degradation paths:**
  - Sonnet dedup fails → ship panel with `dedup_pending` rows flagged; alert; no retry blocking.
  - Empty day → panel refresh still runs; digest emits "Quiet day" if enabled.
  - Sonnet digest fails → skip the send; ops summary fires regardless.

**Acceptance:**

- `dedup_correctness` eval passes (precision ≥0.90 on "should merge" pairs).
- `gold_news.signal_panel` populated; sample SQL query returns expected `(dicofre, week, event_type)` rollups against the validation corpus.
- `metadata.news_llm_spend` records every Haiku + Sonnet call across the prior 2 weeks.
- Budget guard fires correctly on a manually-induced over-spend test (set cap to €0.01, expect skip-downstream).
- Dev-loop digest arrives by 07:00 local for ≥4 of 5 weekday runs over 2 weeks.

**Wiki updates:**

- Extend `wiki/architecture/news-pipeline.md` with the dedup + panel + digest-retirement sections.
- `wiki/decisions/2026-MM-DD-news-sonnet-dedup-vs-corpus-summary.md` — locks "Sonnet as surgical dedup call, not corpus summarizer," with the per-article-extraction rationale.
- `wiki/log.md`.

## PR5 — DRE + tema-filter + backfill DAG + popular-name dictionary

**Scope:**

- `pipelines/news/adapters/outsystems_post.py` — DRE-specific adapter wrapping `DataActionGetPesquisaByTema` (filtered listing), `DataActionGetConteudoData` (full diploma), `DataActionGetConteudoByElastic` (keyword fallback). Replay pattern from HAR analysis.
- `config/sources/dre.py` — endpoint URLs, tema ID set ({8 Arrendamento, 35 Urbanismo, 48 Fiscal, 33 Turismo, 46 Estrangeiros, 52 Civil} primary; {4 Ambiente, 39 Contratação Pública} as PR5 precision spikes), instrument-type set ({Decreto-Lei, Lei, Portaria, Decreto Regulamentar, Resolução do CM}), date-window param.
- **CSRF bootstrap** — weekly cron'd headless GET of `/dr/home` extracts a fresh `x-csrftoken`; persists to a secrets backend; reused across all daily ingests for the week. Manual capture as fallback.
- `dbt/models/news/staging/stg_dre_articles.sql` — type cast, drop ELI/PDF URL into `source_metadata`, lane hardcoded `regulatory`.
- Extend `silver_news.articles` UNION to 4 sources (Vida + Público + Negócios + DRE; Idealista deferred to PR6+).
- `silver_dre.instruments` (a.k.a. `dim_legal_instruments`) — ELI PK, `popular_names text[]`, `tagged_temas int[]` (recorded from multi-tema dedup during backfill), instrument-type, effective_date, source MinIO path.
- `silver_dre.filter_versions` — tema-set + instrument-type set per backfill batch, semver-tagged. Adding a tema = parameterized re-backfill at new filter version, restricted by date range.
- **DRE backfill DAG** (`news_dre_backfill`) — parameterized by date range + filter_version. Iterates tema set, dedups instruments on ELI (recording `tagged_temas[]`), lands in MinIO + bronze + populates `silver_dre.instruments`. Per-task budget projection.
  - **Primary backfill:** 2017-01-01 → present, full tema set.
  - **Fiscal-codes spike:** 2010-01-01 → 2016-12-31, restricted to `tema=Fiscal` AND instrument-type ∈ {Lei, Decreto-Lei} that amend CIRS/CIMI/IMT/IVA.
- **Popular-name dictionary bootstrap** — one-shot Sonnet pass over backfilled instruments: "is this instrument commonly known by a popular name? If yes, emit." Output reviewed manually (~30–50 entries expected), committed as seed data to `silver_dre.instruments.popular_names[]`.
- **PTdata `legislation/search` citation enrichment** — runs at extraction time on `LAW` entities; attaches canonical article text payload.
- **Eval gate:** `tests/news/evals/gold/dre_relevance.jsonl` — 40 hand-curated known-RE-relevant ELIs (built ~2h pre-PR5). Gate: ≥95% recall against the live tema-filtered ingest.

**Acceptance:**

- DRE backfill DAG completes 2017-present primary + 2010-2016 fiscal spike, populating `silver_dre.instruments` and `silver_news.events` (provenance='dre_only').
- `dre_relevance` eval ≥95% recall.
- CSRF bootstrap survives a forced-rotation test.
- Citation enrichment fires on a test article referencing "artigo 78-E do CIRS".
- Popular-name dictionary committed with ≥30 reviewed entries.
- Subsequent daily DRE ingest delta returns expected ~0–5 instruments/weekday.

**Wiki updates:**

- `wiki/sources/dre.md` — new source page documenting the OutSystems screenservices replay pattern, the tema-filter design, CSRF rotation behaviour, the live tema enumeration findings. Priority P0.
- `wiki/decisions/2026-MM-DD-dre-via-outsystems-screenservices.md` — locks the direct-HTTPS path; references the HAR evidence.
- `wiki/decisions/2026-MM-DD-dre-filter-by-tema.md` — locks the tema-set choice, references the live tema enumeration, documents the dropped keyword-OR design.
- `wiki/log.md`.

## What PR6+ looks like (post-v1)

Driven by UC-3 demand and analyst-feedback. Not in scope of this PoC.

- **Idealista activation** — adapter pattern already exists from PR1's `sitemap_crawl.py`. Activate only if UC-3's panel needs higher article volume in the deal-flow lane.
- **Tema precision spikes** — `Ambiente` (4) and `Contratação Pública` (39): sample 50 instruments each, classify as RE-relevant or noise, include if precision ≥0.4.
- **Additional sources:** INE destaques (statistical releases), ECO, BdP comunicados, AT circulares, Confidencial Imobiliário.
- **News-content backfill spike** — only if UC-3 demands historical news coverage as salience covariate; assess Wayback/sitemap feasibility honestly.
- **Promotion of digest beyond SMTP** — Telegram / Streamlit — only if analyst-surface comes back into scope.
- **Dev-enrichment integration** — when the future LLM enrichment over developer names (architects/promoters via web search) lands, ensure it writes to `silver_dim.entity_aliases` so brand-level joins to news entities work cleanly.

## See also

- [[news-pipeline-design|Design doc]] — **authoritative** — full data-model SQL, inlined preflight evidence, failure handling, file layout, architecture.
- `.claude/plans/news-pipeline.md` — retired to a pointer back at the wiki design (2026-06-11). Do not edit there.

## Last verified

2026-06-11 — sprint plan rewritten from the UC-3-reframed v4 design; effort estimates assume one engineer working from this branch; no PR has shipped yet; Negócios preflight not yet performed.

## Status update history

- 2026-06-11 — v3 sprint plan (Idealista-anchored, dlt-based, daily-Sonnet-synthesis-shaped) superseded by v4 (Vida-anchored, no-dlt, per-article-Haiku-shaped, UC-3 panel as primary output). 5-PR count preserved.
