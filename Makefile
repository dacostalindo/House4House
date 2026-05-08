# House4House developer commands.
# Prerequisite: uv installed and on PATH (see Getting Started in README.md).

.PHONY: help setup verify test up down lint format clean wiki-lint install-cron uninstall-cron

# Allow `UV=~/.local/bin/uv make setup` if uv isn't on PATH yet.
UV ?= uv
AIRFLOW_HOME := $(PWD)/.airflow-home

help:
	@echo "House4House developer commands:"
	@echo "  make setup    Install dependencies and pre-commit hooks"
	@echo "  make verify   Run smoke checks: imports + ruff"
	@echo "  make up       Start Airflow + warehouse + MinIO + Metabase"
	@echo "  make down     Stop services"
	@echo "  make lint     Run ruff check"
	@echo "  make format   Run ruff format"
	@echo "  make clean         Remove caches and stop services"
	@echo "  make wiki-lint     Run /wiki-lint skill on-demand (writes report to wiki/lint-reports/)"
	@echo "  make install-cron  Install weekly /wiki-lint launchd cron (Sun 06:00 local)"
	@echo "  make uninstall-cron Remove the weekly /wiki-lint launchd cron"

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

# ── Wiki maintenance ──────────────────────────────────────────────────────────

# On-demand /wiki-lint run. Writes a timestamped report under wiki/lint-reports/.
wiki-lint:
	@mkdir -p wiki/lint-reports
	@TS=$$(date -u +%Y-%m-%dT%H%M%S); \
	  echo "→ Running /wiki-lint (output → wiki/lint-reports/$$TS.log)"; \
	  claude -p /wiki-lint --max-turns 5 > "wiki/lint-reports/$$TS.log" 2>&1 || \
	    (echo "wiki-lint failed; see wiki/lint-reports/$$TS.log" >&2; exit 1)
	@echo "wiki-lint complete."

# Install the weekly launchd cron. Substitutes the current repo path + claude
# binary location into the plist template so the cron survives moving the repo
# (re-run `make install-cron` after a move). Idempotent.
install-cron:
	@CLAUDE_BIN=$$(command -v claude || echo "/usr/local/bin/claude"); \
	  if [ ! -x "$$CLAUDE_BIN" ]; then \
	    echo "ERROR: claude CLI not found on PATH; install Claude Code first." >&2; \
	    exit 1; \
	  fi; \
	  REPO_PATH="$(PWD)"; \
	  HOME_PATH="$$HOME"; \
	  TARGET="$$HOME/Library/LaunchAgents/wiki-lint.plist"; \
	  mkdir -p "$$HOME/Library/LaunchAgents" wiki/lint-reports; \
	  sed -e "s|__REPO_PATH__|$$REPO_PATH|g" \
	      -e "s|__CLAUDE_BIN__|$$CLAUDE_BIN|g" \
	      -e "s|__HOME__|$$HOME_PATH|g" \
	      .claude/wiki-lint.launchd.plist.template > "$$TARGET"; \
	  launchctl bootout gui/$$UID/wiki-lint 2>/dev/null || true; \
	  launchctl bootstrap gui/$$UID "$$TARGET"; \
	  echo "wiki-lint cron installed."; \
	  echo "  plist:    $$TARGET"; \
	  echo "  schedule: Sunday 06:00 local"; \
	  echo "  output:   wiki/lint-reports/<timestamp>.log"; \
	  echo "  inspect:  launchctl print gui/$$UID/wiki-lint"

uninstall-cron:
	@TARGET="$$HOME/Library/LaunchAgents/wiki-lint.plist"; \
	  launchctl bootout gui/$$UID/wiki-lint 2>/dev/null || true; \
	  rm -f "$$TARGET"; \
	  echo "wiki-lint cron removed."
