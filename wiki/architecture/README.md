# Wiki Architecture Section

## For future Claude

This is the **orientation page** for `wiki/architecture/` — the section that captures the project's as-built / as-designed architecture: tech stack, infrastructure, orchestration topology, and data-quality framework. Read this first to know which page to drill into; each architecture page has its own `## For future Claude` preamble for orientation. The section is companion to (NOT a duplicate of) `wiki/concepts/` (rules + patterns) and `wiki/decisions/` (ADRs).

## What lives here

Four pages, each compressed from a README section:

- [[tech-stack]] — README §3 — every technology choice with rationale + alternative-stack-considered table; cross-links to the 7 stack-decision ADRs landed in PR 6.
- [[infra]] — README §4 — Docker Compose service map, server spec (Hetzner AX102), PostgreSQL schema organization (matches [warehouse/init/001_create_schemas.sql](../../warehouse/init/001_create_schemas.sql)).
- [[orchestration]] — README §11 — Airflow DAG taxonomy (ingestion / transformation / quality / maintenance), schedule map, dependency conventions.
- [[data-quality]] — README §13 — dbt tests + Great Expectations, pipeline metadata table, test-coverage strategy.

## Why this section exists

Before PR 6, the architecture content lived only in the README. Decomposing it into the wiki gives:

1. **Schema-header routing**: per-area `CLAUDE.md` files can route Claude to e.g. [[infra]] for docker-compose questions instead of the full 4,495-line README.
2. **Cross-reference graph**: architecture pages link to the sources (e.g., [[infra]] → [[caop]] / [[bgri]] / etc. for which schemas hold which sources), the concepts ([[medallion-layering]], [[ingest-flows]]), and the decisions ([[2026-05-10-postgis-as-warehouse]] etc.). Obsidian's graph view makes the architecture-decision connections traversable.
3. **Decoupling from README evolution**: the README is being progressively retired (see PR 8 plan); architecture content stays in the wiki where it's maintained alongside code evolution rather than blueprint evolution.

## Page conventions

Architecture pages use `type: plan` in frontmatter (same as sprint and use-case pages). Required sections:

- `## For future Claude` preamble (per the universal rule)
- `## What it is` — short summary of what the page covers
- `## How it's deployed` (or equivalent) — concrete components, versions, ports, paths
- `## Why this shape` — the rationale, with `[[wikilinks]]` to relevant ADRs
- `## See also` — outbound `[[wikilinks]]` to sources, concepts, decisions

Tables are encouraged where they compress information (port maps, schema lists, schedule maps).

## See also

- [[overview]] — 1-page synthesis of the project; entry-point for orientation queries
- [[medallion-layering]] — bronze/silver/gold schema map; foundation for [[infra]]'s schema section
- [[ingest-flows]] — six-flow taxonomy that the [[orchestration]] page operationalizes via Airflow DAGs
