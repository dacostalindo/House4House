# House4House — Claude Code project rules

Portugal real estate + regulatory-GIS data warehouse. Stack: Airflow 2.10 + dlt + dbt-postgres + Cosmos + PostGIS + Streamlit/Kepler.gl. Local dev via uv workspace + Docker Compose; entry point is `make setup`.

## Schema for Claude Code (read this first)

This project uses a **karpathy-style LLM Wiki** at [`wiki/`](./wiki/). The wiki is the single source of truth for project rules, patterns, and accumulated knowledge. **Before editing files in this repo, scan the area-CLAUDE.md (linked below) for your task type and read the linked `wiki/concepts/` page(s).** Don't read every wiki page on every edit — the per-area task routing tells you exactly which to read.

The schema for the wiki itself (page conventions, ingest/query/lint workflows) lives at [`wiki/CLAUDE.md`](./wiki/CLAUDE.md) — read it if you'll be touching wiki content.

## Area routing

| When editing files in… | Read first |
|---|---|
| `pipelines/` (any source, DAG, dlt resource, scraper) | [pipelines/CLAUDE.md](./pipelines/CLAUDE.md) |
| `dbt/` (any model, macro, source YAML) | [dbt/CLAUDE.md](./dbt/CLAUDE.md) |
| `apps/` (Streamlit pages, Kepler.gl maps) | [apps/CLAUDE.md](./apps/CLAUDE.md) |
| `wiki/` (knowledge base content) | [wiki/CLAUDE.md](./wiki/CLAUDE.md) |

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Wiki maintenance → invoke /wiki-lint (also runs weekly via launchd cron)
