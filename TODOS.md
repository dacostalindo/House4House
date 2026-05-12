# TODOS

## Obsidian Local REST API integration (Phase 3e enhancement, deferred)

**What:** wire the [Obsidian Local REST API plugin](https://github.com/coddingtonbear/obsidian-local-rest-api) into Claude Code workflows for real-time wiki updates when Obsidian is open, plus a programmatic query surface for the Streamlit app and future skills.

**Why:** today, Claude Code writes to `wiki/*.md` on disk. Obsidian re-reads on focus, but there's a small lag and occasional file-lock weirdness when both are writing. The plugin's REST API solves both. Beyond that, it unlocks: a `/wiki-search` skill that queries Obsidian's native full-text + tags + Dataview indexes (much faster than grep at 100+ pages), and a Phase 5+ Streamlit page that surfaces wiki context alongside Idealista enrichment data.

**Pros:** real-time edit sync, structured queries via Dataview, programmable graph queries (find orphan pages, hubs, dead links), no filesystem-locking edge cases.

**Cons:** requires Obsidian running locally with the plugin installed and an API token. Couples some workflows to Obsidian (the wiki is still readable as plain markdown without it, but advanced features require it). Not a fit for Docker-side workflows like `wiki_lint_dag` (which keeps using filesystem reads).

**Context:** Phase 3e plan defers this. The wiki itself is plain markdown; the REST API is an opt-in enhancement layer. Right time to revisit: when the wiki crosses ~50 pages OR when the first concrete Streamlit use case for surfacing wiki content lands.

**Depends on:** Phase 3e (LLM Wiki) shipped first.

---

## Wiki schema-version migration

**What:** when `wiki/CLAUDE.md` schema evolves (new required sections, new YAML frontmatter fields, new naming convention), establish a migration playbook. Without one, schema drift accumulates: half the source pages have `## Last verified`, half don't.

**Why:** Phase 3e seeds the wiki with one schema. Over months the schema will evolve (new section types, new tags, new required metadata). Pages written under the old schema get inconsistent with the new schema. The wiki/lint DAG can flag drift but doesn't fix it.

**Pros:** keeps the wiki structurally consistent as it grows; makes Dataview queries reliable; reduces "search returned 8 pages but only 5 have the field I need" bugs.

**Cons:** requires committing to a versioning convention upfront (e.g., `schema_version: 1` in CLAUDE.md frontmatter) and a migration command (`/wiki-migrate-schema vN→vM`).

**Context:** captured during Phase 3e devex-review (Pass 5 gap). Not blocking — Phase 3e ships with one schema; revisit when the second schema change is needed.

**Depends on:** Phase 3e shipped + at least one real schema evolution observed.

---

## Wiki rot signal — DX measurement

**What:** instrument the wiki to detect when it's rotting vs being maintained. Candidate metrics: weekly lint-finding count trend, ratio of source pages with `Last verified` < 30 days, ingest count per week, query count per week (if we can count those).

**Why:** the wiki only delivers value if it stays current. The risk pattern: ingest enthusiasm fades after 3 months, lint findings climb, no one notices, the wiki becomes a museum. Adding a small dashboard (or appending a 1-line metric to `wiki/log.md` weekly) catches this before it gets bad.

**Pros:** lets us answer "is the wiki actually working" with data instead of vibes.

**Cons:** adds a tiny instrumentation burden. The metrics could become noise if the user dismisses them.

**Context:** Phase 3e devex-review Pass 8 gap. The wiki_lint_dag is the natural place to emit metrics — extend it to write a one-line trend entry to log.md or a separate `wiki/health.md` page.

**Depends on:** Phase 3e shipped + wiki_lint_dag running for ≥4 weeks (need a baseline).

---

## Adopt qmd or equivalent search engine for the wiki

**What:** integrate [qmd](https://github.com/tobi/qmd) (or build a minimal alternative) for hybrid BM25 + vector search over `wiki/*.md`. Expose as both a CLI (so Claude can shell out) and an MCP server (so Claude uses it as a native tool).

**Why:** at small scale (~50 pages), `index.md` + grep is fine. At ~150+ pages, finding the relevant subset becomes the bottleneck for Claude's ingest/query workflows.

**Pros:** much faster than reading index.md + grepping at scale; semantic search catches topical matches grep misses.

**Cons:** new infrastructure to maintain; qmd is a tool we don't yet use; alternative homemade search is "vibe-coded helper" territory.

**Context:** explicit non-goal of Phase 3e. Re-evaluate when wiki crosses ~150 pages.

**Depends on:** Phase 3e shipped + wiki growing past the search-by-grep threshold.

---

## Recency annotations on wiki/sources/* pages (deferred from PR 2)

**What:** add a `last_api_check: <date>` YAML frontmatter field + inline `(as of YYYY-MM, url)` markers to every external claim (rate limits, schema column behaviors, deprecation notes, pagination patterns) on every `wiki/sources/<name>.md` page.

**Why:** the wiki describes upstream APIs and GIS sources whose behavior drifts over time. Without dated annotations, future-Claude reading a quirk doesn't know whether to trust it or re-verify against current API behavior. With annotations: `/wiki-lint` flags pages whose `last_api_check` is older than 90 days; future-Claude can decide per-claim whether a fact is fresh.

**Pros:** scales as the wiki ages; small operational cost per ingest (re-stamp `last_api_check` when refreshing a page); makes `/wiki-lint` materially more useful at staleness detection.

**Cons:** zero benefit on day 1 (every seed page would carry the same date). Only kicks in 60-90 days post-PR-2. Reviewing inline markers in PR 2 would inflate the diff. Separation of concerns argues for "extract content first, annotate later."

**Context:** borrowed from [eugeniughelbur/obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) per [research artifact 2026-05-08](file:///Users/manuellindo/.gstack/projects/dacostalindo-House4House/obsidian-second-brain-research-20260508.md), top-5 borrow #5. Their case was stronger because they're an AI-first personal-knowledge vault (free-form claims that age fast). Ours is a technical-infrastructure wiki anchored to code in the same repo — stale claims can be re-derived by reading the code, so the urgency is lower.

**Depends on:** PR 2 seed content lands; ~60-90 days of `/wiki-lint` cron runs to confirm staleness becomes a real concern.

**Estimated effort when actioned:** ~1 day to walk all `wiki/sources/<name>.md` pages, add `last_api_check` frontmatter + inline `(as of ..., url)` to each claim against an upstream source, update `wiki/CLAUDE.md` schema to document the convention.

---

## obsidian-second-brain borrows — distributed into PRs (TODO closed)

**Status:** the four cherry-picked patterns from [eugeniughelbur/obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) (per [research artifact 2026-05-08](file:///Users/manuellindo/.gstack/projects/dacostalindo-House4House/obsidian-second-brain-research-20260508.md)) have been folded into specific PRs in the design doc. Tracking pointers below — no further TODO action needed; each lands when its PR/Phase is built.

| Borrow | Lands in | Where in design doc |
|---|---|---|
| #1 Reconcile pattern → `/wiki-reconcile` skill + reconcile-on-merge workflow | Phase 7d (skill); PR 3+ workflow note | Phase 7 section + implementation plan PR 3+ section |
| #2 `vault_health.py` programmatic wiki health check | Phase 4d | Phase 4 CI/CD section |
| #3 Parallel-subagent orchestration in skills | Phase 7 cross-skill conventions | Phase 7 cross-skill conventions section |
| #4 ADR frontmatter shape on decision records | PR 2 seed | Phase 3e seed-sources section |
| #5 Recency markers on source pages | DEFERRED — separate TODO above | TODO entry above this one |
| #6 `/research-deep` 4-phase pipeline (Anthropic-only port) | DEFERRED — Phase 7+ trigger-gated | TODO entry below ("`/research-deep` skill") |
| #7 `## For future Claude` preamble (from `references/ai-first-rules.md`) | PR 2 schema amendment | Phase 3e "Schema amendments before PR 2 ships" |
| #8 `confidence: high \| medium \| speculation` on `wiki/decisions/` ADRs (rule #7 in `references/ai-first-rules.md`) | PR 2 schema amendment | Phase 3e "Schema amendments before PR 2 ships" |
| #9 `llms.txt` at repo root | Phase 4d | Phase 4 CI/CD section |
| #10 `wiki/raw/` immutable-clipping pattern (from `references/vault-schema.md`) | DEFERRED — trigger-gated | TODO entry below ("`wiki/raw/` immutable-clipping directory") |
| #11 Cross-links are mandatory, Obsidian-style `[[wikilinks]]` (from `references/ai-first-rules.md` rule #6; user chose Obsidian as primary reader 2026-05-08) | PR 2 schema amendment + Phase 4e BLOCKING CI rule | wiki/CLAUDE.md "Cross-links are mandatory" subsection + Phase 4e wiki_health.py |
| #12 Write rules triad (Search-before-write + Update-not-duplicate + Propagation; from `references/write-rules.md`) | Phase 4 schema amendment | wiki/CLAUDE.md "Write rules" subsection (locked 2026-05-11) |

**PostCompact hook pattern** (their `obsidian-bg-agent.sh`) is NOT being borrowed today — captured here as a future note: their hook fires after Claude compacts session context to propagate session learnings to vault automatically. Could complement our weekly cron with per-session wiki updates. Revisit only if our manual + cron model produces stale pages between cron runs.

---

## `scripts/wiki_health.py` mechanical linter — DEFERRED to Phase 7 (NEW 2026-05-12)

**What:** the original Phase 4 plan included `scripts/wiki_health.py` (~400 lines) enforcing the `wiki/CLAUDE.md` schema as a BLOCKING CI rule. Implementation started, then was annulled during the Phase 4 PR. The work moves to Phase 7 where it co-locates with the structured-schema-first refactor and the `/wiki-reconcile` + `/wiki-import-gstack` skills that also need schema knowledge.

**Why deferred to Phase 7:**

1. **Single source of truth concern.** `wiki_health.py` as drafted would have re-implemented rules already stated in `wiki/CLAUDE.md` prose (frontmatter enums, required sections, `[[wikilinks]]` resolution algorithm). Two parallel sources of truth drift. The right fix is to extract machine-parseable rules into `wiki/_schema.yaml` (or equivalent structured format) that both the human-readable schema doc and the linter read from. That refactor is Phase 7-shaped.

2. **Co-design with Phase 7 skills.** `/wiki-reconcile` and `/wiki-import-gstack` (Phase 7d + 7e) also need to know the schema. Designing the structured schema once and landing three consumers (linter + reconcile + import) against it is one coherent design pass instead of "ship linter against prose-as-truth in Phase 4, refactor when Phase 7 lands."

3. **No regression in safety.** The weekly `/wiki-lint` LLM cron (Phase 3e, already shipped) continues to catch contradictions, stale claims, and orphans semantically. The mechanical layer is the missing piece, not the only layer.

**What Phase 7 absorbs (from the original Phase 4 plan):**

- `wiki/_schema.yaml` (NEW) — structured schema, single source of truth
- `scripts/wiki_health.py` or `.claude/scripts/wiki_health.py` — reads `_schema.yaml`, enforces full rule set (frontmatter per type, preamble, `[[wikilinks]]` resolution incl. directory-refs + placeholder allowlist + schema-doc self-exclusion, supersedes reciprocity, sprint Status-update-history)
- `tests/test_wiki_health.py` — per-check unit tests + integration + clean-wiki regression guard, `--wiki-root` injectable for `tmp_path` fixtures
- `Makefile` `wiki-lint-fast` target
- `.pre-commit-config.yaml` `wiki-health` local hook
- `.github/workflows/ci.yml` `wiki_health` step with `[wiki-health]` annotation tag
- `pyproject.toml` dev-group `pyyaml>=6` explicit addition (defensive against transitive churn — currently reachable via `airflow → apispec[yaml]`)
- `tests/test_wiki_schema_consistency.py` — drift-sentinel test asserting known rule strings in `wiki/CLAUDE.md` match `_schema.yaml`

**Implementation notes from the Phase 4 prototype** (the partial-implementation surfaced these conventions that the schema doc should formalize before the linter enforces them):

- `wiki/CLAUDE.md` self-exclusion clause needed — schema doc contains illustrative `[[wikilinks]]` examples (e.g., `[[name]]`, `[[YYYY-MM-DD-topic]]`) that aren't real refs.
- Documentation-placeholder allowlist needed — tokens `[[wikilinks]]`, `[[wikilink]]`, `[[name]]`, `[[topic]]`, `[[slug]]`, `[[YYYY-MM-DD-topic]]`, `[[subdir/name]]` used in prose as generic syntax placeholders, not real targets.
- Directory-reference syntax needed — `[[wiki/sources/]]` (trailing slash) is a directory pointer; resolver should validate the directory exists rather than expecting a page.
- Inline-code skip — `` `[[wikilinks]]` `` (inside single-backtick code spans) is a documentation reference, not a real link. Inline-code-stripping logic was prototyped and works.
- Sprint Status-history regex — should accept ISO date (`YYYY-MM-DD`), quarterly (`YYYY-Q1`-`YYYY-Q4`), and month-precision (`YYYY-MM`) entries. Prototype used `^- \d{4}[-Q]\S*:\s+\S.*$` and worked against real wiki content.

**Real wiki drift surfaced during the Phase 4 prototype run** (fixed during Phase 4 PR, kept fixed regardless of when the linter lands):

- `wiki/concepts/medallion-layering.md:84` referenced `[[staging-yaml-conventions]]` — page doesn't exist (was a forward-placeholder).
- `wiki/sprints/sprint-dev-tooling.md:49` referenced `[[dev-tooling-design]]` — page was deleted in PR 3.
- `wiki/use-cases/UC-1.md:120` referenced `[[2026-05-08-streamlit-keplergl-not-superset]]` — wrong date AND wrong name; correct ADR is `[[2026-05-10-metabase-streamlit-not-superset]]`.

These three real bugs were caught by the prototype linter before it was annulled. The catch validates that the linter approach works — just needs a clean architecture (structured schema) before it ships permanently.

**Status:** annulled 2026-05-12 (the script + pyyaml dev-dep). Re-instates in Phase 7 with structured-schema-first design. No further TODO action; tracked here for Phase 7 implementation.

---

## `/research-deep` skill — Phase 7+ candidate (Anthropic-API-only path) (NEW 2026-05-08)

**What:** port the obsidian-second-brain `/research-deep` 4-phase pipeline (vault scan → gap analysis → gap-fill → delta synthesis) as a House4House skill at `.claude/skills/research-deep/SKILL.md`, but **without the Perplexity + Grok external API dependencies**. Run the whole pipeline on the existing Claude Code subscription using Claude Code's native `WebSearch` + `WebFetch` tools for the gap-fill phase.

**Why we chose this over the original obsidian implementation:**

- The original calls Perplexity sonar-pro / sonar-deep-research and Grok+Live Search; ~$0.20-0.80 per run, plus separate API keys to manage.
- Anthropic-only path: same skill structure, but each phase runs as Claude reasoning + Claude Code tool calls. Gap analysis = Claude reads `wiki/index.md` + greps the wiki for the topic, then proposes 3-5 targeted queries. Gap-fill = Claude runs each query via `WebSearch`, fetches the top results via `WebFetch`. Synthesis = Claude in the same session writes the delta. No external API keys, no per-run dollar cost — the cost is subscription rate-limit usage, which is a budget the user already pays for and visibly tracks.
- Trade-off: Anthropic web search isn't quite as deep as Perplexity sonar-deep-research. For most House4House research workflows (regulatory API changes, dependency upgrade risks, OGC spec details), this is good enough. If we later hit a topic where the depth gap actually bites, we can layer Perplexity in as an optional second pass.

**Trigger condition (do not build until met):** the user repeatedly hits the same research topic 2-3+ times because informal Claude conversation can't compress the answer (i.e., Claude re-derives from web every session, no compounding). Examples that would qualify: "what's actually changed in OGC API Features 1.1?", "Airflow 2 → 3 migration risk in the wild", "Cosmos 1.6 vs 1.7 actual breakage list". One-off curiosity does NOT qualify.

**Gating dependencies:**
- PR 2 must have landed (~30 wiki pages) so the vault-scan phase has a real baseline. Running gap-analysis against an empty wiki produces "all gaps" which is useless.
- Ideally PR 3+ has populated `wiki/plan/` so the topic taxonomy is settled — gap-fill respects existing `wiki/concepts/` and `wiki/sources/` rather than creating duplicates.

**Implementation sketch (Phase 7+):**
1. `wiki-scan` agent: Read `wiki/index.md`, grep wiki/ for topic keywords, return baseline page list.
2. `gap-analyze` agent: Given baseline + topic, propose 3-5 web queries that would close the gap.
3. `gap-fill` agents (parallel, one per query): each runs `WebSearch <query>` + `WebFetch <top-3-urls>`, returns extracted facts + sources.
4. `synthesize` step: main thread merges all agent outputs, writes a delta report to `wiki/research/YYYY-MM-DD-<slug>.md` (new directory, parallel to `wiki/lint-reports/`), proposes updates to existing wiki/sources/ + wiki/concepts/ pages, and offers to apply them via the standard manual ingest flow.
5. Honors the multi-agent error reporting convention (Phase 7 cross-skill conventions, devex-review G3): each subagent prefixes output with `[<agent>]`, the main thread prints a per-agent summary, partial successes commit by default.

**Does NOT need:** Perplexity API key, Grok API key, X-discourse search (the obsidian original tags some queries as `x` for Twitter discourse — irrelevant for our regulatory-data domain).

**Cost:** $0 incremental (covered by Claude Code subscription). Per-run uses ~5-10 web searches + several reads — comparable to a verbose investigate session.

**Acceptance gate (when built):** invoke `/research-deep "OGC API Features schema evolution 2024-2026"` against the post-PR 2 wiki; produces a delta report at `wiki/research/<date>-ogc-api-evolution.md` that (a) cites specific URLs, (b) flags at least one drift between current `wiki/sources/srup-ogc.md` claims and upstream spec, (c) proposes targeted page updates rather than full rewrites.

**Status:** captured 2026-05-08 (during Phase 3 PR 1 DX-review closeout). User explicitly chose Anthropic-API-only path. Defer to post-PR 2 + post-PR 3 minimum; concretely build only when the trigger condition above is hit.

---

## `wiki/raw/` immutable-clipping directory (deferred, trigger-gated, NEW 2026-05-08)

**What:** add a `wiki/raw/` directory pattern borrowed from [obsidian-second-brain/references/vault-schema.md](https://github.com/eugeniughelbur/obsidian-second-brain/blob/main/references/vault-schema.md). Holds immutable original artifacts (regulator press releases as `.html`, source-API spec PDFs, scraped HAR files, Excel datasheets exported by INE/eurostat, screenshots from a portal's "what changed in 2026" page) that the wiki layer derives summaries from. Pattern: `wiki/raw/` is read-only — Claude may read it but never overwrite or rewrite. The corresponding `wiki/sources/<name>.md` page summarizes what's in `raw/` and links to the original artifact for verification.

**Why we don't need it today:** PR 2's seed pages derive entirely from in-repo artifacts (docstrings, design doc, git log, prior commits). No external clippings yet. The orphan `scripts/smiga.cm-aveiro.pt.har` is a counter-example — it's already a captured external artifact sitting in the wrong place, but it's a one-off and doesn't justify a new directory pattern by itself.

**Trigger condition (do not build until met):** the user needs to preserve a non-trivial external artifact for re-verification later — typically a regulator's API spec PDF that we want to diff against next year, or a portal's "deprecated endpoints" announcement we want to cite verbatim in `wiki/decisions/`. When the second such artifact accumulates (proving it's a recurring need, not one-off), establish `wiki/raw/<source-slug>/<date>-<artifact-name>` as the canonical location and migrate any stragglers (the HAR file, etc.) into it.

**When triggered, also do:**
- Add `wiki/raw/` to `wiki/CLAUDE.md` schema with the read-only convention spelled out.
- Update `scripts/wiki_health.py` (Phase 4e) to skip `wiki/raw/` for schema checks (different rules apply — original artifacts don't get a "For future Claude" preamble, frontmatter, etc.).
- Update `/wiki-lint` skill prompt to note that `wiki/raw/` orphan-detection runs differently (raw files are deliberately not linked from `index.md`; only the corresponding `wiki/sources/<name>.md` summary needs an inbound link).
- Decide on storage: `wiki/raw/` committed to git for small text artifacts (HTML pages, JSON dumps); large binaries (PDFs over a few MB, screenshots) go to MinIO via a `raw_artifacts/` bucket and `wiki/raw/<source>/<date>-<name>.md` becomes a small pointer page with the MinIO URL + sha256.

**Status:** captured 2026-05-08 (during Phase 3 PR 1 DX-review closeout, obsidian-second-brain `references/` review). Defer indefinitely; build only when the second non-trivial external artifact accumulates.

---

## Live contradiction-detection integration test (deferred from Phase 3 PR 1)

**What:** re-enable `tests/test_wiki_lint_skill.py::test_skill_detects_intentional_contradiction` once PR 2 has landed real wiki content. The `with-contradiction/` fixture exists; the test is currently `@pytest.mark.skip`'d because the `WIKI_PATH` env-var override in SKILL.md isn't reliably honored by claude in headless mode — it falls back to the real wiki via `git rev-parse --show-toplevel`.

**Why:** live integration testing of contradiction detection is the strongest validation that the lint mechanism works on real-world cases. Phase 3 PR 1 verified the skill works end-to-end (clean run produces a coherent report) but didn't verify it catches actual contradictions.

**Pros:** restores the eng-review T1 acceptance gate's third test.

**Cons:** requires either a different override mechanism (e.g., a `--wiki-path` argument to the skill, or a wrapper script) or accepting that the test runs against real wiki content.

**Context:** discovered during Phase 3 PR 1 implementation on 2026-05-08. The fixture is at `tests/wiki-fixtures/with-contradiction/` and is fully usable. Two paths forward: (a) add a real arg-parsing mechanism in SKILL.md, or (b) test by temporarily symlinking `wiki/` → fixture before the test (cleanup in finally).

**Depends on:** PR 2 landing real wiki content + a robust override mechanism for SKILL.md.

---

## Phase 2.5 — closed (no work to do)

**Status:** absorbed by Phase 2 on 2026-05-08.

The eng-review's "267 inline validators" estimate was a bad-grep artifact. The audit on 2026-05-08 found **zero Pydantic-eligible input-validation sites** in `pipelines/`. The 90 `raise/assert` statements that exist are all control flow, error handling, or external-data shape guards — exactly what the bronze-permissive rule keeps out of Pydantic. Phase 2's typed configs already cover the surface that mattered.

## Consolidate bronze-count anomaly checks into a data-quality helper

**What:** the 15 scattered `if listings_current < N or listings_current > M: alert/raise` patterns across portal DAGs (`remax_dlt_dag.py`, `zome_dlt_dag.py`, etc.) move into either a small Python helper (`pipelines/common/bronze_quality.py` with `assert_bronze_count_in_range(...)`) or dbt singular tests on the bronze tables.

**Why:** the checks are real signal (catches "scrape silently broke and only got 50 listings instead of 5,000"), but the implementation is copy-pasted with slightly different bounds in each DAG. Consolidating gives one place to tune thresholds and one place to find the alert logic.

**Pros:** DRY, easier to review and tune thresholds, opens the door to per-source baseline tracking. Plays naturally with the dbt singular-test pattern (one SQL test per bronze table with hardcoded bounds).

**Cons:** moving the checks out of the DAG hides them from the task-level airflow logs slightly. Mitigated by having the helper raise with a clear error string.

**Context:** discovered during the Phase 2.5 audit (2026-05-08). The 15 sites are exclusively bronze-volume guards — they assert the scrape returned a sane number of rows. Listed sites: see `pipelines/portals/remax/remax_dlt_dag.py:231-248`, `pipelines/portals/zome/zome_dlt_dag.py:258`, plus a few more across portals.

**Depends on:** nothing blocking. Pure refactor. Can also be deferred until the dbt staging tests for portal bronze tables get fleshed out, since dbt singular tests are arguably the better home for these.

---

## Post-autofix idealista verification (Phase 1 final gate)

**What:** trigger `idealista_ingestion_dag` once on the merged main with the autofix sweep applied. Verify the DAG completes green and bronze row counts grow within the same drift envelope as the pre-merge smoke (Δ ~3 developments / ~35 units per run).

**Why:** the eng-review's T1 acceptance gate specified post-autofix idealista smoke before considering Phase 1 fully landed. The pre-merge smoke (commit 8a1646e) covered the .uv migration but predates the ruff autofix (340751b). Closes the gate.

**Context:** ran the dual-stack pre-merge smoke on 2026-05-06 with clean parity. Autofix touched 70 tracked files including some pipeline modules (excluding the 3 with prior WIP). Mechanical fixes only (no UP032 f-string-rewrite landmines triggered, RUF unsafe fixes not enabled), so risk is low — but T1 was explicit about post-autofix verification.

**Depends on:** PR #N merged to main.

---


## Pydantic AI for image_classification_dag.py

**What:** wrap the LLM calls in [pipelines/portals/idealista/image_classification_dag.py](pipelines/portals/idealista/image_classification_dag.py) with Pydantic AI for typed outputs (replacing whatever ad-hoc string parsing currently lives there).

**Why:** typed schema for image-tag silver columns; consistent with the Pydantic AI pattern landed for description enrichment in Phase 5 of the dev-tooling design.

**Context:** Phase 5 of the 2026-05-05 dev-tooling design lands Pydantic AI for *description* enrichment. Image classification is the natural next surface — same shape (LLM input → typed Pydantic output → dlt → silver), different content. Hold until Phase 5 ships and the pattern is exercised once in production.

**Depends on:** Phase 5 of `manuellindo-main-design-20260505-120707.md` (Idealista description enrichment).

---

## Graduate `ty` from advisory to gating CI step

**What:** flip the `continue-on-error: true` flag off in the GitHub Actions workflow added in Phase 4, making `ty check` a hard gate on PRs.

**Why:** type errors should block PRs once tooling is mature, same as `ruff check`. Today ty is in preview and noisy enough that gating would cause more friction than it saves.

**Context:** Phase 6 of the 2026-05-05 dev-tooling design lands ty as advisory. Trigger to graduate is external — Astral declaring ty stable. No deadline. Watch the Astral blog and ty changelog.

**Depends on:** Astral marking ty stable (external trigger, no internal blocker).
