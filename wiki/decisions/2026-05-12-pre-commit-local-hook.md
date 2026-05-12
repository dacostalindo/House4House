---
title: Pre-commit uses local `uv run ruff` over pinned `ruff-pre-commit`
type: decision
last_verified: 2026-05-12
tags: [pre-commit, ruff, ci, phase-4, version-pin, decision]
confidence: medium
---

## For future Claude

This is a decision record about wiring `.pre-commit-config.yaml` ruff hooks via `language: system` + `entry: uv run ruff …` (the local-hook pattern) instead of pinning `astral-sh/ruff-pre-commit` at a fixed `rev:`. The choice eliminates ruff version drift between pre-commit and CI/Makefile at the cost of requiring `uv` on every contributor's PATH (already required by `make setup`). Read this when adding new pre-commit hooks, considering whether to migrate to the pinned pattern, or wondering why `.pre-commit-config.yaml` doesn't follow the more common `repo:` style.

## Decision

`.pre-commit-config.yaml` uses **local hooks** that shell out to `uv run ruff check --fix` and `uv run ruff format`:

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff
        name: ruff (lint)
        entry: uv run ruff check --fix
        language: system
        types: [python]
      - id: ruff-format
        name: ruff (format)
        entry: uv run ruff format
        language: system
        types: [python]
```

NOT the more common pinned-repo pattern (`repo: https://github.com/astral-sh/ruff-pre-commit` + `rev: v0.6.9`).

## Why

1. **Eliminates version drift.** With the pinned-repo pattern, `pre-commit` ships ruff `v0.6.9` (or whatever rev is pinned) while `pyproject.toml` ships ruff at whatever version `uv sync` resolves. Contributors hit the bug where `pre-commit run --all-files` passes but CI's `uv run ruff check` (using the project's actual ruff) fails on a rule the pinned ruff didn't know about — or vice versa. Local hooks use the project's ruff, the same one CI runs, the same one `make verify` runs. One version, one rule set, no drift.
2. **No autoupdate cron.** The pinned-repo pattern requires a quarterly `pre-commit autoupdate` task to keep `rev:` in sync with new ruff releases. Easy to forget; drift accumulates silently. Local hooks bypass this entirely — when `uv sync` upgrades ruff, pre-commit picks it up on the next commit.
3. **Acceptable contributor cost.** The pattern requires `uv` on every contributor's PATH. `make setup` already requires `uv` (it's the entire workspace toolchain — see [[2026-05-05-uv-workspace-shape]]). Net cost: zero.

## Options considered

1. **Local hook via `uv run ruff`** (chosen) — `language: system`, no version drift.
2. **Pinned ruff-pre-commit** — `repo: https://github.com/astral-sh/ruff-pre-commit, rev: v0.6.9, hooks: [ruff, ruff-format]`. Standard pattern, isolated environment (pre-commit caches the hook venv), but version drift requires quarterly `pre-commit autoupdate`. Rejected.
3. **No pre-commit hooks, rely on CI only** — `git commit` succeeds with style violations; CI catches them on PR. Rejected because the feedback loop is 1-2 minutes (push + CI run) vs <1 second (pre-commit blocks the commit). Pre-commit is for fast feedback; CI is for the contract.

## Consequences

- Contributors run `pre-commit install` (already part of `make setup`) and pre-commit fires on every `git commit`.
- Pre-commit reads from the project's `uv` environment, so the ruff version is whatever `uv.lock` resolves. Upgrading ruff: bump `pyproject.toml`, `uv sync`, done — pre-commit picks up the new version on the next commit.
- `language: system` means pre-commit does NOT create an isolated hook venv. The hook runs against the contributor's actual environment (which is `uv`-managed, so it's deterministic). Slightly faster than the pinned pattern.
- `types: [python]` filters the hook to `.py` files only. Pre-commit doesn't waste cycles on markdown/yaml.
- `require_serial: false` (default) means pre-commit can parallelize across hooks. Both ruff hooks (lint + format) run together.
- `make wiki-lint-fast` (Phase 7) will follow the same pattern — `entry: uv run python scripts/wiki_health.py` — when the wiki linter ships (per [[2026-05-12-wiki-linter-deferred-to-phase-7]]).

## Risks

- **`uv` not on PATH**: a contributor without `uv` cannot run pre-commit. Mitigation: `make setup` installs uv as its first action; the project README is explicit that uv is required. Effectively: same risk surface as `make verify` failing.
- **Hook-venv isolation lost**: the pinned-repo pattern isolates hooks from project dependencies; the local-hook pattern doesn't. Risk: a future hook with a dep conflict could break. Mitigation: only ruff is wired this way in Phase 4; if a future hook has dep conflicts, switch THAT hook to the pinned-repo pattern (the patterns can coexist in one `.pre-commit-config.yaml`).
- **Confidence: medium** rather than `high` because the pattern is less common than the pinned-repo style; if a contributor's PATH issue surfaces or a future hook conflicts, we may need to revisit. The pattern is reversible (~5 lines of YAML).

## Status

`accepted` — locked 2026-05-12 during Phase 4 implementation. Phase 4 PR (#22, merged at 593ec18) ships with this pattern.

## See also

- [[2026-05-05-uv-workspace-shape]] — uv workspace decision; this hook pattern depends on uv being the toolchain
- [[2026-05-12-wiki-linter-deferred-to-phase-7]] — sibling Phase 4 decision; the deferred wiki linter (Phase 7) will use the same local-hook pattern
