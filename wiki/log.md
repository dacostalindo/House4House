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

Each new page carries the standard frontmatter + `## For future Claude` preamble per [[wiki/CLAUDE.md|wiki schema]]; all wikilinks resolve. The wiki/index.md Concepts section grew from 10 to 13 pages; the `## By area of code` `pipelines/` row updated to list the three new portal-* concepts.

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
