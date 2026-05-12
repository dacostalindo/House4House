# Wiki Schema for Claude Code

## For future Claude

This is the **schema document** for the House4House wiki. It defines the page conventions (filename rules, required frontmatter, required sections per page type), the ingest workflow (how new sources enter the wiki), the query workflow (how Claude answers using the wiki), and the lint workflow (how the weekly `/wiki-lint` LLM cron + the on-demand `/wiki-reconcile` skill check the wiki for drift). Read this file at the start of any session that touches `wiki/`.

This file is the **schema layer** for the House4House wiki — the configuration that makes Claude a disciplined wiki maintainer rather than a generic chatbot. It defines page conventions, ingest workflow, query workflow, and lint workflow.

You and Claude co-evolve this document over time as conventions firm up. **Read this file at the start of any session that touches `wiki/`.**

## Wiki structure

```
wiki/
├── README.md              orientation for human readers
├── CLAUDE.md              this file — schema for Claude
├── index.md               content-oriented catalog (every page + 1-line summary)
├── log.md                 chronological append-only log of ingest/query/lint events
├── sources/               one page per data source
├── concepts/              architectural patterns + cross-cutting rules
├── pipelines/             one page per ingestion pipeline
├── decisions/             dated decision records (lighter-weight ADRs)
├── plan/                  strategic roadmap decomposed from root README
└── lint-reports/          output of the weekly /wiki-lint cron
```

## Page conventions

### File naming

- Lowercase kebab-case: `pydantic-not-in-dlt.md`, `srup-ogc.md`.
- Decision records use date prefix: `2026-05-08-uv-workspace-shape.md`.
- Sprint pages use zero-padded number: `sprint-04.md` (consistent sort order).

### YAML frontmatter

All wiki pages start with YAML frontmatter:

```yaml
---
title: <human-readable title>
type: source | concept | pipeline | decision | plan
last_verified: 2026-05-08      # date this page was last cross-checked against reality
tags: [tag1, tag2]
---
```

Sprint pages additionally carry:

```yaml
status: done | mostly_done | in_progress | planned | deferred
sprint_number: <int>
weeks: "<n>-<m>"
last_status_update: <date>
```

Source pages additionally carry (locked 2026-05-08 in PR 5):

```yaml
priority: P0 | P1 | P2
```

`P0` = foundation, must load first (dim_geography backbone, primary listing portal, statistical-API foundation). `P1` = use-case-enabling (secondary portals, regulatory layers, terrain). `P2` = specialty / Aveiro-specific / coverage-narrowed (e.g. APA's EU-Floods-Directive scope, LNEG's 1:500k geology, the aveiro-pmot one-off extractor). Every new source page MUST declare a priority on creation; absence will be a `wiki_health.py` BLOCKING finding once Phase 7 ships the mechanical linter (per [[2026-05-12-wiki-linter-deferred-to-phase-7]]). Until then, the rule is human/Claude discipline + LLM cron. Tier ordering drives load sequencing for cold bootstrap and prioritization in [[sprint-04.5]] and beyond.

Decision records additionally carry (per obsidian-second-brain `references/ai-first-rules.md` borrow #8, locked 2026-05-08):

```yaml
confidence: high | medium | speculation
supersedes: <old-record-filename>      # only when this ADR obsoletes an older one
superseded_by: <new-record-filename>   # only when this ADR has been obsoleted
```

The `confidence:` field is required on every decision record. `high` = battle-tested in a Phase spike or production run; `medium` = picked deliberately but not yet stress-tested; `speculation` = best-guess at decision time, expected to be revisited. Tells a future Claude session how much to trust an old ADR before proposing changes. Scoped to decisions/ only — sources/concepts/pipelines have their confidence implicit in the underlying code.

### Cross-links are mandatory (per obsidian-second-brain `references/ai-first-rules.md` borrow #11, locked 2026-05-08)

Every wiki page MUST link to every other wiki page it references on first mention, using **Obsidian-style `[[wikilinks]]`**. The wiki is browsed by humans in Obsidian (graph view, backlinks panel, autocomplete on `[[`) and edited by Claude Code via file reads. Both modes work: Obsidian renders `[[wikilinks]]` as first-class clickable links with graph traversal; Claude (the LLM) reads them as text and resolves them to file paths via the rule below.

**Resolution rule** (Claude follows this when resolving `[[name]]` during reads/grep/ingest):

- `[[name]]` resolves to the first match found across `wiki/concepts/<name>.md`, `wiki/sources/<name>.md`, `wiki/decisions/<name>.md`, `wiki/pipelines/<name>.md` — basename match (case-insensitive, ignoring `.md` extension).
- For ambiguous names (e.g., a concept and a source with the same slug), use an explicit subdir prefix: `[[concepts/scd2-row-hash]]` or `[[sources/srup]]`.
- For human-readable label override: `[[scd2-row-hash|the row-hash dedup pattern]]` — Obsidian renders "the row-hash dedup pattern" as the link text; the link still targets `scd2-row-hash`.
- Decision records: link by full filename including date prefix — `[[2026-05-05-cosmos-pin]]`, NOT `[[cosmos-pin]]`.

**Apply on first mention** of any:

- concept that has its own `wiki/concepts/<name>.md` page → `[[name]]`
- source that has its own `wiki/sources/<name>.md` page → `[[name]]`
- decision record → `[[YYYY-MM-DD-topic]]`
- pipeline that has its own `wiki/pipelines/<name>.md` page → `[[name]]`

Subsequent mentions on the same page do not need to repeat the link (avoids link soup; matches markdown convention).

**Caveat for Claude Code IDE preview:** Claude Code's built-in VSCode markdown preview does NOT natively render `[[wikilinks]]` as clickable links (they appear as literal text). This affects only the IDE preview UX during editing — Claude (the LLM) still reads + resolves them correctly via the rule above, and Obsidian renders them perfectly. If you want clickable in the IDE preview, install an Obsidian-compatible VSCode extension (e.g., "Foam" or "Markdown Memo"). Not a blocker.

**Why mandatory, not advisory:** the wiki's value compounds with its graph density. A future Claude session (or human in Obsidian) reading `wiki/sources/idealista.md` and seeing "SCD2 + ZenRows two-pass" should get one-click access to `[[scd2-row-hash]]` and `[[zenrows-universal-vs-re-api]]`. That's the difference between a flat collection of pages and a traversable knowledge graph. Obsidian's graph view becomes meaningful; backlinks tell you which pages cite a given concept.

**Lint enforcement:** two complementary skills.

- **Semantic check** — the weekly `/wiki-lint` LLM cron (Phase 3e, Sundays 06:00 via launchd) catches contradictions, synonym variants, stale claims, and orphan pages (low inbound-link count). Advisory-only; writes a timestamped report under `wiki/lint-reports/` and one log line.
- **Structural check + interactive resolution + post-merge ingest** — the on-demand `/wiki-reconcile` skill (Phase 7b, shipped 2026-05-12). Spawns parallel subagents to scan frontmatter compliance, `## For future Claude` preambles, required sections per page type, `[[wikilinks]]` resolution (skip inline-code spans, support `[[dir/name]]` prefix), supersedes reciprocity, sprint Status-update-history regex, and basename ambiguity. Walks the user through resolution per finding. Also handles post-merge gstack-artifact ingest — proposes ADR drafts from `~/.gstack/projects/<slug>/` design + review artifacts (folds in the prior `/wiki-import-gstack` plan). See [[2026-05-12-wiki-linter-deferred-to-phase-7]] for the architectural reasoning (structured-schema dropped; rules live in this prose doc + the skill's subagent prompts).

**Mid-PR caveat:** during iterative commits within a single PR (e.g., PR 2 commits sources/ in commit 2, concepts/ in commit 3), forward `[[wikilinks]]` from sources/ to not-yet-created concepts/ pages will appear "broken" in the intermediate state. Lint runs against the merged final state, so the BLOCKING check fires only when a fully merged wiki has missing cross-refs — but if you run `make wiki-lint-fast` against a partial commit during authoring, expect false-positive findings until the rest of the PR's commits land.

### `## For future Claude` preamble (required on every page)

Per obsidian-second-brain `references/ai-first-rules.md` borrow #7 (locked 2026-05-08), every wiki page begins with a 2-3 sentence preamble in plain English, immediately after the frontmatter (or after the page title for structural files without frontmatter), before any other section:

```markdown
## For future Claude

This note is a [type] about [topic]. It [main purpose]. [Optional caveat about staleness, confidence, or scope.]
```

The preamble lets a future Claude Code session judge a page's relevance in ~10 seconds before parsing the full content. The schema-header routing in the CLAUDE.md hierarchy directs Claude to specific wiki pages on every edit; the preamble shaves the per-page-load cost when the routing was a near-miss rather than a direct hit.

**Typed-content pages** (`source` / `concept` / `pipeline` / `decision` / `plan` types) follow the canonical shape above. **Structural files** (`README.md`, `CLAUDE.md`, `index.md`, `log.md`, `plan/README.md`) carry the same `## For future Claude` heading but the body describes the file's role in the wiki ("This is the catalog Claude reads first…", "This is the schema document…") rather than a typed [type]/[topic]. Same purpose, slightly different shape.

### Required sections per page type

**Source page** (`sources/<name>.md`):
- `## Source` — what it is, official name, owner, license
- `## Schema` — fields produced, key types
- `## Quirks` — known gotchas, rate limits, drift patterns
- `## Last verified`

**Concept page** (`concepts/<name>.md`):
- `## What it is`
- `## Why` — motivation, what breaks without it
- `## How` — concrete pattern in code
- `## See also` — cross-links to related concepts/sources/decisions

**Decision record** (`decisions/<date>-<topic>.md`):
- `## Decision` — one-paragraph summary
- `## Why` — context, alternatives considered
- `## Consequences` — what changes downstream
- `## Status` — accepted | superseded | deprecated

**Pipeline page** (`pipelines/<name>.md`):
- `## What it does`
- `## Sources used` — links to `sources/*`
- `## Schedule + triggers`
- `## Bronze tables produced`

**Plan page**: see `wiki/plan/README.md` for sub-section conventions (use cases, sprints, etc.).

## Workflows

### Ingest workflow

A new source/decision/concept enters the wiki via either path:

- **Free-form**: user says "ingest raw/article.md" or pastes a URL or paste content directly. Claude reads it and follows the steps below.
- **Skill-routed**: `/wiki-ingest <path-or-url>` — Phase 7 skill, codified after the manual workflow has been done 3-5 times. Same operations, reproducible.

Steps Claude takes on every ingest:

1. **Read** the source artifact.
2. **Find relevant pages**: read `index.md` first to scan available pages, then `grep` the wiki for keyword overlap with the new source. **Do NOT read all wiki pages on every ingest** — the targeted set from index + grep is sufficient.
3. **Write/update** the relevant page(s). A single source might touch 5-15 pages (e.g., a new data source: sources/<name>.md + concepts/medallion-layering.md + decisions/<date>-<source>-onboarded.md).
4. **Update** `index.md` — add new entries, fix summaries that no longer match content.
5. **Append** one entry to `log.md` in the format: `## [YYYY-MM-DD] ingest | <title>`.
6. **Surface** to the user: a one-line summary of what changed and which pages were touched.

### Query workflow

When the user asks a question that touches accumulated knowledge:

1. **Read** `index.md` first to find candidate pages.
2. **Drill into** the relevant pages.
3. **Synthesize** the answer with citations (link to the wiki pages that informed the answer).
4. **Offer to file** the answer back into the wiki if it produced novel synthesis worth keeping. Format: a new page under `concepts/` or `decisions/`, OR an addition to an existing page.

### Lint workflow

A weekly `launchd` cron fires `claude -p /wiki-lint --max-turns 5` Sundays at 06:00 local time. The skill is at `.claude/skills/wiki-lint/SKILL.md`.

Lint surface:
- **Contradictions** between pages (semantic match, e.g., page A says "SCD2 dedups by row_hash", page B says "by primary key").
- **Stale claims**: pages whose `last_verified` is older than 90 days.
- **Orphan pages**: no inbound links from `index.md` or other wiki pages.
- **Concepts mentioned but lacking own page**: a term keeps appearing in 3+ pages without its own `concepts/<term>.md`.
- **Missing cross-references / unresolved `[[wikilinks]]`**: a page mentions a canonical name (e.g., "SCD2") without an `[[scd2-row-hash]]` link OR has an `[[wikilink]]` that doesn't resolve to any wiki page. Per the cross-links-are-mandatory rule (above), the weekly LLM lint catches both — including synonym/paraphrase variants. Phase 7 adds the mechanical `wiki_health.py` companion that treats these as BLOCKING findings in CI (per [[2026-05-12-wiki-linter-deferred-to-phase-7]]).
- **`index.md` drift**: index summaries that no longer match the page content.

Output:
- A timestamped report at `wiki/lint-reports/YYYY-MM-DD-HHMMSS.md`.
- One summary line appended to `wiki/log.md`.
- The `Last lint run: YYYY-MM-DD` line at the top of `wiki/index.md` is updated.

Failure mode: lint findings are advisory. The skill never errors loudly; if a Sunday cron is missed (Mac off), `Last lint run:` shows staleness as the signal.

## Write rules

Per obsidian-second-brain [`references/write-rules.md`](https://github.com/eugeniughelbur/obsidian-second-brain/blob/main/references/write-rules.md) borrow (locked 2026-05-11). Three rules form a complete write-discipline triad — proactive check + corrective check + followup. They apply to every write into `wiki/` regardless of trigger (manual edits, `/wiki-ingest`, ADR drafts, sprint creation, `/wiki-import-gstack` invocations in Phase 7+).

### 1. Search before write (proactive)

Before creating a new wiki page or adding a substantive new claim to an existing page, **search the wiki first**. Cheapest version: read `wiki/index.md` (the catalog) + run `grep -ri "<topic>" wiki/`.

- Before creating a new `wiki/sources/<name>.md`: `grep -ri "<source-name>" wiki/` — catches name-variant collisions (`srup_ogc` vs `srup-ogc`) AND catches the case where another page already documents this source under a different filename.
- Before creating a new `wiki/concepts/<name>.md`: scan `wiki/index.md` Concepts section + `grep -ri "<concept-keyword>" wiki/concepts/` — catches cases where the pattern is already documented under a different name (e.g., considering writing `concepts/dlt-schema-contract.md` when `concepts/bronze-permissive.md` already covers it).
- Before adding a fact to an existing page: scan the page for prior statements on the same topic that might already cover, contradict, or need updating instead.

The ingest workflow (step 2 above: "read `index.md` first... then grep the wiki for keyword overlap") already mandates this for ingest. This rule extends the same discipline to ALL writes.

### 2. Update-not-duplicate (corrective)

When the search above finds an existing page on the same topic, **UPDATE it**; don't create a parallel `<name>-v2.md` or a near-synonym file. The basename-ambiguity check in the future `wiki_health.py` (Phase 7) will enforce this mechanically — two files sharing a basename across `wiki/{concepts,sources,decisions,pipelines}/` produces a BLOCKING `[[wikilinks]]` ambiguity finding. Until Phase 7 lands, the rule is human/Claude discipline.

The rule also extends to near-synonyms (`scd2-row-hash.md` and `row-hash-dedup.md` are NOT a basename collision but ARE a violation of this rule).

### 3. The Propagation Rule (followup)

**Never create a note in isolation.** Every write to the wiki has ripple effects. AFTER the search-and-update steps above, trace forward and ask: what other pages need to know about this?

- New `wiki/sources/<name>.md` → add to `wiki/index.md` Sources section; cross-link from any `wiki/concepts/` page that mentions this source's domain; if the source crosses a P0/P1/P2 boundary, update `wiki/planning/resources.md` data-volume table.
- New `wiki/concepts/<name>.md` → add to `wiki/index.md` Concepts section; add to per-area `CLAUDE.md` task→concept routing where relevant; cross-link from `wiki/overview.md` if it's a load-bearing rule.
- New `wiki/decisions/<date>-<topic>.md` → add to `wiki/index.md` Decisions section under the right group (Foundational / Stack / Spatial / etc.); if it supersedes an old ADR, flip the old ADR's `status: superseded` + `superseded_by:` per the existing convention.
- New sprint page → update `wiki/sprints/README.md` + `wiki/planning/milestones.md` if it gates a milestone.
- Always append a one-line entry to `wiki/log.md` describing what changed.

## No-content-duplication guardrail

Rules and patterns live ONLY in `wiki/concepts/`. The CLAUDE.md hierarchy at the project root + per-area directories are pure pointer indexes — they say "see `wiki/concepts/<topic>.md`" and never duplicate the content. This is the single-source-of-truth guarantee.

When Claude updates a rule, it updates the wiki page. The CLAUDE.md pointers don't drift because they are 1-line stubs.

## Version of this schema

Schema version: 1 (initial — 2026-05-08). When this schema evolves substantively, bump to 2 and document the migration playbook in TODOS.md.
