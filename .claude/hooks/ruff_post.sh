#!/usr/bin/env bash
# PostToolUse hook: run ruff check --fix + ruff format on the changed Python file.
# Advisory only — always exits 0 even when ruff finds issues. Per design doc C2.
#
# Reads the edited file path from $CLAUDE_TOOL_FILE_PATH (set by Claude Code).
# If unset or not a .py file, exits cleanly.

set -uo pipefail

FILE="${CLAUDE_TOOL_FILE_PATH:-}"

# No file or non-Python: skip silently.
[[ -z "$FILE" ]] && exit 0
[[ "$FILE" != *.py ]] && exit 0
[[ ! -f "$FILE" ]] && exit 0

# Find uv (PATH may be sparse in hook context).
UV="${UV:-$(command -v uv 2>/dev/null || echo "$HOME/.local/bin/uv")}"
[[ ! -x "$UV" ]] && exit 0  # uv not installed — skip rather than block.

# Run on the changed file only. Output goes to stderr (advisory).
"$UV" run ruff check --fix "$FILE" >&2 || true
"$UV" run ruff format "$FILE" >&2 || true

exit 0
