# House4House

Portugal real estate + regulatory GIS data warehouse. Airflow + dlt + dbt-postgres + Cosmos + PostGIS + MinIO + Streamlit/Kepler.gl.

## Getting Started

**Prerequisites**: Docker (or OrbStack), [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh` — make sure `~/.local/bin` is on `PATH`).

```bash
git clone <repo>
cd House4House
make setup       # uv sync (workspace) + pre-commit install
make verify      # smoke check: imports + ruff + ty (advisory) + pytest
make up          # docker compose up: airflow + postgres + minio + metabase
```

For project rules and conventions Claude should follow when editing this repo, see [CLAUDE.md](./CLAUDE.md). For the project's strategic blueprint (use cases, sources, architecture, sprints, risks, roadmap), see [the wiki](./wiki/) — start with [wiki/overview.md](./wiki/overview.md).

## Repo layout

| Path | Role |
|---|---|
| [pyproject.toml](./pyproject.toml) | Workspace coordinator (`apps`, `pipelines` members) + ruff/pytest config |
| [apps/](./apps/) | Streamlit app (Kepler.gl maps, warehouse views) — workspace member |
| [pipelines/](./pipelines/) | Airflow DAGs + dlt sources + scrapers — workspace member |
| [dbt/](./dbt/) | dbt-postgres models (staging → silver → gold) |
| [warehouse/init/](./warehouse/init/) | PostGIS schema bootstrap |
| [wiki/](./wiki/) | LLM-maintained knowledge base — sources, concepts, decisions, sprints, use-cases, architecture, planning |
| [Dockerfile.airflow.uv](./Dockerfile.airflow.uv) | uv-based Airflow image (Phase 1 of dev-tooling plan) |
| [apps/Dockerfile.uv](./apps/Dockerfile.uv) | uv-based Streamlit image |

---

## Project blueprint — see the wiki

The full strategic + technical blueprint (originally a ~4,500-line section here) was migrated into [wiki/](./wiki/) across Phase 3 PRs 2-7 of the dev-tooling plan. Each former README section now lives as one or more wiki pages, cross-linked via `[[wikilinks]]` for navigation in Obsidian or via Claude Code.

**Where to start:**

- [wiki/overview.md](./wiki/overview.md) — 1-page synthesis of the project; entry-point for orientation queries.
- [wiki/index.md](./wiki/index.md) — full catalog of every wiki page grouped by type (sources / concepts / decisions / architecture / planning / sprints / use-cases).
- [wiki/CLAUDE.md](./wiki/CLAUDE.md) — schema document for how the wiki itself is structured (page conventions, ingest workflow, lint workflow).

**Section map** (former README → current wiki location):

| Former README section | Lives in the wiki at |
|---|---|
| §1 Business Use Cases (UC-1, UC-2, UC-3) | [wiki/use-cases/](./wiki/use-cases/) — three UC pages combining product narrative + conceptual data model + serving layer |
| §2 MVP Data Sources (31 Sources) | [wiki/sources/](./wiki/sources/) — 23 source pages with `priority: P0 \| P1 \| P2` frontmatter (P0 = foundation; P1 = use-case-enabling; P2 = specialty). Source-priority replaces the README's tier discussion. |
| §3 Technology Stack | [wiki/architecture/tech-stack.md](./wiki/architecture/tech-stack.md) + 7 stack-decision ADRs in [wiki/decisions/](./wiki/decisions/) |
| §4 Infrastructure & Deployment | [wiki/architecture/infra.md](./wiki/architecture/infra.md) + [wiki/decisions/2026-05-10-single-server-self-hosted.md](./wiki/decisions/2026-05-10-single-server-self-hosted.md) |
| §5 Conceptual Architecture (Medallion) | [wiki/concepts/medallion-layering.md](./wiki/concepts/medallion-layering.md) |
| §6 Data Flows by Source Type | [wiki/concepts/ingest-flows.md](./wiki/concepts/ingest-flows.md) — six-flow taxonomy (A REST / B scraping / C GIS / D derived / E spatial composition / F portal cross-reference) |
| §7 Conceptual Data Models | Per-UC: [wiki/use-cases/UC-1.md](./wiki/use-cases/UC-1.md), [UC-2](./wiki/use-cases/UC-2.md), [UC-3](./wiki/use-cases/UC-3.md) |
| §8 Physical Data Models | **Deferred — dbt-docs is the source of truth.** Run `dbt docs serve` for the canonical schema graph. Re-imported into the wiki only if the dbt-docs surface proves insufficient. |
| §9 Spatial Data Strategy | [wiki/concepts/spatial-strategy.md](./wiki/concepts/spatial-strategy.md) + [wiki/decisions/2026-05-10-dual-crs-storage.md](./wiki/decisions/2026-05-10-dual-crs-storage.md) |
| §10 Dependency Graph & Critical Path | Folded into [wiki/sprints/](./wiki/sprints/) (per-sprint dependencies in each sprint page's frontmatter + body) |
| §11 Orchestration & Scheduling | [wiki/architecture/orchestration.md](./wiki/architecture/orchestration.md) |
| §12 Sprint Plan (10 Sprints / 20 Weeks) | [wiki/sprints/](./wiki/sprints/) — 11 data-product sprint pages + sprint-dev-tooling (gstack 7-Phase roadmap) |
| §13 Data Quality Framework | [wiki/architecture/data-quality.md](./wiki/architecture/data-quality.md) |
| §14 Risk Register & Mitigation | [wiki/planning/risks.md](./wiki/planning/risks.md) |
| §15 Resource Requirements & Costs | [wiki/planning/resources.md](./wiki/planning/resources.md) |
| §16 Future Expansion (P3/P4 Roadmap) | [wiki/planning/roadmap-p3-p4.md](./wiki/planning/roadmap-p3-p4.md) |
| §17 Serving Layer + Go/No-Go Milestones | Serving-layer per UC: in each `wiki/use-cases/` page. Go/No-Go gates: [wiki/planning/milestones.md](./wiki/planning/milestones.md) |

**Total wiki content**: ~80 typed-content pages across 23 sources + 10 concepts + 13 ADRs + 4 architecture + 4 planning + 12 sprints + 3 use-cases + the overview.

## Why this README is a stub

The original ~4,500-line strategic blueprint accumulated value over months of solo planning, but it was a single file evolving in-place — easy to drift, hard to navigate, impossible to graph-traverse, and increasingly stale relative to shipped code. Phase 3 of the dev-tooling plan (gstack-driven; see [wiki/sprints/sprint-dev-tooling.md](./wiki/sprints/sprint-dev-tooling.md)) decomposed it into a structured wiki where each rule, decision, source, and milestone has its own page + cross-references. The wiki is read in Obsidian (graph view + backlinks) and edited via Claude Code; both modes operate on the same `[[wikilinks]]` syntax per [wiki/CLAUDE.md](./wiki/CLAUDE.md).

The original README is preserved in git history at the commit immediately preceding this stub. Run `git log --diff-filter=D --follow -- README.md` to find the retirement commit; `git show <commit>^:README.md` recovers the original content if needed.
