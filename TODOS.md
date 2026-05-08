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

**PostCompact hook pattern** (their `obsidian-bg-agent.sh`) is NOT being borrowed today — captured here as a future note: their hook fires after Claude compacts session context to propagate session learnings to vault automatically. Could complement our weekly cron with per-session wiki updates. Revisit only if our manual + cron model produces stale pages between cron runs.

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
