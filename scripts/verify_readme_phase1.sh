#!/usr/bin/env bash
# scripts/verify_readme_phase1.sh
#
# Checks that the Phase 1 README cleanup edits are applied. Greps for the
# 14 expected markers across 8 numbered edits + the README freeze banner.
#
# Per /plan-eng-review finding 1.1 (2026-05-09). Used by PR 4+ migration
# sessions to refuse proceeding when Phase 1 cleanup is incomplete.
#
# Usage:
#   bash scripts/verify_readme_phase1.sh           # checks ./README.md
#   bash scripts/verify_readme_phase1.sh path/to/README.md
#
# Exit codes:
#   0 — all 14 markers present (Phase 1 complete)
#   1 — some markers missing (lists which)
#   2 — README file not found

set -uo pipefail

README="${1:-README.md}"

if [ ! -f "$README" ]; then
  echo "ERROR: $README not found" >&2
  exit 2
fi

PASS=0
FAIL=0
MISSING=()

check() {
  # Args: <description> <grep args...>
  local desc="$1"
  shift
  if grep -E "$@" "$README" >/dev/null 2>&1; then
    echo "  ✅ $desc"
    PASS=$((PASS + 1))
  else
    echo "  ❌ $desc"
    MISSING+=("$desc")
    FAIL=$((FAIL + 1))
  fi
}

echo "Verifying Phase 1 README cleanup markers in $README"
echo

check "Edit 2a — Sprint 4.4 header marked '✅ COMPLETE'" \
  '^### Sprint 4\.4.*✅ COMPLETE'

# Edit 2b: count ✅ Done occurrences inside the Sprint 4.4 task table
SPRINT_4_4_DONE_COUNT=$(awk '/^### Sprint 4\.4/,/^### Sprint [0-9]/' "$README" | grep -c "✅ Done" || true)
if [ "${SPRINT_4_4_DONE_COUNT:-0}" -ge 9 ]; then
  echo "  ✅ Edit 2b — Sprint 4.4 has ≥9 '✅ Done' rows (found $SPRINT_4_4_DONE_COUNT)"
  PASS=$((PASS + 1))
else
  echo "  ❌ Edit 2b — Sprint 4.4 has <9 '✅ Done' rows (found ${SPRINT_4_4_DONE_COUNT:-0})"
  MISSING+=("Edit 2b: flip Sprint 4.4 task statuses to '✅ Done'")
  FAIL=$((FAIL + 1))
fi

check "Edit 3 — Sprint 1 Metabase row '✅ Done'" \
  'Metabase docker-compose.*✅ Done'

check "Edit 3 — Sprint 1 Streamlit row '✅ Done'" \
  'Streamlit base app.*✅ Done'

check "Edit 4 — §4.1 has 'warehouse:' service block" \
  '^[[:space:]]*warehouse:'

check "Edit 4 — §4.1 has 'osrm-car:' service" \
  '^[[:space:]]*osrm-car:'

check "Edit 4 — §4.1 has 'osrm-walking:' service" \
  '^[[:space:]]*osrm-walking:'

check "Edit 4 — §4.1 has 'osrm-cycling:' service" \
  '^[[:space:]]*osrm-cycling:'

check "Edit 5 — §4.3 mentions bronze_terrain" \
  'bronze_terrain'

check "Edit 5 — §4.3 mentions bronze_geology" \
  'bronze_geology'

check "Edit 5 — §4.3 mentions bronze_hydrology" \
  'bronze_hydrology'

check "Edit 6 — §3.1 stack table mentions 'nodriver'" \
  'nodriver'

check "Edit 8 — §6 Flow F prefixed with 'Status: planned, not yet implemented'" \
  'Status: planned, not yet implemented'

check "Edit 9 — README freeze banner present" \
  'README migration in progress'

echo
echo "Result: $PASS passed / $FAIL missing"

if [ "$FAIL" -gt 0 ]; then
  echo
  echo "Missing markers:"
  for m in "${MISSING[@]}"; do
    echo "  - $m"
  done
  echo
  echo "Reference: see Phase 1 deliverable section of"
  echo "  ~/.claude/plans/give-me-a-full-virtual-crown.md"
  echo "  for the precise edits + line numbers + diffs."
  exit 1
fi

echo
echo "Phase 1 README cleanup complete. Migration PRs (PR 4+) can proceed."
exit 0
