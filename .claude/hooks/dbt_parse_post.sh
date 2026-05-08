#!/usr/bin/env bash
# PostToolUse hook: run dbt parse --select <model>+ for the changed dbt SQL file.
# Blocks (non-zero exit) on real schema errors (ref/source/macro typos).
# Exits 0 (advisory) when warehouse is unreachable — connection failure ≠
# schema error. Per design doc A2 + C2 + warehouse-down guard.
#
# Reads the edited file path from $CLAUDE_TOOL_FILE_PATH.

set -uo pipefail

FILE="${CLAUDE_TOOL_FILE_PATH:-}"

# Skip silently if no file or not a dbt model.
[[ -z "$FILE" ]] && exit 0
[[ "$FILE" != *.sql ]] && exit 0
[[ "$FILE" != */dbt/models/* ]] && exit 0
[[ ! -f "$FILE" ]] && exit 0

# Derive model name from filename (strip dirs + .sql).
MODEL_NAME="$(basename "$FILE" .sql)"

UV="${UV:-$(command -v uv 2>/dev/null || echo "$HOME/.local/bin/uv")}"
[[ ! -x "$UV" ]] && exit 0  # uv not installed — skip.

# Capture stderr separately so we can distinguish connection failures from
# schema errors before deciding the exit code.
STDERR_FILE="$(mktemp)"
trap 'rm -f "$STDERR_FILE"' EXIT

cd "$(dirname "$FILE")/../../.." 2>/dev/null || cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

if "$UV" run dbt parse --no-partial-parse --select "${MODEL_NAME}+" --project-dir dbt 2>"$STDERR_FILE" >&2; then
    exit 0
fi

# dbt parse failed. Check stderr for connection-failure markers.
if grep -qiE 'connection (refused|reset|timed out)|could not translate host name|operationalerror|could not connect to server|network is unreachable|warehouse_(host|user|password)' "$STDERR_FILE"; then
    # Warehouse unreachable. Surface a warning but don't block.
    echo "[dbt_parse_post] warehouse unreachable; skipping schema check (advisory)" >&2
    cat "$STDERR_FILE" >&2
    exit 0
fi

# Real schema error — block.
echo "[dbt_parse_post] schema error in ${MODEL_NAME}; blocking" >&2
cat "$STDERR_FILE" >&2
exit 1
