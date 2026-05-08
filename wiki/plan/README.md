# Wiki Plan Section

This section breaks down the **project's strategic plan** from the root [`README.md`](../../README.md) into navigable wiki pages. The root README is ~4,300 lines covering 16 sections; each topic gets its own wiki page (or grouped page) here.

## Goal: living roadmap

Pages in this section reflect **current project state**, not just the original plan. Sprint pages have a `Status:` YAML frontmatter field that updates as work lands. The weekly `/wiki-lint` cron flags drift between declared status and reality (git log, TODOs, design doc).

## Structure

```
plan/
├── README.md              this file
├── overview.md            16-section blueprint distilled to 1 page
├── use-cases/             one page per UC (UC-1, UC-2, UC-3)
├── sources-by-priority/   one page per priority tier (P0, P1, P2)
├── data-flows/            one page per ingestion-pattern flow (A-F)
├── conceptual-models/     one page per UC's E-R model
├── sprints/               one page per sprint (sprint-01 ... sprint-09)
├── tech-stack.md          single page — tech choices + rationale
├── infra.md               single page — Docker compose service map + server spec + PG schemas
├── data-quality.md        single page — dbt tests + Great Expectations + metadata
├── risks.md               single page — risk register + mitigations
├── resources.md           single page — team + budget + effort + data volume estimates
└── roadmap-p3-p4.md       single page — Future Expansion (Phase 2A + 2D)
```

## Iterative population

This section's content arrives across multiple PRs after PR 2 (the "what is" seed) lands. Recommended sequencing:

| PR | Content | Pages |
|---|---|---|
| 3 | `sprints/*` | ~11 |
| 4 | `use-cases/*` | 3 |
| 5 | `sources-by-priority/*` | 3 |
| 6 | `data-flows/*` | 6 |
| 7 | `conceptual-models/*` | 3 |
| 8 | Single-page topics (tech-stack, infra, data-quality, risks, resources, roadmap-p3-p4) | 6 |

The order is not strict — pick what's most operationally useful at the time.

## Sprint Status semantics

Each sprint page has YAML frontmatter:

```yaml
---
status: in_progress | done | mostly_done | planned | deferred
sprint_number: <int>
weeks: "<n>-<m>"
last_status_update: <date>
---
```

`/wiki-lint` cross-checks: if a sprint says `Status: planned` but the design doc / TODOs.md / git log show work has happened on it, flag the drift.

## Cross-linking pattern

Plan pages link aggressively into the rest of the wiki. A use-case page links to every `sources/<name>.md` it depends on. A sprint page links to relevant `decisions/<date>-<topic>.md`. This makes the wiki a graph: plan describes intent, source/concept/decision pages describe reality.
