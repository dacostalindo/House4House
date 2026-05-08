#!/usr/bin/env bash
# PreToolUse hook for Bash: block destructive commands targeting protected paths.
# Non-zero exit blocks the command. Per design doc 3c.
#
# Reads the proposed Bash command from $CLAUDE_TOOL_BASH_COMMAND.

set -uo pipefail

CMD="${CLAUDE_TOOL_BASH_COMMAND:-}"
[[ -z "$CMD" ]] && exit 0

# Anchored regex patterns. Match if the command contains any of these.
# Use grep -E with multiple patterns; case-insensitive.
PATTERNS=(
    'rm[[:space:]]+-rf?[[:space:]]+([^|;&]*)?warehouse/init'
    'airflow[[:space:]]+db[[:space:]]+reset'
    'rm[[:space:]]+-rf?[[:space:]]+/[[:space:]]*$'
    'rm[[:space:]]+-rf?[[:space:]]+/[[:space:]]'
    'DROP[[:space:]]+(TABLE|SCHEMA|DATABASE)[[:space:]]+(IF[[:space:]]+EXISTS[[:space:]]+)?(bronze|silver|gold|warehouse)'
    'TRUNCATE[[:space:]]+(TABLE[[:space:]]+)?(bronze|silver|gold)'
)

for pattern in "${PATTERNS[@]}"; do
    if echo "$CMD" | grep -qiE "$pattern"; then
        echo "[bash_destructive_pre] BLOCKED: command matches destructive pattern: $pattern" >&2
        echo "[bash_destructive_pre] command was: $CMD" >&2
        echo "[bash_destructive_pre] if you genuinely need to do this, run it manually outside Claude Code." >&2
        exit 1
    fi
done

exit 0
