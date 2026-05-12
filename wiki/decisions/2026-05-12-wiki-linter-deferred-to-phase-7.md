---
title: Wiki linter (scripts/wiki_health.py) deferred from Phase 4 to Phase 7
type: decision
last_verified: 2026-05-12
tags: [wiki, lint, ci, phase-4, phase-7, dry, decision]
confidence: high
---

## For future Claude

This is a decision record about deferring the mechanical wiki linter (`scripts/wiki_health.py`) from Phase 4 to Phase 7 of the dev-tooling roadmap. The deferral surfaced during Phase 4 implementation when a prototype linter would have re-implemented rules already stated in `wiki/CLAUDE.md` prose, creating two parallel sources of truth. Read this when reviewing why Phase 4's CI doesn't enforce wiki rules mechanically, why Phase 7 carries the wiki-linter work, or when designing the eventual `wiki/_schema.yaml` structured schema.

## Decision

The mechanical wiki linter (`scripts/wiki_health.py`) + its tests + Makefile `wiki-lint-fast` target + `.pre-commit-config.yaml` `wiki-health` hook + `.github/workflows/ci.yml` `wiki_health` step **move from Phase 4 to Phase 7**. Phase 4 ships the rest of its scope unchanged: ruff + ruff-format + pytest + `dbt parse` CI gating, `llms.txt`, the write-rules borrow into `wiki/CLAUDE.md`, the dbt `ci:` profile, and ruff-only pre-commit hooks.

Phase 7 picks up the linter alongside `/wiki-reconcile` and `/wiki-import-gstack`, and all three consume a structured `wiki/_schema.yaml` (or equivalent) extracted from `wiki/CLAUDE.md` prose. The schema file becomes the single source of truth; both the human-readable schema doc and the mechanical linter read from it.

## Why

1. **DRY / single source of truth.** A Phase 4 linter would have hard-coded the rules that live in `wiki/CLAUDE.md` prose: required frontmatter fields, page-type required sections, `[[wikilinks]]` resolution rules, supersedes reciprocity, the `## For future Claude` preamble check, sprint Status-update-history regex. Two parallel sources drift; the right fix is to extract the machine-parseable rules into a structured file and have BOTH the schema doc AND the linter read from it.
2. **Co-design with Phase 7 skills.** Phase 7 ships `/wiki-reconcile` (interactive wiki health resolver) and `/wiki-import-gstack` (structured ingest from gstack artifacts). Both need schema knowledge — what fields are required, what frontmatter shape, which `## section` headings are mandatory per page type. Designing the structured schema once and landing all three consumers (linter + reconcile + import) in one coherent pass is cleaner than Phase 4 shipping a linter against prose-as-truth and Phase 7 then refactoring.
3. **No regression in safety.** The weekly `/wiki-lint` LLM cron (Phase 3e, already shipped via launchd Sundays 06:00) continues to catch semantic-level drift — contradictions, stale claims, orphan pages, synonym variants. The mechanical layer is the missing piece, not the only layer. Until Phase 7 lands, the LLM cron + human discipline per the `wiki/CLAUDE.md` "Write rules" section (Search before write / Update-not-duplicate / Propagation Rule) carries the load.
4. **Concrete surfacing trigger.** The DRY concern surfaced during the Phase 4 prototype implementation pass when a working linter (566 lines, 7 checks) caught 12 real findings — including 3 stale wiki refs that got fixed regardless of whether the linter ships. The findings validate the linter design; what they don't validate is the rules-source-of-truth shape. Better to defer than to ship a structural decision that will need refactoring.

## Options considered

1. **Ship Phase 4 linter against prose-as-truth, refactor in Phase 7** — rejected; locks in a DRY violation that Phase 7 has to undo.
2. **Ship Phase 4 linter, simultaneously extract `wiki/_schema.yaml`** — rejected; scope-creeps Phase 4 from "CI/CD bootstrap" to "schema-first refactor + CI/CD bootstrap". The schema design needs Phase 7's `/wiki-reconcile` + `/wiki-import-gstack` requirements as inputs to be designed once correctly.
3. **Defer linter entirely to Phase 7** (chosen) — Phase 4 ships only mechanical CI gates (ruff/pytest/dbt-parse). Wiki gating stays LLM-cron-only until Phase 7's structured schema lands.
4. **Cancel the wiki linter entirely** — rejected; the weekly LLM cron catches semantic drift but misses mechanical regressions (frontmatter typos, missing `## For future Claude` preambles, unresolved `[[wikilinks]]`). The mechanical layer has value; it's a deferral, not a cancellation.

## Consequences

- Phase 4 ships smaller scope. PR shape: one PR with CI/CD + llms.txt + write-rules. No `scripts/wiki_health.py`, no `wiki-lint-fast` Makefile target, no pre-commit wiki hook, no CI wiki step.
- `pyproject.toml` does NOT add `pyyaml>=6` to the dev group in Phase 4. Phase 7 reintroduces it (defensive against transitive-dep churn even though pyyaml is currently transitively available via `airflow → apispec[yaml]`).
- `wiki/CLAUDE.md` forward-references to `scripts/wiki_health.py --format=github (Phase 4e, runs in CI on every PR)` are stale and get fixed to read "Phase 7" + "the weekly `/wiki-lint` LLM cron is the only automated wiki gate until Phase 7 ships the mechanical layer".
- Wiki schema correctness depends on human/Claude discipline + the LLM cron until Phase 7. Acceptable trade-off — the cron has run weekly since Phase 3e shipped without surfacing structural rot.
- Phase 7 absorbs the deferred work as a known scope addition (see Phase 7 scope additions section in the Phase 4 plan `~/.claude/plans/give-me-a-full-virtual-crown.md`):
  - Structured `wiki/_schema.yaml`
  - Full `scripts/wiki_health.py` (all 7 checks from the prototype: frontmatter, preamble, required sections, `[[wikilinks]]` with directory-ref + placeholder-allowlist + schema-doc self-exclusion, supersedes reciprocity, sprint Status-update-history)
  - `tests/test_wiki_health.py` with `--wiki-root` injectable + per-check unit tests + clean-wiki regression guard
  - `Makefile wiki-lint-fast` target
  - `.pre-commit-config.yaml` `wiki-health` local hook
  - `.github/workflows/ci.yml` `wiki_health` step with `[wiki-health]` annotation tag
  - `pyproject.toml` dev-group `pyyaml>=6` explicit add
  - `tests/test_wiki_schema_consistency.py` — sentinel test asserting `wiki/CLAUDE.md` rule strings match the structured schema

## Status

`accepted` — locked 2026-05-12 during Phase 4 implementation pass. Phase 4 PR shipped at 593ec18 (merged) with the deferral in effect. Phase 7 carries the deferred work as a known scope addition.

## See also

- [[sprint-dev-tooling]] — the 7-Phase roadmap with the Phase 4 / Phase 7 boundary now reflecting this decision
- [[2026-05-12-pre-commit-local-hook]] — the sibling Phase 4 decision on pre-commit hook resolution
- `wiki/CLAUDE.md` — the prose-as-truth schema doc that Phase 7 will extract into structured form
- `~/.claude/plans/give-me-a-full-virtual-crown.md` — the Phase 4 plan that locked this deferral
