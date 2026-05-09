# Wiki Log

## For future Claude

This is the **chronological append-only log** of every wiki event — ingests, queries that produced new wiki content, lint runs, schema-version bumps, seed/migration passes. Read it when you need to know when a page was created or last updated, what triggered a wiki change, or how the wiki has evolved over time. Most recent entries are at the bottom (append-only). Never delete or reorder entries; if a past entry is wrong, append a correction with the original date referenced.

Chronological append-only record of wiki events: ingests, queries, lint runs, schema changes.

## [2026-05-08] seed | scaffold-only PR 1

Phase 3 PR 1 of the dev-tooling design. Created wiki/ skeleton: README, CLAUDE.md (schema), index.md, log.md, empty subdirs (sources, concepts, pipelines, decisions, plan, lint-reports). PR 2 will land the "what is" content seed (~30 pages). PR 3+ will iteratively populate `wiki/plan/`.

## [2026-05-08] lint | 0 issues across 0 categories

## [2026-05-08] lint | 0 issues across 0 categories

## [2026-05-08] lint | 2 issues across 1 category

## [2026-05-08] lint | 0 issues across 0 categories

## [2026-05-08] lint | 0 issues across 0 categories

## [2026-05-08] seed | content seed via PR 2 — 23 sources + 8 concepts + 5 ADRs + overview

PR 2 of Phase 3 of the dev-tooling design. Seven content commits on top of the
PR 1 scaffold:

- Schema amendments (commits 0613dda + 6354692): added `## For future Claude`
  preamble (all page types), `confidence: high | medium | speculation` on
  decisions/, and Obsidian-style `[[wikilinks]]` as the canonical cross-link
  syntax. Mechanical enforcement deferred to Phase 4e wiki_health.py BLOCKING
  CI rule.
- Post-merge gstack-ingest convention (703cb94): root CLAUDE.md now mandates
  the next-session-runs-ingest workflow whenever a gstack PR merges to main.
- Seed sources (ae465b8 + ab82c4a): 23 source pages — 4 portals + 4 API + 1
  scraper + 14 GIS — generated from each pipeline's *_config.py + *_dag.py,
  enriched from the corresponding README. aveiro-pmot added as the 23rd
  page after README review surfaced it as a real (one-off) data source.
- Seed concepts (7c35b6b): 8 highest-stakes pattern pages encoding the
  project rules referenced from the CLAUDE.md hierarchy's task→concept
  routing.
- Seed decisions (ade1d08): 5 ADRs covering Phase 1 + 2 + 2.5 + 3
  decisions surfaced through the gstack design + review process. README-
  derived stack-decision ADRs deferred to PR 3+ alongside `wiki/plan/`
  content.
- Overview synthesis (ade1d08): wiki/overview.md compresses the root
  README's 16 sections into a 1-page entry-point with [[wikilinks]]
  outbound to every typed-content page.

PR 3+ will iteratively populate `wiki/plan/` (sprints, use-cases, source-
priority tiers, data flows, conceptual models, single-page topics).

## [2026-05-09] seed | PR 3 — sprints + folder relocation + 3-layer architecture rationalization

PR 3 of Phase 3 of the dev-tooling design. Five commits implementing the
README→wiki migration plan (post pre-flight audit + post plan-design-review +
post plan-eng-review):

- **Plan revisions** (in plan file `/Users/manuellindo/.claude/plans/give-me-a-full-virtual-crown.md`):
  pre-flight audit found README is materially stale; §8 Physical Data Models
  ~78% aspirational; Sprint 4.4 underreported by 12 days; 13 README-listed
  sources missing from code; Flow F describes non-existent code; tech-stack
  drift (Scrapy → nodriver, etc.); docker-compose service map outdated.
  Decisions: skip §8 entirely (dbt-docs as source of truth); user-led Phase 1
  README cleanup checklist (8 edits + freeze banner); migrate via PR 3-7 + PR 8
  README stub. Locked taxonomy: drop wiki/plan/ + wiki/pipelines/; add top-level
  wiki/sprints/, wiki/use-cases/ (PR 4), wiki/architecture/ (PR 6),
  wiki/planning/ (PR 7).

- **Commit 3a** (2a51af8) — folder relocation + canonical first-visit entry:
  `git mv wiki/plan/sprints/README.md → wiki/sprints/README.md`; deleted
  wiki/plan/dev-tooling-design.md (793-line gstack snapshot, content folded
  into commit 3c); deleted wiki/plan/ entirely (was placeholder, never
  populated); deleted wiki/pipelines/ from schema (YAGNI per design-review);
  refreshed wiki/README.md to be the canonical first-visit entry with
  explicit routing tables (per design-review Pass 1 finding 2 trunk test);
  added wiki/.obsidian/ to .gitignore.

- **Commit 3b** (68a5c92) — 11 data-product sprint pages: sprint-01 through
  sprint-09 plus sub-sprints sprint-04.4 + sprint-04.5. Each follows
  wiki/sprints/README.md schema. Statuses reflect AUDIT findings (Sprint 4.4
  = `done`, not `planned`). Sprint 4.4 page includes a worked Status update
  history showing the planned→done transition with commit references
  edf4b72/210e3e1/7cc2bbe/a9aae01 (per design-review Pass 2 finding +
  eng-review finding 2.1).

- **Commit 3c** — sprint-dev-tooling.md: single page consolidating the
  gstack-driven Phase 1-7 roadmap with explicit `## Phase status table`
  (per eng-review finding 1.5). Frontmatter status: in_progress; per-Phase
  detail in body. Replaces the deleted dev-tooling-design.md snapshot.

- **Commit 3d** — wiki/index.md regenerated with Sprints subsection (12 pages)
  + Forthcoming subsection (PR 4-7 + PR 8 plan).

- **Commit 3e** (this) — wiki/log.md append.

After PR 3 merges, hand off to user for the Phase 1 README cleanup PR (8
specific edits with line numbers + diffs). PR 4-7 strict-sequential per
eng-review finding 1.4: PR 3 → 4 → 5 → 6 → 7 → 8.
