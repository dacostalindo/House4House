# Wiki Schema for Claude Code

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
- **Missing cross-references**: a page mentions a canonical name (e.g., "SCD2") without linking to its concept page.
- **`index.md` drift**: index summaries that no longer match the page content.

Output:
- A timestamped report at `wiki/lint-reports/YYYY-MM-DD-HHMMSS.md`.
- One summary line appended to `wiki/log.md`.
- The `Last lint run: YYYY-MM-DD` line at the top of `wiki/index.md` is updated.

Failure mode: lint findings are advisory. The skill never errors loudly; if a Sunday cron is missed (Mac off), `Last lint run:` shows staleness as the signal.

## No-content-duplication guardrail

Rules and patterns live ONLY in `wiki/concepts/`. The CLAUDE.md hierarchy at the project root + per-area directories are pure pointer indexes — they say "see `wiki/concepts/<topic>.md`" and never duplicate the content. This is the single-source-of-truth guarantee.

When Claude updates a rule, it updates the wiki page. The CLAUDE.md pointers don't drift because they are 1-line stubs.

## Version of this schema

Schema version: 1 (initial — 2026-05-08). When this schema evolves substantively, bump to 2 and document the migration playbook in TODOS.md.
