---
title: AIRFLOW_HOME isolation
type: concept
last_verified: 2026-05-08
tags: [airflow, devops, gotcha, makefile]
---

## For future Claude

This is a concept page about the AIRFLOW_HOME bleed gotcha — the failure mode where a stale `~/airflow/airflow.cfg` left behind by a prior Airflow 3 install corrupts a fresh Airflow 2.10 venv. It documents why `make verify` exports `AIRFLOW_HOME=$(PWD)/.airflow-home`, why this isolation lives in the Makefile rather than imports, and why Docker is unaffected. Read this when adding Airflow imports to a script, debugging "why does my fresh venv crash with `xcom_backend = airflow.sdk.execution_time.xcom.BaseXCom`?", or onboarding a new contributor with `airflow` previously installed globally.

## What it is

`AIRFLOW_HOME` is the env var Airflow reads to find its config file (`airflow.cfg`), DAG folder, plugins, and SQLite metadata DB. **Default is `~/airflow/`.** When unset, every venv shares the user-global `~/airflow/airflow.cfg`.

The House4House Makefile sets `AIRFLOW_HOME=$(PWD)/.airflow-home` for `make verify` (and any task that imports Airflow), so each project gets its own isolated config dir. `.airflow-home/` is gitignored.

## Why

This issue was discovered during the Phase 1 spike (uv workspace + Ruff baseline). The user had previously installed Airflow 3 globally; uninstalling left the config file behind:

```ini
# ~/airflow/airflow.cfg (stale, from prior Airflow 3 install)
xcom_backend = airflow.sdk.execution_time.xcom.BaseXCom
```

`airflow.sdk` is an Airflow-3-only module. Any fresh Airflow 2.10 venv that imported airflow read this config and crashed:

```
ModuleNotFoundError: No module named 'airflow.sdk'
```

The error message points at the import path, not the config; debugging by re-installing Airflow / pinning versions / clearing pip caches doesn't fix it. The fix is to move or override the config file — either delete `~/airflow/airflow.cfg` (destructive, may surprise other projects) or point `AIRFLOW_HOME` somewhere else.

The project-local approach makes the isolation explicit, gitignored, and reset-on-clean.

## How

**The Makefile pattern**:

```makefile
AIRFLOW_HOME := $(PWD)/.airflow-home

verify:
    @mkdir -p $(AIRFLOW_HOME)
    @AIRFLOW_HOME=$(AIRFLOW_HOME) $(UV) run python -c "import airflow, ..."
    @$(UV) run ruff check
    ...
```

**`.gitignore` entry**: `.airflow-home/` — never commit a per-machine state dir.

**`make clean` removes it**: `rm -rf .pytest_cache .ruff_cache .airflow-home` — fresh start when needed.

**Why not put the export in a shell rc file** (e.g., `.envrc` for direnv): two reasons:
1. Not every contributor uses direnv. The Makefile pattern works on a clean machine.
2. The isolation should be visible in the command surface (`make verify` shows the env var inline) rather than implicit in shell setup.

**Docker is unaffected**: the Airflow container has its own `AIRFLOW_HOME` baked into the image (`/opt/airflow/`); there's no bleed from a host `~/airflow/`. `make up` (docker-compose) runs cleanly regardless of host state.

**When you might still hit this**: importing Airflow from a Python script run outside `make verify` — e.g., `python my_script.py` directly. If the script does `import airflow`, it reads `AIRFLOW_HOME`. If unset, defaults to `~/airflow/`. Either set the env var manually or wrap the entry point in a Makefile target.

**Failure-mode signal**: if you see `ModuleNotFoundError: No module named 'airflow.sdk'` when `airflow` is clearly installed at the right version, the config file is the cause. Check `$AIRFLOW_HOME` and inspect the `xcom_backend` line.

## See also

- [Makefile](../../Makefile) — the source-of-truth for the AIRFLOW_HOME export
- [[2026-05-08-phase-2-5-closure]] — Phase 1 spike that surfaced this gotcha (decision record)
- [pipelines/CLAUDE.md](../../pipelines/CLAUDE.md) — area-routing entry pointing to this page
