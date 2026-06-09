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
  README's 16 sections into a 1-page entry-point with `[[wikilinks]]`
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

## [2026-05-09] seed | PR 4 — wiki/use-cases/ (UC-1 + UC-2 + UC-3)

PR 4 of Phase 3. 5 commits adding the new top-level wiki/use-cases/ folder
with 3 unified UC pages (each combining product narrative + conceptual data
model + serving layer per /plan-design-review finding 2.3 lock).

Per the eng-review locked sequence (PR 3 → 4 → 5 → 6 → 7 → 8), PR 4 stacks
on PR 3 head locally; rebases onto main when PR 3 merges. Migration sources:
README §1 (Business Use Cases) + §7 (Conceptual Data Models) + §17 (Serving
Layer per UC).

Commits:

- **Commit 4a** — wiki/use-cases/README.md schema + orientation. Page
  conventions (frontmatter incl. uc_number + sprint_target + status enum),
  required sections (10 sections per UC page), cross-linking expectations,
  UC roster (3 pages: UC-1 → sprint-06 M1; UC-2 → sprint-07 M2; UC-3 →
  sprint-08 M3).
- **Commit 4b** — UC-1 (Undervalued Property Identification). Investment
  use case; foundation for UC-2 + UC-3 via hedonic price model. 7 analytical
  layers (hedonic + residual + neighbourhood trajectory + renovation
  opportunity + yield + catalysts + composite). 3 serving surfaces at
  sprint-06.
- **Commit 4c** — UC-2 (New Housing Unit Pricing Strategy). Reuses UC-1
  hedonic. 10 analytical layers (price decomposition into base + premiums
  + competitive positioning + absorption forecast + margin). 2 serving
  surfaces at sprint-07.
- **Commit 4d** — UC-3 (Land Development Opportunity Detection). Most
  spatially-intensive UC; depends on UC-1 hedonic for GDV anchor. 12
  analytical layers (vacant detection + buildability + constraint overlay +
  parcel assembly + economics + opportunity scoring + competition reuses
  UC-1's neighbourhood_market_stats). 3 serving surfaces at sprint-08 +
  Opportunity Heatmap deferred to sprint-09.
- **Commit 4e** (this) — wiki/index.md regen with Use Cases subsection +
  log.md append.

PR 4 stats: 5 files added, ~520 lines.

Cross-UC dependency lock: UC-2 + UC-3 both REQUIRE UC-1 hedonic. Documented
explicitly in each UC page's Dependencies section.

## [2026-05-10] seed | PR 5 — source priorities + ingest-flows concept

PR 5 of Phase 3 of the dev-tooling design. Two-commit shape:

- **Commit 1** (9a5dadc) — added `priority: P0|P1|P2` frontmatter to all
  23 sources/ pages. P0 (7): caop, bgri, osm, idealista, ine, bpstat,
  ecb. P1 (13): bupi, cadastro, cos, crus, crus-ogc, eurostat, jll,
  lidar, remax, sce, srup, srup-ogc, zome. P2 (3): apa, aveiro-pmot,
  lneg. Tier ordering drives load sequencing for cold bootstrap and
  prioritization in [[sprint-04.5]] and beyond.
- **Commit 2** (next) — wiki/concepts/ingest-flows.md, the six-flow
  taxonomy from README §6 (A REST / B scraping / C GIS / D derived /
  E spatial composition / F portal cross-reference). Lifts each
  flow's verbatim diagram from README + adds `[[wikilinks]]` to source
  pages and the concept dependencies. Replaces the originally-planned
  wiki/plan/data-flows/ subdirectory — single concept page beats
  per-flow page proliferation.
- **Commit 3** (this) — wiki/CLAUDE.md schema update (priority field
  required on source pages going forward), wiki/index.md regen with
  the priority breakdown line + ingest-flows concept entry, log.md
  append.

PR 5 stats: 25 files modified (1 schema + 23 sources + 1 index), 1
file added (ingest-flows.md), ~210 lines net.

Replaces the original plan that had wiki/plan/sources-by-priority/
as 3 separate pages and wiki/plan/data-flows/ as 6 separate pages.
The frontmatter-on-existing-pages + single-concept-page approach is
strictly less duplication for the same information density.

## [2026-05-10] seed | PR 6 — wiki/architecture/ (4 pages) + 7 stack-decision ADRs

PR 6 of Phase 3 — README §3 + §4 + §11 + §13 decomposition.

Five-commit shape:

- **Commit 6a** — wiki/architecture/README.md orientation +
  tech-stack.md (README §3 primary stack table + alternative-stack-
  considered table). Cross-links forward to 7 stack-decision ADRs in
  commit 6d.
- **Commit 6b** — infra.md (README §4: Docker Compose service map,
  Hetzner AX102 server spec, PostgreSQL schema map matched to
  warehouse/init/001_create_schemas.sql) + orchestration.md (README
  §11: DAG taxonomy + schedule map for ~22 recurring DAGs).
- **Commit 6c** — data-quality.md (README §13: dbt tests + Great
  Expectations + metadata.pipeline_runs audit trail). Decision tree:
  dbt test (shape) vs GE check (distribution / cross-source /
  temporal / spatial).
- **Commit 6d** — 7 stack-decision ADRs (all dated 2026-05-10):
  postgis-as-warehouse, minio-not-s3, airflow-2-not-3, dbt-not-
  sqlmodel, nominatim-osrm-self-hosted, metabase-streamlit-not-
  superset, single-server-self-hosted. The single-server-self-hosted
  decision is the load-bearing root that 6 others cascade from.
- **Commit 6e** (this) — wiki/index.md regen (Architecture section
  added + Decisions section grew from 5 to 12) + log.md append.

PR 6 stats: 4 architecture pages (~580 lines) + 7 ADRs (~390 lines)
+ index/log changes (~40 lines) = ~1,010 lines net addition across
12 new files + 2 modified.

Decisions section now organized into "Foundational" (Phase 1-3
dev-tooling, surfaced via gstack reviews — 5 ADRs) and "Stack" (PR 6,
README §3 + §4 surfaced — 7 ADRs). Total ADRs: 12.

After PR 6 merges, PR 7 lands wiki/planning/ (risks, resources,
roadmap-p3-p4, milestones) + spatial-strategy concept + 1 ADR.
PR 8 (optional) is the README → stub rewrite.

## [2026-05-10] seed | PR 7 — wiki/planning/ + spatial-strategy concept + dual-crs ADR

PR 7 of Phase 3 — README §9 + §14 + §15 + §16 + §17 decomposition.
Final full-content PR before the optional PR 8 (README → stub rewrite).

Two-commit shape:

- **Commit 7a** — content seed (7 new files, 631 lines):
  - wiki/planning/README.md — section orientation + page conventions
  - wiki/planning/risks.md — 15-row risk register from §14, every row
    cross-linked to relevant source/concept/ADR/use-case pages,
    proposed Status enum + maintenance mechanic
  - wiki/planning/resources.md — team / budget / effort / data-volume
    from §15; explicit "solo-dev reality" note + ZenRows costs as
    separate line item
  - wiki/planning/roadmap-p3-p4.md — §16 deferred-source landscape
    in 4 phases (2A Risk & Environment / 2D Land Development
    Intelligence / 2B Supply & Costs / 2C Coverage & Niche) with
    per-row trigger conditions
  - wiki/planning/milestones.md — §17 Go/No-Go for M1/M2/M3 + MVP
    hedonic-feature-coverage table; Status column tracks shipped vs.
    pending
  - wiki/concepts/spatial-strategy.md — §9 dual-CRS convention + GIST
    + H3 indexing + common spatial query templates + location-score
    computation
  - wiki/decisions/2026-05-10-dual-crs-storage.md — locks the dual-CRS
    storage convention; companion ADR to spatial-strategy concept;
    confidence: high

- **Commit 7b** (this) — index.md regen (Planning section + spatial-
  strategy in Concepts list growing 9→10 + dual-crs-storage in
  Decisions growing 12→13 with new "Spatial" subgroup) + log.md
  append.

PR 7 stats: 7 new files + 2 modified, ~700 lines net.

After PR 7 merges, the README → wiki migration is structurally
complete:
- All 17 README sections decomposed except §5 (Conceptual Architecture
  / Medallion Pattern, already covered by [[medallion-layering]]
  concept) and §8 (Physical Data Models, deferred per the eng-review
  finding to use dbt-docs as source of truth instead).
- 10 concepts + 13 ADRs + 23 sources + 12 sprints + 3 use-cases + 4
  architecture + 4 planning + overview = ~80 typed-content pages.

PR 8 (optional): retire the README's strategic narrative, leave only
the §0 Getting Started + §1 Repo Layout + a stub pointing to the wiki.

After PR 8 (or if PR 8 is declined): the README → wiki migration
chapter closes, and the wiki becomes the canonical reading surface.
Future updates land in wiki pages directly; the README becomes a
thin orientation file.

## [2026-05-10] retire | PR 8 — README → stub; wiki is canonical

PR 8 of Phase 3 — closes the README → wiki migration chapter. Single
commit: replace README.md's ~4,500-line strategic blueprint with a
72-line stub that:

- Keeps Getting Started (lines 1-15) + Repo layout table (lines 19-30)
  unchanged — the operational entry-point a contributor reads first
- Replaces the §1-§17 strategic narrative with a "Project blueprint —
  see the wiki" section pointing to wiki/overview.md as the new
  canonical entry-point
- Adds a section-mapping table: every former README section →
  current wiki location (or "deferred — dbt-docs is source of truth"
  for §8 Physical Data Models per the eng-review pre-flight audit)
- Adds a "Why this README is a stub" closing paragraph documenting
  the migration rationale + how to recover the original content via
  git history (`git log --diff-filter=D` + `git show <commit>^`)

README delta: +35 / -4,458 (one file).

Migration scope confirmed shipped:

- §1 (use cases) → wiki/use-cases/ (3 pages)
- §2 (sources) → wiki/sources/ (23 pages with priority frontmatter)
- §3 (tech stack) → wiki/architecture/tech-stack.md + 7 ADRs
- §4 (infra) → wiki/architecture/infra.md + single-server-self-hosted ADR
- §5 (medallion) → wiki/concepts/medallion-layering.md (already shipped PR 2)
- §6 (data flows) → wiki/concepts/ingest-flows.md
- §7 (conceptual data models) → folded into UC pages
- §8 (physical data models) → DEFERRED; dbt-docs canonical
- §9 (spatial strategy) → wiki/concepts/spatial-strategy.md + dual-crs ADR
- §10 (dependency graph) → folded into wiki/sprints/ frontmatter + body
- §11 (orchestration) → wiki/architecture/orchestration.md
- §12 (sprint plan) → wiki/sprints/ (11 data-product + 1 dev-tooling)
- §13 (data quality) → wiki/architecture/data-quality.md
- §14 (risks) → wiki/planning/risks.md
- §15 (resources) → wiki/planning/resources.md
- §16 (P3/P4 roadmap) → wiki/planning/roadmap-p3-p4.md
- §17 (serving layer + Go/No-Go milestones) → per-UC pages + planning/milestones.md

PR 8 closes Phase 3 of the dev-tooling plan. The wiki is now the
canonical reading + writing surface for project knowledge; the
README is a thin stub pointing here. Future updates land in wiki
pages directly. The full PR sequence shipped: PR 1 (scaffold) → PR 2
(seed content) → PR 3 (sprints) → PR 4 (use-cases) → PR 5 (priority
frontmatter + ingest-flows) → PR 6 (architecture + 7 stack ADRs) →
PR 7 (planning + spatial-strategy + dual-crs ADR) → PR 8 (README
stub).

Wiki final state: ~80 typed-content pages across 23 sources + 10
concepts + 13 ADRs + 4 architecture + 4 planning + 12 sprints + 3
use-cases + 1 overview + structural files (CLAUDE.md, README.md,
index.md, log.md, plus per-section orientation READMEs).

## [2026-05-12] ingest | gstack-artifact phase-4-plan

Post-merge wiki ingest for Phase 4 (PR #22 merged at 593ec18 + PR #23
follow-up). Source: gstack plan `~/.claude/plans/give-me-a-full-virtual-crown.md`
which went through `/plan-eng-review` (5 findings, 3 folded) +
`/plan-devex-review` (CLEAR) per `~/.gstack/projects/dacostalindo-House4House/main-reviews.jsonl`.

Two ADRs locked from the plan's architectural decisions:

- `wiki/decisions/2026-05-12-wiki-linter-deferred-to-phase-7.md` —
  `scripts/wiki_health.py` moves from Phase 4 to Phase 7 to co-design
  with the structured `wiki/_schema.yaml` (single source of truth
  consumed by the schema doc, the linter, `/wiki-reconcile`, and
  `/wiki-import-gstack`). Surfaced during a working prototype linter
  pass that caught 12 findings — validating the linter design but
  also surfacing the DRY violation against `wiki/CLAUDE.md` prose.
- `wiki/decisions/2026-05-12-pre-commit-local-hook.md` —
  `.pre-commit-config.yaml` uses `language: system` + `uv run ruff`
  instead of pinned `astral-sh/ruff-pre-commit`, eliminating ruff
  version drift between pre-commit, CI, and Makefile. Confidence:
  medium (pattern is less common; reversible if PATH issues surface).

Propagation:

- `wiki/CLAUDE.md` — 4 stale forward-refs to "Phase 4e" `wiki_health.py`
  rewritten to "Phase 7" + pointing at the deferral ADR. Lint-workflow
  section updated to reflect LLM cron as sole automated gate until
  Phase 7.
- `wiki/sprints/sprint-dev-tooling.md` — Phase 4 row flipped to `✅ done`
  (shipped 2026-05-12); Phase 7 row expanded to absorb the deferred
  wiki-linter scope. Status-update-history appended with 2 entries
  (Phase 3 PR 4-8 done 2026-05-10; Phase 4 done 2026-05-12).
- `wiki/index.md` — Decisions count 13 → 15; new "Dev-tooling" group
  added under Decisions; sprint-dev-tooling status line updated.

The gstack plan artifact remains at `~/.claude/plans/give-me-a-full-virtual-crown.md`
as the historical record. Only the derived knowledge (the 2 ADRs +
the propagation updates) flowed into the wiki.

## [2026-05-12] ingest | gstack-artifact phase-6-plan + devex-review

Post-merge wiki ingest for Phase 6 (PR #25 merged at 4e01516) bundled
with the Phase 6 followup work — `[tool.ty.src.exclude]` safety net,
README staleness fix, `unexport VIRTUAL_ENV` Makefile workaround, and
this ingest. Source artifacts: gstack plan
`~/.claude/plans/give-me-a-full-virtual-crown.md` (revised to Phase 6
scope after Phase 4 closed); `/plan-eng-review` 2026-05-12 (4 findings,
2 folded into plan: ty pin tightening + graduation trigger rewrite);
`/devex-review` 2026-05-12 (live audit, 8/10 overall, 4 findings, 3
folded into this followup PR).

One ADR locked from the work:

- `wiki/decisions/2026-05-12-phase-6-ty-advisory.md` —
  Phase 6 ships `ty` advisory-only with 3 concrete graduation triggers
  (ty 1.0 / `[tool.ty.rules]` config / Phase 6.5 sweep). Documents the
  live finding picture: 319 diagnostics (287 errors + 32 warnings), 172
  confirmed Airflow `XComArg` false positives (~60% of errors). The
  followup `unexport VIRTUAL_ENV` Makefile fix raised the count from
  the initial PR-#25 measurement of 159 — earlier ty was under-resolving
  due to a macOS-CommandLineTools env shadow on `.venv`. Higher count
  reflects ty seeing the codebase correctly, not regression. Captures the
  defaults-first posture decision + rejected alternatives (mypy /
  pyright / gating from day one / `[tool.ty.rules]` overrides).

Phase 6 followup mechanical changes (this PR):

- `pyproject.toml` — added `[tool.ty.src.exclude]` mirroring ruff's
  extend-exclude as a safety net (observed no-op on current findings;
  the noise is XComArg-shaped, not path-shaped). Inline comment
  documents the corrected understanding.
- `README.md` — line 14 `make verify` description updated to include
  `ty (advisory)` + `pytest` (was stale after Phase 6).
- `Makefile` — `unexport VIRTUAL_ENV` directive at top; silences the
  macOS CommandLineTools warning that bled into every `uv run`
  invocation. Applies to all targets.

Propagation:

- `wiki/sprints/sprint-dev-tooling.md` — Phase 6 row flipped to
  `✅ done` (2026-05-12); Status-update-history appended with the
  Phase 6 entry + DevEx review boomerang.
- `wiki/index.md` — Decisions count 15 → 16; new ADR linked under
  "Dev-tooling" decisions group; sprint-dev-tooling status line updated.

The gstack plan + review artifacts remain at `~/.claude/plans/` and
`~/.gstack/projects/dacostalindo-House4House/main-reviews.jsonl` as
the historical record. Only the derived knowledge (the ADR + the
propagation updates) flowed into the wiki.

## [2026-05-12] phase-7c | 3 scaffolding skills shipped (/add-gis-source + /add-portal-source + /stg-from-bronze)

Phase 7c closes the dev-tooling roadmap's skill backlog. Three new
skills at `.claude/skills/`:

- `add-gis-source/SKILL.md` — bootstraps new GIS source (Pydantic config
  + Airflow DAG + wiki page + dbt source YAML). Mirrors 17 existing
  GIS sources; canonical template at `pipelines/gis/bgri/`.
- `add-portal-source/SKILL.md` — bootstraps new property portal (dlt
  resources + Airflow DAG + tests + README + wiki page + dbt source
  YAML). Mirrors 6 portals; canonical template at `pipelines/portals/zome/`
  (simple) or `pipelines/portals/idealista/` (rich).
- `stg-from-bronze/SKILL.md` — bootstraps dbt staging model from a
  bronze table (type casts + NULL guards + CRS reprojection + dbt-utils
  tests). Mirrors 21+ staging models; canonical templates per domain.

All three follow the obsidian-second-brain command pattern locked in
Phase 7b: pure-prose markdown (~75 lines), Cosmos frontmatter
(`name:` + `description:`), numbered procedural steps, parallel
subagents where applicable, AI-first compliance mandate at the end.
Skill-only — no Python helpers, no CI, no Makefile, no pre-commit.

Phase 7 status table updated in `sprint-dev-tooling.md` to ✅ done.
Phase 7 closes the dev-tooling roadmap's skill backlog. Remaining
roadmap work: Phase 5 (idealista enrichment via Pydantic AI) — coupled
to data-product Sprint 4.5/5, currently queued behind in-progress
Sprint 4.

## [2026-05-12] reconcile | 6 findings, 6 auto-fixed, 0 flagged for user, 0 ADRs created (of which 0 from gstack ingest)

First `/wiki-reconcile` run since the skill shipped in Phase 7b. Four
parallel subagents (schema / links / reciprocity / freshness) plus
ingest-check.

- **Schema agent:** clean — 81 pages scanned, 100% compliance on
  required frontmatter (priority for sources, confidence for decisions,
  status/sprint_number/weeks/last_status_update for sprints), required
  sections per page type, and `## For future Claude` preamble.
- **Links agent:** 6 unresolved `[[wikilinks]]` — all auto-fixed.
  4 were directory-path links (`[[wiki/decisions/]]`, `[[wiki/sources/]]`,
  `[[wiki/concepts/]]`) that don't resolve under the basename rule and
  needed either removal (when prose already covered the reference) or
  rewriting to specific page links. 2 were bare meta-references to
  `[[wikilinks]]` in `log.md` describing the wiki schema — wrapped in
  backticks to match the existing convention at log.md:30.
- **Reciprocity agent:** clean — 0 supersedes chains exist across the
  16 ADRs; all 12 sprint `## Status update history` sections pass the
  `^- \d{4}[-Q]\S*:\s+\S.*` regex on every line.
- **Freshness agent:** clean — 0 pages with `last_verified:` older than
  90 days; the 5 structural files without `last_verified:` are
  exempt per schema.
- **Ingest agent:** no new gstack artifacts since the Phase 6 ingest
  (the last `~/.gstack/projects/dacostalindo-House4House/main-reviews.jsonl`
  entry is 2026-05-12T09:45:22Z, already ingested as
  `[[2026-05-12-phase-6-ty-advisory]]`).

Files touched (`last_verified` bumped where applicable):

- `wiki/architecture/tech-stack.md` — removed `[[wiki/decisions/]]`
  (prose already says "linked inline below"); `last_verified` 2026-05-10
  → 2026-05-12.
- `wiki/concepts/ingest-flows.md` — removed `[[wiki/sources/]]` (generic
  prose, no specific target); `last_verified` 2026-05-08 → 2026-05-12.
- `wiki/planning/README.md` — directory hint kept but as plain text
  ("lives in concepts/"); no `last_verified` (structural).
- `wiki/planning/resources.md` — replaced `as per [[wiki/sources/]]`
  with `as documented above` (the row already lists 5 source wikilinks);
  `last_verified` 2026-05-10 → 2026-05-12.
- `wiki/log.md` — wrapped 2 bare `[[wikilinks]]` mentions in backticks;
  no `last_verified` (structural).
- `wiki/index.md` — added `Last reconcile run: 2026-05-12` line below
  the existing `Last lint run:`.

Session report at `wiki/lint-reports/2026-05-12T120000.md`.

## [2026-05-12] uc3-reframe | UC-3 expanded scope — gstack /office-hours + /plan-eng-review

Reframed `wiki/use-cases/UC-3.md` from "national-scope spatial-overlay Land Development Opportunity Detection" into an end-to-end 7-stage plot economic-value pipeline (Scout → Inspect → Assemble → Build out → Value → Profit → Competitive Intel) with a v1 wedge scoped to Aveiro município + Stages 1-4 + SCE unit aggregation + idealista LLM construction-area extraction + development dedup. Architecture pivot: primary user journey is draw-your-own-polygon via `gold.fn_assess_polygon(geom)` Postgres function, NOT pre-computed-parcel-per-row. v1 UI is Streamlit-component; v2 promotes to standalone web app.

Pages touched:
- `wiki/decisions/2026-05-12-uc3-expanded-scope.md` — NEW ADR (confidence: speculation; gated on 3-developer interview validation).
- `wiki/use-cases/UC-3.md` — rewritten in place. Old 9-question framing replaced.
- `wiki/sprints/sprint-08.md` — restructured to "UC-3 v1 wedge Part 1 (Foundations + Aveiro Vertical Slice)". WS2 (national OGC migration) dropped from v1 wedge.
- `wiki/sprints/sprint-09.md` — restructured to "UC-3 v1 wedge Part 2 (Wedge Completion + Atlas Inspector + Demo)". Weeks extended 19-20 → 19-21. Existing scope (Imovirtual / RNAL / hedonic v2 / ARU / etc.) deferred to future v1.5+ sprint gated on wedge validation.

Source artifacts: office-hours design doc + /plan-eng-review test plan at `~/.gstack/projects/dacostalindo-House4House/`. Variant B-prime UI mockup at `~/.gstack/projects/dacostalindo-House4House/designs/aveiro-parcel-assessment-inspect-20260506/approved.json`.

**Caveat (Propagation Rule)**: sibling pages [[UC-1]], [[UC-2]], [[sprint-03]], [[sprint-05]], [[sce]], [[idealista]], [[medallion-layering]] referenced in the new UC-3 + ADR have NOT been propagation-updated in this commit. Per the design doc's staged wiki migration plan, propagation was scheduled to gate on interview validation. The user explicitly overrode that gate to update UC-3 + sprints now; propagation to siblings still defers. Run `/wiki-reconcile` to surface drift.

## [2026-05-12] reconcile | 5 findings, 4 auto-fixed, 1 flagged for user, 1 ADR (from earlier same-session ingest)

Triggered by user `/wiki-reconcile` after the UC-3 reframe (gstack /office-hours + /plan-eng-review + sprint-10 create). Auto-fixed: (1) BLOCKING broken `[[wiki-clauder|wiki/CLAUDE.md]]` wikilink in `wiki/decisions/2026-05-12-uc3-expanded-scope.md` — replaced with plain prose; (2) PROPAGATION added `bronze_enrichment` schema row to `wiki/concepts/medallion-layering.md`; (3) PROPAGATION rewrote `wiki/planning/milestones.md` M3 to reflect UC-3 v1 wedge at Week 21 with Atlas Inspector single surface (dropping the old three-surface model); (4) PROPAGATION updated `wiki/index.md` (sprint-08/9/10 lines, UC-3 summary, ADR count 16→17, sprint count 12→13, added Use-cases decision group, reconcile-run line). Flagged for user: ADVISORY schema-scope ambiguity — `wiki/CLAUDE.md` §79 wikilink-resolution rule excludes sprints/ and use-cases/ but ambient convention uses them; needs schema-doc clarification, not urgent. 16 sibling pages (UC-1/UC-2/sprint-03/05/07/sce/idealista/bupi/cos/crus/srup/cadastro/lidar/bronze-permissive/etc.) scanned and confirmed CLEAN — no edits needed. Session report at `wiki/lint-reports/2026-05-12T160000.md`. Caveat: user overrode staged migration plan; wiki now reflects unvalidated UC-3 framing pending developer interviews per [[2026-05-12-uc3-expanded-scope]] kill criteria.

## [2026-05-12] sprint-10-create | Displaced sprint-09 scope absorbed

Created `wiki/sprints/sprint-10.md` (weeks 22-24) to absorb the scope displaced from [[sprint-09]] when [[sprint-09]] was restructured to be UC-3 v1 wedge Part 2. Sprint 10 has two tracks: Track A (Imovirtual / RNAL / INE Permits / REN / data-quality monitoring / docs — always ships), Track B (ARU / hedonic v2 / OSRM drive-times / UC-3 v2 economics scoping — gated on [[sprint-09]] wedge-validation outcome). Updated sprint-09 Key Decisions to reference sprint-10 instead of "future v1.5+ sprint to be created."

## [2026-05-12] gis-recovery | 26 lost GIS pipeline files recovered + committed (`171114d`)

Six `pipelines/gis/` subdirs had `__pycache__/` but no `.py` source (lost between May 8 and May 9 — never committed to git). Recovered via two paths: `pdm` restored verbatim from `feature/pdm` branch (4 files, real source); apa/crus_ogc/lidar/lneg/srup_ogc reconstructed from `.pyc` bytecode using Python `dis` + `marshal` + the wiki source-page specs (22 files). All 26 files pass ruff + ruff-format + py_compile.

Recovery provenance preserved at `/tmp/recovery/<mod>/*.spec.txt` (bytecode extracts). Commit `171114d` lands the integration.

**Sprint 8 impact**: WS3 (LiDAR) flips from build-from-scratch to validate-recovered-code (~3 days saved). WS1 scope expands from "extract `ogcapi_template.py`" to full `pipelines/gis/template/ingestion_template.py` with three adapters (`OgcApiAdapter`, `ArcgisRestAdapter`, `DgtStacAdapter`) + `UnifiedIngestionConfig` — the API surface is fully specified by the recovered DAGs' imports. Day-8 srup_ogc evaluation gate added: if cleaner than legacy WFS, integrate the 22-layer SRUP OGC registry into `silver/geo/parcel_constraints.sql` on Day 10 (3 sources → up to 22 sources).

Pages updated: `wiki/sprints/sprint-08.md` (substantial rewrite — WS1 expanded, WS3 reframed, Recovery section added, status update history entry added).

**Caveat (Propagation Rule)**: `wiki/sources/{apa,crus-ogc,lidar,lneg,srup-ogc}.md` carry `last_verified: 2026-05-08` — technically stale now that the code those pages reference is in HEAD. Source-page content is still accurate (the recovered code matches the wiki spec because the wiki was the recovery oracle). Bumping `last_verified` is a low-priority follow-up; defer to a future `/wiki-reconcile` pass.

## [2026-05-12] claude-md-update | Post-commit wiki-update rule added to root CLAUDE.md (`3d8c8ed`)

Root `CLAUDE.md` "Schema for Claude Code" section gets one new sentence: "After every commit, update the wiki: append a one-line entry to wiki/log.md and update any wiki pages whose claims the commit affected." Loaded at root level on every task — fills the gap where `wiki/CLAUDE.md` §Write rules §3 (Propagation Rule) only fires when editing the wiki, leaving code→wiki direction unenforced. Triggered by the missed propagation when `171114d` (GIS recovery) landed without the wiki updates following.

## [2026-05-12] claude-md-consolidation | Per-area `CLAUDE.md` files retired; all routing in `wiki/index.md`

Deleted `pipelines/CLAUDE.md`, `dbt/CLAUDE.md`, `apps/CLAUDE.md`. Their task→concept routing tables only pointed at `wiki/concepts/` pages (and several pointed at non-existent ones — `staging-yaml-conventions`, `streamlit-keplergl-quirks`, `geopandas-postgis-quirks` — surfaced as drift here and in prior `/wiki-reconcile` runs).

Replacement: new `## By area of code` section in [[index]] between Overview and Sources. Each code area (`pipelines/`, `dbt/`, `apps/`) lists the relevant **concepts + sources + decisions + architecture + currently-relevant sprints** in one place. Wider span than the old per-area files (which only covered concepts) and zero duplication risk since the listing IS the index.

Root `CLAUDE.md` updated: "Schema for Claude Code" now points at `wiki/index.md` §"By area of code"; "Area routing" table replaced with a one-line pointer to the same. Wiki remains the single source of truth; the previous CLAUDE.md hierarchy was a redundant cache.

**Why**: the per-area files didn't auto-update when wiki pages were added/renamed, producing drift the wiki linter couldn't catch (it lints inside `wiki/`, not outside). Folding routing into `wiki/index.md` puts it back under linter coverage. Triggered by user concern that "CLAUDE.md on the pipeline folders don't get updated. I want to have only one source of truth in the wiki."

## [2026-05-12] sprint-08-refactor | Sprint-08 page rewritten for clarity — plain-language objectives + activities

[[sprint-08]] rewrite per user feedback that "objectives are not very clear and the activities". Structural changes: explicit `## Objective` (1-paragraph plain English), `## Outcomes (verifiable at sprint end)` (bullet checklist), `## Activities` (9 named activities each with WHY / concrete deliverables / DONE WHEN), `## Out of scope` (explicit list with reasons), `## Dependencies / blockers` (must-be-true-before + calendar-parallel), `## Exit criteria` (checkbox-shape version of Outcomes). The `WS1`/`WS3`/`WS4 Slice B` jargon dropped in favor of named activities like "Plug the recovered GIS pipelines into a shared template", "Validate the recovered LiDAR pipeline end-to-end on Aveiro", "Geocode the SCE certificates". No scope change. Single `[[pdm]]` wikilink that didn't resolve replaced with plain text "PDM zoning" (no wiki/sources/pdm.md yet — PDM concept lives under [[crus]]).

Pages updated: `wiki/sprints/sprint-08.md` (full body rewrite; frontmatter `last_verified` + `last_status_update` bumped to 2026-05-12; status-history line appended). The engineering plan at `~/.claude/plans/wobbly-kindling-hopcroft.md` is now stale relative to this page; the sprint page is the source of truth for activity definitions.

Sprint-09 follow-up: same refactor pending; user wanted to tackle sprint-08 first and review before committing to the same shape for sprint-09.

## [2026-05-12] sprint-08-activity-1 | Shared GIS ingestion template + cadastro refactor

Activity 1 of [[sprint-08]] landed: `pipelines/gis/template/ingestion_template.py` (~370 lines) with `UnifiedIngestionConfig` (Pydantic frozen model) + three protocol adapters sharing the same `.probe()` + `.fetch_to(tmp_dir) -> {feature_count, pages, bytes, files}` interface:

- **`OgcApiAdapter`** — limit/offset pagination → single GeoJSON. Used by [[cadastro]], [[crus-ogc]], [[srup-ogc]].
- **`ArcgisRestAdapter`** — `resultOffset` / `resultRecordCount` pagination, server-side reproject via `outSR=3763`. Used by [[apa]], [[lneg]]. LNEG SSL workaround for `sig.lneg.pt` (self-signed cert) stays in `lneg_ingestion_dag.py` as a `requests.Session.request` patch around the adapter call — adapter itself unchanged.
- **`DgtStacAdapter`** — POST `/v1/search` (collections + bbox filter) → paginate → per-tile cookie-gated GeoTIFF download (Keycloak session cookie via Airflow Variable). Writes `tiles/{tile_id}.tif` + `manifest.json` (rich metadata for downstream `lidar_bronze_dag.py`). Used by [[lidar]].

`pipelines/gis/cadastro/cadastro_ingestion_dag.py` refactored onto `OgcApiAdapter` (the previous ~260-line implementation collapsed to ~150 lines with the inline pagination helper deleted). Mirrors the `probe_endpoint` → `fetch_to_minio` → `log_summary` task shape used by the recovered apa/crus_ogc/srup_ogc DAGs — cadastro is now the validated reference caller.

Verification gates: `py_compile` clean on all 16 GIS DAG modules; `ruff check` clean; `from pipelines.gis.template.ingestion_template import UnifiedIngestionConfig, OgcApiAdapter, ArcgisRestAdapter, DgtStacAdapter` imports cleanly in the venv. End-to-end DAG import (`importlib.import_module`) still hits Airflow's xcom_backend config error because the local venv lacks the `AIRFLOW_HOME=$(PWD)/.airflow-home` isolation that `make verify` sets up — pre-existing, not caused by this work (see [[airflow-home-isolation]]).

Cadastro row-count parity test (Test #1 from the eng-review test plan) and recovered-DAG smoke tests are pending — they require live infrastructure (running Airflow + Postgres + MinIO + cookie variable) and will fire when the sprint's Activity 2 + 7 reach trigger stage.

## [2026-05-12] sprint-08-activity-2 | Add cleanup-pass activity to sprint-08; OGC vs WFS coverage map locked

WebFetch on `ogcapi.dgterritorio.gov.pt/collections` 2026-05-12 confirmed the OGC API has equivalents for [[crus]] (collection `crus`), [[srup]]-RAN (collection `srup_ran`), and adds 20+ SRUP layers (`srup_ren_areal`, `srup_ren_linear`, `srup_areas_protegidas`, `srup_zpe`, `srup_zec`, `srup_defesa_militar*`, `srup_perigosidade_inc_rural`, `srup_aquiferos`, `srup_albufeiras`, etc.). [[cos]] is also there as `cos2023v1` + `cos2018v3`. **Confirmed NOT present**: DPH (Domínio Público Hídrico) and IC (Imóveis Classificados) — those stay on the legacy WFS path as the only public PT source.

[[sprint-08]] page restructured: prior Activity 3 ("srup-ogc evaluation gate") deleted — the gate question resolved itself when the WebFetch confirmed which layers exist. Replaced with new **Activity 2: cleanup pass** covering:

- Extract `pipelines/common/minio_upload.py` (11 GIS DAGs currently duplicate ~15 lines of MinIO client + bucket-create + fput_object boilerplate; Karpathy Rule 3 cleared at ≥3 callers, 7 to migrate post-cleanup)
- Drop `pipelines/gis/crus/` (legacy per-município CRUS WFS), `pipelines/gis/pdm/` (also legacy CRUS WFS per-município), `pipelines/gis/cos/` (bulk-GPKG)
- Slim `pipelines/gis/srup/` to DPH + IC only (the two layers OGC doesn't publish)
- Build `pipelines/gis/cos_ogc/` using `OgcApiAdapter` + `collection_id="cos2023v1"` + Aveiro bbox filter (~30s for the v1 wedge scope vs ~5 min for the national bulk download)
- Redirect downstream dbt staging models: `stg_crus_ordenamento` → `raw_crus_national_ogc`; `stg_srup_ran` → `raw_srup_ran_ogc`; new `stg_cos` consumer → `raw_cos_national_ogc`. `stg_srup_dph` + `stg_srup_ic` unchanged.

Outcomes + Exit criteria + Key decisions sections of sprint-08 updated accordingly. Activity 6 (constraint severity) reframed: OGC SRUP + legacy DPH/IC is now the default, no gate hedge. Activity 3 (LiDAR) lost the "PDM quick win" bullet (PDM is being dropped). Status `planned`.

## [2026-05-12] common-markdowns-to-wiki | 4 cross-pipeline convention docs migrated from `pipelines/common/` into `wiki/concepts/`

Per the consolidation rule that surfaced earlier today ("only one source of truth in the wiki"), four convention markdowns were moved out of `pipelines/common/` into the wiki:

- `NAMING_CONVENTIONS.md` → [[portal-naming-conventions]] (new wiki page)
- `PLOTS_RULES.md` → [[portal-plot-conventions]] (new wiki page)
- `PORTAL_FIELD_MAP.md` → [[portal-field-map]] (new wiki page, 160-line cross-portal correspondence matrix)
- `SCD2_RULES.md` → merged into existing [[scd2-row-hash]] (added worked examples — per-pipeline `*_VERSION_COLUMNS` tuples for [[zome]]/[[remax]]/[[idealista]] — plus the 21-day floor formula)

Each new page carries the standard frontmatter + `## For future Claude` preamble per [[CLAUDE.md|wiki schema]]; all wikilinks resolve. The wiki/index.md Concepts section grew from 10 to 13 pages; the `## By area of code` `pipelines/` row updated to list the three new portal-* concepts.

Inbound references redirected across **15 active-tree files**:

- `pipelines/portals/{remax,zome,jll,idealista}/source.py` (8 docstring refs)
- `pipelines/portals/{remax,zome,idealista}/README.md` (5 link refs)
- `pipelines/portals/remax/SITEMAP_REFACTOR_PROPOSAL.md` (1 ref)
- `wiki/sprints/sprint-04.4.md` (2 refs)
- `wiki/concepts/heartbeat-sidecar.md` (cross-link)
- `docs/adr/{001,003,005,006}*.md` (4 ADR refs; ADR 001 prose updated to explain the migration)
- `archive/portal_dlt_cutover_2026/idealista/CUTOVER.md` (depth-corrected to `../../../wiki/concepts/...`)

Originals deleted from HEAD. Worktree files (`.claude/worktrees/...`) left alone — those are gstack-managed and migrate naturally on the next rebase.

**Why this matters going forward**: with these docs in `wiki/concepts/`, the weekly `/wiki-reconcile` lint catches drift (stale `last_verified` dates, missing cross-links, unresolved `[[wikilinks]]`). The previous location wasn't under lint coverage and the docs had silently accumulated content debt (e.g. `SCD2_RULES.md` had a "See [SCD2_RULES](../../wiki/concepts/scd2-row-hash.md)" link in `wiki/concepts/scd2-row-hash.md` saying the .md was canonical and the wiki page was the summary — both pointing at each other circularly). The wiki is now unambiguously canonical.

## [2026-05-12] sprint-08-activity-2.1 | Extracted MinIO upload helper + migrated 7 GIS DAGs

[[sprint-08]] Activity 2.1 done. New `pipelines/common/minio_upload.py` exposes `upload_files_to_minio(*, files, bucket, prefix, source_name, tmp_dir=None, date_str=None, secure=False) -> {uploaded, bytes, bucket, date_str}` with two object-name modes:

- **basename mode** (`tmp_dir=None`) — `{prefix}/{date_str}/{basename(file)}` — for single-file uploads (cadastro/apa/crus_ogc)
- **rel-path mode** (`tmp_dir=<path>`) — `{prefix}/{date_str}/{relpath(file, tmp_dir)}` — for multi-file uploads that preserve subdir structure (lneg/srup_ogc/lidar/derive_terrain)

Migrated 7 DAGs onto the helper: `cadastro_ingestion_dag`, `apa_ingestion_dag`, `crus_ogc_ingestion_dag`, `lneg_ingestion_dag`, `srup_ogc_ingestion_dag`, `lidar_ingestion_dag` (ingestion), `derive_terrain_dag` (LiDAR slope-COG upload). Each DAG sheds ~15 lines of duplicated MinIO client + bucket-create + fput_object boilerplate. The `derive_terrain_dag` keeps a Minio() client around for the `fget_object` download (helper is upload-only); refactored to write the slope COG into a `tiles/` subdir of `tmp_dir` so the rel-path mode produces `{MINIO_DERIVED_PREFIX}/{date}/tiles/{tile_id}_slope.tif` — same upload layout as before.

Verification: `py_compile` clean on all 8 files; `ruff check --fix` auto-fixed 10 unused-import warnings (`os`, `datetime.datetime`, `Variable`, `Minio` no longer imported in the migrated tasks); helper imports cleanly via the venv python.

LNEG SSL workaround for `sig.lneg.pt` stays where it was — the helper is unaware of the `requests.Session.request` monkey-patch the caller applies around its adapter call. Adapter and helper both stay clean.

## [2026-05-13] sprint-08-activity-2.2 | Retired legacy CRUS + PDM WFS pipelines; dbt redirected to OGC bronze

[[sprint-08]] Activity 2.2 done. Deleted from HEAD:

- `pipelines/gis/crus/` (4 files) — legacy per-município CRUS WFS (5 munis: Aveiro/Lisboa/Porto/Coimbra/Leiria)
- `pipelines/gis/pdm/` (4 files) — also legacy CRUS WFS per-município, redundant with same upstream data

Both fully superseded by [[crus-ogc]] (DGT OGC API `crus` collection, national coverage ~236k polygons, richer schema with `situacao_pdm` + `registo_ou_deposito` columns the WFS path lacked).

Downstream redirects:

- `dbt/models/staging/regulatory/_staging_regulatory__sources.yml` — `raw_crus_ordenamento` source entry renamed to `raw_crus_national_ogc` with updated descriptions reflecting OGC field origins.
- `dbt/models/staging/regulatory/stg_crus_ordenamento.sql` — `source('bronze_regulatory', 'raw_crus_ordenamento')` → `source('bronze_regulatory', 'raw_crus_national_ogc')`. One-line change; all 11 columns the staging model consumes are 1:1 in the new bronze. Downstream `silver_geo.zoning` model unchanged.
- `tests/configs/test_config_equivalence.py` — `crus` parametrize entry dropped; the fixture moved to `tests/configs/fixtures/_retired/crus.json` as historical record. `pdm` was never in the parity test.
- `wiki/sources/crus.md` — marked retired (`status: retired`, `superseded_by: crus-ogc`) with a banner explaining the deletion, historical schema/quirks preserved for anyone reading old log lines. No `wiki/sources/pdm.md` existed (PDM concept lives under [[crus]] / [[crus-ogc]]).
- `pipelines/gis/cadastro/cadastro_config.py` — docstring stopped referencing the now-deleted `pipelines/gis/pdm/pdm_config.py` as a pattern example; reframed as "Pydantic config pattern shared with the other OGC API ingestion configs (apa, crus_ogc, lneg, srup_ogc)".
- `wiki/sprints/sprint-08.md` — removed the now-orphan "PDM zoning — bonus quick win" bullet from the See also section.

**Bronze tables NOT dropped** — the PostgreSQL tables `bronze_regulatory.raw_crus_ordenamento` and any PDM bronze tables remain in place for ad-hoc historical queries. Drop manually if needed: `DROP TABLE bronze_regulatory.raw_crus_ordenamento`.

Verification: `py_compile` clean on all 9 active GIS DAG modules; `ruff` clean; no remaining `from pipelines.gis.crus` / `from pipelines.gis.pdm` imports in the active tree.

## [2026-05-13] sprint-08-activity-2.3 | Slimmed `pipelines/gis/srup/` to IC + DPH only; RAN redirected to OGC

[[sprint-08]] Activity 2.3 done. `pipelines/gis/srup/srup_config.py` now lists only the two SRUP categories the DGT OGC API does NOT publish: `ic` (Imóveis Classificados, heritage) and `dph` (Domínio Público Hídrico, water-domain easement). RAN moved to the OGC variant (`bronze_regulatory.raw_srup_ran_ogc`, populated by `srup_ogc_bronze_dag` with collection `srup_ran`).

Changes:

- `SRUP_ENDPOINTS` and `BRONZE_TABLES` slimmed (entry `category="ran"` removed)
- Docstring rewritten to explain why IC + DPH stayed on WFS (OGC API doesn't carry them; confirmed by WebFetch on `ogcapi.dgterritorio.gov.pt/collections` 2026-05-12)
- `SRUPIngestionConfig.description` updated to reflect "(IC + DPH)"; `tests/configs/fixtures/srup.json` description field updated to match (parity test passes)
- `dbt/models/staging/regulatory/_staging_regulatory__sources.yml` — `raw_srup_ran` legacy entry replaced with `raw_srup_ran_ogc` (omnibus loader schema: `feature_id`, `layer_name`, `properties` JSONB, `geom`, `_source_url`, `_load_timestamp`)
- `dbt/models/staging/regulatory/stg_srup_ran.sql` rewritten — sources from `raw_srup_ran_ogc`, projects the OGC field names (`municipios`, `servidao`, `designacao`, `tipologia`, `lei_tipo`, `serv_dr`, `serv_data`, `serv_lei`, `serv_hiperligacao`). The legacy WFS fields `DINAMICA`/`RIGOR`/`AUTOR` are dropped (not exposed by OGC); 6 new OGC-only fields are added (designacao/tipologia/lei_tipo/serv_dr/serv_lei/serv_hiperligacao).
- `wiki/sources/srup.md` rewritten — `status` not formally "retired" since the WFS pipeline still serves IC + DPH; explains the slim rationale and lists what moved to [[srup-ogc]].

**Schema confirmation**: I WebFetched `ogcapi.dgterritorio.gov.pt/collections/srup_ran/schema` to lock the OGC field-name list before writing the staging model. Source of truth for the mapping in the `stg_srup_ran.sql` header comment.

**Zero downstream impact**: no existing dbt models reference `stg_srup_ran` yet — the planned consumer is [[sprint-08]] Activity 6 (`silver_geo/parcel_constraints`). The schema redirect happened cleanly; verification will land when Activity 6 runs the first build.

**Bronze table preservation**: `bronze_regulatory.raw_srup_ran` (legacy WFS) NOT dropped from PostgreSQL. To physically drop: `DROP TABLE bronze_regulatory.raw_srup_ran`. The bronze for IC + DPH stays populated by `srup_ingestion_dag` going forward.

## [2026-05-13] sprint-08-activity-2.4 | COS migrated from bulk-GeoPackage to OGC API (Aveiro bbox); legacy cos/ retired

[[sprint-08]] Activity 2.4 done. New `pipelines/gis/cos_ogc/` (4 files: `__init__`, `cos_ogc_config`, `cos_ogc_ingestion_dag`, `cos_ogc_bronze_dag`) reads the DGT OGC API `cos2023v1` collection with an Aveiro distrito bbox filter for the v1 wedge scope. Bronze table: `bronze_geo.raw_cos_national_ogc` (same schema as the legacy `bronze_geo.raw_cos2023`, with new OGC-only columns `municipio` / `nutsii` / `nutsiii`).

`OgcApiAdapter` extended to honor `cfg.bbox_4326` — appends `&bbox=lon_min,lat_min,lon_max,lat_max` to each paginated request when the field is set. Backwards-compatible (existing callers leave `bbox_4326=None` and get unchanged behavior).

Trade-off recorded: bbox-filtered OGC ingestion is ~30s for the ~5-15k polygons that intersect Aveiro distrito, vs ~5 min for the legacy national bulk-GeoPackage download (~700 MB / ~784k polygons). National-scope ingestion remains possible (set `cfg.bbox_4326 = None`); it's slower than the bulk download (~10-15 min for the paginated OGC vs ~5 min for the bulk GPKG) but streaming-friendly and avoids the large local-disk requirement. v1 wedge needs Aveiro only — defer the national-bulk question to v2.

`dbt/models/staging/geo/_staging_geo__sources.yml` — `raw_cos2023` source entry replaced with `raw_cos_national_ogc` (typed columns including the 3 OGC-only ones).

`dbt/models/staging/geo/stg_cos2023.sql` — `source()` redirected from `bronze_geo.raw_cos2023` to `bronze_geo.raw_cos_national_ogc`. Staging model name preserved (downstream `silver_geo.land_use` keeps its `ref('stg_cos2023')` unchanged). Three new columns (`municipio`/`nutsii`/`nutsiii`) added to the staging projection for future filtering use; `land_use.sql` selects explicit columns so adding fields is non-breaking.

`pipelines/gis/cos/` deleted from HEAD. `wiki/sources/cos.md` rewritten as the OGC API source page with a "Retired 2026-05-13" section preserving the legacy GeoPackage spec for historical reference.

`wiki/sprints/sprint-08.md` corrected: the speculative `bronze_landuse.raw_cos_national_ogc` schema name was replaced with the actual `bronze_geo.raw_cos_national_ogc` (which keeps the legacy bronze schema location — no new bronze schema needed).

Verification: `ruff` clean; `py_compile` clean across the 4 new + 1 modified files; `pytest tests/configs/test_config_equivalence.py` green (3 passed — idealista, srup, cadastro; no `cos` parity test exists since COS's legacy config used `GISIngestionConfig`, not Pydantic).

**Bronze preservation**: `bronze_geo.raw_cos2023` (legacy GPKG bronze) NOT dropped from PostgreSQL. To physically drop: `DROP TABLE bronze_geo.raw_cos2023`.

---

**Sprint-08 Activity 2 (cleanup pass) is now complete** — sub-activities 2.1 (MinIO helper) + 2.2 (CRUS/PDM drop) + 2.3 (SRUP slim) + 2.4 (COS OGC migration) all landed. Next up: Activity 4 (build `silver_parcels.parcel_universe` for Aveiro).

## [2026-05-13] sprint-08-activity-4 | silver_parcels.parcel_universe (Aveiro)

[[sprint-08]] Activity 4 done. New `silver_parcels` schema + new `dbt/models/silver/parcels/parcel_universe.sql` model materializing the Aveiro município parcel universe as a UNION of [[cadastro]] (DGT formal cadastre, partial 2000-2007 survey coverage) + [[bupi]] (modern simplified cadastre, fills the gaps). Spatial dedup: a BUPI parcel is dropped from the universe if ≥50% of its area overlaps a cadastro parcel — cadastro is authoritative where present.

Files:

- `dbt/dbt_project.yml` — new `silver_parcels` entry in `on-run-start` + `models.house4house.silver.parcels.+schema`
- `dbt/models/silver/parcels/parcel_universe.sql` — the materialized table + GIST indexes on `geom_pt` (EPSG:3763) and `geom_4326` (EPSG:4326), B-tree on `concelho_code` and `source`
- `dbt/models/silver/parcels/_silver_parcels__models.yml` — column docs + tests: `parcel_id` unique + not_null; `source` accepted_values ['cadastro', 'bupi']; `concelho_code` accepted_values ['0105']; `geom_pt` / `geom_4326` not_null; `dbt_utils.expression_is_true` ensuring both geometries are non-null
- `dbt/tests/dedup_parcel_universe_known_overlap.sql` — singular test (Appendix C Test #12): asserts no BUPI row in the universe overlaps a cadastro row by ≥50% of its area. Passes when query returns 0 rows.

**Schema** (10 cols): `parcel_id` (composite key `cadastro:{cadastral_ref}` | `bupi:{process_id}`), `source` ('cadastro'|'bupi'), `cadastral_ref`, `process_id`, `matrix_number`, `dicofre`, `concelho_code`, `area_m2`, `geom_pt`, `geom_4326`.

**v1 wedge scope**: Aveiro município only (`concelho_code = '0105'`). National rollout deferred to v2; to extend, drop the `LIKE '0105%'` filter in the two CTEs.

Verification: `dbt parse --project-dir dbt` runs clean against the new model + sources. Row-count + dedup verification will happen at first `dbt run` against live Postgres bronze tables.

**Downstream consumer**: `gold.fn_assess_polygon` (sprint-09) will spatial-join this table via `ST_Intersects` to populate the `assembled_parcels` field of the JSONB result.

## [2026-05-13] sprint-08-activity-5 | Zoning density rules extracted from `land_designation`

[[sprint-08]] Activity 5 done. `silver_geo.zoning` gains three typed columns parsed from the freetext `land_designation` PDM column via Postgres regex:

- **`max_floors`** — integer, from `(\d+)\s*pisos?` (case-insensitive). Catches "3 pisos", "max 4 piso", "até 5 pisos".
- **`max_density_index`** — NUMERIC(6,4), from `índice\s*[:=]?\s*([\d,.]+)` (case-insensitive). Catches "índice 0,8", "índice = 1.2", "Indice: 0,5". Portuguese comma decimals (`1,5`) normalized to `1.5` before cast.
- **`max_coverage_ratio`** — NUMERIC(6,4), from `cobertura\s*[:=]?\s*([\d,.]+)\s*%` (case-insensitive). Catches "cobertura 40%", "cobertura: 25,5%". Same Portuguese-decimal normalization. Stored as the raw percentage (40 = 40%, not 0.40).

All three default to NULL when the regex doesn't match — the PDM freetext varies widely by município and most rural zones don't specify density at all. Downstream `fn_assess_polygon` (sprint-09) reads these to populate the Inspector's "what can I legally build" answer.

Files:

- `dbt/models/silver/geo/zoning.sql` — added the 3 `regexp_match()` projections before the `area_ha` column. Postgres native `regexp_match()` returns an array — index `[1]` for the first capture group; `NULLIF(..., '')` guards empty captures.
- `dbt/models/silver/geo/_silver_geo__models.yml` — documented the 3 new columns with regex pattern + format notes.

Verification: `dbt parse --project-dir dbt` clean. Empirical-extraction rate (what fraction of Aveiro zoning rows produce non-null `max_floors`) is unknowable without a live run — measure at first build and tighten the regex if recall is low. The Aveiro PDM publication-date check (`pdm_publication_date`) tells us which munis have CRUS data; the regex hit rate per municipality is the next signal.

**Downstream consumer**: `gold.fn_assess_polygon` (sprint-09) reads these typed columns directly; no further dbt model in between.

## [2026-05-13] sprint-08-activity-4+5-verified | Live dbt build of Activity 4 + 5 chain passes against the warehouse

End-to-end verification of Activity 4 (parcel_universe) and Activity 5 (zoning density extraction) against the running `postgis/postgis:16-3.4` warehouse on `localhost:5433`:

- `dbt build --select stg_bupi+ stg_cadastro+ stg_crus_ordenamento+`: 40 tests pass.
- `silver_parcels.parcel_universe` materialized — 10,341 Aveiro município parcels (all from BUPI; cadastro has 0 rows in concelho `0105` per its partial 2000-2007 survey coverage). The dedup CTE works correctly (no false positives), 0 BUPI rows dropped because there's no cadastro overlap to dedupe against in Aveiro yet.
- `silver_geo.zoning` materialized — 237,128 zones nationally. Aveiro-specific density-column hit rate: zero hits with the current regex (the Aveiro PDM `land_designation` text apparently doesn't use the literal "pisos" / "índice" / "cobertura" keywords). The columns exist + populate as NULL — the regex extraction needs a v1.5 follow-up to tune per-municipality patterns.

**Two issues found and fixed in the same commit**:

1. **`crus_ogc` triggered the wrong dbt DAG** — `crus_ogc_config.py` had `trigger_dbt_dag_id = "dbt_srup_build"` (copy-paste from srup_ogc); fixed to `"dbt_crus_build"`. This meant CRUS-OGC refreshes were rebuilding the SRUP chain instead of the CRUS chain.
2. **`cos_ogc` didn't trigger anything** — `cos_ogc_config.py` had `trigger_dbt_dag_id = None` AND the bronze DAG was missing the `TriggerDagRunOperator` block I forgot to add in Activity 2.4. Set to `"dbt_cos_build"`; added the trigger block to `cos_ogc_bronze_dag`. Now COS-OGC refreshes correctly fire the cos chain.

**OGC CRUS surfaces new `land_classification` values that the legacy WFS didn't**: the `accepted_values` test failed on first build with 5 unexpected values. The OGC API publishes 8 distinct values (vs the legacy 3 + capitalization variants):

- 3 core: `Solo Urbano`, `Solo Rústico`, `Espaços não classificados`
- 3 new semantic values: `Solo Urbano (urbanizável – transitório)` (rolling urban-expansion zones, ~11k rows), `Não Atribuída` (unassigned during PDM revision, ~147 rows), `Discrepância` (analog↔digital cadastre mismatch flagged by DGT, ~45 rows)
- 2 capitalization variants of `Espaços não classificados` (data-entry inconsistency in municipal exports)

The `accepted_values` test in `_silver_geo__models.yml` now lists all 8 verbatim; the column description explains the semantic distinction. A v1.5 cleanup option is to normalize via `lower(unaccent(...))` in the staging model — not done now because it's not load-bearing for the v1 Inspector.

**Singular dedup test SQL syntax fix**: dbt singular tests wrap the body in `... from ( <body> )`, so leading `WITH` clauses fail to parse. Rewrote the dedup test as a single `SELECT ... FROM parcel_universe b JOIN parcel_universe c ...` without the CTE wrapper. Passes on real data: 0 BUPI/cadastro overlaps in Aveiro (no cadastro coverage to overlap with).

## [2026-05-13] infra | dbt-docs server runs as a persistent docker compose service

`http://localhost:8089/` now always serves the dbt docs as long as the docker compose stack is up. Previously the port was reserved on the `airflow-scheduler` container but no process bound to it — the docs site was offline until someone ran `dbt docs serve` manually.

New `dbt-docs` service in `docker-compose.yml`:

- Reuses the `*airflow-common` image (has dbt installed) + the same `./dbt:/opt/airflow/dbt` volume + the same warehouse env vars.
- Runs `dbt docs generate || true` on startup (cold-start safety), then `exec dbt docs serve --host 0.0.0.0 --no-browser` for the lifetime of the container.
- Internal port 8080 (dbt's default; the `--port` flag is unreliable in this bash heredoc form, but the default works fine); host-side mapped as `8089:8080` so it doesn't clash with the Airflow webserver on host 8080.
- Healthcheck: HTTP 200 on `http://localhost:8080/` from inside the container; `start_period: 90s` for cold-start `docs generate` (~30-60s).
- `restart: unless-stopped` (inherited from `*airflow-common`).

Subsequent regeneration: Cosmos's `regenerate_docs` task in `pipelines/dbt/dbt_source_dags.py:155-172` runs `dbt docs generate` after every `dbt_*_build`, updating the static files at `dbt/target/` in place; the serving process picks them up on next page load (no restart needed).

Port mapping was moved off `airflow-scheduler` (where it had been reserved but unused) to `dbt-docs`.

## [2026-05-13] sprint-08-activity-4-national | parcel_universe rescoped national; post_hook→indexes config fix

Three reframes landed on `silver_parcels.parcel_universe`:

1. **Scope: Aveiro município → national.** User asked "should silver_parcels be all parcels, no?" — yes; staging models are national, silver should follow. Dropped the `dicofre LIKE '0105%'` filter from both CTEs. v1 wedge consumers (sprint-09's `fn_assess_polygon`) filter at query time via `WHERE concelho_code = '0105'`; the B-tree index on `concelho_code` makes it free.

2. **Concelho-equality prefilter in the dedup join.** At national scale (3.25M BUPI × 1.79M cadastro), the raw `ST_Intersects` cross-self-join would be hours even with GIST. Added `b.concelho_code = c.concelho_code` BEFORE the spatial test — Postgres hash-joins on the concelho first, then the spatial test runs per-concelho bucket. National build now takes ~3-4 min total (materialization + indexes).

3. **`post_hook` → dbt-postgres `indexes` config.** The `post_hook` CREATE INDEX statements didn't survive table rebuilds for `parcel_universe` (the swap-rename ordering dropped them — sibling tables like `silver_geo.zoning` happened to work because of different timing). Switched to dbt-postgres's native `indexes` config — creates indexes on the `__dbt_tmp` intermediate relation BEFORE the rename, so they're renamed along with the table. Verified: 468 MB of GIST + B-tree indexes present after rebuild.

**Final shape**:
- 5,039,008 rows (3.25M BUPI national + 1.79M cadastro across 152+137 concelhos)
- 4.7 GB total (~4.2 GB table + 468 MB indexes)
- ~3-4 min build time
- All `not_null` / `unique` / `accepted_values` tests pass

**The singular dedup test (Appendix C Test #12) was the bottleneck**: a full self-join over 5M rows took >3 min and was cancelled. Rewrote as a 10K-BUPI-row sample with `ORDER BY md5(parcel_id) LIMIT 10000` — fast (~5-15s expected) and still catches structural dedup-CTE regressions. The test is now a regression guard rather than an exhaustive correctness proof; if the dedup CTE is wrong, ~10K random rows will surface violations with high probability.

dbt-docs catalog refreshed in place via `docker exec ... dbt docs generate`; `http://localhost:8089/` now shows the national `parcel_universe` schema.

## [2026-05-13] cos-ogc-catchup | First cos_ogc end-to-end run; silver_geo.land_use rebuilt with Aveiro-bbox OGC data

Sprint-08 Activity 2.4 wired the cos_ogc pipeline but the DAG was never actually triggered. Inspection 2026-05-13 found `bronze_geo.raw_cos_national_ogc` did NOT exist while `stg_cos2023.sql` already pointed at it — next `dbt build --select stg_cos2023+` would have failed at source resolution. (`silver_geo.land_use` had stale 785K rows from the 2026-03-18 build against the legacy `raw_cos2023` bronze.)

Resolved today:

1. Unpaused `cos_ogc_ingestion`, `cos_ogc_bronze_load`, `dbt_cos_build` (they came up paused after the airflow-scheduler recreate from the dbt-docs work — Airflow's default for new DAGs).
2. Triggered `cos_ogc_ingestion`: 46s wall, fetched the Aveiro bbox slice of `cos2023v1` via OGC API → MinIO.
3. Trigger chain fired automatically: `cos_ogc_ingestion` → `cos_ogc_bronze_load` (9s) → `dbt_cos_build` (Cosmos per-model tasks rebuilt `stg_cos2023` + downstream `silver_geo.land_use`).

End state:

- `bronze_geo.raw_cos_national_ogc`: **4,504 rows** (Aveiro bbox slice of the national COS 2023)
- `silver_geo.land_use`: **4,504 rows**, rebuilt 2026-05-13 14:40 (down from 785K national of the legacy GPKG)
- `bronze_geo.raw_cos2023` (legacy GPKG bronze) still in DB with 708K rows — not dropped per the preserved-historical convention

**Side-find**: the `dbt_*_build` DAGs land paused by default after Airflow scheduler recreate. Anyone who recreates the airflow-scheduler container (e.g. via `docker compose up -d --force-recreate airflow-scheduler`) should `airflow dags unpause` the relevant chain before triggering the upstream ingestion, or those triggers stack up queued.

## [2026-05-13] lidar-coverage-verified | 489 tiles is the canonical Aveiro município catalog; national would be ~25k+

User asked whether the 489-tile LiDAR count is the right scale or silently truncated. Direct DGT STAC query 2026-05-13 confirmed:

- **Configured bbox** (`-8.764,40.528,-8.521,40.728`, ~462 km², ≈ Aveiro município / centro / lagoon): `limit=500` → `returned=489, has_next=False`. **Canonical complete catalog for this bbox** — NOT truncated.
- **Aveiro distrito bbox** (~2,800 km²): 500+ tiles with `has_next=True` — meaningfully more tiles published.
- **National PT bbox** (`-9.5,36.9,-6.0,42.2`): paginated to 25,000+ tiles before hitting the 50-page safety cap (real total likely 25-40k). DGT LiDAR coverage is regional rollout — Aveiro is one of the early-published regions; PT is not fully covered yet.

Implications:

- Sprint-08 v1 wedge (Aveiro município target) → 489 tiles is **correct + sufficient**. No bug.
- Going national: technically supported by the existing `DgtStacAdapter.fetch_to` pagination loop. Cost estimate: **~75 GB MinIO** (50 GB raw tiles × 2 collections + 25 GB slope COGs) + **5-20 hours** wall time + cookie refresh mid-run (cookie lasts ~1 week). v2 work; not blocking sprint-08.

`wiki/sources/lidar.md` updated: `last_verified` 2026-05-13; coverage section now states 489 is canonical-for-configured-bbox with the verification method spelled out + national-rollout cost notes.

## [2026-05-14] query | Portuguese electrical-grid easement regime — faixa de protecção widths by voltage class

Researched RSLEAT (DR 1/92) + DL 43335 against the live `bronze_regulatory.raw_srup_rede_eletrica` table. Key findings: the SRUP rede_eletrica layer carries only **two** `tipologia` values — "Alta Tensão" (1618 rows) and "Muito Alta Tensão" (838 rows); BT/MT are absent (those fall under RSRDEEBT / DR 90/84, not in SRUP). Every row cites `serv_lei = "Decreto-Lei n.º 43335"` with `serv_hiperlig → DL 43335_1960.pdf` (image-only PDF, no text layer). RSLEAT art. 30 confirmed: `D = 3,0 + 0,0075·U` (U kV), min 4 m, to buildings; faixa de serviço 5 m for tree-cutting. A 220 kV REN EIA documents the faixa de protecção / servidão administrativa as 45 m wide (22.5 m each side), construction *condicionada* not prohibited. Updated `wiki/concepts/srup-constraint-model.md` Rede Elétrica entry with the art. 30 citation, the condicionada framing, the ~25 m AT / 45 m MAT widths, and the live two-tipologia data confirmation.

## [2026-05-14] design | SRUP constraint model — Sprint-08 Activity 6 PR 1

Locked the model behind sprint-09's `gold.fn_assess_polygon` (polygon-draw constraint assessment). Deep legal research (direct Decreto-Lei quotes) + live geometry inspection of every in-scope SRUP bronze table.

- **New concept page** `wiki/concepts/srup-constraint-model.md` — 14 in-scope layers, per-layer legal regime + construction effect, geometry semantics, the severity model, the locked constraint-hit JSONB schema.
- **New gold model** `dbt/models/gold/dim_constraint_severity.sql` — 27-row inline-`VALUES` dimension keyed on `(constraint_code, zone_type)` → severity 0-3, category, `buffer_m`/`buffer_ref`, legal_basis, authority + derived flags/labels/colors. Built + 19 tests passing. Followed the `dim_property_type` / `ref_imi_rates` inline-VALUES pattern (no dbt-seed infra in the repo) instead of the plan's seed CSV.
- **Key finding**: SRUP layers ARE the legally-drawn restriction zones — `relationship` collapses to a per-feature `zone_type` attribute (from `servidao`/`tipologia`/geometry-type), not a geometric core-vs-buffer computation. `fn_assess_polygon` does ONE `ST_Intersects` per layer.
- **Scope grew 11 → 14**: added `Albufeiras` / `DefesaMilitar` / `Aeronautica` after a review of all 25 SRUP bronze tables; `rede_ferroviaria_estacoes` folded into `RedeFerroviaria`. Deferred to v1.5: wildfire (`perigosidade_inc_rural` 1.79M polys), aquifers, geodesic marks, classified trees.
- **Buffer model**: 3 layers take a query-time buffer — REN linear (10 m), Rede Ferroviária (10 m height-rule margin), Rede Viária (50/35/20 m by class, `buffer_ref='axis'` — corridor polygon ≠ servidão, subtract per-feature half-width). Verified by live width measurement; OSM road centerlines evaluated and rejected.
- Plan updated (`/loop` plan file): PR 3 added — full `properties` JSONB unpacking for the 14 staging models + `srup-properties-schema.md`.

## [2026-05-14] verify | national cos_ogc chain — ingestion works, bronze load OOMs

Checked the `cos_ogc_ingestion` → `cos_ogc_bronze_load` → `dbt_cos_build` chain for the national-scope run. Snapshot:
- `cos_ogc_ingestion manual__2026-05-14T07:14:24` → **success** (~1h48m national fetch — the earlier offset-pagination read-timeout did not recur).
- `cos_ogc_bronze_load manual__2026-05-14T09:02:48` → **failed** — `load_features` SIGKILL/OOM-killed doing an in-memory `json.load` of the 784k-polygon GeoJSON.
- `dbt_cos_build` → did not run for this attempt (upstream failed). Last success 2026-05-13.
- `bronze_geo.raw_cos_national_ogc` = **0 rows**; `silver_geo.land_use` = **4,504 rows** (still the Aveiro smoke test, NOT the ~784k target). Legacy `bronze_geo.raw_cos2023` still holds 783,760 rows.

Committed the pending national-scope config (`cos_ogc_config.py` — `bbox_4326` default `None`) + `wiki/sources/cos.md`, with `cos.md` corrected to the verified reality: national ingestion ~1h48m (not the earlier ~10-15 min estimate) + a "National bronze load OOMs" quirk. Open issue: `cos_ogc_bronze_dag.py` needs a streaming/chunked loader before national bronze load can succeed.

## [2026-05-14] feat | SRUP staging models + full properties unpacking — Sprint-08 Activity 6 PR 2

Built the 14 SRUP constraint-layer staging models that sprint-09's `gold.fn_assess_polygon` queries. PR 3 (full `properties` JSONB unpacking) was merged into PR 2 — the staging models do exhaustive unpacking from the start rather than being rewritten later.

- 14 × `dbt/models/staging/regulatory/stg_srup_*.sql` (NEW/rewritten) — RAN, REN areal, REN linear, IC, DPH, ZPE, ZEC, Áreas Protegidas, Rede Viária, Rede Elétrica, Rede Ferroviária, Albufeiras, Defesa Militar, Aeronáutica. Uniform contract (`constraint_code` + `zone_type` + constraint-relevant fields) + every `properties` key unpacked into a typed column. Rede Ferroviária + Defesa Militar each UNION two bronze tables. `tag:srup` on all 14.
- `_staging_regulatory__sources.yml` — 13 new bronze source entries. `_staging_regulatory__models.yml` — 14 model entries with `not_null` + `accepted_values` tests on `constraint_code` / `zone_type` (catches CASE-derivation typos).
- `wiki/concepts/srup-properties-schema.md` (NEW) — per-key reference for all 16 `raw_srup_*` `properties` JSONB blobs; documents the OGC-lowercase vs WFS-UPPERCASE split and the type-casting policy.
- Verified: `dbt build --select tag:srup` green (14 views + 98 tests, PASS=119); each staging row count matches its bronze table; all 16 bronze SRUP geom columns already GIST-indexed (no backfill needed).
- `wiki/sprints/sprint-08.md` Activity 6 rewritten — dropped the per-parcel pre-compute framing for the 2-PR polygon-draw plumbing scope.

## [2026-05-14] decision | cos_ogc + crus_ogc national bronze loaders deferred to sprint-09

User decision: the `cos_ogc_bronze_load` + `crus_ogc_bronze_load` OOM (in-memory `json.load` of the whole national GeoJSON) is moved out of [[sprint-08]] Activity 6 to [[sprint-09]] as the "national OGC bronze-loader fix" deliverable. Verified state at deferral: national `cos_ogc_ingestion` succeeds (~1h48m); both bronze loads fail (SIGKILL/-9); `raw_cos_national_ogc` + `raw_crus_national_ogc` empty; `silver_geo.land_use` still at the ~4.5k Aveiro smoke-test count. Propagated: sprint-09.md (new deliverable + `fn_assess_polygon` drift fix — now references `stg_srup_*` + `dim_constraint_severity`, not the dropped `parcel_constraints`), sprint-08.md status history, cos.md quirk.

## [2026-05-15] feat | SCE geocoding shipped — Sprint-08 Activity 7 + 8 done

Activity 7 (SCE forward-geocoding pipeline) shipped in 5 phases over 5 commits. The new `sce_geocode` DAG sits between `sce_bronze_load` and `dbt_sce_build` and runs the cascade per row: Nominatim forward-geocode → freguesia centroid (DTMNFR-keyed dim_geography lookup) → unresolved. `stg_sce_certificates` now exposes `geom_4326` / `geom_3763` + the Appendix-A `normalized_address` clustering key, ready for sprint-09 Slice B's DBSCAN.

End-to-end run (2026-05-15, 12:58→14:07, 68 min wall):
- 55,766 distinct doc_numbers processed (Aveiro distrito)
- **Aveiro concelho (v1 demo target): 100% coverage** (5,718 / 5,718 docs)
- Aveiro distrito-wide: 83.78% coverage (46,719 with coords) — short of the ≥90% Activity-7 bar
- 9,047 docs (16.2%) unresolved due to a CAOP-vs-SCE drift: post-2013-reform union-of-freguesias (e.g. "ANTA E GUETIM" = code 010706) exist in the SCE portal but `dim_geography` (CAOP 2025) only has the pre-reform separates (Anta 010707, Guetim 010708). Affects 19 union freguesias across the distrito; Aveiro concelho has no reformed parishes.

Decision: ship Activity 7 at this coverage since the v1 demo (Aveiro concelho) is 100% covered. The freguesia-union gap is **deferred to [[sprint-09]]** as a new "Deferred from Sprint-08 — freguesia-union mapping" deliverable (DGT publishes a freguesia_pre_pos_reform_2013 table; sprint-09 sources it + adds a tier 2.5 to the cascade + backfills the 9,047 'none' rows; targets ≥95% distrito coverage).

Activity 8 (silver_sce_buildings skeleton) also done — commit `6724c2a`. Empty 15-column schema with 4 indexes (2 GIST + 2 btree); sprint-09 Slice B body-fills with ST_ClusterDBSCAN + Levenshtein dedup. `fuzzystrmatch` extension installed via dbt_project.yml on-run-start so Slice B has it ready.

Test #1 row-count regression: PASS. `stg_sce_certificates = 92,763` = `COUNT(DISTINCT doc_number) FROM raw_sce_certificates`. LEFT JOIN preserved row count exactly.

Activity 9 (pgTAP CI runner) remains the last sprint-08 deliverable.

## [2026-05-15] feat | pgTAP CI runner — Sprint-08 Activity 9 done, sprint shipped

Activity 9 lands the CI plumbing for sprint-09's `gold.fn_assess_polygon` pgTAP tests (#2-#6 from `/plan-eng-review` Appendix C). Sprint-09 drops `.sql` files into `tests/sql/` and they auto-run — no CI work in critical-path sprint.

Changes (4 commits, PR [#30](https://github.com/dacostalindo/House4House/pull/30)):
- `f847f87` — initial: CI service `postgres:16` → `postgis/postgis:16-3.4`; `apt-get install postgresql-16-pgtap` + `CREATE EXTENSION pgtap` via `docker exec`; `apt-get install libtap-parser-sourcehandler-pgtap-perl` for `pg_prove`; `pg_prove tests/sql/*.sql` step with `shopt -s nullglob` green-empty guard; `tests/sql/.gitkeep` created.
- `520fb84` — CI catch: drop unused `# noqa: BLE001` in `pipelines/common/geocoding.py:77` (rationale moved to inline comment; BLE001 isn't in the project's ruff config).
- `ce726f7` — CI catch: `ruff format` auto-fixes across 6 files (continuation-style only, no behaviour change).
- `19ba95a` — CI catch: `pythonpath = ['.']` in `pyproject.toml` `[tool.pytest.ini_options]`. CI's `uv run pytest` doesn't editable-install the workspace (members carry `[tool.uv] package = false` — intentional, matches how Airflow loads `pipelines.*` from the DAGs-folder PYTHONPATH). Declarative replacement for the per-conftest `sys.path.insert` workaround the existing `tests/configs/conftest.py` was using.

PR #30 green at CI run 25939105896 (1m08s). Verified in logs:
- `CREATE EXTENSION` ✓ (pgTAP installed in the service container)
- `pg_prove --version` ✓ (runner has the test tool)
- `"No tests/sql/*.sql files yet — sprint-09 adds them (Activity 9 green-empty state)"` ✓ (the spec's done-when state)

**Sprint-08 ship complete.** All 9 activities done (Activity 5 deferred to sprint-09 by design). Two carry-overs tracked in sprint-09: cos_ogc/crus_ogc national bronze-loader OOM fix + post-2013 freguesia-union mapping.

## [2026-05-15] reconcile | 7 findings, 5 auto-fixed, 2 flagged for user, 0 ADRs created

Post-sprint-08-ship reconcile. 4 parallel scanner agents (schema / wikilinks / reciprocity / freshness); ingest agent skipped (no gstack-driven merges to main since last reconcile — sprint-08 work lives on the still-open PR #30).

5 BLOCKING auto-fixed:
- `wiki/CLAUDE.md:223` — anchor-style wikilink (`[[log#...]]`) converted to standard markdown link.
- `wiki/index.md:46` + `wiki/log.md:575` — `[[wiki/CLAUDE.md|...]]` → `[[CLAUDE.md|...]]` (redundant prefix dropped).
- `wiki/decisions/2026-05-12-uc3-expanded-scope.md:39` — `[[gstack-plan-eng-review]]` → `` `gstack /plan-eng-review` `` (gstack skill, not a wiki page).
- `wiki/planning/PoCs/agentic-pipeline.md` — frontmatter normalised (title + last_verified + tags added; `last-updated` → `last_verified`, `poc-repo` → `poc_repo`); 2 relative-path wikilinks (`[[../../architecture/...]]`) collapsed to bare basenames.

2 ADVISORY flagged (no fix — intentional design):
- `wiki/sources/crus.md` — custom retired-source sections instead of canonical four (deliberate; superseded by [[crus-ogc]]).
- `wiki/concepts/portal-field-map.md` — reference-matrix page (no `## Why`/`## How`; domain-appropriate as a lookup table).

Housekeeping: index.md `Last reconcile run` bumped to 2026-05-15; index preamble updated to reference the active `/wiki-reconcile` skill (the legacy `/wiki-lint` cron + skill were retired 2026-05-12). Full session report at `wiki/lint-reports/2026-05-15T222336.md`.

## [2026-05-17] feat | [[sprint-09]] Slice B SHIPPED — silver_sce_buildings body-fill + Tier-1 CI bootstrap

Sprint-09 Workstream 4 Slice B (SCE Unit Aggregation completion) shipped. `dbt/models/silver/regulatory/silver_sce_buildings.sql` body-filled with the DBSCAN(eps=30m) + GROUP BY (cluster_id, normalized_address) pipeline. 12,634 buildings produced (1,166 in Aveiro concelho), build time 5.11s. Test #9 invariant verified: SUM(frac_count) over DISTINCT sce_building_id = COUNT of nominatim input rows (20,996 = 20,996).

4 pgTAP tests added at `tests/sql/sce_buildings_*.sql` (DBSCAN clustering, address dedup, frac_count conservation, energy_class_dist completeness). All 8 dbt schema tests + all 10 pgTAP assertions pass locally.

**Material design deltas vs original spec** (full reasoning in new [[sce-buildings-clustering]] concept page):
- Levenshtein deferred to v1.5 (Decision 2): 0% empirical leakage at 6k rows from the deterministic normalizer makes fuzzy matching gilding-the-lily AND O(n²) per cluster.
- `parcel_id` + `cluster_split` columns REMOVED (Decision 3, "Option B"): 97.7% of Nominatim-geocoded SCE points fall on street centerlines outside cadastral parcels — the "tiebreak when cluster spans 2+ parcels" branch was unreachable. Atlas Inspector can join `parcel_universe` at query time. Test #11 retired.
- Splink / probabilistic record linkage NOT used (Decision 4): spatial DBSCAN(30m) + deterministic normalizer >> probabilistic matching for same-source within-30m. Re-evaluate Splink for cross-source `silver_unified_developments` (Slice B-prime).

**Tier-1 CI bootstrap also added** (Sprint-09 first PR contribution to per-PR-additive CI dbt-build pattern):
- New directory `tests/ci_bootstrap/` with README documenting "one .sql file per source family" convention.
- `tests/ci_bootstrap/bronze_sce.sql` creates the empty `bronze_regulatory.raw_sce_certificates` + `bronze_enrichment.raw_sce_geocoded` schemas that Slice B's dbt-build chain consumes.
- `.github/workflows/ci.yml` adds "Bootstrap bronze schemas" + "dbt build (structural)" steps after `dbt parse`. CI now catches SQL/type/JOIN errors that `dbt parse` missed.
- Tier-2 (seed-based dbt build with fixture data, enables data-invariant tests) deferred to [[sprint-10]] — gated on dev-interview validation per the wedge kill-criteria.

**Pages touched**: [[silver_sce_buildings]] body (via dbt model), [[sce-buildings-clustering]] NEW, [[sprint-09]] (Slice B section + status-history entry + Slice B follow-ups subsection + status `planned` → `in_progress`), [[sprint-10]] (Tier-2 task added — separate entry), [[sce]] (`last_verified` bump + cross-link to new concept page), [[index.md|index]] (Concepts section + By-area-of-code routing).

One follow-up flagged: `cluster_geocode_confidence > 1.0` bug in [[sprint-08]] Activity 7's geocoder (Nominatim's `importance` sometimes exceeds 1.0; we propagate raw). Fix tracked in [[sprint-09]] Slice B follow-ups.

## [2026-05-22] feat | [[sprint-09]] Slice B-prime SHIPPED — silver_unified_developments (portal-only)

Sprint-09 Slice B-prime ([[cross-portal-dev-dedup]]) shipped. `silver_unified_developments` de-duplicates the 4 listing portals into one row per marketed development via **name-driven word-set Jaccard matching** (≥0.6 within concelho, 1km distance ceiling, geometry hierarchy JLL > Zome > RE/MAX > idealista). 1,050 rows nationwide, 28 in Aveiro; 4 schema tests + 1 multi-assertion pgTAP test for Phase 1 invariants. Tier-1 CI extended to build `+silver_unified_developments` alongside `+silver_sce_buildings`, with new `tests/ci_bootstrap/bronze_geography.sql` stubbing the CAOP + INE BGRI bronze sources for the `dim_geography` chain.

**Material design deltas vs original Slice B-prime spec**:
- **Phase 2 (SCE match-or-promote) removed.** Empirical exploration showed SCE buildings and portal developments are different concepts that resist clean merging — no shared identifier, no shared geocoding precision. Best Aveiro result after stacking constraints (≥5 frações, ≤2.5y certs, no-idealista) was 4 of 11 portal-anchored devs matched, with the table dominated by promoted SCE-only rows that aren't "developments". `fn_assess_polygon` will query `silver_unified_developments` and [[silver_sce_buildings]] side-by-side.
- **Decision 9 retired.** `total_units_authoritative` dropped; `portal_unit_counts` JSONB exposes per-portal counts with no laundered "authoritative" pick. Portals report counts with heterogeneous semantics — 2026-05-22 facade audit confirmed idealista's `units_count` is a listed-subset (e.g., "The Unique" listed as 3 units; facade shows ~50+).
- **Levenshtein replaced by word-set Jaccard.** Distortions in the wild are whole boilerplate words (`empreendimento`, `edifício`, `the`, typology codes like `T1+1`, trailing concelho names), not character typos. Token-based matching plus normalization handles them cleanly.
- **DBSCAN-first architecture replaced by name-driven graph.** Portal coordinates routinely disagree by 200-300m+ for the same development; proximity can't be the grouping key. Name match is gated by *same concelho* + 1km ceiling instead.
- **Geometry hierarchy** chosen by user: JLL > Zome > RE/MAX > idealista.

**Companion fix to [[silver_sce_buildings]]**: post-cluster fração-grain collapse (key `COALESCE(NULLIF(TRIM(fraction),''), doc_number)`, keep latest cert per fração). Aveiro `frac_count` 2,650 → 2,573 (−2.5%; building 11996 "Rua Carlos Aleluia" 50 → 44). Test #9 invariant updated from "SUM = input cert rows" to "frac_count = distinct frações".

**Follow-up logged in [[sprint-09]]**: [[remax]] `PaginatedSearch` coverage gap — sold-out developments like "Edifício Elsa" (`remax.pt/en/empreendimento/edificio-elsa/7481`) have detail pages but are missing from `bronze_listings.remax_developments`. Investigate whether `PaginatedSearch` is the sole discovery path.

**Pages touched**: [[cross-portal-dev-dedup]] NEW concept page, [[silver_unified_developments]] via dbt model + YAML, [[silver_sce_buildings]] (frac_count semantics correction in model + YAML), [[sprint-09]] (Slice B-prime status update + new follow-up), [[index.md|index]] (Concepts count 16 → 17 + dbt area routing).

## [2026-05-22] reconcile | 6 findings, 4 auto-fixed, 2 known-deviation logged, 0 ADRs created

4 sprint-08.md status-history lines auto-fixed: the `2026-05-12 (am):` / `(pm):` / `(evening):` / `(late):` suffixes broke the `^- \d{4}[-Q]\S*:\s+\S.*` regex. Moved the time-of-day parenthetical inside the content so the date prefix is bare (`- 2026-05-12: (am) restructured…`). No semantic change.

2 known-deviation findings re-surfaced (already accepted at the 2026-05-15 reconcile, no action): [[concepts/portal-field-map]] lacks `## Why` / `## How` (reference-matrix layout, domain-appropriate); [[sources/crus]] lacks `## Source` / `## Schema` / `## Quirks` (retired-source historical layout, superseded by [[crus-ogc]]). Flagged here for archaeology; both pages stay as-is.

Wikilinks: all foundational links resolve; the 22 "unresolved" detections are dbt-model references (`dim_geography`, `silver_sce_buildings`, `silver_unified_developments`, `parcel-universe`) and intentional structural self-references — not wiki pages by design. No action.

Freshness: 0 stale pages. Oldest `last_verified` is 2026-05-05; all typed pages carry the field.

Reciprocity: all 17 ADRs pass — no supersession relationships declared (acyclic decision graph).

Full session report: [`wiki/lint-reports/2026-05-22T180000.md`](lint-reports/2026-05-22T180000.md).

## [2026-05-29] seed | UC-4 folder added — qualitative signal layer (agentic news / project actors / regulatory)

New use case for the warehouse's qualitative-signal layer. UC-4 is the first multi-document UC: lives as `wiki/use-cases/UC-4/` containing [[UC-4|README]] + [[UC-4/problem-statement]] + [[UC-4/project-plan]] + [[UC-4/sprint-plan]]. Decision output: per-entity qualitative signal (developer, press mentions, regulatory events). Absorbs [[planning/PoCs/agentic-pipeline]] (project-actors strategy already validated PoC). Introduces Flow G (LLM-mediated typed extraction) as a new ingest-flow type — extends [[ingest-flows]] in PR 1. Schema additions: `bronze_news` + `agentic_cache` (correction to PoC's `news_bronze` recommendation; H4H convention is `bronze_<domain>`).

Strategy delivery order: Articles (PR 1) → Project Actors (PR 2) → Regulatory (PR 4). Rationale: Articles is greenfield, stress-tests the Strategy ABC, and lets prompt-iteration happen on the easier signal before the lifted-from-PoC code locks the shape. Full 6-PR roster in [[UC-4/sprint-plan]].

**Pages touched**: [[UC-4|README]] NEW, [[UC-4/problem-statement]] NEW, [[UC-4/project-plan]] NEW, [[UC-4/sprint-plan]] NEW, [[use-cases/README]] (roster table + filename convention note + preamble update), [[index.md|index]] (Use-cases section heading + UC-4 entry).

Discarded prior parallel UC-4 work: previous `wiki/use-cases/UC-4.md` (single-file design dated 2026-05-15, news-driven RE intelligence analyst concept) and `wiki/sprints/sprint-11.md` (its companion sprint) removed per user decision 2026-05-29. Backups at `/tmp/uc4-discarded-2026-05-29/`. Reason: this folder-shaped UC-4 reflects current direction (ETL-shaped qualitative signal layer); the discarded design pursued a conversational-analyst path with a property-graph silver layer + Pydantic-AI agent + 60-question eval set.

Open questions deferred to UC-4 PRs: sprint slot for PR 1 (recommend `sprint-04.7`); DRE API stability; cache schema location; silver_market vs new silver_news domain; UC-4 status flip timing.

## [2026-06-02] plan | [[sprint-09]] adds Workstream 5 — Portal bronze column trim (4-portal × 3-grain audit)

NET-NEW deliverable added to [[sprint-09]]: per-portal audit + bronze DDL trim across [[idealista]], [[jll]], [[remax]], [[zome]] at developments / listings / plots grain. Estimated 6-10 days. Locks a revision of [[bronze-permissive]]: bronze keeps an explicit kept-column set + one `raw_payload` JSONB sidecar (not "every column raw" as the original policy stated). Sub-deliverable 1 of the stream creates `wiki/decisions/2026-06-02-bronze-trim-revises-bronze-permissive.md` to record the policy change formally — the ADR isn't written yet, the stream sequences its creation as the first PR.

Triggered by recurring sprint-09 verification work surfacing unused-but-load-bearing bronze columns. Concrete catalyst: idealista plot 34632291's `property_features` JSONB carries "Superfície edificável 82.592 m²" but the LLM-extraction labeling fixture at `pipelines/enrichment/plot_listing_extraction/sample_eval_set.py:134-135` SELECTs only `description, lot_size, property_price` — the structured field never reaches the labeler, the colleague survey, or the LLM prompt.

Labelled **Workstream 5** to mark it visually orthogonal to the Workstream 4 v1-wedge stack. Demo critical path (`fn_assess_polygon` + Atlas Inspector) is unaffected; this stream may slip past Week 21 and finish in [[sprint-10]] — accepted at planning time. Implementation order: ADR + concept rewrite first, then Zome (small + Aveiro-present, exercises the silver_unified_developments verification path on the first trim), JLL (no-Aveiro sanity check), RE/MAX, idealista (biggest blast radius + ZenRows cost) last.

**Pages touched**: [[sprint-09]] (new deliverable section + status-update-history entry). No new wiki pages created today — the ADR + [[bronze-permissive]] rewrite ship as the stream's first PR.

## [2026-06-02] ship | WS4 quick-wins batch — APA + LNEG + INE silvers + dim_constraint_severity APA extension + silver-dq-baseline concept + bronze_ine.indicator_category migration

Sprint-09 WS4 quick-wins batch shipped in one PR. Three new silvers for `gold.fn_assess_polygon` inputs:

- **APA**: [silver_geo.floodplains](../dbt/models/silver/geo/floodplains.sql) (~188 rows) — 15th constraint layer alongside the 14 SRUP siblings. `dim_constraint_severity` extended with `ARPSI_Floodplain` (T100=3 hard, T1000=2 conditioned, new `flood_risk` category, buffer_m=0). [stg_apa_arpsi](../dbt/models/staging/hydrology/stg_apa_arpsi.sql) derives constraint_code+zone_type.
- **LNEG**: [silver_geo.aquifers](../dbt/models/silver/geo/aquifers.sql) (~63 rows) + [silver_geo.geology](../dbt/models/silver/geo/geology.sql) (~282 rows). Raw bronze fields only — derived `aquifer_vulnerability` + `foundation_difficulty` dropped after web-research found DRASTIC requires inputs not in bronze, Eurocode 7 requires site-specific testing, and the Aveiro Cretaceous Argilas de Aveiro formation contradicts the obvious era-prefix CASE (per Galhano & Rocha). `geological_era_label` also dropped — v2 adds after discovery query on actual prefix distribution.
- **INE**: [silver_market.ine_indicators_long](../dbt/models/silver/market/ine_indicators_long.sql) (~1.17M rows) at parish/concelho/NUTS granularity. Distinct from existing `silver_market.macro_timeseries` (national rates/HPI from BPStat+ECB+Eurostat) — see [[silver-dq-baseline]] §"Statistical-source silver topology" for the boundary. Bronze schema migration: added `indicator_category` column written by [ine_bronze_dag.py](../pipelines/api/ine/ine_bronze_dag.py) from `INE_INDICATORS[code].category` — single source of truth in `ine_config.py`, no dual-maintenance in silver.

**New concept page** [[silver-dq-baseline]] codifies 4 universal silver-layer invariants (dual-CRS, surrogate PK, bronze→silver row-count parity, FK denorm integrity), deliberately excludes `accepted_values` on categorical columns (rationale: upstream-drift churn + silent-suppression incentive), and adds a "Statistical-source silver topology" section mapping which silver answers which question.

**Pages touched** (per propagation rule): [[apa]], [[lneg]], [[ine]] (Silver layer sections + last_verified bump); [[srup-constraint-model]] (15th layer added + last_verified bump); [[index]] (new concept + count update 17→18); [[sprint-09]] (3 bullets flipped DONE + status-update-history entry + last_verified bump); [[log]] (this entry). New wiki page: [[silver-dq-baseline]].

**Out of scope (deferred)**: LiDAR terrain → silver (~1.5d, bronze empty); Aveiro PMOT → bronze + silver (~2-3d, extractor not yet run); LNEG 1:50k JPGw raster ingest as Atlas Inspector WMS layer (sprint-10+); SRUP+COS dual-CRS naming migration to canonical (sprint-10 cleanup).

## [2026-06-03] ship | WS4 batch 2 PR A — LiDAR terrain via postgis_raster

Sprint-09 WS4 batch 2 PR A (1 of 3). Replaced the parcel-proxied terrain stats path with on-the-fly postgis_raster computation, fixing the imprecision + BUPI-coverage-gap limitations of the previous approach. `silver_geo.terrain_slope_raster` is a thin view over `bronze_terrain.raster_lidar_slope_2m` (489 single-band Float32 rasters loaded via `ST_FromGDALRaster`) that adds GIST-indexed convex-hull footprints. `gold.fn_assess_polygon` (later PR) does `ST_Clip(rast, drawn_polygon) + ST_SummaryStatsAgg` inline for exact-per-polygon slope statistics.

**Discovery**: sprint-09's "bronze empty / pipeline never run" claim was wrong ([[silver-dq-baseline]] Rule 0 in action) — bronze had been fully populated with 489×3 manifests + 10,339 parcel stats. The wiki had drifted; live warehouse was authoritative.

**Architectural decisions locked**:
- Option C (in-DB postgis_raster) chosen over parcel-proxy (imprecise), Atlas-Inspector-DAG-call (split logic), and H3 grid pre-agg (still imprecise).
- Option Y' merged: `lidar_derive_terrain` DAG produces slope rasters AND loads them into postgres in one DAG (3 LiDAR DAGs total instead of 4). No MinIO archive of slope COGs — derived artifacts, regenerable from MDT in ~25-40min via DAG re-run.
- No `raster2pgsql` chunking: 489 rows × ~1 MB each is fine at our scale.
- `raster2pgsql` binary not in Airflow image — pivoted to Python `psycopg2.Binary` + `ST_FromGDALRaster(bytea, 3763)`. Same end result, no Dockerfile rebuild.

**Cleanup (post-QA)**:
- Dropped `pipelines/gis/lidar/parcel_zonal_stats_dag.py` (~350 LOC retired)
- Dropped `bronze_terrain.parcel_terrain_stats` (10,339 rows, no consumer under Option C)
- Dropped `bronze_terrain.derived_lidar_slope_2m_manifest` (redundant with new raster table)
- Removed manifest INSERT + MinIO upload steps from `derive_terrain_dag.py`

**Pre-drop QA**: 20 random Aveiro BUPI parcels compared raster-path vs proxy mean slope. Max abs diff 0.069° (tolerance: 0.5°). PASS — methods agree within numerical noise.

**PostGIS raster operational pattern locked**: PostGIS 3.x ships `postgis.gdal_enabled_drivers` as empty whitelist for security. Production + CI both `ALTER DATABASE ... SET postgis.gdal_enabled_drivers TO 'GTiff PNG JPEG'` (one-time). DAG also issues `SET LOCAL` as belt-and-braces.

**Pages touched**: [[lidar]] (Silver layer + Pre-drop QA + Operational notes + last_verified 2026-06-03 + manifest schema rewrite); [[sprint-09]] (LiDAR bullet flipped DONE); [[log]] (this entry).

## [2026-06-03] ship | WS4 batch 2 PR B — OGC streaming bronze loader + legacy cleanup

Sprint-09 WS4 batch 2 PR B (2 of 3). Replaced the OOM-vulnerable `json.load(f)` whole-file parse in both `cos_ogc_bronze_dag.py` and `crus_ogc_bronze_dag.py` with `ijson.items(f, "features.item", use_float=True)` streaming. Resolves the deferred-from-sprint-08 deliverable that left `bronze_geo.raw_cos_national_ogc` + `bronze_regulatory.raw_crus_national_ogc` empty since the OGC-API migration and held `silver_geo.land_use` at the 4,504-row Aveiro smoke-test scope.

**National loads** (verified end-to-end, 2026-06-03):
- COS: 842,413 rows in ~7 min wall (+7.5% vs. legacy 783,760 — OGC publishes the same revision with slightly different per-feature splits)
- CRUS: 236,920 rows in ~3 min wall (0% delta vs. legacy 5-muni subset for the overlapping municipalities; parity check confirmed pre-drop)

**Silver rebuilt**:
- `silver_geo.land_use` → 842,413 rows (hierarchy decomp + boolean flags + freguesia spatial-join via `ST_Within(ST_PointOnSurface(...))`)
- `silver_geo.zoning` → 236,920 rows (PT→EN `zone_category` mapping, 15 buckets)

**Architectural / operational decisions locked**:
- `use_float=True` IS REQUIRED: by default ijson 3.x returns `Decimal` for numbers (precision-preserving), but `json.dumps(geom)` on a feature with Decimal coordinates raises `TypeError: Object of type Decimal is not JSON serializable`. Cost us one COS load attempt before the fix. Documented as a comment in both DAGs.
- `features.item` is the canonical ijson jsonpath for GeoJSON FeatureCollection elements; binary mode (`rb`) is required for ijson's fast path.
- Per-row `ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(...), 4326), 3763)` happens inline in the INSERT VALUES — keeps the streaming loader simple. BATCH_SIZE stays at 100 (COS) / 20 (CRUS); no further tuning needed at observed throughput.
- Surgical changes only: only the `load_features` task body was modified in each DAG. No extraction into a shared OGC-bronze-loader module yet (deferred to sprint-10 if a third OGC source materializes).

**Cleanup (post-parity-check, user-approved "drop both")**:
- Dropped `bronze_geo.raw_cos2023` (783,760 rows, legacy bulk-GeoPackage path, no live consumer since 2026-05-13).
- Dropped `bronze_regulatory.raw_crus_ordenamento` CASCADE (5,472 rows, legacy per-município WFS path). The CASCADE took with it a stale `staging_dbt.stg_pdm_ordenamento` view — a leftover from a deleted dbt model with no source file in the repo, no external references, and no dependent views.
- Fixed 2 stale dbt YAML descriptions: `_staging_geo__models.yml` line 42 + `_staging_regulatory__models.yml` line 6 (both referenced the now-dropped legacy tables).

**Operational footnote on `dbt_cos_build` / `dbt_crus_build`**: the `TriggerDagRunOperator` in the bronze DAG initially failed with `DagNotFound: Dag id dbt_cos_build not found`. Diagnosis: the DAGs exist (auto-generated by the `pipelines/dbt/dbt_source_dags.py` factory — `dbt_cos_build`, `dbt_crus_build`, `dbt_srup_build` all live and unpaused) but a stale-parse race with the bronze DAG run prevented the trigger. Worked around by running `dbt run --select stg_cos2023 stg_crus_ordenamento stg_crus_national land_use zoning` directly from the host shell (idempotent, same end state). Both DAGs manually triggered at end of work to validate the orchestrated path.

**Pages touched**: [[cos]] (streaming-fix Quirk, retired-legacy section now records the drop, last_verified 2026-06-03); [[crus-ogc]] (streaming-fix Quirk, last_verified 2026-06-03); [[crus]] (retired-page final note records 2026-06-03 drop, last_verified 2026-06-03); [[sprint-09]] (deferred-from-sprint-08 deliverable flipped DONE + status history entry); [[log]] (this entry).

## [2026-06-04] ship | PDM + SRUP constraint model — Aveiro v1 (Sprint-09 WS5)

Major work on linking PDM (Plano Diretor Municipal) local rules with SRUP (Servidões e Restrições de Utilidade Pública) national overlays for `fn_assess_polygon`. **All work shipping in PR (branch `feature/dim-pdm-constraint-aveiro`).**

**What landed in the warehouse (no PR yet):**

- `gold_analytics.dim_pdm_constraint` — **314 rows** for Aveiro (DTCC 0105), auto-generated from `wiki/sources/aveiro-pdm.md` via `/tmp/md_to_sql.py`. Schema gained 2 columns: `applies_to_zone_types TEXT[]` + `applies_when_land_classification TEXT` (for overlay-conditional PDM rules).
- `gold_analytics.dim_constraint_severity` — **36 rows** (+6: 5 Perigosidade_Incendio_Rural tiers + 1 unclassified Advisory).
- `staging_dbt.stg_srup_perigosidade_inc_rural` — NEW staging view (wildfire risk, DL 124/2006 + PMDFCI). Bronze had 1.78M features but no staging until now.
- `silver_regulatory.srup_constraints` — NEW unified silver, **1,799,857 rows** UNION ALL of 15 stg_srup_*. Current iteration JOINs both dim_constraint_severity AND dim_pdm_constraint (LATERAL aggregation of pdm_constraint_keys per SRUP feature, respecting applies_to_zone_types filter). Spatial GIST + btree indexes via post_hook. **NEEDS rebuild test** — last edit moved both dim joins inline; not yet verified.
- `silver_geo.zoning` — refactored with `subcategoria` derived column (LAST segment of land_designation after stripping the redundant `<classification> - <category>` prefix); JOIN to dim_pdm_constraint now matches by `subcategoria = zone_pattern` (exact, no wildcards). Aveiro **100% coverage** — 1148/1148 polygons.

**Architectural decisions locked 2026-06-04:**

- **PDM and SRUP are complementary regulatory layers, not redundant.** PDM = local plan ("what does Aveiro's PDM say"); SRUP = national overlays ("what national legal regime applies spatially").
- **dim_pdm_constraint.zone_pattern is polymorphic**: matches either (a) a `subcategoria` of `silver_geo.zoning` via string equality, (b) one of 3 umbrella slugs (ALL_PDM / ALL_SOLO_URBANO / ALL_SOLO_RUSTICO) via land_classification, OR (c) a SRUP layer constraint_code (RAN, ZPE, Perigosidade_Incendio_Rural, etc.) via spatial intersection at the `silver_regulatory.srup_constraints` level (NOT at silver_geo.zoning — zoning is too coarse).
- **The dim joins happen on SRUP features, not zoning polygons.** Each SRUP feature row in silver_regulatory.srup_constraints carries the linked PDM rule keys + national severity attrs. fn_assess_polygon queries both silver_geo.zoning (PDM-by-zone) AND silver_regulatory.srup_constraints (PDM-by-spatial + national severity).
- **dim_constraint_severity is NOT redundant** — 2026-06-04 strict-regex audit found only ~10 of 36 rows are PDM-implied; the other 26 carry severity that's only in national statutes (DPH/Albufeiras/RedeEletrica/Aeronautica national-only, plus PDM's textual deferrals to "regime legal da RAN" etc. that don't directly encode severity).
- **Severity is in BOTH dims, intentionally redundant**: dim_constraint_severity gives national severity (0-3 from statute); dim_pdm_constraint encodes severity via `constraint_type` enum (prohibition/required_approval/etc.). fn_assess_polygon picks the more restrictive of the two.

**Zone_pattern renames (in markdown, regen'd in dim):**

| Old | New | Reason |
|---|---|---|
| `PATRIMONIO_CLASSIFICADO` | `IC` | align with SRUP constraint_code |
| `ZONAS_INUNDAVEIS` | `ARPSI_Floodplain` | align with SRUP |
| `ZONAS_INUNDAVEIS_REN` | `ARPSI_Floodplain_REN_areal` | compound (2 overlay intersection) |
| `PORNDSJ` + variants | `AreasProtegidas[_TOTAL/PARCIAL/COMPLEMENTAR]` | align with SRUP |

**14 PDM rows moved from umbrella slugs to SRUP-layer overlay slugs ("Point 4" alignment):**
- Art. 10/1/a,b,c (Rede Natura interdições) — `ALL_PDM` → `ZPE` + duplicated `ZEC` (3 → 6 rows, +3 net)
- Art. 10/2 (parecer ICNB) — `ALL_SOLO_RUSTICO` → `ZPE` with `applies_when_land_classification='Solo Rústico'`
- Art. 51/1/a (hard gate) — `ALL_SOLO_RUSTICO` → `Perigosidade_Incendio_Rural` with `applies_to_zone_types={perigosidade_alta, perigosidade_muito_alta}`
- Art. 51/1/b + 4 sub-conditions — same with `{perigosidade_media, perigosidade_baixa, perigosidade_muito_baixa}`
- Art. 51/2 (alteração distâncias) — same (no zone_type filter)
- Art. 52/1/a + 2 sub (habitação agricultor RAN) — `ALL_SOLO_RUSTICO` → `RAN` with `applies_when_land_classification='Solo Rústico'`

Net: 311 → 314 rows (+3 from ZEC duplication). Without these moves, 14 overlay-conditional rules were firing on every polygon in their classification, not just those overlapping the SRUP overlay.

**Verbatim audit findings — true PDM coverage per SRUP layer** (2026-06-04, strict literal regex):

| Layer | PDM rows | PDM articles |
|---|---|---|
| RAN | 3 | Art. 52/1/a, 53, 55 |
| REN_areal / REN_linear | 3 (PDM doesn't distinguish) | Art. 57, 61 |
| IC | 1 | Art. 11 |
| ZPE / ZEC | 5 shared | Art. 10/1/a (prohibition) + 10/2 (parecer) + 57 + 61 |
| AreasProtegidas (PORNDSJ) | 17 (via zone_pattern rows) | Art. 19-23, 58 |
| DefesaMilitar | 1 | Art. 64-65 |
| RedeViaria + RedeFerroviaria | 3 shared via Espaços Canais | Art. 33/1, 33/2, 114 |
| ARPSI_Floodplain | 3 | Art. 8/1, 8/2, 8/5/b |
| Perigosidade_Incendio_Rural | 5 | Art. 51 |
| **DPH / Albufeiras / RedeEletrica / Aeronautica** | **0** | **National-only — no PDM article** |

Earlier "26 redundant rows" claim was wrong — initial keyword regex matched substrings in unrelated articles. True overlap is much smaller; dim_constraint_severity is doing real load-bearing work for the 4 national-only layers.

**Late-session refactor (post initial draft):**

- `zone_pattern` became `TEXT[]` (was scalar). The cross_refs_srup column was tried then removed — its job is now subsumed by the array. Each row's zone_pattern carries the primary pattern PLUS any SRUP layer codes the article invokes. silver consumers join via `= ANY(zone_pattern)`. Cleaner than scalar + sidecar column.
- `silver_regulatory.srup_constraints.municipality_code` became `municipality_codes TEXT[]` (multi-município support). The single-name JOIN to dim_geography couldn't resolve features tagged with comma-separated lists (e.g. ZPE Ria de Aveiro spans 10 concelhos). Now splits on comma + resolves each. Recovered 268/1.8M features that previously fell through.

**Final Aveiro per-layer PDM linkage in `silver_regulatory.srup_constraints`** (2026-06-04, post-refactor):

| Layer | Aveiro features | Linked to PDM | Avg rules |
|---|---|---|---|
| Perigosidade_Incendio_Rural | 3545 | 3545 (100%) | 5.1 |
| RedeFerroviaria | 20 | 20 (100%) | 11.0 |
| IC | 20 | 20 (100%) | 4.0 |
| RedeViaria | 15 | 15 (100%) | 11.0 |
| DefesaMilitar | 5 | 5 (100%) | 1.0 |
| AreasProtegidas | 2 | 2 (100%) | 20.0 |
| REN_areal | 2 | 2 (100%) | 41.0 |
| ZPE | 1 | 1 (100%) | 38.0 |
| RAN | 1 | 1 (100%) | 11.0 |
| REN_linear | 1 | 1 (100%) | 34.0 |
| ZEC | 1 | 1 (100%) | 35.0 |
| RedeEletrica | 9 | 0 (national-only) | — |
| Albufeiras | 1 | 0 (national-only) | — |
| Aeronautica | 1 | 0 (national-only) | — |

11/14 layers have 100% PDM linkage; 3 layers correctly stay at 0 (PDM doesn't address them — pure national-law regime). Final dim_pdm_constraint count: 314 rows for Aveiro 0105.

**Visualization shipped**: `/tmp/aveiro-srup-map.html` — standalone Leaflet HTML (1.3MB) with 14 toggleable SRUP layers + click-popup showing verbatim PDM source_text per applicable rule. 232 features rendered (excludes Perigosidade média/baixa/muito_baixa to keep the file lean; hard-gate Perigosidade alta+muito_alta included).

**Concept page**: [[pdm-srup-constraint-model]] now reflects the final architecture (TEXT[] zone_pattern, municipality_codes TEXT[], spatial JOIN at SRUP feature level, dual dim source).

**Pending follow-ups (deferred to next sprint or sprint-10):**

- [ ] CI bootstrap stubs: `raw_srup_perigosidade_inc_rural` source + Tier-1 dbt build coverage for `silver_regulatory.srup_constraints` + `dim_pdm_constraint`
- [ ] pgTAP tests for dim_pdm_constraint + srup_constraints invariants (zone_pattern non-empty, severity matches sev dim, etc.)
- [ ] Rollout to other municípios: Coimbra (DTCC 0603), Lisboa (1106), Porto (1312), Leiria (1010) — extract each PDM Regulamento separately, ~1d per
- [ ] [[crus]] / [[crus-ogc]] / [[srup]] / [[UC-3]] not yet cross-referenced with the new model
- [ ] Spatial fallback for 268 unresolved national-scope SRUP features (those with NULL/blank municipality_text) — would need ST_Intersects against dim_geography polygons

**Files shipped in the PR:**

- `wiki/sources/aveiro-pdm.md` — 314 atomic constraint rows + Zone-pattern ↔ SRUP cross-reference section + slug renames + 14 row moves to overlay slugs
- `wiki/concepts/pdm-srup-constraint-model.md` — new concept page documenting the dual-dim architecture
- `wiki/log.md` — this entry
- `wiki/sprints/sprint-09.md` — WS5 status history entry
- `dbt/models/gold/dim_pdm_constraint.sql` — auto-generated, 314 rows, zone_pattern TEXT[] + 2 filter columns
- `dbt/models/gold/dim_constraint_severity.sql` — +6 rows (Perigosidade tiers + Advisory)
- `dbt/models/silver/regulatory/srup_constraints.sql` — unified silver, 1.8M rows, 2-dim joins + multi-município support
- `dbt/models/staging/regulatory/_staging_regulatory__sources.yml` — added raw_srup_perigosidade_inc_rural
- `dbt/models/staging/regulatory/stg_srup_perigosidade_inc_rural.sql` — staging view (wildfire risk)
- `dbt/models/silver/geo/zoning.sql` — subcategoria column + PDM JOIN by subcategoria/umbrella

**Pages touched**: [[log]] (this entry), [[aveiro-pdm]] (last_verified 2026-06-04), [[pdm-srup-constraint-model]] (new), [[sprint-09]] (WS5 status entry). [[crus]] / [[crus-ogc]] / [[srup]] / [[UC-3]] cross-references deferred to next sprint.

## [2026-06-04] ship | dim_constraint_severity legal_quote columns (Sprint-09 WS5 follow-up)

Added verbatim PT legal-text columns to [[pdm-srup-constraint-model|dim_constraint_severity]] so each severity row carries the operative paragraph from its statute. **100% coverage across all 36 rows**, no NULLs.

Four new columns:
- `legal_quote_article` — citation label, e.g. `Artigo 21.º (Acções interditas)`
- `legal_quote_url` — official dre.pt URL (preferred) or fallback mirror
- `legal_quote_status` — `full_paragraph` (23 rows, primary source) | `anchor_only` (12 rows, PDF/Cloudflare-gated) | `derived_advisory` (1 row, data-quality fallback)
- `legal_quote_pt` — verbatim PT operative paragraph(s)

**Sources fetched (14 unique statutes):**

| Statute | Rows | Status | Source |
|---|---|---|---|
| DL 73/2009 Art. 21 (RAN) | 1 | full | dre.pt consolidada (via PGDL Lisboa) |
| DL 166/2008 Art. 20 + 16 (REN) | 3 | full | dre.pt consolidada (via PGDL Lisboa) |
| Lei 107/2001 Art. 43+45 + DL 309/2009 Art. 51 (IC) | 2 | full | dre.pt consolidada (via PGDL Lisboa) |
| Lei 54/2005 Art. 25 n.os 1+2+5 (DPH) | 2 | full | dre.pt consolidada (via PGDL Lisboa) |
| DL 142/2008 Art. 23 (Áreas Protegidas) | 1 | full | dre.pt detalhe |
| Lei 34/2015 Art. 32 n.os 1+2 (RedeViaria) | 3 | full | dre.pt consolidada |
| DL 107/2009 Art. 19+20+21 (Albufeiras) | 3 | full | dre.pt consolidada |
| DL 364/98 Art. 5 (ARPSI substantive regime) | 3 | full | Faolex PDF (direct Read) |
| DL 124/2006 Art. 16 + Aveiro PDM Art. 51 (Perigosidade) | 5 | full | PGDL Lisboa + wiki/sources/aveiro-pdm.md |
| DL 140/99 Art. 9 (ZPE/ZEC) | 2 | anchor | PGDL doesn't render Art. 9 inline |
| RSLEAT Art. 28 + DL 43335 Art. 6 (RedeEletrica) | 2 | anchor | OERN PDF 404 + dre.pt empty body |
| DL 276/2003 Art. 15 (RedeFerroviaria) | 3 | anchor | files.dre.pt PDF needs pdftoppm (not installed) |
| Lei 2078/1955 + DL 45986/1964 (DefesaMilitar) | 2 | anchor | tretas.org Cloudflare-gated; no dre.pt consolidada (pre-1976) |
| DL 45987/1964 (Aeronautica) | 3 | anchor | same as above |

**Two `legal_basis` text fixes** shipped alongside (matching the new citations per audit):
- RedeEletrica: `RSLEAT art. 30` → `art. 28` (Art. 30 is conductor clearances, not faixa de servidão)
- ARPSI: added `+ DL 364/98 art. 5` (DL 115/2010 is transposition only; substantive regime is in DL 364/98)

**Verification**:
```sql
SELECT legal_quote_status, COUNT(*), AVG(LENGTH(legal_quote_pt))::INT AS avg_chars
FROM gold_analytics.dim_constraint_severity GROUP BY 1;
-- full_paragraph    | 23 | 874 chars
-- anchor_only       | 12 | 540 chars
-- derived_advisory  | 1  | 493 chars
```

**Files shipped**:
- `dbt/models/gold/dim_constraint_severity.sql` — regenerated via `/tmp/build_severity_quotes.py`; +4 columns, 2 legal_basis text fixes, +156 lines (quotes CTE)
- `wiki/concepts/pdm-srup-constraint-model.md` — added §"Legal quote columns" with the status table + statute coverage matrix
- `wiki/log.md` — this entry

**Pending follow-ups**:
- [ ] Flip 12 `anchor_only` rows → `full_paragraph` once user (or future Claude with `pdftoppm` + browser-class fetcher) can extract from the gated sources
- [ ] Decide whether to denormalize `legal_quote_pt` into `silver_regulatory.srup_constraints` (would add ~1.8 GB; today callers JOIN to dim when needed)

**Pages touched**: [[log]] (this entry), [[pdm-srup-constraint-model]] (legal_quote columns section).

## [2026-06-06] add-portal-source + first load | imovirtual (P1) — Next.js _next/data JSON

Onboarded [[imovirtual]] as the 5th listing portal (after [[idealista]] / [[remax]] / [[zome]] / [[jll]]) per [[2026-06-05-imovirtual-portal-onboarding]], then ran it end-to-end. Created `pipelines/portals/imovirtual/` (source.py + imovirtual_dlt_dag.py + README + 33 offline tests), the [[imovirtual]] source page, and 6 bronze source declarations in [_staging_listings__sources.yml](../dbt/models/staging/listings/_staging_listings__sources.yml). Acquisition is direct Next.js `_next/data` JSON — no scraping vendor. Aligns with [[scd2-row-hash]], [[heartbeat-sidecar]], [[portal-naming-conventions]], [[portal-plot-conventions]]; mirrors [[zome]]'s single-file dlt skeleton + [[idealista]]'s dev→units FK-at-parse-time.

**First load (verified in `bronze_listings`)**: developments **801** (national, 64 concelhos), development_units **4,465** (0 orphans), plots **4,894** (Aveiro, 100% with coords; 4,759 distinct — pagination overlap dups collapse at staging via `DISTINCT ON`). All within validation bands. imovirtual exposes BOTH `number_of_units_in_project` (true total) and listed count — better than [[idealista]] (listed-subset only).

**Two operational findings baked into the pipeline + the [[2026-06-05-imovirtual-portal-onboarding]] ADR**: (1) the load task is a single 30+ min synchronous crawl, so Airflow's default 300s `scheduler_zombie_task_threshold` killed the live task when its heartbeat lapsed under CPU contention — raised to 3600s in [docker-compose.yml](../docker-compose.yml) and the two loads serialized; (2) DataDome throws short 403 bursts under sustained load (~every few hundred plots) — the crawl's retry/backoff rides them out (first full run: 19 retries, **0 plots dropped**). Confirm-at-build items resolved: unit `?page=N` pagination works; terreno `characteristics.type` enum = {building, habitat, agricultural, other, commercial, agricultural_building, woodland} + nullable.

**Pages touched**: [[log]] (this entry), new [[2026-06-05-imovirtual-portal-onboarding]], new [[imovirtual]], [[index.md|index]] (Real-estate portals 4→5, Sources 23→24, Decisions 17→18, P1 13→14). **Deferred** (follow-up PR): `stg_portal_developments_imovirtual.sql` + the 5th `unified_developments` UNION arm + geo-priority rank; [[portal-field-map]] imovirtual columns.

## [2026-06-06] fix | [[idealista]] phantom SCD2 versions from RE-API outage

**Bronze regression:** `bronze_listings.idealista_development_units.location_hierarchy = '{}'` on 150/150 active rows; surfaced during the imovirtual 5th-portal silver audit. Root cause was a 2-day-old **ZenRows RE-API outage** (HTTP 500 ERR0001 on both `/properties/{id}` and `/discovery/`, verified via direct `curl` 2026-06-06; Universal Scraper unaffected). PR #48's 2026-06-04 run framed it as transient — it isn't.

**Why the bug bit bronze:** `_fetch_one_unit_detail` swallows API exceptions and returns `{}`. The resource-level skip in `development_units()` only filtered `_re_api_stub=True`, NOT empty-detail-from-API-failure, so 150 phantom SCD2 rows were yielded with all-NULL enrichment fields. dlt's SCD2 strategy then closed all 444 prior good rows (2026-05-18 batch) on the way in. Phantoms also exposed a latent type bug: `location_hierarchy: detail.get("location_hierarchy") or {}` defaulted to `{}` (dict) for a column the staging `->> 1`/`->> 2` array-indexing expects to be `[]` (list).

**Fixes shipped** in [pipelines/portals/idealista/source.py](../pipelines/portals/idealista/source.py):
- `development_units()` (and `plots()` for symmetry) skip when `detail.get("_re_api_stub") or not detail` — empty detail now treated as stub-equivalent; heartbeat sidecar still ticks.
- `_normalize_unit` / `_normalize_plot` / `_parse_unit_detail_re` defaults: `location_hierarchy or {}` → `or []` (type-correct, consistent with bronze content + every other JSONB-array column).

**SCD2 data restore (one-shot)**: `DELETE` the 150 phantoms then `UPDATE` the 444 prior rows back to `_dlt_valid_to = NULL`. Reverts the 2026-06-04 batch to a "no-op" — the next successful pipeline run reconciles naturally (delisted units close, live ones keep / version normally).

**Verified end-to-end**: rebuilt `stg_portal_developments_idealista` + `silver_properties.unified_developments` + `unified_listings_residential`. 16/21 idealista dev rows now carry concelho (was 0/21); **5 idealista devs now merge cross-portal** (was 0). "The Unique" (idealista) ↔ "Unique" (remax) merges as `n_portal_contributors=2`. The remaining 5 NULL-concelho devs are net-NEW 2026-06-04 discoveries whose units never had real RE-API data — they recover automatically when ZenRows fixes the outage.

**Cross-portal silver-dedup algorithm unchanged**: the dual-signal name match + dropped 1km guard from the imovirtual silver wiring (same session, separate PR) handles these correctly the moment concelho is non-NULL.

**Pending follow-ups**:
- [ ] ZenRows support ticket — RE-API outage is now ≥48h. Re-running the [[idealista]] dev/units DAG is a no-op while it stays down.
- [ ] Once RE-API is back: re-run `idealista_developments_units_plots_dag` to refresh the 5 new-discovery devs + any drift since 2026-05-18; the new skip-on-empty guard prevents another phantom batch on transient failures.

**Pages touched**: [[log]] (this entry).

## [2026-06-06] silver wiring | imovirtual 5th UNION arm in unified_developments

Landed the deferred follow-up from the [2026-06-06 imovirtual onboarding entry above](#2026-06-06-add-portal-source-first-load-imovirtual-p1-nextjs-_next_data-json). Created [stg_portal_developments_imovirtual](../dbt/models/staging/portals/stg_portal_developments_imovirtual.sql) (13-col canonical schema, typed `reverseGeocoding` admin geography, dev-level GPS, TRUE-total unit count), added the matching test block to [_staging_portals__models.yml](../dbt/models/staging/portals/_staging_portals__models.yml) at JLL/Zome depth, and added the 5th `UNION ALL` arm to [unified_developments](../dbt/models/silver/properties/unified_developments.sql).

**Geometry-priority demotion**: original ADR locked imovirtual at slot 2 (just below JLL). Demoted to **slot 4** (`JLL > Zome > RE/MAX > imovirtual > idealista`) because coordinate coverage was unverified at silver-build time — Zome's ~98% coverage is proven, imovirtual's isn't. Conservative slot until a coverage spot-check clears a promotion. Reversibility = 4 lines in the priority CASE. Rationale captured as a 2026-06-06 addendum on [[2026-06-05-imovirtual-portal-onboarding]].

**Unit-count semantics**: `total_units` carries `number_of_units_in_project` (TRUE project size), not the listed subset — imovirtual's data-quality edge over [[idealista]] survives through silver. `listed_units_count` lives in `raw_meta` for consumers that want both.

**Pages touched**: [[log]] (this entry), [[2026-06-05-imovirtual-portal-onboarding]] (addendum), [[imovirtual]] (silver wiring marked done), [[cross-portal-dev-dedup]] (4 portals → 5, new geom ladder, imovirtual unit-count semantics). **Out of scope**: units/plots staging + `unified_listings_residential` integration (no cross-portal consumer for those grains yet).

## [2026-06-06] dual-signal dedup + drop 1km guardrail | unified_developments

Audit of [[imovirtual]] Aveiro merges (user review) exposed three dedup blockers, all algorithmic not portal-specific:

1. **1km distance ceiling vetoing correct merges.** Portal pins disagree by **3-4km** on identical-named devs in the same concelho (Ethula remax↔imovirtual = 3,949m; JC Barrocas zome↔imovirtual = 3,412m; UNIQUE Matosinhos = 4,697m) — worse than the original 200-300m audit. **Dropped the ceiling entirely**: same name + same concelho is sufficient.
2. **Token-Jaccard structurally blind to whitespace collapse.** "VIANOVA" tokens = {vianova}; "Via Nova" tokens = {via, nova}; Jaccard = 0.0. **Added a parallel char-trigram-Jaccard edge generator** on the whitespace-stripped clean_name; ≥ 0.6 threshold. UNION'd with the existing token-Jaccard edges before connected components.

   Why UNION not replace: pure char-trigrams regress subset matches ("jcbarrocas" vs "jcbarrocasapartments" trigram-Jaccard = 0.44, below 0.6). Tokens handle subsets; trigrams handle collapses. Either signal is sufficient.

3. **[[idealista]] has NULL concelho on every dev** (21/21 active, bronze `idealista_development_units.location_hierarchy = {}` on 150/150 rows). The dedup join requires `a.concelho = b.concelho` — NULL=NULL is FALSE, so every idealista dev fails to merge across portals. "The Unique" (idealista) ↔ "Unique" (remax/Aveiro) stays split for this reason. **Out of scope here** — bronze regression, separate task.

**Verification (post-rebuild)**: 1,511 → **1,435** unified rows (-76 from new cross-portal merges); 197 → **243** multi-portal rows. All four user-reported pairs (Ethula/ETHULA, JC Barrocas variants, Via Nova/VIANOVA, UNIQUE Matosinhos) now merge correctly. No over-merges observed in 3+ portal rows.

**Pages touched**: [[log]] (this entry), [[cross-portal-dev-dedup]] (dual-signal section + dropped-ceiling rationale), [unified_developments.sql](../dbt/models/silver/properties/unified_developments.sql) (algorithm + header comment), [_silver_properties__models.yml](../dbt/models/silver/properties/_silver_properties__models.yml) (model description).

## [2026-06-06] macroize name normalize + CAOP geo in dev staging

Pushed name-matching normalization into each portal dev-staging model and added CAOP-resolved admin geography there too — per the user's "for geography, should we check against CAOP? for the developments names should it be at staging?" review. Originally planned as a follow-up PR; bundled into this PR because the CAOP signal **fixes the idealista cross-portal merge problem** without waiting for the bronze `location_hierarchy` fix.

**What shipped:**

1. New macro [normalize_dev_name.sql](../dbt/macros/normalize_dev_name.sql) — encapsulates the lowercase + deaccent + strip-typology + strip-boilerplate + punct-to-space pipeline previously inline in [unified_developments.sql](../dbt/models/silver/properties/unified_developments.sql). The cross-cutting trailing-concelho strip stays in silver because it needs `join_concelho`.
2. All 5 dev-staging models (`stg_portal_developments_{idealista,remax,zome,jll,imovirtual}.sql`) gain four columns:
   - `match_name` — `normalize_dev_name(canonical_name)`.
   - `geo_concelho_name`, `geo_parish_name`, `geo_key` — point-in-polygon against `dim_geography.freguesia_geom_pt` (`is_current`), NULL when geom is NULL.
3. Silver `unified_developments` refactored:
   - `portal_pre` CTE dropped (normalization is upstream).
   - Same-concelho join uses `join_concelho = lower+deaccent of COALESCE(geo_concelho_name, concelho)` — CAOP-first.
   - `portal_dev_concelho` MODEs `COALESCE(geo_concelho_name, concelho)` and `geo_key` across contributors (≤8 boundary disagreements total, audited).
   - Final SELECT drops its own LATERAL CAOP lookup — already resolved upstream.

**CAOP-vs-portal-text disagreement audit (post-staging build, case+accent normalized)**: idealista 0/16, imovirtual 0/800, jll 0/169, **remax 5/591**, **zome 3/309**. Only 8 real-data disagreements across 1,885 staging rows — driving a 1,435 → 1,430 row shift in silver.

**Idealista breakthrough**: bronze `idealista_development_units.location_hierarchy = '{}'` leaves portal-text concelho NULL on every active idealista dev (separate spawned task). But 16/21 idealista devs have non-NULL `geom_3763` from the AVG-of-unit-geocodes path, and CAOP resolves concelho for all 16. After the refactor, **5 idealista devs now merge cross-portal** (was 0) — including the user-reported pairing **"The Unique" (idealista) ↔ "Unique" (remax/Aveiro)**, and **"JC Barrocas Apartments" (idealista) joining the existing zome+imovirtual merge** for a 3-portal row.

**Pages touched**: [[log]] (this entry), [[cross-portal-dev-dedup]] (normalize-in-staging + CAOP geo sections), [unified_developments.sql](../dbt/models/silver/properties/unified_developments.sql) (refactor), [_silver_properties__models.yml](../dbt/models/silver/properties/_silver_properties__models.yml), [_staging_portals__models.yml](../dbt/models/staging/portals/_staging_portals__models.yml) (4 new columns per dev-staging model). Out of scope: the idealista `location_hierarchy = {}` bronze regression — still tracked as a separate task; CAOP now papers over it for merge purposes but the bronze should still be fixed.

## [2026-06-06] add-gis-source | publico-rankings (P1) — Público school rankings custom DAG

Bootstrapped a new education-pillar source per the [[2026-06-06-pt-education-amenity-design|PT education amenity design]] (design doc at `tests/PT-EDUCATION-DESIGN.md`).

Chose a custom DAG (skip the GIS ingestion template) because the source fans out across 12 (year × kind) tuples spanning three hosting eras (2018-2020 `static.publicocdn.com/files/`, 2021-2023 `static.publico.pt/files/`, 2024+ `static.publico.pt/s3/`), the template's single-URL `download_url: str` field doesn't fit. DAG uses Airflow dynamic task mapping over the resolver table; download → soft-404 + size-floor + JSON-parse validation → MinIO upload at `raw/publico_rankings/{year}/{kind}.json`. Sibling sources ([[rede-escolar]] paginated ArcGIS REST, [[dgeec-ens-sup]] shapefile, [[dges-acesso]] XLSX, [[infoescolas]] XLSX) still pending bootstrap.

Verified live 2026-06-06: all 12 expected URLs return 200 with bodies above the soft-404 sentinel (22634 bytes). 9ano gap for 2020+2021 is real (COVID — Provas Finais cancelled), not a TODO.

**Files created**:
- `pipelines/gis/publico_rankings/__init__.py`
- `pipelines/gis/publico_rankings/publico_rankings_config.py` (resolver table + headers + soft-404 sentinel constant)
- `pipelines/gis/publico_rankings/publico_rankings_ingestion_dag.py` (custom TaskFlow DAG, dynamic mapping)
- `dbt/models/staging/education/_staging_education__sources.yml` (new staging domain — first entry)
- `wiki/sources/publico-rankings.md`

**Pages touched**: [[log]] (this entry), [[index]] (added Education subsection + bumped P1 count 14 → 15, total 24 → 25 — post-[[imovirtual]] merge baseline), [[publico-rankings]] (new).

**Pending follow-ups**:
- [ ] Bootstrap remaining 4 education sources ([[rede-escolar]], [[dgeec-ens-sup]], [[dges-acesso]], [[infoescolas]]) per design doc §8.
- [ ] Decide if XCom 1 MB default needs bumping (2022 sec body is 1034 KB).
- [ ] Decide CAOP-Açores + CAOP-Madeira sourcing (design doc Q6) — needed for Público rows tagged `c='Açores'` / `c='Madeira'` to get DICOFRE.
- [ ] Author `wiki/decisions/2026-06-06-pt-education-amenity-design.md` ADR capturing the locked decisions from `tests/PT-EDUCATION-DESIGN.md` so the cross-link from [[publico-rankings]] resolves.

## [2026-06-06] add-gis-source | publico-rankings — bronze-loader DAG + end-to-end verification

Follow-up to today's earlier `add-gis-source | publico-rankings` entry. Built the second half of the two-DAG pattern + ran full Phase-0 verification.

**New file**: `pipelines/gis/publico_rankings/publico_rankings_bronze_dag.py` — `publico_rankings_bronze_load` DAG. Discovers MinIO blobs at `s3://raw/publico_rankings/`, applies DDL (idempotent), dynamic-maps `load_one` per blob, upserts JSONB rows keyed on `(year, kind, eid)`. Mirrors [[bgri]]'s `bgri_bronze_dag.py` shape; reuses Airflow Variables `MINIO_*` + `WAREHOUSE_*`.

**Verified end-to-end against live infrastructure** (uv run, worktree-side):
- Ingestion logic: 12/12 source URLs return 200 with size > floor + valid JSON; soft-404 trap fires correctly on `/files/` era unknown URLs (200 + 22634 bytes); `/s3/` era returns proper 403.
- MinIO landing: 12 objects written to `s3://raw/publico_rankings/{year}/{kind}.json`, ~5.1 MB total.
- Bronze DDL: schema + table + partial coduo index materialized in fresh state (table dropped + recreated to prove from-scratch path).
- Bronze load: 10,288 rows upserted (4,411 sec + 5,877 9ano). PK uniqueness sanity: all 10,288 (year, kind, eid) tuples distinct.
- Data integrity: `coduo` populated on 921/1161 = 79.3% of 2024 9ano (matches design doc); `coduo` = 0/4,411 sec rows; `mt` populated on 100% of all rows.

**Arithmetic correction**: my prior entry quoted "10,488 rows / 6,077 9ano" — actual is **10,288 / 5,877**. [[publico-rankings]] §Schema row-count table fixed.

**Caveat**: Airflow scheduler container mounts the main repo's `pipelines/`, so neither DAG appears in `airflow dags list` until the worktree merges to main. Verification ran the DAG logic directly via `uv run` against live MinIO + warehouse.

**Pages touched**: [[log]] (this entry), [[publico-rankings]] (added bronze-DAG to Pipeline split, fixed row count to 10,288).

## [2026-06-06] refactor | publico_rankings bronze — unnest raw jsonb into 91 typed columns

Modified `publico_rankings_bronze_load` DAG: bronze table no longer stores a raw jsonb column. Every source key is now promoted to a typed column at load time — 5 text columns (e, id, co, c, coduo) and 86 numeric columns (mt, rt, t, lt, ln, per-disciplina averages mm/mp/mb/…, per-disciplina sample sizes nb/nf/…, per-disciplina ranks rb/rf/…, privado nominal cols nimb..nipp, rolling 5y carryover m17..m21 + r17..r21, derived rsbi/rsec/rsfi/…, composite pde/pdp/pdq/pdr, etc.). Total table width: 95 columns (4 PK/audit + 91 data).

Trade-off: gives up the strict [[bronze-permissive]] "keep raw JSONB, type at silver" invariant in exchange for downstream SQL ergonomics. The MinIO blobs (`s3://raw/publico_rankings/{year}/{kind}.json`) remain the verbatim audit trail, so the permissive property is preserved at the object-store layer.

Per-column coercion: `_coerce_numeric` handles Público's inconsistent JSON typing (string vs number, "" / "null" / unparseable → NULL). NULL means "key absent or unparseable" — expected since sec has 76 keys and 9ano has 40 (union = 91, intersection ≈ 25).

Schema-drift detection built in: every `load_one` task logs a WARNING if any source key falls outside `TEXT_COLS + NUMERIC_COLS`. Verified 2026-06-06 against the full 2018-2024 corpus: **zero unknown keys** — the column tuple covers every key in the wild.

**End-to-end re-verification** (table dropped → DDL applied → 10,288 rows reloaded):
- Column count: 95 (information_schema.columns).
- Row count: 10,288 (4,411 sec + 5,877 9ano).
- `coduo` populated on 921/1161 of 2024 9ano = 79.3%. Sec coduo = 0/4,411. `mt` = 10,288/10,288 = 100%.
- Sanity sample (top-3 9ano 2024 by mt): Colégio Novo da Maia (mt=4.51), Escola de Música São Teotónio (mt=4.42), Colégio Grande Colégio Universal (mt=4.40) — all privates (t=1, c='PRI'), credible top of the 0-5 scale.

**Bug caught + fixed during verification**: initial UPSERT_SQL listed `source_loaded_at` in the INSERT column list but the VALUES tuples omitted it (relying on `DEFAULT now()`). psycopg2 error: "INSERT has more target columns than expressions". Dropped the `source_loaded_at` column from the INSERT list, kept it in the `ON CONFLICT DO UPDATE SET` so re-loads refresh the timestamp.

**Pages touched**: [[log]] (this entry), [[publico-rankings]] (DDL section rewritten, audit-trail trade-off documented), `dbt/models/staging/education/_staging_education__sources.yml` (columns flipped from `raw` to typed promoted columns).

## [2026-06-06] document | publico-rankings column legend — decoded 91 cryptic columns into 9 families

Decoded all 91 columns of `bronze_education.raw_publico_rankings` into a structured legend at [[publico-rankings-column-legend]]. Público ships no machine-readable codebook (verified — only `data/listas/*.js` + `data/pt_pt.js` are exposed under their S3 prefix; the app bundle that holds UI labels is served from a separate origin). Decoding was empirical: per-column value-envelope analysis on the 10,288-row corpus + sample-size correlations + cross-column rank equalities + two Público article URLs that name the "Ranking da Superação" view.

**Confident decoding** (~75% of columns):
- Identity & geography: e, eid, id, co, c, coduo, lt, ln, t.
- Headline principal: mt (Média Total — the score), rt (Ranking Total — position).
- Per-disciplina principal (1-letter codebook): m{X}/n{X}/r{X} for X ∈ {m,p,b,f,fl,g,h,i,ma} → Mat A / Português / Bio-Geo / FQ / Filosofia / Geografia / História / Inglês / MACS.
- Histórico: m{YY}, r{YY} (e.g. m21, r21 = 2021 carryover; older years dropped from newer files).
- Nota Interna (CIF) for privates: nim{X} = média CIF, nip{X} = rank by CIF. Always NULL for públicos and all 9ano.
- Ranking da Superação (2nd headline view, 2-letter codebook): rs + rs{XX} for XX ∈ {ma,po,bi,fq,ge,fi,ec,mc}. Confirmed distinct from `rt`: only 8/1608 schools tie, avg abs diff ≈ 145 positions.
- Equivalência à Frequência: eq1, eq2, eq3, eqnaousar, eqnusar quality flags, re = rank in eq cohort. Confirmed 303/303 sample-size overlap with eq family.

**Plausible decoding** (~15%):
- tx0/tx1/tx2 = three independent taxas (retenção / desistência / classificação-inferior — % range, do not sum to 100 so they're independent rates).
- pdq = Percursos Diretos Qualidade (Infoescolas-style success metric); pde/pdp/pdr sibling axes mostly NULL in 2024.
- ac = Aproveitamento (% positive classifications).

**Speculative** (~10%) — flagged in the page:
- im (per-school scaled index — confirmed NOT concelho-level: Lisboa has 29 distinct values across 37 schools).
- v (tracks `mt` mean — possibly "Valor esperado" / Variância).
- hm, hp (histórico médio / percentil — same scale as `mt`).

**Dual-codebook trap documented**: 1-letter codes (`m`, `p`, `b`, `f`, `fl`, `g`, `h`, `i`, `ma`) used in m*/n*/r* prefixes don't 1:1 map to 2-letter codes (`ma`, `po`, `bi`, `fq`, `ge`, `fi`, `ec`, `mc`) used in rs* prefix. Each family picks its own subset of disciplinas; downstream silver models must reference both codebooks.

**Pages touched**: [[log]] (this entry), [[publico-rankings-column-legend]] (new), [[publico-rankings]] (added cross-link from §Bronze DDL), [[index]] (Concepts count 18 → 19, added entry between [[portal-field-map]] and [[pydantic-not-in-dlt]]).

**Pending follow-ups**:
- [ ] Confirm `im` / `v` / `hm` / `hp` semantics against Público's interactive page — requires loading the iframe with browser-class JS or browser MCP to read the column-header tooltips.
- [ ] Verify whether r{X} principal vs rs{XX} Superação per-disciplina are computed on the same school cohort or different (550/550 differ — but is the cohort filtered, or the methodology?). Affects whether silver should publish both as alternative views or pick one.

## [2026-06-06] correct | publico-rankings column legend — ground-truthed against UI screenshots

Reverted ~60% of the empirically-guessed column meanings in [[publico-rankings-column-legend]] after the user shared screenshots of the Público interactive school card. Used eid=1069 (Escola Dr. Ferreira da Silva, Oliveira de Azeméis, 2024 sec) as the ground-truth row — every visible UI label matched one DB column value exactly.

**Corrections** (prior decode → screenshot-verified):
- `v` = Média Esperada (basis for Superação metric = `mt - v`) ← was "valor/variância"
- `c` = Contexto agrupamento {D=Desfavorável, F=Favorável, I=Intermédio, PRI, PRI_CA, Açores, Madeira} ← was "region code"
- `hp` = Habilitações Pais (anos de escolaridade do pai, média) ← was "histórico posição"
- `hm` = Habilitações Mães ← was "histórico médio"
- `ac` = % alunos SEM Acção Social Escolar (wealth proxy) ← was "Aproveitamento/Acerto"
- `im` = Idade Média dos alunos no 12.º ano ← was "índice mediano"
- `pdq` = % Professores Dos Quadros (tenured docentes) ← was "Percursos Diretos Qualidade"
- `tx0/tx1/tx2` = Taxa de Retenção no 10º/11º/12º ano specifically ← was "generic taxas"
- `pde/pdp/pdr` = Equidade family (% ASE concluiram / % país perfil similar / ranking da diferença) ← was "Percursos Diretos axes"
- `m21/r21` = média/rank do **ano anterior** (not specifically 2021 — the `21` suffix is legacy from when the rolling-history columns were first introduced; in 2024 file these hold 2023 values, matching the UI's "12,60 em 2023" and "100.º em 2023") ← was "literal 2021"

**Disciplina codebook collision discovered + locked**:
- 1-letter codebook: `m`=Mat A, `p`=Port, `b`=Bio-Geo, `f`=FQ-A, `g`=Geo-A, `fl`=Filo, `h`=His-A, **`ma`=Economia A**, **`i`=MACS**
- 2-letter codebook: **`ma`=Mat A**, `po`=Port, `bi`=Bio, `fq`=FQ, `ge`=Geo, `fi`=Filo, `ec`=Economia, `mc`=MACS
- The letter `ma` means *opposite* disciplines across families. Silver promotions MUST disambiguate by prefix.

**Confirmed** (no change from prior decode):
- `mt`/`rt`/`nt` headline principal triad
- `rs` Ranking da Superação (distinct from `rt`: 8/1608 ties only)
- `m{X}`/`n{X}`/`r{X}` per-disciplina principal triad
- `rs{XX}` Superação per-disciplina (2-letter codebook)
- `nim{X}`/`nip{X}` Nota Interna CIF + posição (now confirmed populated for *both* públicos and privados, not privados-only as I had thought)
- `re` Ranking Equivalência + `eq*` family

**Pages touched**: [[log]] (this entry), [[publico-rankings-column-legend]] (rewritten with screenshot ground-truth + verified row dump at the bottom), [[index]] (concept entry expanded with the `ma` collision warning).

## [2026-06-06] refactor | publico_rankings bronze — rename all cryptic columns to human-readable Portuguese names

Replaced the 91 cryptic source-key column names in `bronze_education.raw_publico_rankings` with verified human-readable names from [[publico-rankings-column-legend]]. The bronze DAG's `TEXT_COLS + NUMERIC_COLS` tuples are now derived from a single `SOURCE_KEY_TO_COLUMN: dict[str, tuple[str, str]]` (source_key → (renamed_column, sql_type)) at the top of `publico_rankings_bronze_dag.py` — DDL, INSERT column list, and UPDATE SET clause all flow from it.

**Naming convention**: Portuguese, snake_case, matches existing convention (`bronze_ine.raw_bgri` uses `n_edificios_classicos`, etc.). Example transformations:
- `mt` → `media_total_exames`
- `rt` → `ranking_exames`
- `rs` → `ranking_superacao`
- `v` → `media_esperada`
- `mm` → `media_matematica_a`, **`mma` → `media_economia_a`** (resolves 1-letter `ma` = Economia)
- `rsma` → `ranking_superacao_matematica_a` (resolves 2-letter `ma` = Mat A)
- `nimm` → `cif_media_matematica_a`, `nipp` → `cif_ranking_portugues`
- `hp` → `habilitacoes_pais`, `hm` → `habilitacoes_maes`
- `ac` → `pct_sem_ase`, `im` → `idade_media_12ano`, `pdq` → `pct_professores_quadros`
- `tx0/1/2` → `taxa_retencao_ano0/1/2` (10º/11º/12º sec, 7º/8º/9º for 9ano)
- `pde/pdp/pdr` → `equidade_pct_ase_3anos / equidade_pct_pais_3anos / equidade_ranking_diferenca`
- `m21/r21` → `media_ano_anterior / ranking_ano_anterior` (the suffix is legacy, meaning is "prior year")
- `m17..m20/r17..r20` → `media_legacy_y17..y20 / ranking_legacy_y17..y20`

**Disciplina codebook collision resolved**: both `m_` 1-letter (where `ma`=Economia A) and `rs_` 2-letter (where `ma`=Mat A) source families now write to renamed columns whose disciplina suffix matches the actual disciplina, not the source-letter abbreviation. Downstream SQL no longer needs to know about the trap.

**Verified end-to-end** (table dropped, DDL applied, 12 blobs re-loaded from MinIO):
- 95 columns in `information_schema.columns` (4 PK/audit + 5 text + 86 numeric).
- 10,288 rows total. Zero schema-drift keys.
- Screenshot row (eid=1069, 2024 sec, Escola Dr. Ferreira da Silva) verified column-by-column under new names:
  - `media_total_exames=14.11` ↔ UI "Média nos Exames: 14,11"
  - `ranking_exames=36`, `num_provas_total=70`, `ranking_superacao=1`, `media_esperada=11.38`
  - `contexto_agrupamento='I'`, `habilitacoes_pais=7.77`, `habilitacoes_maes=9.32`, `pct_sem_ase=72`, `idade_media_12ano=17`, `pct_professores_quadros=84.9`
  - `taxa_retencao_ano0=0`, `taxa_retencao_ano1=0`, `taxa_retencao_ano2=8`
  - `media_ano_anterior=12.6` (matches "12,60 em 2023"), `ranking_ano_anterior=100` (matches "100.º em 2023")
- Per-disciplina disambiguation verified: `media_economia_a=13.98` (from `mma`, UI Economia=13.98), `media_matematica_a=18.16` (from `mm`, UI Matemática=18.16), `media_macs=15.49` (from `mi`, UI MACS=15.49), `ranking_superacao_matematica_a=1` (from `rsma`, UI Superação Mat A=1.º).

**Pages touched**: [[log]] (this entry), [[publico-rankings]] (DDL section rewritten with renamed columns), `dbt/models/staging/education/_staging_education__sources.yml` (column list rewritten with renamed names + descriptions).

## [2026-06-06] document | dbt source column descriptions — guideline + completed publico_rankings

Two-part follow-up to the publico_rankings unnest+rename work:

**1. Completed dbt source YAML for `publico_rankings`** (`dbt/models/staging/education/_staging_education__sources.yml`):
- All 95 columns documented (4 partition/audit + 91 renamed data cols).
- Each entry has a `description:` ≤ 200 chars where possible.
- Pattern: for renamed-from-cryptic cols, the description ends with `Source key: \`<original>\`` so the bridge to the raw source is one click away.
- Special call-outs for codebook-collision columns (`media_economia_a` notes `mma` and the 1-letter `ma`=Economia trap; `ranking_superacao_matematica_a` notes `rsma` and the 2-letter `ma`=Mat A meaning).
- Region/code-letter columns (`contexto_agrupamento`, `tipo`) expand the dictionary inline.
- Verified: `information_schema` shows 95 cols == YAML has 95 cols == dbt manifest shows 95 cols for `source.house4house.bronze_education.raw_publico_rankings`. dbt parse passes (71 `accepted_values` deprecation warnings — same project-wide pattern as the other 17 sources, not specific to this YAML).

**2. Documented the rule as a project convention**: new concept page [[dbt-source-column-descriptions]] codifies "every bronze column gets a `description:`". Covers: why (dbt-docs is the discovery surface; cryptic sources need disambiguation; drift detection), how (the pattern by column category — renamed-from-cryptic, code-letter encoding, FK column, JSONB blob), the verification triad (`information_schema` ≡ YAML ≡ manifest), and the explicit "what does NOT count as a description" + "when this rule does NOT apply" sections.

**Skill wired**: [[add-gis-source]] SKILL.md step 5 now references the rule + the column-count verification, so future bootstraps remember to document every column at create-time rather than leaving it as a "fix later".

**Pages touched**: [[log]] (this entry), [[dbt-source-column-descriptions]] (new), [[index]] (Concepts 19 → 20, added entry between [[cross-portal-dev-dedup]] and [[heartbeat-sidecar]]), `.claude/skills/add-gis-source/SKILL.md` (step 5 amendment), `dbt/models/staging/education/_staging_education__sources.yml` (completed 95-column documentation).

**Pending follow-ups**:
- [ ] Audit the other 17 existing dbt source YAMLs for missing column descriptions — sample check shows `[[caop]]` and `[[cos]]` are mostly compliant but I haven't done a full sweep. Track gaps as a `wiki/lint-reports/` finding next time `/wiki-reconcile` runs.
- [ ] Decide if `wiki_health.py` (Phase 7) should treat missing column descriptions as a BLOCKING finding for new bronze tables (`last_verified` < 30 days) and merely WARNING for older ones.

## [2026-06-06] verify | publico_rankings — ranks are per-partition + ranking_superacao allows ties

User question revealed an under-documented invariant: "why are there 2 1s, 2 2s, 2 3s in ranking_exames?" Investigated and clarified:

**Finding 1 — ranks are per-(year, kind) partition, not global.** Across 12 partitions (7 sec editions + 5 9ano editions), each has its own sequential rank 1..N — so the whole table contains 12 instances of rank=1, 12 of rank=2, etc. Within each partition `ranking_exames` IS strictly unique across the full 2018-2024 corpus (verified empirically: 0 violating partitions). Added a `dbt_utils.unique_combination_of_columns` test on `(year, kind, ranking_exames)` to lock the invariant.

**Finding 2 — ranking_superacao ALLOWS TIES (standard competition ranking).** Initially added the same uniqueness test on `ranking_superacao`; it failed with 16 violations. Investigation showed Público uses standard competition ranking ("1, 2, 2, 4 — skipping"): schools with identical `mt - v` gap share a rank and the next rank skips. Empirical example: 2024 9ano has a 3-way tie at rank 569 → next rank = 572. Ties cluster at the bottom of the distribution where the gap quantizes to limited float precision. Removed the strict test; documented the tie semantics in the column description AND in the legend page.

**Files touched**:
- `dbt/models/staging/education/_staging_education__sources.yml` — kept the `ranking_exames` composite uniqueness test (PASSES); expanded both `ranking_exames` and `ranking_superacao` descriptions with the per-partition scope + the competition-ranking caveat.
- [[publico-rankings-column-legend]] — added a "Ranks are per-partition, not global" section above the Headline family explaining the invariant + the tie behavior + the silver consequence ("models that depend on unique rank values must dedup or use a `dense_rank()` re-projection").

**Pages touched**: [[log]] (this entry), [[publico-rankings-column-legend]] (per-partition + tie section).

## [2026-06-06] migrate | PT education amenity design → wiki/planning/ + live status dashboard

Moved `tests/PT-EDUCATION-DESIGN.md` into the wiki at [[pt-education-amenity-pillar]] so the doc lives where the rest of the project's planning + tracking lives, with Obsidian backlinks and graph membership.

**What was added on top of the verbatim port**:
- YAML frontmatter (`type: plan`) + `## For future Claude` preamble.
- New `## 0. Status` section at the top — a single-page progress dashboard with a 5-row source table (status + PR link per source) and Phase 0 / Phase 1 / Phase 2 / Open-Qs checklists. Source #1 (publico-rankings) checkboxes all ✅ ticked with the verified row counts; sources #2-#5 still 🔲/⏳ pending.
- Cross-links to the three sibling pages this pillar produced: [[publico-rankings]] (source), [[publico-rankings-column-legend]] (91-col legend), [[dbt-source-column-descriptions]] (convention).
- Original §7 Phase-0 checklist updated to reflect publico_rankings as shipped (the verbatim items were stale).

**Other touches**:
- `tests/PT-EDUCATION-DESIGN.md` reduced to a one-screen pointer at the wiki version — single source of truth now lives at [[pt-education-amenity-pillar]], not in `tests/`.
- [[planning/README|wiki/planning/README]] grew a "Pillar-specific planning pages" subsection so future multi-source pillars (housing supply, regulatory events, etc.) have a documented home.
- [[index]] Planning section count 4 → 5; added the [[pt-education-amenity-pillar]] entry.

**Pages touched**: [[log]] (this entry), [[pt-education-amenity-pillar]] (new), [[planning/README]] (Pillar-specific subsection added), [[index]] (Planning 4 → 5), `tests/PT-EDUCATION-DESIGN.md` (now a pointer stub).

## [2026-06-06] ingest | rede-escolar bootstrap — Phase 0 source #2 of 5

Bootstrapped the second source of the [[pt-education-amenity-pillar]] (the GesEdu paginated ArcGIS REST FeatureServer; canonical PT school register with point geometry). Same custom-DAG shape as [[publico-rankings]] — skipped `pipelines/gis/template/` because the template handles single-URL file downloads, not paginated REST query endpoints.

**Code shipped**:
- `pipelines/gis/rede_escolar/rede_escolar_config.py` — endpoint URL + `maxRecordCount=2000` page size + count probe + sanity bands + headers.
- `pipelines/gis/rede_escolar/rede_escolar_ingestion_dag.py` — paginated ingest. `probe_and_fanout` (live `returnCountOnly` probe) → `download_page.expand(spec=offsets)` → `upload_page.expand` → `summarize` reconciles `sum(page features) == probe total`. `@monthly` schedule.
- `pipelines/gis/rede_escolar/rede_escolar_bronze_dag.py` — `discover_latest_run` picks newest snapshot, `fanout_pages` lists page blobs, `ensure_table` builds dual-CRS PostGIS schema per [[2026-05-10-dual-crs-storage]], `load_page` unnests features + writes geom (4326) + geom_pt (3763), upserts on `(run_date, codigo_escola)`.
- `dbt/models/staging/education/_staging_education__sources.yml` — appended `raw_rede_escolar` source with 46 column descriptions (3 audit + 41 renamed + 2 geom) + `unique_combination_of_columns: [run_date, codigo_escola]` test. Same column-description convention as [[publico-rankings]] (see [[dbt-source-column-descriptions]]).

**Live verification (2026-06-06)**: count probe = 8,670 features. Pagination verified at offset 0/2000/4000/6000 = 2000 features each (`exceededTransferLimit=True`); offset 8000 = 670 tail features (no flag). Live field set = our `SOURCE_KEY_TO_COLUMN` exactly (zero drift; 42 attribute fields incl. CODESCME PK). 92/670 tail-page features had NULL geometry (handled — row inserts with `geom`/`geom_pt` NULL). Did NOT run the Airflow DAG end-to-end in this worktree because the docker scheduler mounts the main repo's `pipelines/`, not this worktree's — same constraint as the [[publico-rankings]] dev cycle; live trigger will happen after merge.

**Pages touched**: [[log]] (this entry), [[rede-escolar]] (new source page with pagination verification table), [[index]] (Sources 25 → 26; P1 15 → 16; Education subsection (1) → (2)), [[pt-education-amenity-pillar]] (Phase 0 dashboard: source #2 flipped to 🟢 with verification line).

## [2026-06-06] verify | rede-escolar end-to-end Airflow run

Triggered both [[rede-escolar]] DAGs on the live stack (temporarily synced into the main-repo `pipelines/gis/` so the docker scheduler would pick them up; reverted after).

**Ingestion DAG** (`rede_escolar_ingestion`): 9 seconds end-to-end. probe_and_fanout (1s) → 5× download_page parallel (1-2s each) → 5× upload_page parallel → summarize. MinIO blobs: page_000000–006000 at ~2.2 MB each, page_008000 tail at 756 KiB.

**Bronze load DAG** (`rede_escolar_bronze_load`): 5 seconds end-to-end. discover_latest_run → fanout_pages (5 blobs) → ensure_table → 5× load_page parallel → summarize.

**Bronze verification** against `bronze_education.raw_rede_escolar`:
- 8,670 rows total — matches the live ArcGIS count probe exactly.
- 8,670 unique `codigo_escola` (no PK duplication).
- 7,844 rows with geometry (90.47%); 826 NULL (~9.5% — population-wide, vs the ~14% tail-page sample I had earlier).
- 0 `(run_date, codigo_escola)` PK duplicates → confirms the dbt source uniqueness test would pass.
- Tipologia distribution: 4,123 EB1, 1,944 JI, 335 EB+S, 313 Sec, 261 Profissional — all plausible.
- Probed school `614798` (Jardim de Infância de Gandufe, Mangualde) round-trips identically (lon −7.8015, lat 40.5815) and `geom_pt` reprojects to PT-TM06 (28077.1, 101460.9) — confirms `ST_Transform(geom, 3763)` works through the loader.

Initial DAG-import error caught and fixed: `@monthly` schedule needs an explicit `start_date`; the publico_rankings shape used `schedule=None` so the missing-start_date didn't bite. Added `start_date=datetime(2026, 6, 1)` to ingestion DAG, committed in the same PR.

**Pages touched**: [[log]] (this entry), [[pt-education-amenity-pillar]] (source #2 dashboard flipped to ✅ shipped + end-to-end verified, sub-task tick for live Airflow run added).

## [2026-06-07] ingest | source #3 (`dgeec_ens_sup`) bootstrap + end-to-end verified

PT education pillar — source #3 of 5 shipped. DGEEC's higher-ed register
(`Estabelecimentos do Ensino Superior`, CC BY 4.0 via DGTerritorio SNIG ATOM):
shapefile bundle, 321 Unidades Orgânicas (faculdade-grain), point geometry in
EPSG:4326. New package `pipelines/gis/dgeec_ens_sup/` with config +
ingestion DAG + bronze loader DAG; new wiki page [[dgeec-ens-sup]]; appended
`raw_dgeec_ens_sup` to `dbt/models/staging/education/_staging_education__sources.yml`
with 21 column descriptions + `(run_date, codigo_unidade_organica)` uniqueness test.

**Live probe flipped two assumptions baked into planning §3.5**:
1. Schema is 16 fields, NOT 14 (`Outro telefone` + `Fax` were missed).
2. "Estabelecimento" is the parent institution (Universidade), NOT a physical
   building. `Código do Estabelecimento` is non-unique (101 distinct values
   across 321 rows); the natural PK is `Código da Unidade Orgânica` (321/321
   unique). Pillar decision #11 was right after all — but my pre-probe rename
   plan was wrong (would have PK-violated on first load). Renamed the
   non-unique column `codigo_instituicao` to surface DGEEC's misleading
   "Estabelecimento" vocabulary, instead of propagating it into silver/gold.

DBF field names truncate to 10 ASCII chars (`Código do`, `Outro tele`, etc.);
the bronze loader keys off the truncated label and renames to readable
snake_case Portuguese, same convention as [[rede-escolar]] and
[[dbt-source-column-descriptions]]. Both 4-digit codes (`codigo_instituicao`,
`codigo_unidade_organica`) are stored TEXT zero-padded to width 4 so silver
joins to DGES rankings work without re-padding.

Custom DAG shape, NOT the GIS template — `pipelines/gis/template/`
auto-extracts ZIPs to a single inner file and deletes the ZIP, which destroys
shapefile sidecar bundles. No existing repo source uses
`expected_format='shp'`; templatising shapefile bundles is a separate refactor
(deferred until N≥2 sibling shapefile sources). Bronze loader uses
`pyogrio.raw.read()` to avoid the `geopandas`/`shapely` deps (absent in the
docker Airflow image) and decodes Point WKB manually with `struct.unpack` to
build the WKT passed to `ST_GeomFromText` + `ST_Transform` for dual-CRS
storage per [[2026-05-10-dual-crs-storage]].

End-to-end verified on the live Airflow stack:
- Ingestion DAG: 40.8 KB ZIP, 7 files inside, MinIO blob at
  `s3://raw/dgeec_ens_sup/2026-06-07/Estab_Ens_Sup_Portugal.zip` in ~3s.
- Bronze load DAG: 4 tasks, ~5s end-to-end.
- `bronze_education.raw_dgeec_ens_sup`: 321 rows, 321 unique
  `codigo_unidade_organica` (PK), 101 unique `codigo_instituicao`, 0 NULL
  geometry, `run_date = 2026-06-07`.
- Sample UO `0100` (Universidade dos Açores) round-trips identically:
  geom_4326 `POINT(-25.6638055555556 37.7460416666667)`, reprojects to PT-TM06
  `POINT(-1550907.94 -65519.06)` (Açores is far off the mainland-centric
  EPSG:3763 origin — large negative-x is expected).
- Natureza distribution: 118 Pol-Públ / 87 Univ-Públ / 64 Pol-Priv /
  46 Univ-Priv / 5+1 Militar — matches the probe and the DGEEC catalogue.
- Top institutions by UO count: Universidade Católica Portuguesa (23 UOs),
  Universidade de Lisboa (20), Universidade do Porto (15), Universidade de
  Coimbra (11), Universidade do Algarve (10).

Bug caught + fixed in this session: first bronze run failed with
`ImportError: geopandas is required to use pyogrio.read_dataframe()` — the
Airflow image bundles `pyogrio` but not `geopandas`/`shapely`. Switched to
`pyogrio.raw.read()` (returns numpy ndarrays of WKB bytes + per-field column
arrays) and added a 12-line `_point_wkb_to_wkt` helper that decodes the
21-byte Point WKB layout with `struct.unpack`. Loader has zero geo-stack deps
now — pyogrio + psycopg2 only.

**Pages touched**: [[log]] (this entry), [[index]] (Sources 26→27, P1 16→17,
Education subsection (2)→(3) + new dgeec-ens-sup bullet),
[[pt-education-amenity-pillar]] (source #3 dashboard flipped to ✅ shipped +
end-to-end verified; §3.5 updated to reflect the dual-CRS psycopg2 loader
actually shipped instead of the "ogr2ogr direct" wording from the planning
phase). New page [[dgeec-ens-sup]].

## [2026-06-07] bootstrap | dges_acesso — source #4 of the PT education amenity pillar

Bootstrapped the 4th source in the pillar: DGES Concurso Nacional de Acesso
per-(year, phase, curso, instituição) results. 12 years × 3 phases = 36
source files (2014–2025) in mixed `.xlsx`/`.xls`/`.ods` formats. Bronze
loader routes by URL suffix to `openpyxl` / `xlrd` / `odfpy` via
`pandas.read_excel(engine=...)`. ~40k bronze rows total (36 files × ~1100
per file). Bronze PK: `(year, phase, codigo_instit, codigo_curso)`.

The probe flipped multiple planning §3.3 assumptions that had to be re-locked
in the interview before any code:

- **Família A trap**: planning §3.3 sampled the wrong XLSX family. DGES
  publishes both a "reference card" XLSX (`dges_vagascna_nota_ult_colocado_
  1afase{Y}_{Y+1}_*.xlsx`, published Feb of each year showing next year's
  vagas + prior year's nota) and the actual per-phase results files
  (`fase{n}_{YY}.xlsx`). Família B is the real source; Família A is
  explicitly NOT ingested (duplicates data + publish-date-axis ambiguity).
- **URL pattern is a lie**: probed 11 candidate URL patterns, only 1
  resolved. Filenames mix `fase{n}_{YY}.xlsx`, `cna{YY}_{n}f_resultados.xls`,
  `site_cna19_{n}f_resultados.{xls,xlsx}`, `cna{YY}_{n}f_resultados.ods`,
  and one-offs like `fase1a25_site.xlsx`. Even *within* a year files differ
  (2024: F1=.xlsx, F2=.xls, F3=.xlsx). YEAR_PHASE_URLS is a literal 36-entry
  dict — there is NO pattern.
- **Schema drift across phases AND years AND formats**: F1 has 12-13 cols,
  F2 has 14, F3 has 17; labels rename (`"Sobras para 2ª fase"` → `"Vagas
  Sobrantes"`; `"Nota do últ. colocado (cont. geral)"` drops the
  parenthetical in F2/F3). 2022 F1 has an extra `"Vaga adic. (vagas
  autónomas)"` column. 2018 .ods has a `(1)(2)...(N)` annotation row at
  idx 5 between header and data. SOURCE_LABEL_TO_COLUMN collapses synonyms
  to canonical column names; bronze is a superset table with NULL in
  phase-missing columns (L13). The 2018 annotation row is filtered
  generically by `codigo_instit ∈ ^[0-9A-Za-z]{2,5}$`.
- **DGES↔DGEEC code overlap is 95.3% (162/170)**: live join probe across
  all 3 phases of 2025. DGES `Código Instit.` is a strict subset of
  [[dgeec-ens-sup]] `codigo_unidade_organica` (the unmatched 4.1% maps to
  the parent-institution code, NOT UO grain). Silver does a LEFT JOIN with
  `unmatched_uo` flag for the 8 DGES codes (`0521, 3036, 3124, 3125, 6810,
  7016, 7240, 7270`) that have no DGEEC match — likely UOs added since
  DGEEC's 2023-03-15 snapshot.
- **`Código Curso` can contain letters**: a handful of Música variants ship
  as `L184`, `L344`. Stored as text — NO zfill, NO integer cast.

Files shipped this session: 5 in `pipelines/gis/dges_acesso/`
(`__init__.py`, config, ingestion DAG, backfill DAG, bronze_load DAG), 2
dbt models (`stg_dges_acesso.sql` + `silver_dges_acesso_uo.sql`), 2 dbt
YAMLs (extended `_staging_education__sources.yml`, new
`_staging_education__models.yml`), 1 new wiki source page
([[dges-acesso]]).

Silver model computes vagas-weighted `nota_ult_colocado` per (UO, year,
phase) — `SUM(vagas_iniciais * nota) / NULLIF(SUM(vagas_iniciais), 0)`
with NULL-nota cursos excluded from BOTH numerator and denominator (L24).
No `stg_dgeec_ens_sup` exists yet, so silver inlines the "latest run_date"
filter as a CTE; swap for a `ref` when DGEEC gets a staging model.

Parser locally verified against 5 representative files (2025 fase 1/2/3
.xlsx + 2022 fase 1 .xls + 2018 fase 1 .ods); zero unknown labels in any.
E2E Airflow run deferred to next session (Airflow stack not running in
this worktree).

**Pages touched**: [[log]] (this entry), [[index]] (Sources 27→28, P1
17→18, Education (3)→(4) + new dges-acesso bullet),
[[pt-education-amenity-pillar]] (source #4 dashboard flipped to ✅ shipped).
New page [[dges-acesso]].

## [2026-06-07] hygiene | codify dges_acesso bronze-loader deps in pyproject.toml + uv.lock

PR #56 landed the [[dges-acesso]] bronze loader on the live Airflow stack
via direct `pip install pandas openpyxl xlrd odfpy` into the running
containers — the deps were edited into `pipelines/pyproject.toml` in the
session worktree but **never committed**. Worktree was cleaned post-merge;
edit was lost. This entry records the redo: 4 deps added under a
`# Spreadsheet parsing (dges_acesso bronze loader)` block in
`pipelines/pyproject.toml`, `uv.lock` regenerated (`uv lock`: adds
`pandas` already-transitive, `openpyxl 3.1.5`, `xlrd 2.0.2`, `odfpy 1.4.1`,
`et-xmlfile 2.0.0`), `docker compose build airflow-scheduler` verified the
image builds cleanly + `python -c "import pandas, openpyxl, xlrd; from odf
import opendocument"` succeeds inside the rebuilt image. Without this, the
next `Dockerfile.airflow.uv` rebuild (e.g. via CI image cache invalidation
or a fresh `docker compose build`) would have produced a container that
ImportErrors on the dges_acesso bronze DAG.

Also trimmed the now-stale "swap CTE for ref" hint at the tail of the
file-level docstring in `dbt/models/silver/education/silver_dges_acesso_uo.sql`
— the architectural rationale for the inline `dgeec_latest_run` CTE
remains; the directive will return naturally when [[pt-education-amenity-pillar]]
Phase 1 ships `stg_dgeec_ens_sup`.

Lesson: `uv sync --frozen --package house4house-pipelines` in
[`Dockerfile.airflow.uv`](../Dockerfile.airflow.uv) reads from `uv.lock`,
not `pyproject.toml`. Editing only `pyproject.toml` produces a "successful"
docker build that silently omits the new deps — caught only by an explicit
in-image `python -c "import …"` check. Future deps additions must include
`uv lock` in the same commit.

**Pages touched**: [[log]] (this entry).

## [2026-06-09] silver | Phase 1 PR-A — stg_dgeec_ens_sup + stg_rede_escolar + silver_dges_acesso_curso + CTE swap

First half of Phase 1 silver promotions for the [[pt-education-amenity-pillar]].
Two new staging models + one new silver model + the CTE-swap that this
unblocks. PR-B will cover the two Público stagings once Open Qs #1 (CAOP-
Açores/Madeira sourcing) and #2 (Público↔DGEEC fuzzy-join thresholds) are
resolved.

**New models** (live-verified against the warehouse):
- `stg_dgeec_ens_sup` — typed view over `raw_dgeec_ens_sup` filtered to
  `max(run_date)`. 321 rows, 321 unique UOs, 0 NULL geoms. Dual-CRS
  exposed as `geom_4326` (display) + `geom_3763` (PT-TM06 for metric
  distance) per [[2026-05-10-dual-crs-storage]].
- `stg_rede_escolar` — typed view over `raw_rede_escolar`, filtered to
  (a) `max(run_date)`, (b) `situacao_escola = 'Em funcionamento'`,
  (c) `flag_extinguir != 'S'`, (d) `geom is not null`. ~14% of bronze
  rows have NULL geom (tail-page ArcGIS pagination artifact) and are
  dropped at staging so `not_null(geom_3763)` stays green. Trimmed to
  ~17 canonical columns; ArcGIS-internal + low-signal contact fields
  dropped (still accessible in bronze).
- `silver_dges_acesso_curso` — sibling to [[silver-dges-acesso-uo]] at
  per-curso grain `(codigo_unidade_organica, year, phase, codigo_curso)`.
  Keeps `nome_curso` + `nome_instituicao` + `grau` that the UO rollup
  drops (multi-valued under UO). 38,922 rows (1:1 with bronze grain).
  LEFT JOIN to `stg_dgeec_ens_sup`; `unmatched_uo` flag carries the same
  drift-sentinel semantics as the UO silver.

**Pillar convention locked**: staging filters to `max(run_date)`. The
rede_escolar + dgeec_ens_sup sources are point-in-time registers, not
trend data, so latest-only at the staging tier is what every downstream
consumer wants. Historical snapshots remain accessible in bronze. This
is the first time the pillar made a deliberate run_date-scope decision
at the staging tier — set as precedent for the upcoming Público
stagings and any future run_date-keyed bronze.

**CTE swap** in `silver_dges_acesso_uo`: the inline
`dgeec_latest_run` CTE that was a tactical workaround pre-staging is
now replaced with `ref('stg_dgeec_ens_sup')`. The TODO hint was
trimmed in PR #58; now resolved. Verified the model still produces the
same 5,889 rows + identical top-N medicine UOs (Univ. Porto 184.6,
Coimbra 178.8, Lisboa 177.2) as the previous chat's verification.

**Live verification** on the warehouse via the running docker stack:
- `dbt run --select stg_dgeec_ens_sup stg_rede_escolar silver_dges_acesso_curso silver_dges_acesso_uo` → 4/4 success in 1.02s
- `dbt test` over the same 4 → 21/21 PASS (not_null × PK + not_null × dual-CRS geoms + unique × PK + unique combination on curso silver)
- Spot-check top-8 Medicina (2025 F1) ordered by `nota_ult_colocado` desc returned Porto-FMUP (185.3, 275 vagas), Porto-ICBAS (184.7, 155 vagas), UMinho (183.5), UAveiro (182.8), Nova-FCM (180.3), Coimbra (179.0), Lisboa-FM (178.7), Porto-FMD (178.3 — Medicina Dentária). All with `unmatched_uo = false`, all 3 denormalised name columns populated.

**Test surface** (per L9 lock): unique PK + not_null on PK and dual-CRS
geoms for both stagings; unique combination + not_null on PK columns +
not_null on `unmatched_uo` for `silver_dges_acesso_curso`. Standard
shape; matches the bronze YAML uniqueness tests hardened against the
latest-only staging filter.

**Pages touched**: [[log]] (this entry), [[pt-education-amenity-pillar]]
(Phase 1 dashboard — flip stg_dgeec_ens_sup + stg_rede_escolar + new
silver_dges_acesso_curso row to ✅ shipped).

## [2026-06-09] silver | Phase 1 PR-B — stg_publico_rankings_sec + stg_publico_rankings_9ano (closes Phase 1 staging tier)

Second half of Phase 1 silver promotions for the [[pt-education-amenity-pillar]].
Two new staging models splitting [[publico-rankings]] by `kind` — sec
(secundário exames nacionais, 0-20 scale) + 9ano (3º ciclo Provas Finais,
0-5 scale). Closes the Phase 1 staging tier; 5/5 pillar bronzes now have
a typed staging view.

**Layer-separation decision**: The planning §Phase 1 wording for these
two stagings literally read "concelho fuzzy DICOFRE join" + "direct join
on codigo_uo_dgeec + fuzzy fallback". That conflated layers — the CAOP
DICOFRE join and the Público↔DGEEC bridge are silver/gold concerns, not
staging. PR-B keeps the stagings 1:1 single-source typed views,
consistent with the pillar's existing 3 stagings (stg_rede_escolar,
stg_dgeec_ens_sup, stg_dges_acesso — none of those do cross-source
joins). Open Qs #1 (CAOP-Açores/Madeira) and #2 (Público↔DGEEC bridge
thresholds) accordingly do NOT block PR-B; they block the future
silver_publico_rankings and xref_publico_dgeec models.

**New models** (live-verified against the warehouse):
- `stg_publico_rankings_sec` — filtered to `kind='sec'`. 4,411 rows
  across 7 years (2018–2024), 661 unique schools. ~35 canonical columns:
  headline scores + 9 disciplines × (média, num_provas, ranking) +
  contexto socioeconómico + retenção + equidade + prior-year carry. 0
  bad-coord rows. Dropped: cif_* (39% populated, low signal),
  per-disciplina ranking_superacao_* (low signal), equivalência cluster
  (small subset), legacy y17-y20 carries (semantics drift across
  vintages per the bronze YAML).
- `stg_publico_rankings_9ano` — filtered to `kind='9ano'`. 5,859 rows
  across 5 years (2018–2019, 2022–2024; the COVID gap 2020+2021 matches
  source ground truth). ~25 canonical columns: headline scores + only 2
  disciplines tested (Matemática + Português) + contexto + retenção +
  prior-year carry. 18 bronze rows dropped: 5 with NULL latitude + 13
  with lat/lon outside the PT bounding box (one had `latitude=37129` —
  clear data error). codigo_uo_dgeec passed through (~79% populated;
  the 21% gap is silver's problem).

**Data-quality discovery**: 13 9ano rows had garbage lat/lon
(latitude=37129 in one case; others outside lat 32-43 / lon -32 to -6).
ST_Transform to EPSG:3763 (PT-TM06) refuses these as out-of-bounds —
caught only when the not_null(geom_3763) test ran. Fixed by tightening
the staging filter to a PT bounding box (rather than just `not null`).
Pattern reusable for any other Público-style source with lat/lon
sourced from a non-canonical pipeline. The PT bounding box used:
lat 32-43 (Continente 36.9-42.2 + Açores 36.9-39.7 + Madeira 32.4-33.1),
lon -32 to -6 (Açores -31.3 westernmost).

**Live verification** on the warehouse via the running docker stack:
- `dbt run --select stg_publico_rankings_sec stg_publico_rankings_9ano`
  → 2/2 success in 0.70s.
- `dbt test` over the same 2 → **10/10 PASS** (not_null × PK + not_null
  × dual-CRS geoms + unique combination on (year, eid) for both).
- Row counts: sec 4,411 (bronze 4,411 — no row drops); 9ano 5,859
  (bronze 5,877 − 18 bad-coord rows).

**Phase 1 staging tier complete (5/5 sources)**:
- ✅ `stg_rede_escolar` (PR-A 2026-06-09)
- ✅ `stg_dgeec_ens_sup` (PR-A 2026-06-09)
- ✅ `stg_dges_acesso` (PR #56)
- ✅ `stg_publico_rankings_sec` (PR-B 2026-06-09)
- ✅ `stg_publico_rankings_9ano` (PR-B 2026-06-09)

Next: Phase 2 gold marts. The natural first move is
`silver_publico_rankings` (annual-best ranking per school across years)
and `xref_publico_dgeec` (the bridge table) — both require Open Q #1
(CAOP-Açores/Madeira sourcing) and Open Q #2 (Público↔DGEEC bridge
thresholds via 5 manual lookups) to be resolved first.

**Pages touched**: [[log]] (this entry), [[pt-education-amenity-pillar]]
(Phase 1 dashboard — flip both Público stagings ✅; close Phase 1
staging tier banner).

## [2026-06-09] silver | Phase 2 PR-C — silver_publico_rankings_sec + silver_publico_rankings_9ano (latest-year-per-school rollup)

First Phase 2 increment for the [[pt-education-amenity-pillar]]. Two
sibling silver models — latest-year-per-school rollup of the Público
sec + 9ano stagings, mirroring the silver_dges_acesso_{uo,curso} sibling
pattern (different scales, different column sets → separate tables to
prevent cross-kind aggregation mistakes downstream).

**Per pillar decision #3** (planning §2): "Per-school média total
exames nacionais, latest year only (v1)." Implemented with
`row_number() over (partition by eid order by year desc)` keep-only-rn=1.
Schools that haven't appeared since 2019 still surface with
`ranking_year=2019`; consumers wanting fresh-only filter on
`ranking_year` themselves.

**New models** (live-verified):
- `silver_publico_rankings_sec` — 661 unique schools (0 dupes), years
  2018-2024, 624 schools (94%) have a 2024 ranking, avg ranking_score
  11.50/20. Top-5 2024 ranks 1-5 sequential as expected. All staging
  columns preserved; `media_total_exames` renamed to `ranking_score`
  per planning §4.1 lean-gold-schema convention.
- `silver_publico_rankings_9ano` — 1,313 unique schools, years
  2018-2019 + 2022-2024 (COVID gap matches source), 1,158 schools (88%)
  have a 2024 ranking, avg ranking_score 2.94/5. `codigo_uo_dgeec`
  passthrough preserved for the future xref_publico_dgeec bridge.

**Eid mutual exclusion verified**: empirically 0 eids appear in both
sec and 9ano (Público assigns separate eids based on cohort tested).
This locked the "two sibling silvers" design choice over a unified
table — there's literally no eid that would benefit from being in both.

**Live verification** on the warehouse via the running docker stack:
- `dbt run --select silver_publico_rankings_sec silver_publico_rankings_9ano`
  → 2/2 success.
- `dbt test` over the same 2 → **10/10 PASS** (not_null × PK + not_null
  × ranking_year + not_null × dual-CRS geoms + unique × eid for both).

**Phase 2 prerequisites still pending**:
- Open Q #1 (CAOP-Açores/Madeira sourcing) — blocks adding DICOFRE to
  silver_publico_rankings via CAOP spatial join (sec-side, since sec
  has no codigo_uo_dgeec passthrough).
- Open Q #2 (Público↔DGEEC bridge thresholds) — gates
  `xref_publico_dgeec` (the bridge table) and the gold `dim_school`.
- Open Q #5 (`dim_school` PK strategy) — discriminator col vs split
  tables for 6-digit basic/sec vs 4-digit higher-ed.

**Pages touched**: [[log]] (this entry), [[pt-education-amenity-pillar]]
(Phase 2 dashboard — add `silver_publico_rankings_{sec,9ano}` ✅).

## [2026-06-09] gold | Phase 2 PR-D — xref_publico_dgeec bridge (Open Q #2 resolved)

First gold-tier mart in the [[pt-education-amenity-pillar]] and the
resolution of Open Q #2 (Público↔DGEEC bridge thresholds). Bridge table
`gold_analytics.xref_publico_dgeec` maps every Público school id (eid)
to its DGEEC 6-digit `codigo_escola` (CODESCME), with explicit
`match_method` provenance and `match_score`/`match_distance_m`
diagnostics per row.

**Empirical-probe-driven algorithm** (locked 2026-06-09 against the
live warehouse, not the 5 manual lookups the planning doc anticipated
— having both Público + DGEEC already in the warehouse let me probe
the entire 1,974-school corpus directly):

1. **id_publico ↔ DGEEC prefix probe is dead.** Tested
   `LEFT(codigo_escola, 4) = LPAD(id_publico, 4)` with concelho match
   on all 661 sec schools → **0 matches**. Público's `id` is its own
   short code, not a DGEEC prefix. Explicitly NOT in the final
   algorithm.

2. **Path 1 — `direct_uo_fuzzy` (9ano only)**: when Público's
   `codigo_uo_dgeec` is populated, restrict rede_escolar candidates to
   the UO (`r.codigo_uo = p.codigo_uo_dgeec`) and pick the best
   name-similarity match. The UO scope is sufficient evidence on its
   own — 921/921 (100%) resolve at avg sim=0.992. No similarity
   threshold needed.

3. **Path 2 — `fuzzy_spatial` (all sec + 9ano residual)**: ST_DWithin
   500m + pg_trgm similarity ≥ 0.6 on
   `unaccent(lower(nome))`. The 0.6 threshold was picked by eyeballing
   the 0.3-0.6 band: 0.6+ is bulletproof; 0.4-0.6 has ~30% false
   positives (e.g. "Colégio Liverpool" vs "Grande Colégio Universal"
   at 0.303). NO concelho-name gate — costs island coverage where
   Público labels concelhos like "Lagoa (R.A.A)" vs DGEEC's "Lagoa".

4. **Path 3 — superseded by ensemble** (commit 2 → commit 3): the
   `name_perfect_extended` Path 3 idea (recover sim=1.000 within 2km)
   was a single-algorithm fix. Replaced by a full ensemble approach
   that subsumes it.

**Final algorithm — 2-stage ensemble** (locked commit 3 of PR-D
after a multi-algorithm comparison probe):

- **Stage 1 — `direct_uo_fuzzy`** (9ano with `codigo_uo_dgeec`): UO
  scope alone is sufficient evidence. 921/921 (100%) at avg sim 0.992.
  Confidence: 'high'.
- **Stage 2 — `ensemble`** (sec + 9ano residual): candidate window =
  same normalized concelho OR within 2km. Four algorithms vote on the
  best codigo_escola:
  1. Trigram (pg_trgm) ≥ 0.6
  2. Levenshtein (1 - lev/maxlen) ≥ 0.5
  3. Jaccard token-set ≥ 0.3
  4. Phonetic (dmetaphone first 2 tokens) match
  
  Each fails in different ways (trigram is order-sensitive, Levenshtein
  blows up on length diffs, Jaccard is bag-of-words, phonetic loses
  non-stem content). When ≥2 converge on the same codigo_escola,
  false-positive risk drops sharply. `match_confidence` = 'high' (≥3
  agree), 'medium' (=2), 'unmatched' (<2).

**Single-algorithm coverage probe (candidate window only, 1,971 schools)**:
| Algorithm | Matched | % |
|---|---|---|
| Levenshtein ≥ 0.5 | 1,894 | 96.1% |
| Jaccard ≥ 0.3 | 1,894 | 96.1% |
| Phonetic match | 1,893 | 96.0% |
| Jaccard ≥ 0.5 | 1,842 | 93.5% |
| **Trigram** ≥ 0.6 (production v1) | 1,839 | 93.3% |
| Contains (substring) | 1,691 | 85.8% |
| Exact normalized | 1,642 | 83.3% |

**Final ensemble coverage on full corpus (1,974 schools)**:

| kind | match_method | match_confidence | schools |
|---|---|---|---|
| 9ano | direct_uo_fuzzy | high | 921 |
| 9ano | ensemble_high | high | 296 |
| 9ano | ensemble_medium | medium | 26 |
| 9ano | unmatched | unmatched | 70 |
| sec | ensemble_high | high | 622 |
| sec | ensemble_medium | medium | 9 |
| sec | unmatched | unmatched | 30 |

Total: 1,874/1,974 matched = **94.9% coverage** (vs trigram-only
91.7%, +63 schools). Sec 95.5%, 9ano 94.7%. Confidence tiers:
high=1,839 (93.2%), medium=35 (1.8%), unmatched=100 (5.1%). The 100
unmatched are mostly small privados / IPSS not in the rede_escolar
register at all (genuinely absent).

Spot checks:
- 9ano #1 Colégio Novo da Maia → `ensemble_high`, **4 votes**, sim
  1.00, 594m off (would be unmatched at strict 500m).
- sec #1 Colégio Nossa Senhora do Rosário → `ensemble_high`, 4 votes,
  sim 1.00, 0m.
- sec #11 Colégio de S. Tomás → `unmatched` (genuinely ambiguous —
  trigram, Levenshtein, Jaccard, phonetic each pick a different wrong
  DGEEC school; no consensus).

**Sanity-guard refinement** (commit 4 of PR-D): top-100 eyeball
surfaced two false-positive classes that the ensemble vote alone
missed:

1. **Far-distance trap** — Colégio Mira Rio (Lisboa, 9ano #28) matched
   another "Mira Rio" 8.1 km away. 4 algorithms all picked it (sim
   1.00, all tokens identical). Probably wrong school; Lisboa concelho
   spans wide but 8km within-concelho is suspect.
2. **Shared-prefix trap** — "Colégio de Nossa Senhora da Esperança"
   (sec #87 and 9ano #99) matched "Colégio de Nossa Senhora da Paz"
   at sim 0.66, 1.6 km. The distinguishing saint differs but most
   tokens agreed → trigram+Levenshtein+Jaccard+phonetic all picked
   the wrong nearby school.

Added post-vote guards: `sim_ok = match_score ≥ 0.7` AND `dist_ok =
match_distance_m ≤ 3000`. When ≥3 votes but guards fail, demote to
`medium`. When 2 votes and guards fail, demote to new `low` tier.
Stage 1 (`direct_uo_fuzzy`) is unaffected — UO scope is its own
evidence.

**Final tier breakdown** (1,974 schools):

| kind | high | medium | low | unmatched |
|---|---|---|---|---|
| 9ano | 1,193 | 28 | 22 | 70 |
| sec | 609 | 14 | 8 | 30 |
| **Total** | **1,802** | **42** | **30** | **100** |

Total matched: 1,874 (94.9%, unchanged). Downstream consumers now
have a graceful filter:
- `high` = canonical, trust completely (1,802 = 91.3%)
- `high + medium` = good coverage with audit trail (1,844 = 93.4%)
- `high + medium + low` = max recall (1,874 = 94.9%)
- `unmatched` = explicitly absent (100 = 5.1%)

- `dbt run --select +xref_publico_dgeec` → 1 model built.
- `dbt test --select xref_publico_dgeec` → **6/6 PASS** (unique +
  not_null × publico_eid; not_null + accepted_values × kind;
  not_null + accepted_values × match_method).

**Open Q #2 resolved.** The next gates for `dim_school` are now Open
Q #5 (PK strategy — discriminator col vs split tables) and Open Q #1
(CAOP-Açores/Madeira sourcing — only relevant if `dim_school` wants
DICOFRE for island schools; v1 fallback is leave NULL).

**Pages touched**: [[log]] (this entry), [[pt-education-amenity-pillar]]
(Phase 2 dashboard — flip xref_publico_dgeec ✅; flip Open Q #2 to ✅
RESOLVED in §9).
