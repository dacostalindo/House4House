# House4House Wiki

## For future Claude

This is the **landing page** for the wiki — orientation for human readers. It explains how the wiki is structured (sources/concepts/pipelines/decisions/plan/lint-reports), who maintains what (Claude writes; humans read), and how to invoke the lint workflow (`make install-cron` for the weekly cron). The schema document for actual page conventions is at `CLAUDE.md` next to this file. Read this file when a human is exploring the wiki for the first time; otherwise prefer `CLAUDE.md`.

This directory is the project's persistent knowledge base. It is **maintained by Claude Code**, not written by hand. You read it; the LLM writes it.

## How to use

- **Browse**: open `index.md` to see every page with a one-line summary.
- **Schema for Claude**: `CLAUDE.md` is the schema document — it tells Claude how to maintain the wiki (page conventions, ingest workflow, query workflow, lint workflow). Read it if you want to understand how the LLM treats this directory.
- **What you do**: drop new sources into `raw/` (or paste them in chat), tell Claude to ingest them. Claude reads the source, updates the relevant wiki pages, refreshes `index.md`, and appends an entry to `log.md`.
- **What Claude does**: writes and maintains everything in `sources/`, `concepts/`, `pipelines/`, `decisions/`, and `plan/`.

## Sections

- `sources/` — one page per data source (idealista, srup, crus, etc.).
- `concepts/` — architectural patterns and cross-cutting rules (bronze-permissive, SCD2 row-hash, Pydantic-not-in-dlt, etc.).
- `pipelines/` — one page per ingestion pipeline.
- `decisions/` — dated decision records (why we picked uv workspace, why cosmos pinned, etc.).
- `plan/` — the project's strategic roadmap, decomposed from the root README. See `plan/README.md` for organization.
- `lint-reports/` — output of the weekly `/wiki-lint` cron. Last lint timestamp visible at the top of `index.md`.
- `log.md` — chronological append-only record of ingest/query/lint events.

## Lint

A weekly `launchd` cron fires `claude -p /wiki-lint --max-turns 5` Sundays 06:00 local. Output lands in `lint-reports/`. Install via `make install-cron` from the repo root.
