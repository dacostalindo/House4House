---
description: Reconcile the wiki — surface drift, resolve contradictions, ingest post-merge gstack artifacts. The wiki maintains its own truth.
---

Use the wiki-reconcile skill. Execute `/wiki-reconcile $ARGUMENTS`:

The optional argument is a topic, page name, or sub-folder to focus on. If not provided, scan the whole wiki.

1. Read `wiki/CLAUDE.md` first — the schema rules (page conventions, required frontmatter, `[[wikilinks]]` resolution, write rules).
2. Read `wiki/index.md` to understand the full wiki landscape.

3. Spawn parallel subagents to find drift:
   - **Schema agent**: scan all `wiki/*.md` for frontmatter compliance per page type (required fields, `type` enum, `confidence` enum for decisions, `priority` enum for sources), `## For future Claude` preamble presence + position, required sections per page type.
   - **Links agent**: scan all `wiki/*.md` for `[[wikilinks]]` — skip inline-code spans, resolve each via the rule in `wiki/CLAUDE.md` (case-insensitive basename across `concepts/`, `sources/`, `decisions/`, `pipelines/`, with support for `[[dir/name]]` explicit prefix). Flag unresolved links and basename ambiguities.
   - **Reciprocity agent**: scan `wiki/decisions/` for `supersedes:` and `superseded_by:` frontmatter fields — verify reciprocal pairing. Also scan `wiki/sprints/` for `## Status update history` sections and verify each line matches regex `^- \d{4}[-Q]\S*:\s+\S.*`.
   - **Freshness agent**: scan all `wiki/*.md` `last_verified:` dates. Flag pages older than 90 days.
   - **Ingest agent** (conditional): if `git log --oneline main..HEAD` shows a recent gstack-driven merge AND `~/.gstack/projects/<slug>/main-reviews.jsonl` has entries newer than the last `wiki/log.md` ingest entry, read the merged gstack design doc (`~/.gstack/projects/<slug>/manuellindo-main-design-*.md`) + recent review entries. Identify decisions worth capturing as ADRs.

4. For each finding, evaluate:
   - **Severity**: BLOCKING (broken wikilink, missing required field, supersedes-orphan) vs ADVISORY (stale freshness, basename ambiguity).
   - **Auto-fixable**: can the fix be derived without judgment? Examples: missing `last_verified` → bump after user confirms page is current; malformed sprint history line → fix punctuation; missing `## For future Claude` heading → propose a draft preamble from the page body.
   - **Authority** (for stale findings): which source is most recent / most authoritative? Newer commits, ADRs, code reality.

5. Resolve each finding:
   - **Auto-fixable**: propose the fix; user confirms; apply. Append to current-session change log.
   - **Human-needed**: present the finding + 2-3 options + recommendation with one-line reason. User picks; apply chosen resolution.
   - **Ingest proposal**: present each proposed new ADR (filename, frontmatter draft, body skeleton, propagation list — which sprint pages / index sections / log entries get updated alongside). User reviews each before write.

6. After all resolutions:
   - Update affected sections of `wiki/index.md` (decisions count, sprint-dev-tooling status line, `Last reconcile run: YYYY-MM-DD` line at the top).
   - Append to `wiki/log.md`: `## [YYYY-MM-DD] reconcile | X findings, Y auto-fixed, Z flagged for user, W ADRs created (of which G from gstack ingest)`.
   - Write a `wiki/lint-reports/<timestamp>.md` session report (same format as wiki-lint reports).

7. Report back:
   - **Auto-fixed** (list with file + old → new diff per fix)
   - **Flagged for user** (skipped or follow-up needed; one-line per item)
   - **Stale pages refreshed** (pages with `last_verified` bumped)
   - **ADRs created** — every new `wiki/decisions/<date>-<topic>.md` written this session, whatever the source (gstack ingest, drift-resolution that warranted a decision, user-initiated). Include the propagation summary per ADR: which sprint pages / index sections / log entries got updated alongside.

The wiki should never contain unresolved drift without knowing about it. Findings are either resolved or explicitly logged as open. The wiki is for future-Claude retrieval.

---

**AI-first rule:** Every page created or updated by this command MUST follow `wiki/CLAUDE.md` schema — `## For future Claude` preamble, required frontmatter per page type, `confidence:` field for decisions, `priority:` field for sources, mandatory `[[wikilinks]]` on first mention of any wiki-resident concept/source/decision, `last_verified` bumped when content is touched. Plus the project's "Write rules" (Search before write, Update-not-duplicate, Propagation) from `wiki/CLAUDE.md`. The skill is the mechanism; the rules in `wiki/CLAUDE.md` are the authority.
