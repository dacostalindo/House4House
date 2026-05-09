# Wiki Plan — Sprints

## For future Claude

This is the **orientation page for the sprints/ subsection** of `wiki/plan/`. It explains the sprint-page schema (filename convention, required frontmatter fields, required content sections, status semantics) and the living-roadmap mechanic where each sprint page's `status:` field reflects current project state — not just the README's original snapshot. Read this when adding a new sprint page, updating a sprint's status, or auditing sprint pages for drift against `git log` / `TODOS.md` / the design doc.

This subsection breaks down the project's data-product sprint plan from [README §12](../../../README.md). The sprint plan is parallel to (but distinct from) the dev-tooling Phase plan captured in [[dev-tooling-design]] — sprints ship product features (data sources, silver models, gold analytics, serving-layer apps); Phases ship dev-tooling infrastructure (workspace, Pydantic configs, the wiki itself, CI, skills).

## Filename convention

Zero-padded sprint number: `sprint-01.md`, `sprint-02.md`, ..., `sprint-09.md`. Sub-sprints carry the decimal: `sprint-04.4.md`, `sprint-04.5.md`. The pattern keeps lexical sort order matching chronological order.

## Required YAML frontmatter

Every sprint page carries:

```yaml
---
title: <human-readable title, including sprint number>
type: plan
last_verified: <YYYY-MM-DD>
tags: [sprint, plan, ...sprint-specific tags]
status: done | mostly_done | in_progress | planned | deferred
sprint_number: "<number, possibly with decimal as string>"
weeks: "<n>-<m>"
last_status_update: <YYYY-MM-DD>
---
```

`status` semantics (locked 2026-05-08):

- `done` — every task in the sprint shipped; exit criteria met. README marker: ✅ COMPLETE.
- `mostly_done` — the sprint's exit criteria are met but a small set of tasks deferred to a later sprint or marked Pending. README marker: ✅ MOSTLY COMPLETE.
- `in_progress` — work is actively happening this week / this sprint window. README marker: 🔄 IN PROGRESS.
- `planned` — declared in the README but no work has started. Default for upcoming sprints.
- `deferred` — was scheduled, then scope-deferred or cancelled. Page documents the deferral rationale.

## Required content sections

Per `wiki/CLAUDE.md` schema (every typed-content page) plus sprint-specific:

1. `## For future Claude` — 2-3 sentence preamble per the cross-cutting wiki rule.
2. `## Goal` — 1-paragraph statement of what the sprint is for and why.
3. `## Deliverables` — bulleted list (or compact table) of the sprint's outputs. Use `✅ Done` / `🔄 In progress` / `Pending` / `Deferred` markers per task.
4. `## Exit criteria` — explicit conditions that mean "this sprint is done."
5. `## Key decisions` — sprint-shaped decisions made during execution (one-liners; deeper architectural decisions become `wiki/decisions/<date>-<topic>.md` ADRs and get linked here).
6. `## Status update history` — append-only log of status transitions (`2026-04-18: planned → in_progress`, etc.). Lets future Claude see the velocity story without rebuilding it from git log.
7. `## See also` — cross-links to relevant sources/concepts/decisions in the wiki.

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

11 sprints across 20 weeks:

| Page | Sprint | Weeks | Status (PR 3 seed) |
|---|---|---|---|
| [[sprint-01]] | Infrastructure & Geography | 1-2 | `done` |
| [[sprint-02]] | Core Market Data | 3-4 | `done` |
| [[sprint-03]] | Silver Layer: Unification + UC-3 GIS Foundation | 5-6 | `mostly_done` |
| [[sprint-04]] | Image Classification + Location Scores | 7-8 | `in_progress` |
| [[sprint-04.4]] | Pre-Sprint 4.5 Preparation | 8.5 | `planned` |
| [[sprint-04.5]] | Listings + Developments: Bronze→Silver→Gold + Cross-Portal Dedup | 9 | `planned` |
| [[sprint-05]] | Hedonic Model & Valuation | 10-11 | `planned` |
| [[sprint-06]] | UC-1 MVP: Investment Opportunities | 12-13 | `planned` |
| [[sprint-07]] | UC-2 MVP: Pricing Strategy | 14-15 | `planned` |
| [[sprint-08]] | UC-3 MVP: Land Development Opportunities | 16-18 | `planned` |
| [[sprint-09]] | Enhancements + Production Hardening | 19-20 | `planned` |

Three production milestones land along the way: M1 (UC-1 LIVE) at Sprint 6, M2 (UC-2 LIVE) at Sprint 7, M3 (UC-3 LIVE) at Sprint 8.

## See also

- [[plan/README|Plan section overview]] — the broader `wiki/plan/` orientation
- [[dev-tooling-design]] — gstack-driven Phase plan (parallel roadmap; this is for product features, that's for dev-tooling infrastructure)
- [[overview]] — 1-page project synthesis
- [README §12](../../../README.md) — canonical source of the original sprint plan
