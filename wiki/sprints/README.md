# Wiki Sprints

## For future Claude

This is the **orientation page for `wiki/sprints/`**. It explains the sprint-page schema (filename convention, required frontmatter fields, required content sections, status semantics) and the living-roadmap mechanic where each sprint page's `status:` field reflects current project state — not just the README's original snapshot. Read this when adding a new sprint page, updating a sprint's status, or auditing sprint pages for drift against `git log` / `TODOS.md` / the design doc.

This folder holds two parallel tracks:

- **Data-product sprints** (11 pages, `sprint-NN.md` zero-padded): the project's data-warehouse roadmap from [README §12](../../README.md) — Sprint 1 through Sprint 9 plus sub-sprints 4.4 and 4.5. Each ships product features (data sources, silver models, gold analytics, serving-layer apps).
- **Dev-tooling sprint** (1 page, `sprint-dev-tooling.md`): the gstack-driven dev-tooling roadmap covering 7 Phases (uv workspace, Pydantic configs, LLM Wiki, CI/CD, Idealista enrichment via Pydantic AI, ty, Claude Skills). Each Phase ships dev-tooling infrastructure rather than product features.

The two tracks ran in parallel during 2026-Q1/Q2. Frontmatter `sprint_number` distinguishes them (`"1"` through `"9"` and `"4.4"`, `"4.5"` for data-product; `"dev-tooling"` for the gstack sprint).

## Filename convention

- Data-product: zero-padded sprint number — `sprint-01.md`, ..., `sprint-09.md`. Sub-sprints carry the decimal: `sprint-04.4.md`, `sprint-04.5.md`. Lexical sort matches chronological.
- Dev-tooling: `sprint-dev-tooling.md`. Single file consolidating all 7 Phases (per `/plan-eng-review` finding 1.5 — frontmatter status reflects overall trajectory; per-Phase status table in body).

## Required YAML frontmatter

Every sprint page carries:

```yaml
---
title: <human-readable title, including sprint number>
type: plan
last_verified: <YYYY-MM-DD>
tags: [sprint, plan, ...sprint-specific tags]
status: done | mostly_done | in_progress | planned | deferred
sprint_number: "<1, 2, 3, 4, 4.4, 4.5, 5-9, dev-tooling>"
weeks: "<n>-<m>"  # or "parallel" for the dev-tooling sprint
last_status_update: <YYYY-MM-DD>
---
```

**`status` semantics** (locked 2026-05-08):

- `done` — every task in the sprint shipped; exit criteria met. README marker: ✅ COMPLETE.
- `mostly_done` — exit criteria met but a small set of tasks deferred to a later sprint. README marker: ✅ MOSTLY COMPLETE.
- `in_progress` — work is actively happening this week / this sprint window. README marker: 🔄 IN PROGRESS.
- `planned` — declared in the README but no work has started. Default for upcoming sprints.
- `deferred` — was scheduled, then scope-deferred or cancelled. Page documents the deferral rationale.

For the `sprint-dev-tooling.md` page specifically: `status: in_progress` while ANY Phase is in flight or planned. The per-Phase status table in the page body is the source of truth for which specific Phases are done/in_progress/planned.

## Required content sections

Per `wiki/CLAUDE.md` schema (every typed-content page) plus sprint-specific:

1. `## For future Claude` — 2-3 sentence preamble per the cross-cutting wiki rule.
2. `## Goal` — 1-paragraph statement of what the sprint is for and why.
3. `## Deliverables` — bulleted list (or compact table) of the sprint's outputs. Use `✅ Done` / `🔄 In progress` / `Pending` / `Deferred` markers per task.
4. `## Exit criteria` — explicit conditions that mean "this sprint is done."
5. `## Key decisions` — sprint-shaped decisions made during execution (one-liners; deeper architectural decisions become `wiki/decisions/<date>-<topic>.md` ADRs and get linked here).
6. `## Status update history` — append-only log of status transitions. Format: `YYYY-MM-DD: <old_status> → <new_status>` with optional one-line reason in parentheses. Worked example below.
7. `## See also` — cross-links to relevant sources/concepts/decisions in the wiki.

For `sprint-dev-tooling.md` specifically, add an explicit `## Phase status table` between Deliverables and Exit criteria covering all 7 Phases.

## Status update history — convention + worked example

Each transition gets one line:

```
YYYY-MM-DD: <old_status> → <new_status> (optional reason)
```

**Worked example — Sprint 4.4** (the audit found Sprint 4.4 underreported by 12 days):

```markdown
## Status update history

- 2026-04-18: declared in README §12 update; status `planned`
- 2026-04-30: `planned` → `done` (all 5 workstreams shipped per commits `edf4b72`, `210e3e1`, `7cc2bbe`, `a9aae01`)
```

This shows: when the sprint was declared, when it shipped, and what evidence (commit SHAs) supports the status transition. Future Claude reading `sprint-04.4.md` a year from now sees the velocity story without re-running git log.

For dev-tooling sprint transitions, list per-Phase shipping dates (e.g., `2026-05-05: Phase 1 → done (uv workspace + Ruff sweep merged in commit X)`).

Phase 7 `wiki_health.py` will enforce the format via regex `^(\d{4}-\d{2}-\d{2}): (\w+) → (\w+)( \(.*\))?$` — malformed entries are findings. Until then, human/Claude discipline (per [[2026-05-12-wiki-linter-deferred-to-phase-7]]).

## Living-roadmap mechanic

Each sprint page's `status:` field reflects **current project reality**, not the README's original snapshot. When a sprint ships (or partially ships, or gets deferred), the next session updates:

- `status:` field
- `last_status_update:` field
- An entry in `## Status update history` documenting the transition + reason

`/wiki-lint` cross-checks for drift: if a sprint says `status: planned` but `git log --oneline` references work on it, OR `TODOS.md` shows tasks tagged with the sprint number being closed out, OR the design doc's matching section shows progress, the lint flags the drift as a finding.

This makes the wiki a living roadmap, not a frozen snapshot of "the plan as of date X."

## Cross-linking expectations

Every sprint page links via `[[wikilinks]]` to:

- Sources it ingests or transforms (`[[idealista]]`, `[[bgri]]`, `[[caop]]`, etc.)
- Concept pages it depends on (`[[scd2-row-hash]]`, `[[medallion-layering]]`, etc.)
- Decision records it implements or supersedes (`[[2026-05-08-idealista-enrichment-architecture]]`, etc.)
- Adjacent sprint pages (a sprint that builds on / blocks / depends on another sprint links to it)

First mention only per the cross-links-mandatory rule in `wiki/CLAUDE.md`.

## Sprint roster (PR 3 seed, 2026-05-09)

12 sprint pages: 11 data-product + 1 dev-tooling.

| Page | Sprint | Weeks | Status (PR 3 seed, audit-corrected) |
|---|---|---|---|
| [[sprint-01]] | Infrastructure & Geography | 1-2 | `done` |
| [[sprint-02]] | Core Market Data | 3-4 | `done` |
| [[sprint-03]] | Silver Layer: Unification + UC-3 GIS Foundation | 5-6 | `mostly_done` |
| [[sprint-04]] | Image Classification + Location Scores | 7-8 | `in_progress` |
| [[sprint-04.4]] | Pre-Sprint 4.5 Preparation | 8.5 | `done` (audit: shipped 2026-04-30) |
| [[sprint-04.5]] | Listings + Developments: Bronze→Silver→Gold + Cross-Portal Dedup | 9 | `planned` |
| [[sprint-05]] | Hedonic Model & Valuation | 10-11 | `planned` |
| [[sprint-06]] | UC-1 MVP: Investment Opportunities | 12-13 | `planned` |
| [[sprint-07]] | UC-2 MVP: Pricing Strategy | 14-15 | `planned` |
| [[sprint-08]] | UC-3 MVP: Land Development Opportunities | 16-18 | `planned` |
| [[sprint-09]] | Enhancements + Production Hardening | 19-20 | `planned` |
| [[sprint-dev-tooling]] | gstack dev-tooling roadmap (Phases 1-7) | parallel | `in_progress` (Phase 3 in flight; 4-7 planned) |

Three production milestones land along the way for the data-product track: **M1 (UC-1 LIVE)** at Sprint 6, **M2 (UC-2 LIVE)** at Sprint 7, **M3 (UC-3 LIVE)** at Sprint 8.

## See also

- [[overview]] — 1-page project synthesis
- [[sprint-dev-tooling]] — companion track for dev-tooling infrastructure
- [README §12](../../README.md) — canonical source of the original sprint plan (post-Phase-1 cleanup; reflects audit corrections)
