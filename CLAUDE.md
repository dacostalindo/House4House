# House4House — Claude Code project rules

Portugal real estate + regulatory-GIS data warehouse. Stack: Airflow 2.10 + dlt + dbt-postgres + Cosmos + PostGIS + Streamlit/Kepler.gl. Local dev via uv workspace + Docker Compose; entry point is `make setup`.

## How to operate (4 rules)

Borrowed from [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) — a third-party distillation of observations Andrej Karpathy has made about common LLM coding pitfalls. Apply these to every coding task in this repo; they override defaults like "be helpful by suggesting more."

1. **Think Before Coding.** Don't assume. Don't hide confusion. Surface tradeoffs explicitly before writing code. If two reasonable approaches exist, name both and pick one with one-sentence reasoning — don't quietly choose.
2. **Simplicity First.** Minimum code that solves the problem. Nothing speculative. No future-proofing abstractions, no helper functions for a single caller, no error handling for impossible states. Three similar lines beats a premature abstraction.
3. **Surgical Changes.** Touch only what you must. Clean up only your own mess. A bug fix doesn't need surrounding refactors; a one-shot script doesn't need a class hierarchy. Leave adjacent code alone unless the task requires it.
4. **Goal-Driven Execution.** Define success criteria before starting. Loop until verified — don't declare done on "the code compiles." For UI work, test in a browser. For pipelines, run against fixtures. For wiki edits, check the linter passes. Verification is part of the task, not a follow-up.

These rules apply at the *behavior* layer; the area-routing table below tells you *which files* a given task touches.

## Schema for Claude Code (read this first)

This project uses a **karpathy-style LLM Wiki** at [`wiki/`](./wiki/). The wiki is the single source of truth for project rules, patterns, and accumulated knowledge. **Before editing files in this repo, scan the area-CLAUDE.md (linked below) for your task type and read the linked `wiki/concepts/` page(s).** Don't read every wiki page on every edit — the per-area task routing tells you exactly which to read.

**After every commit, update the wiki**: append a one-line entry to [`wiki/log.md`](./wiki/log.md) and update any wiki pages whose claims the commit affected (sprint pages, source pages, concept pages, decision records). Commits that diverge from the wiki create drift; the wiki is the source of truth.

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
- Wiki reconciliation + post-merge gstack ingest → invoke /wiki-reconcile
