---
title: Phase 6 — `ty` type-check shipped advisory-only with 3 graduation triggers
type: decision
last_verified: 2026-05-12
tags: [ty, type-check, ci, phase-6, advisory, decision]
confidence: medium
---

## For future Claude

This is a decision record about Phase 6 of the dev-tooling roadmap: adding Astral's `ty` (beta as of late 2025) as a fourth CI check in **advisory mode** (`--exit-zero` + `|| echo`) rather than gating. Documents the advisory posture, the 3 concrete triggers that flip the gate to BLOCKING, the live-finding picture (172 of 287 errors are Airflow `XComArg` ty-beta gaps, not real bugs), and the deferral decisions for `[tool.ty.rules]` config + annotation sweep. Read this when reviewing whether to flip ty BLOCKING, when proposing rule-severity overrides, or when explaining to a new Claude session why `make verify` shows 143 ty errors yet exits 0.

## Decision

Phase 6 ships `ty` as an advisory CI check (`uv run ty check --output-format=github --exit-zero`) wired into Phase 4's annotation-grouping pattern (`::group::ty`). Local `make verify` runs ty with `|| echo "(ty findings present...)"` so the dev loop sees findings without breaking on them. `pyproject.toml` pins `ty>=0.0.1,<0.1.0` (per [[2026-05-12-pre-commit-local-hook]] sibling pattern of tight pin against pre-stable tooling).

**No `[tool.ty.rules]` config** ships in Phase 6 — defaults-first posture. **No per-file ignores.** **No annotation sweep across `pipelines/`** (visibility, not fixes, is the Phase 6 goal). The `[tool.ty.src.exclude]` block in `pyproject.toml` mirrors ruff's `extend-exclude` as a safety net for generated dirs (`dbt/dbt_packages`, `data`, `warehouse/init`, `scripts`, `.venv`, `.airflow-home`) — observed to be a no-op on the current finding set, kept for future-proofing.

Graduation from advisory → BLOCKING fires on **any of three concrete triggers** (per [[2026-05-12-wiki-linter-deferred-to-phase-7]] eng-review locked replacement of the prior "~80% typed measured ad-hoc" vagueness):

1. **ty hits 1.0 release.** Astral declares stable; project moves with it.
2. **A follow-up PR adds `[tool.ty.rules]` config.** Signals we've learned enough about ty's behavior to tune rule severity; once we have a config, flipping to BLOCKING is a one-line CI change.
3. **A Phase 6.5 annotation-sweep PR lands.** Explicit codebase-readiness signal — e.g., the team decides type coverage is high enough that BLOCKING is reasonable.

## Why

1. **ty is beta.** Per `docs.astral.sh/ty` (late 2025), known gaps in third-party library typing support. Gating CI on a beta tool with documented gaps would create more friction than value.
2. **Codebase typing state.** 99 Python files across `pipelines/` + `apps/`; 63 partly annotated; 9 import `typing`/`collections.abc`; ~427 total `def` statements. Advisory mode is the right initial posture for a partially-typed codebase.
3. **Reuses Phase 4 CI pattern.** Phase 4 (PR #22, merged 2026-05-12 at 593ec18) shipped the `::group::<name>` + tag-prefix annotation pattern. Phase 6 adds one `::group::ty` step using the same shape. No new CI infrastructure.
4. **Decoupled from data-product sprints.** Phase 5 (idealista enrichment via Pydantic AI) is coupled to Sprint 4.5 + Sprint 5, which queue behind in-progress Sprint 4. Phase 6 has no such coupling — it lands on Phase 4's CI scaffolding independently. Ships cheaply.
5. **Defaults-first posture.** Configuring rule severity before observing real findings invites bikeshedding. The plan-eng-review locked rule: "configure only after findings reveal what needs tuning."

## Live findings picture (2026-05-12, PR #25 + followup)

`uv run ty check` on the post-Phase-6 codebase (with `unexport VIRTUAL_ENV` in Makefile so ty resolves the project's Python env correctly): **287 errors + 32 warnings = 319 diagnostics.** Initial PR-#25 run showed only 159 diagnostics because the macOS-CommandLineTools `VIRTUAL_ENV` shadowed the project's `.venv`, making ty under-resolve types. The followup PR's `unexport VIRTUAL_ENV` Makefile fix surfaced the corrected count.

**Error type breakdown:**

| Count | Type |
|---|---|
| 287 | total errors (top types: `invalid-argument-type` dominant; remainder includes `unresolved-attribute`, `not-iterable`, `invalid-assignment`, `call-non-callable`, `unsupported-operator`, `no-matching-overload`, `unresolved-reference`, `invalid-return-type`) |
| 32 | warnings (`possibly-missing-submodule`, `deprecated` for `datetime.utcnow`) |

**Dominant pattern: Airflow `XComArg` false positives.** 172 of 287 errors (60%) mention `XComArg` in their messages. The TaskFlow API pattern is:

```python
@task()
def load_datasets(files: dict) -> dict: ...

@task()
def validate_counts(loaded: dict) -> dict: ...

# In the DAG body:
files = list_minio_files()         # runtime: XComArg; declared: dict
loaded = load_datasets(files)      # ty error: Expected dict, found XComArg
```

At runtime, `@task()` makes `files` an `XComArg` (lazy reference to the eventual return value). Airflow resolves the chain when the DAG runs. ty (beta) doesn't model this Airflow-specific runtime fluidity yet. **These are not real bugs.**

**Remaining ~115 errors** likely follow the same pattern (top files are DAG templates and dlt-using DAGs). A handful may be real, but advisory mode means we don't need to triage every finding — we surface the gap and let it inform future annotation work.

**Top files by error count** (cross-checked against ty output):

| Errors | File |
|---|---|
| 23 | `pipelines/scraping/template/scraping_ingestion_template.py` |
| 11 | `.venv/lib/python3.12/site-packages/dlt/extract/decorators.py` (info-level, points to dlt's own typing) |
| 10 | `pipelines/portals/idealista/source.py` |
| 10 | `.venv/lib/python3.12/site-packages/nodriver/core/util.py` (info-level) |
|  9 | `pipelines/gis/template/gis_ingestion_template.py` |
|  7 | `pipelines/gis/bgri/bgri_bronze_dag.py` |
|  6 | `pipelines/gis/cadastro/cadastro_ingestion_dag.py` |
|  5 | `pipelines/portals/remax/source.py` |
|  5 | `pipelines/portals/jll/jll_dlt_dag.py` |
|  5 | `pipelines/portals/idealista/idealista_dlt.py` |

The `.venv` entries are info-level annotations (ty showing where the unfamiliar type came from), not error origins.

## Options considered

1. **Advisory-only with `--exit-zero` + `|| echo`** (chosen) — visibility without gating; cheap; defers config tuning until we have real findings to act on.
2. **Skip ty entirely, stay on ruff** — rejected; type-check is a real Phase 6 commitment per the dev-tooling roadmap, and ty's per-error format is gold-standard (Rust/Elm tier) once you accept the beta noise.
3. **Use mypy instead of ty** — battle-tested (Layer 1), no beta risk. Rejected for tooling-family coherence — project already uses ruff + uv from Astral; mypy would introduce a different speed/UX profile + duplicate tool surface. Acceptable fallback if ty is later judged "not worth the beta cost."
4. **Use pyright instead** — fast (TypeScript-based), stable. Rejected for the same coherence reason as mypy.
5. **Gate ty BLOCKING from day one** — rejected; would block PRs immediately on 143 advisory findings (most of which are XComArg false positives). The Phase 4 acceptance-gate "first-PR escape hatch" provision (per [[2026-05-12-pre-commit-local-hook]] sibling pattern) applies in reverse here — escape from forced annotation sweep, not from autofix noise.
6. **Add `[tool.ty.rules]` overrides to silence `invalid-argument-type` globally** — rejected; would mask the ~57 non-XComArg errors that might be real. Per-file ignores would scale better but the plan deferred them.

## Consequences

- `make verify` runs ty advisory; 319 diagnostics visible locally (287 errors + 32 warnings), exits 0. `|| echo` makes the advisory nature explicit.
- CI runs ty advisory; PR diffs show `[ty]`-tagged annotations via `--output-format=github`. CI green regardless of findings.
- `pyproject.toml` pins `ty>=0.0.1,<0.1.0` (eng-review fix #3) — capped to 0.0.x. Next minor bump intentional.
- `pyproject.toml` has `[tool.ty.src.exclude]` block — no-op on current findings but future-proofs for generated dirs.
- TODOS.md "Graduate `ty`" entry documents the 3 concrete graduation triggers (replaces prior "~80% typed measured ad-hoc" framing per eng-review fix #4).
- 319 diagnostics are durable noise until either: (a) ty improves Airflow modeling, (b) we add per-file ignores, or (c) we annotate the DAG functions explicitly. Acceptable in advisory mode; gating without addressing would block every PR.
- DevEx review (post-PR-#25, 2026-05-12) scored ty integration **8/10** overall — Rust-tier per-error format, weak signal aggregation in the summary. Both consequences of ty being beta.
- `unexport VIRTUAL_ENV` added to Makefile (Phase 6 followup) — silences the macOS CommandLineTools warning that bleeds into every `uv run` invocation. Not specific to ty; surfaced during ty integration testing.

## Status

`accepted` — Phase 6 shipped via PR #25 (merged 2026-05-12 at 4e01516). Phase 6 followup (this PR) adds the `[tool.ty.src.exclude]` safety net + README staleness fix + `unexport VIRTUAL_ENV` workaround + this ADR + propagation.

`confidence: medium` because Phase 6 ships against a beta tool. The advisory posture is the right call for now; the graduation triggers are the right shape. What may change: if ty 1.0 ships in 2026 with better Airflow support, the 143 findings could drop dramatically and BLOCKING graduation becomes natural. Until then, the noise floor stays high.

## See also

- [[sprint-dev-tooling]] — Phase 6 row flipped to `✅ done` (2026-05-12)
- [[2026-05-12-wiki-linter-deferred-to-phase-7]] — sibling Phase 4 decision; the "concrete triggers replace vague metric" pattern was established there
- [[2026-05-12-pre-commit-local-hook]] — sibling Phase 4 decision; the tight-pin-against-pre-stable pattern was established there
- [[bronze-permissive]] — the policy that Airflow `XComArg` flexibility serves (bronze ingest pipelines must accept whatever the source returns)
- [README §1](../../README.md) — `make verify` now includes ty advisory step
- TODOS.md "Graduate `ty`" entry — the 3 concrete graduation triggers
