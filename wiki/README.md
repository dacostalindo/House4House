# House4House Wiki

## For future Claude

This is the **canonical first-visit entry** for the wiki — the trunk-test page. Read this first when you open `wiki/` for the first time. It tells you what each file at this directory level does and which subdirectory holds what kind of typed content. The wiki is **maintained by Claude Code** (you read it; the LLM writes it) and **read primarily in Obsidian** (graph view, backlinks panel, autocomplete on `[[`). For Claude Code editing, file paths + `[[wikilinks]]` are how navigation works.

## Where to go

| If you want… | Read |
|---|---|
| 1-page synthesis of the project (entry-point for "what is this?") | [`overview.md`](./overview.md) |
| The schema doc — how the wiki is structured, page conventions, ingest/query/lint workflows | [`CLAUDE.md`](./CLAUDE.md) |
| The catalog — every page grouped by type with a 1-line summary | [`index.md`](./index.md) |
| The chronological event log — when each page was created/updated, lint runs, schema changes | [`log.md`](./log.md) |
| Output of the weekly `/wiki-lint` cron + on-demand `make wiki-lint` runs | [`lint-reports/`](./lint-reports/) |

## Typed-content folders

Each folder holds one shape of page (the schema in `CLAUDE.md` defines required frontmatter + sections per type):

| Folder | Page type | What it holds |
|---|---|---|
| [`sources/`](./sources/) | source | One page per data source — Idealista, JLL, REMAX, Zome (portals); INE, BPStat, ECB, Eurostat (APIs); SCE (scraper); 14 GIS sources |
| [`concepts/`](./concepts/) | concept | Rules + patterns the project enforces — `[[bronze-permissive]]`, `[[scd2-row-hash]]`, `[[pydantic-not-in-dlt]]`, `[[medallion-layering]]`, etc. |
| [`decisions/`](./decisions/) | decision | Dated ADRs — why we picked uv workspace, why Cosmos pinned, why SQLA 1.4 concession, etc. |
| [`sprints/`](./sprints/) | plan / sprint | Sprint pages tracking the project's data-product roadmap + a single dev-tooling sprint covering the gstack-driven Phase 1-7 work |
| `use-cases/` (lands in PR 4) | plan / use-case | One page per UC — UC-1 investment, UC-2 pricing, UC-3 land development. Each combines product narrative + data model + serving layer |
| `architecture/` (lands in PR 6) | plan / architecture | "How it's built" reference — stack, infra, orchestration, data-quality strategy |
| `planning/` (lands in PR 7) | plan / planning | "What might/will happen" — risks, resources, P3/P4 roadmap, milestones |

## Lint

A weekly `launchd` cron fires `claude -p /wiki-lint --max-turns 30` Sundays 06:00 local. Output lands in [`lint-reports/`](./lint-reports/). Install via `make install-cron` from the repo root. On-demand: `make wiki-lint`.
