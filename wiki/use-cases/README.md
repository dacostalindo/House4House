# Wiki Use Cases

## For future Claude

This is the **orientation page for `wiki/use-cases/`**. Each use case (UC-1, UC-2, UC-3) gets a single page combining its product narrative, conceptual data model (E-R relationships), and serving layer (which Metabase dashboards / Kepler maps / Streamlit apps power it). One page per UC keeps the "who is this for, what do they ask, what tables answer, where do they look" story in one place.

This folder migrated content from README §1 (Business Use Cases) + §7 (Conceptual Data Models) + §17 (Serving Layer per UC) into 3 unified pages. Per `/plan-design-review` finding 2.3 lock: serving content is APPENDED to UC pages, not split into separate `UC-N-serving.md` files.

## Page conventions

Filename: `UC-{1,2,3}.md` (zero-padded not needed; only 3 UCs). Frontmatter:

```yaml
---
title: <e.g., "UC-1 — Undervalued Property Identification">
type: plan
last_verified: <YYYY-MM-DD>
tags: [use-case, plan, ...uc-specific tags]
uc_number: "<1, 2, or 3>"
status: planned | in_progress | done
sprint_target: "<which data-product sprint ships this UC's MVP>"
last_status_update: <YYYY-MM-DD>
---
```

`status` semantics for UC pages:

- `planned` — UC scope locked but no analytical models built yet
- `in_progress` — partial; some analytical layers shipped, MVP not complete
- `done` — UC's MVP serving surface (Metabase dashboard + Streamlit app + Kepler map) is live and answering the business questions

`sprint_target`: the data-product sprint where the UC's MVP ships. UC-1 → [[sprint-06]] (M1); UC-2 → [[sprint-07]] (M2); UC-3 → [[sprint-08]] (M3).

## Required content sections

Per `wiki/CLAUDE.md` schema (every typed-content page) plus UC-specific:

1. `## For future Claude` — 2-3 sentence preamble per the cross-cutting wiki rule.
2. `## Users` — who consumes this UC's outputs. Specific roles, not generic personas.
3. `## Business questions` — the actual questions users ask (~5 questions each). These drive every analytical layer.
4. `## Decision output` — what the user gets back (ranked list, recommendation, opportunity flag, etc.).
5. `## What makes a [thing] X` — the qualifying criteria (what makes a property undervalued, what makes a plot a development opportunity, etc.).
6. `## Analytical layers` — the gold + silver models that answer the business questions.
7. `## Conceptual data model` — E-R diagram (ASCII art preferred, per project preference for `[[medallion-layering]]`).
8. `## Serving layer` — Metabase dashboard + Kepler map + Streamlit app that surface this UC. Includes which sprint ships each.
9. `## Dependencies` — sprint prerequisites + cross-UC dependencies (e.g., UC-3 economics depends on UC-1 hedonic).
10. `## See also` — cross-links to relevant sources/concepts/decisions/sprints.

## Cross-linking expectations

Every UC page links via `[[wikilinks]]` to:

- Sources it ingests or transforms (`[[idealista]]`, `[[bupi]]`, `[[sce]]`, etc.)
- Concept pages it depends on (`[[medallion-layering]]`, `[[scd2-row-hash]]`, etc.)
- Decision records that drive its architecture (`[[2026-05-08-idealista-enrichment-architecture]]`)
- Sprint pages that ship its components (`[[sprint-05]]` for hedonic, `[[sprint-06]]` for UC-1 MVP, etc.)
- Other UC pages where they share analytical layers (UC-2 + UC-3 both depend on UC-1's hedonic model — link from UC-2 + UC-3 pages back to UC-1)

First mention only per the cross-links-mandatory rule in `wiki/CLAUDE.md`.

## UC roster (PR 4 seed, 2026-05-09)

3 UC pages:

| Page | UC | Decision output | Sprint MVP | Status (PR 4 seed) |
|---|---|---|---|---|
| [[UC-1]] | Undervalued Property Identification (investors / promoters / fund managers / flippers) | Ranked list of investment opportunities (composite: valuation gap × yield × renovation upside × neighbourhood trajectory × catalysts) | [[sprint-06]] (🏁 M1) | `planned` |
| [[UC-2]] | New Housing Unit Pricing Strategy (developers / commercial directors / project managers) | Unit-level pricing recommendation (floor/view/orientation premiums + competitive positioning + absorption forecast + margin) | [[sprint-07]] (🏁 M2) | `planned` |
| [[UC-3]] | Land Development Opportunity Detection (land developers / promoters / funds / municipal offices) | Ranked list of development sites (composite: buildability × constraint clearance × vacancy × assemblable area × estimated margin) | [[sprint-08]] (🏁 M3) | `planned` |

UC-2 and UC-3 both depend on UC-1's hedonic model ([[sprint-05]]). UC-1 is the foundation — once its hedonic regression lands, the other two unlock.

## See also

- [[overview]] — 1-page project synthesis
- [[sprint-05]] — Hedonic Model & Valuation (foundational prerequisite for all 3 UCs)
- [[sprint-06]], [[sprint-07]], [[sprint-08]] — UC MVPs
- [[medallion-layering]] — bronze/silver/gold pattern that all UC analytical layers follow
- [README §1 + §7 + §17](../../README.md) — canonical sources for narrative + conceptual models + serving (post-Phase-1 cleanup)
