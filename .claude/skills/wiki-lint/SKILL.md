---
name: wiki-lint
description: Health-check the project wiki for contradictions, stale claims, orphan pages, and missing cross-references. Writes a timestamped report to wiki/lint-reports/ and updates the freshness indicator in wiki/index.md. Designed to run weekly via launchd cron AND on-demand from any session.
---

# /wiki-lint

You are the wiki lint pass for House4House. The project's accumulated knowledge lives at `wiki/` (see `wiki/CLAUDE.md` for the schema). Your job is to surface drift, contradictions, and gaps — never to silently fix them. Findings are advisory; the user reviews on Monday morning.

**Operating mode:** This skill runs unattended (weekly cron OR on-demand from a session). **Do NOT ask the user for confirmation before reading files, running grep/git commands, or writing the lint report and the two narrow updates this skill is allowed to make** (the timestamped lint-report file under `wiki/lint-reports/`, the appended line in `wiki/log.md`, and the `Last lint run:` line in `wiki/index.md`). All three writes are explicitly part of this skill's scope and should happen directly. If you find yourself wanting to ask "should I write this?" — the answer is yes; just do it.

## Workflow

Execute these steps in order. Be terse — the output report is read by a human glancing at it Monday morning, not deeply studying it.

### Step 1 — Read the index and log

Read `wiki/index.md` and `wiki/log.md` first. The index tells you what pages exist; the log tells you what's been ingested recently. Don't read every page on every run — your job is to scan, not to deeply re-read.

### Step 2 — Find the wiki root

Determine which wiki directory to lint:

- If the `WIKI_PATH` environment variable is set, use it as the wiki root (used by tests to point at fixture wikis like `tests/wiki-fixtures/seed/`).
- Otherwise, use `git rev-parse --show-toplevel` via Bash to get the repo root, and the wiki is at `<root>/wiki/`.

All paths in the report are relative to the wiki root.

### Step 3 — Scan for issues

Run these checks:

**A. Stale claims.** Glob `wiki/**/*.md`, parse YAML frontmatter, find pages where `last_verified` (or `last_status_update` for sprint pages) is older than 90 days from today. List them.

**B. Orphan pages.** A page is orphaned if no other wiki page links to it AND `index.md` doesn't list it. Use `grep -rE '\[.*\]\(.*<page-filename>.*\)' wiki/` for inbound link detection. Skip `wiki/lint-reports/*` (transient output) and `wiki/log.md` (chronological, no inbound links expected).

**C. Concepts mentioned but lacking own page.** Skim a sampling (~20% of pages) for canonical-name patterns that appear repeatedly without their own `wiki/concepts/<name>.md` file. Examples of canonical names worth their own page: "SCD2", "bronze-permissive", "ZenRows", "PostGIS", "medallion", "Pydantic AI". For each unhomed canonical name, suggest a concept-page filename.

**D. Missing cross-references.** When a wiki page mentions a canonical concept name that DOES have its own `wiki/concepts/<name>.md` page, but doesn't link to it, flag it. Heuristic: text contains "SCD2" but no `concepts/scd2-row-hash.md` link in that page.

**E. Contradictions between pages (semantic).** This is the highest-value check. Read pages topically related (e.g., all wiki/concepts/*.md plus the sources pages they reference) and identify any places where two pages make incompatible claims about the same fact. Examples:
   - Page A says "SCD2 deduplicates by row_hash" while page B says "SCD2 deduplicates by primary key" — contradiction.
   - Page A says "the pipeline runs nightly at 02:00 UTC" while page B says "weekly Sundays". — contradiction.
For each contradiction, name both pages and quote the conflicting claims.

**F. `index.md` drift.** Read each summary line in `wiki/index.md` and compare to the current first paragraph (or `description` frontmatter) of the linked page. If the summary no longer matches, list the index entry that needs updating.

### Step 4 — Write the report

The report path is `wiki/lint-reports/<UTC-timestamp>.md`. Use Bash `date -u +%Y-%m-%dT%H%M%S` to get the timestamp.

Report shape:

```markdown
# Wiki lint — <timestamp>

Pages scanned: <count>
Issues surfaced: <count>

## A. Stale claims (last_verified > 90 days)

- `wiki/sources/foo.md` — last_verified 2025-12-01 (158 days)
- ...

## B. Orphan pages

- `wiki/concepts/example.md` — no inbound links, not in index.md

## C. Concepts mentioned but lacking own page

- "Cosmos DAG generation" mentioned in 3 pages — suggest `wiki/concepts/cosmos-dag-generation.md`

## D. Missing cross-references

- `wiki/sources/idealista.md` mentions "SCD2" but doesn't link to `wiki/concepts/scd2-row-hash.md`

## E. Contradictions

- `wiki/concepts/scd2-row-hash.md` says "..." but `wiki/sources/idealista.md` says "..."

## F. Index drift

- index.md says "Idealista listings via ZenRows discovery API" but `wiki/sources/idealista.md` description starts "Idealista new-construction developments via ZenRows two-pass scrape"

## Summary

<one-line headline>: <N issues across <K> categories>
```

If a category has zero findings, write `_no findings_` under it. Don't omit the heading.

### Step 5 — Append to log

Append one line to `wiki/log.md` in this exact format:

```
## [YYYY-MM-DD] lint | <N> issues across <K> categories
```

### Step 6 — Update freshness indicator

Edit `wiki/index.md` and replace the `Last lint run: ...` line near the top with `Last lint run: YYYY-MM-DD` (today's date). This is the freshness signal the user sees passively whenever they open the index.

### Step 7 — Output a one-line summary

Print one line to stdout:

```
wiki-lint complete: <N> issues, report at wiki/lint-reports/<filename>
```

## Failure modes

- If `wiki/` doesn't exist (e.g., running from outside the repo), exit cleanly with `wiki-lint: no wiki found at <path>; nothing to do`.
- If `wiki/lint-reports/` doesn't exist, create it.
- If reading any page fails (permission, encoding), note it in the report under a `## Errors` section but continue with the rest of the lint.
- If a category genuinely has nothing to scan (e.g., wiki has only the seed pages), say `_no findings_` rather than skipping the heading.

## Scope

You should NOT modify wiki content beyond the three files this skill explicitly updates: `wiki/index.md` (freshness line only), `wiki/log.md` (single appended line), and the new `wiki/lint-reports/<timestamp>.md` (the report itself). All other wiki edits happen via separate `/wiki-ingest` invocations or interactive sessions.
