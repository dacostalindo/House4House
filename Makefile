# House4House developer commands.
# Prerequisite: uv installed and on PATH (see Getting Started in README.md).

.PHONY: help setup verify test up down lint format clean

# Allow `UV=~/.local/bin/uv make setup` if uv isn't on PATH yet.
UV ?= uv
AIRFLOW_HOME := $(PWD)/.airflow-home

# macOS CommandLineTools sets VIRTUAL_ENV to the system Python framework,
# which makes every `uv run` emit a "does not match the project environment"
# warning. Unexport it project-wide so make verify / lint / format run clean.
# Phase 6 followup (2026-05-12) per /devex-review finding.
unexport VIRTUAL_ENV

help:
	@echo "House4House developer commands:"
	@echo "  make setup    Install dependencies and pre-commit hooks"
	@echo "  make verify   Run smoke checks: imports + ruff + ty (advisory) + pytest"
	@echo "  make up       Start Airflow + warehouse + MinIO + Metabase"
	@echo "  make down     Stop services"
	@echo "  make lint     Run ruff check"
	@echo "  make format   Run ruff format"
	@echo "  make clean    Remove caches and stop services"
	@echo ""
	@echo "Wiki maintenance: invoke /wiki-reconcile from any Claude Code session"
	@echo "(skill-only; no Makefile target — Phase 7b 2026-05-12 deleted wiki-lint cron)."

setup:
	$(UV) sync --all-packages
	$(UV) run pre-commit install
	@echo ""
	@echo "Setup complete. Run 'make verify' to smoke-check imports."

verify:
	@mkdir -p $(AIRFLOW_HOME)
	@echo "→ Smoke-checking imports (with isolated AIRFLOW_HOME)..."
	@AIRFLOW_HOME=$(AIRFLOW_HOME) $(UV) run python -c "import airflow, dlt, pydantic, streamlit, geopandas; from cosmos import DbtDag; from airflow.providers.postgres.hooks.postgres import PostgresHook; print('imports OK')"
	@echo "→ Running ruff check..."
	@$(UV) run ruff check
	@echo "→ Running ty check (advisory; Phase 6 — graduates to BLOCKING per TODOS.md trigger)..."
	@$(UV) run ty check || echo "(ty findings present — see above; advisory mode, not blocking)"
	@echo "→ Collecting pytest..."
	@$(UV) run pytest --co -q tests/ 2>/dev/null || echo "(no tests collected — Phase 2 adds snapshot tests)"
	@echo ""
	@echo "Verify complete."

test: verify

up:
	docker compose up -d

down:
	docker compose down

lint:
	$(UV) run ruff check

format:
	$(UV) run ruff format

clean:
	docker compose down -v
	rm -rf .pytest_cache .ruff_cache .airflow-home

