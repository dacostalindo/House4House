---
title: Agentic extraction pipeline — project actors PoC
type: plan
last_verified: 2026-05-15
tags: [plan, agentic, llm, poc, knowledge-graph, project-actors]
status: poc-shipped-outside-h4h
poc_repo: ../../../../Knowledge-graph-PoC/agentic-pipeline/
---

# Agentic extraction pipeline — project actors PoC

## For future Claude

This page captures the **conceptual outline** of a working PoC built outside
House4House (in `~/Desktop/Apps/Knowledge-graph-PoC/agentic-pipeline/`) that
takes a real-estate development name and returns its **architect** and
**promoter** via an LLM + web-search + page-fetch loop.

The PoC is **shipped and validated** — 21 ok rows over 20 H4H-sourced names
(JLL + ZOME developments), 100% precision on the verified ground-truth subset.
This page exists so that when H4H is ready to absorb agentic ingestion, the
design decisions are recorded and don't have to be rediscovered.

Read this when:
- You're about to add a new pipeline that needs to **discover URLs + extract
  typed entities** (any "given an entity name, find its attributes from the
  open web" use case).
- You want to know which design choices were already validated vs. still TBD
  for H4H integration.
- You're considering whether to graft the PoC into `pipelines/` as a `dlt`
  source.

## What this PoC validates

Three things, in order of leverage:

1. **The 3-layer split (fetch / extract / orchestrate) survives contact with
   real Portuguese RE data.** Crawl4AI handles ~80% of developer/trade-press
   sites; the LLM extraction layer reliably names architect + promoter when
   the page contains them; the orchestrator's failure taxonomy (5 statuses)
   makes every miss debugable.
2. **Pydantic-AI is the right orchestration choice for this workload.** Typed
   I/O, native `@output_validator` retries, structured-output enforcement.
   No LangGraph / CrewAI overhead.
3. **The hash-keyed cache (`page + prompt + model`) makes iteration cheap.**
   Prompt-tune → automatic invalidation. Re-run on unchanged pages → 0 LLM
   calls. Critical for the bronze→silver loop H4H already uses.

## Pipeline shape (conceptual)

```
                    project name (string)
                            │
        ╔═══════════════════╪════════════════════════════════╗
        ║                   ▼                                ║
        ║  Phase 1: DISCOVER                                 ║
        ║  ┌──────────────────────────────────────────────┐  ║
        ║  │ Pydantic-AI Agent + WebSearchTool(max=3)     │  ║
        ║  │ Haiku-4.5 → list[CandidateURL]               │  ║
        ║  └──────────────────────────────────────────────┘  ║
        ║       │                                            ║
        ║       │ 0 URLs → status="no_candidates"            ║
        ║       │                                            ║
        ║       ▼                                            ║
        ║  Phase 2: FETCH (parallel within project)          ║
        ║  ┌──────────────────────────────────────────────┐  ║
        ║  │ Crawl4AI + PruningContentFilter              │  ║
        ║  │ asyncio.gather(return_exceptions=True)       │  ║
        ║  │ → list[(markdown, sha256) | Exception]       │  ║
        ║  └──────────────────────────────────────────────┘  ║
        ║       │                                            ║
        ║       │ exception → status="fetch_error"           ║
        ║       │                                            ║
        ║       ▼ (only OK pages continue)                   ║
        ║  Phase 3: EXTRACT (per page, with cache)           ║
        ║  ┌──────────────────────────────────────────────┐  ║
        ║  │ key = sha256(page)+sha256(prompt)+model      │  ║
        ║  │ HIT  → return cached PageExtraction          │  ║
        ║  │ MISS → Pydantic-AI Agent (Haiku, no tools)   │  ║
        ║  │        + @output_validator: evidence-in-src  │  ║
        ║  │        + ModelRetry on validator failure     │  ║
        ║  └──────────────────────────────────────────────┘  ║
        ║       │                                            ║
        ║       │ retry exhausted → status="extract_error"   ║
        ║       │                                            ║
        ║       ▼                                            ║
        ║  Phase 4: CONSOLIDATE (pure Python)                ║
        ║  ┌──────────────────────────────────────────────┐  ║
        ║  │ both null → status="extracted_nothing"       │  ║
        ║  │ else      → status="ok"                      │  ║
        ║  │ Emit one BronzeRecord per (project, url)     │  ║
        ║  └──────────────────────────────────────────────┘  ║
        ╚════════════════════════════════════════════════════╝
                            │
                            ▼
                bronze JSONL (today) / news_bronze.project_actors (H4H target)
```

## The bronze landing contract

Every row carries the same shape regardless of `status`:

| Field | Type | Notes |
|---|---|---|
| `project_name` | str | The input name |
| `source_url` | str? | nullable when `status="no_candidates"` |
| `status` | enum | `ok` / `no_candidates` / `fetch_error` / `extract_error` / `extracted_nothing` |
| `strategy` | str | `"llm"` today; future seam for `"css_idealista"`, etc. |
| `pruned_input_sha256` | str? | hash of fetched markdown for cache + reproducibility |
| `prompt_sha256` | str | hash of the system prompt (auto-invalidates cache on tune) |
| `extracted_at` | timestamp | UTC |
| `extraction_model` | str | e.g. `claude-haiku-4-5` |
| `extraction_version` | str | package version |
| `architect_name` | str? | + evidence + confidence |
| `architect_evidence` | str? | verbatim sentence from page |
| `architect_confidence` | str? | `high` / `medium` / `low` |
| `promoter_name` | str? | + evidence + confidence |
| `promoter_evidence` | str? | verbatim sentence from page |
| `promoter_confidence` | str? | `high` / `medium` / `low` |
| `error_kind` | str? | exception class on failure rows |
| `error_message` | str? | first 500 chars on failure rows |

This is the **direct shape** the H4H `news_bronze` table should adopt. No
silver-layer reconciliation in bronze — that's a downstream concern.

## Design decisions already validated

| Decision | Why | Where it lives in code |
|---|---|---|
| Phased orchestration (not single tool-using agent) | Deterministic, testable, debugable. The Pedra doc's "plain SDK tool-calling is genuinely viable for this use case" | `pedra_poc/agent.py:find_actors` |
| Pydantic-AI over LangGraph/CrewAI | Single agent, single loop; multi-agent overhead unjustified | All agents |
| Haiku for both discovery and extract | Quality drop vs. Sonnet acceptable; cost ~5× cheaper. Tuneable later via eval | `MODEL = "claude-haiku-4-5"` |
| Cache key includes prompt hash | Prompt tune auto-invalidates cached results. Eliminates "why didn't my fix take?" debugging | `cache_key(page_sha, prompt_sha, model)` |
| Evidence-in-source validator with 1 retry | Catches hallucinations cheaply; one retry typically resolves paraphrasing | `@extract_agent.output_validator` |
| Pruned markdown (not HTML) | Promoter "About" pages are prose, not spec tables. ~98% token reduction | `PruningContentFilter(threshold=0.48)` |
| `gather(return_exceptions=True)` per-project | One bad URL doesn't kill the whole project run | `find_actors()` |
| Bounded `Semaphore(4)` across projects | 4× wall-time speedup; safely under Anthropic rate limits | `run.py` |
| Single shared `AsyncWebCrawler` | Avoids ~2s Playwright startup × N URLs | `run.py` |
| Strategy column on bronze even though only "llm" today | When CSS/XPath rules per portal arrive, no bronze migration needed | `BronzeRecord.strategy` |

## Measured results (PoC run, 2026-05-15)

- 20 H4H developments (10 JLL + 10 ZOME) → 43 bronze rows
- **21 ok** (architect or promoter named with evidence)
- 11 extracted_nothing (page fetched, model honestly returned null)
- 7 no_candidates (discovery agent correctly refused to hallucinate)
- 2 fetch_error / 2 extract_error
- Wall time: 1:33
- Precision on the verified subset: 100% (4/4 high-confidence claims correct)
- High-confidence calibration: 4/4 — Haiku is honest about its confidence

Notable findings (cross-corroborated by ≥2 sources):
- ALMAR Beach / Bridge / Park → **Saraiva + Associados × Habitat Invest**
- Alvôr The Breeze → **Costa Lima Arquitectos × KREST Real Estate**
- Águas Santas → **MVCC Arquitetos × VIZTA** (same as Pleno Jardim — probably one project)
- ALURE → Samuel Torres Carvalho × Adriparte
- ALTO Estoril → ARQ Size Architects

JLL names resolved 9/10; ZOME names resolved 1/10 because ZOME's `nome` column
carries shorter / more ambiguous strings ("ACQUA VISTA", "AJ BPorto2"). **Lesson
for H4H integration: enrich the discovery prompt with `localizacaolevel3` +
`localizacaolevel2` (city + freguesia) before sending the name to the agent.**

## H4H integration shape (proposed)

```
┌─────────────────────────────────────────────────────────────────┐
│ Airflow DAG: news_actors_ingestion (per source: idealista, jll, │
│                                     zome, idealista, remax)     │
│                                                                 │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ discover_developments                                 │      │
│  │  SELECT name, city, freguesia                         │      │
│  │  FROM bronze_listings.{src}_developments              │      │
│  │  WHERE name NOT IN (SELECT project_name               │      │
│  │                     FROM news_bronze.project_actors)  │      │
│  └───────────────────────────────────────────────────────┘      │
│                          │                                      │
│                          ▼ .expand() — one mapped task per dev  │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ extract_one (mapped, pool=llm_extraction, slots=4)    │      │
│  │  → calls find_actors(name + city + freguesia)         │      │
│  │  → yields BronzeRecord rows via dlt.resource          │      │
│  │  → idempotent on (project_name, source_url) primary   │      │
│  └───────────────────────────────────────────────────────┘      │
│                          │                                      │
│                          ▼                                      │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ Emit Dataset on completion                            │      │
│  └───────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Airflow DAG: news_actors_transform (triggered by Dataset above) │
│                                                                 │
│  Cosmos DbtTaskGroup:                                           │
│   bronze (news_bronze.project_actors)                           │
│      → silver (silver_market.development_actors)                │
│           — entity resolution against existing                  │
│             silver_properties.unified_listings.agency JSONB     │
│           — promoter portfolio rollup (e.g. all VIZTA projects) │
│           — PDM logic for development-permit cross-reference    │
│      → gold (gold_analytics.developer_portfolio_summary)        │
└─────────────────────────────────────────────────────────────────┘
```

### Concrete next steps when promoting to H4H

1. **Pick the new schema namespace.** `news_bronze.project_actors` (if it
   joins the existing news pipeline) or `bronze_listings.project_actors`
   (if it's portal-listing-adjacent). Recommend `news_bronze` since the
   data shape is news-extraction-shaped, not portal-listing-shaped.

2. **dlt resource wrapper.** Replace `run.py`'s JSONL write with:
   ```python
   @dlt.resource(write_disposition="merge",
                 primary_key=["project_name", "source_url"])
   def project_actors(developments):
       for dev in developments:
           for row in find_actors(dev.name, dev.city, dev.freguesia):
               yield row.model_dump()
   ```

3. **Enrich the discovery query.** Currently `find_actors` takes a bare
   project name. Augment to `find_actors(name, city=None, freguesia=None)`
   so JLL/ZOME rows that have `city`/`freguesia` get a disambiguated query
   ("Alfa Barreiros Funchal apartamentos" vs. just "Alfa Barreiros").
   Single-line change in `DISCOVERY_PROMPT`.

4. **Airflow pool: `llm_extraction`, 4 slots.** Prevents a backfill from
   firing 200 concurrent Anthropic calls.

5. **Idempotency.** Discovery query filters out projects already in
   `news_bronze.project_actors`. Per-page extraction is already idempotent
   via the SQLite cache (or could be reimplemented as a UPSERT in a Postgres
   cache table for H4H multi-worker safety).

6. **Cosmos DbtTaskGroup downstream.** bronze → silver mappings should
   reconcile architect/promoter names against the existing
   `silver_properties.unified_listings.agency` JSONB structure, dedupe via
   the existing silver entity-resolution patterns.

## What's NOT in the PoC (deferred for H4H integration)

| Deferred | Why deferred | When to revisit |
|---|---|---|
| Apify / Scrapfly fetch tier | Idealista/Imovirtual not yet a target | When portal listings become an input |
| Per-portal CSS extraction rules | Single-strategy ("llm") sufficient for the long tail | When a single portal contributes >20% of volume |
| Local LLM fallback (Ollama + Gemma 4) | Anthropic budget acceptable at PoC scale | When 1000+ projects/day or privacy-sensitive |
| Wikidata QID enrichment | Out of scope for "name the actor" job | Silver-layer enrichment, post-resolution |
| Multi-source reconciliation beyond "highest-confidence wins" | Bronze=raw; reconciliation is silver | Silver-layer dbt model |
| Postgres-backed cache instead of SQLite | Single-worker PoC | Multi-worker Airflow execution |
| NIP / NIF lookup against registries | Identity resolution is a separate problem | After basic actor extraction is stable |

## Tradeoffs that will bite if not respected

1. **Cache key MUST include prompt hash.** Drop the prompt hash and every
   prompt tweak silently returns cached old results. Already burned an
   afternoon on this in the PoC; the cache_key tests in `tests/test_schemas.py`
   exist to prevent regression.

2. **Evidence quote MUST be a verbatim substring.** The `@output_validator`
   that enforces this is the only thing keeping Haiku honest. Loosening it
   (e.g., fuzzy substring) re-enables hallucinations.

3. **Discovery returning empty list is a feature, not a bug.** ZOME's
   ambiguous names (ACQUA VISTA, ALPHA VIEW, ''A Namorada'') trigger
   `no_candidates`. Pressuring the model to "just return something" produces
   garbage. Better: enrich the query with city/freguesia at the H4H layer.

4. **Two extraction stacks in the source repo** (v1's `find_project_actors.py`
   using Anthropic native `web_search` builtin vs. v2's phased pipeline).
   v1 is the comparison baseline. When grafting v2 into H4H, drop v1; do
   not try to merge them.

## See also

- PoC source: `~/Desktop/Apps/Knowledge-graph-PoC/agentic-pipeline/`
- Architectural inspiration: the Pedra agentic-web-extraction doc (referenced
  in conversation 2026-05-15)
- Existing H4H news ingestion: this PoC will share `news_bronze` namespace
  with the future Vida Imobiliária + DRE news pipeline (see Knowledge-graph-PoC
  design doc, also 2026-05-12)
- [[orchestration]] — Airflow + dlt + Cosmos patterns
  this PoC will follow
- [[data-quality]] — bronze contract patterns

## Status

- 2026-05-15 — PoC v2 shipped in `Knowledge-graph-PoC/agentic-pipeline/`.
  Architecture validated against 20 H4H developments. Awaiting H4H product
  decision on which sprint absorbs the integration work.
