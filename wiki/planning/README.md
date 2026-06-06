# Wiki Planning Section

## For future Claude

This is the **orientation page** for `wiki/planning/` — the section that captures forward-looking project planning content (NOT roadmap-as-architecture, which lives in [[architecture/README|wiki/architecture/]]). Risks register, resource estimates, P3/P4 future-expansion roadmap, and Go/No-Go milestones — all decomposed from README §14 / §15 / §16 / §17. Read this section to know what's planned but not yet shipped, what budget + effort backs it, and which milestones gate progression.

## What lives here

Four pages from README §14-§17, each a focused planning artifact:

- [[risks]] — README §14 — 15-row risk register with probability + impact + mitigation. Maintained as a living document; revisited each sprint close.
- [[resources]] — README §15 — team composition, infrastructure budget, per-sprint effort estimates, data-volume projections.
- [[roadmap-p3-p4]] — README §16 — deferred sources organized into Phase 2A (Risk & Environment) / 2D (Land Development Intelligence) / 2B (Supply & Costs) / 2C (Coverage & Niche) post-MVP expansion plan.
- [[milestones]] — README §17 partial (Go/No-Go criteria for M1 / M2 / M3 + MVP hedonic feature coverage) — the explicit hard-fail / soft-fail gates per use-case MVP.
- [[pt-education-amenity-design]] — v1 design for the education geo-amenity layer (dual signal: point-proximity + area-quality); resolved decision tree, surfacing spec, and 6-gate verification. Sources [[gesedu]] + [[infoescolas]]. `status: scoped-not-built`.

Plus one paired concept page (lives in concepts/):

- [[spatial-strategy]] — README §9 — CRS dual-storage convention (geom in 4326 + geom_pt in 3763), spatial indexing patterns (GIST + H3), common spatial query templates, location-score computation logic. Concept-shaped (rule + pattern), not planning-shaped.

And one ADR landing in PR 7:

- [[2026-05-10-dual-crs-storage]] — locks in the decision to store geometries in both EPSG:4326 (display + joins) and EPSG:3763 (distance + area calculations) on every spatial table.

## Why this section exists

Before PR 7, planning content lived only in the README. Decomposing it into the wiki gives:

1. **Living-roadmap mechanics**: each risk row + each P3/P4 source can carry its own update history; sprint closeouts can flip risks from `open` → `mitigated` or `realized` without rewriting the README.
2. **Cross-reference graph**: the risks page links to the sources + concepts that mitigate each risk; the milestones page links to the use-case pages; resources links to the sprint pages where each effort estimate gets validated.
3. **Decoupling from README evolution**: same rationale as [[architecture/README]] — wiki content is maintained alongside code, README is being progressively retired.

## Page conventions

Planning pages use `type: plan` in frontmatter (same as sprints, use-cases, architecture pages). Required sections vary per page (risks has a register; milestones has gate tables; roadmap-p3-p4 has phase tables; resources has team + budget + effort + volume tables) — each page documents its own structure in its `## For future Claude` preamble.

The expectation is these pages are **read at sprint closes** (risks revisit), **read during scoping** (milestones gate decisions), **read during budget review** (resources sanity check), and **read when a P3/P4 source becomes interesting** (roadmap-p3-p4 escalation).

## See also

- [[overview]] — 1-page synthesis of the project; entry-point for orientation queries
- [[architecture/README]] — companion section: as-built / as-designed architecture (vs this section's forward-looking planning)
- [[sprints/README]] — operationally-tracked sprint pages with `Status:` frontmatter
- [[use-cases/README]] — UC pages with `sprint_target:` frontmatter
