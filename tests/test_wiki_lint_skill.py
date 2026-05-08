"""Tests for the /wiki-lint Claude Code skill.

Three tests:

1. SKILL.md frontmatter parses cleanly and contains required keys
   (cheap, runs in CI without claude CLI).
2. Smoke run: claude -p /wiki-lint against the seed fixture wiki —
   asserts the skill exits 0 and produces non-empty output.
3. Integration: same against the with-contradiction fixture — asserts
   both SCD2-related concept page filenames appear in the output.

Tests 2 and 3 require the `claude` CLI on PATH. Marked with
pytest.mark.requires_claude_cli; skipped when claude is unavailable
(e.g., in CI without auth) so they don't fail the build.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = REPO_ROOT / ".claude" / "skills" / "wiki-lint" / "SKILL.md"
SEED_FIXTURE = REPO_ROOT / "tests" / "wiki-fixtures" / "seed"
CONTRADICTION_FIXTURE = REPO_ROOT / "tests" / "wiki-fixtures" / "with-contradiction"

CLAUDE_AVAILABLE = shutil.which("claude") is not None
requires_claude_cli = pytest.mark.skipif(
    not CLAUDE_AVAILABLE,
    reason="claude CLI not on PATH; skipping live skill execution tests",
)


# ── Test 1: frontmatter parses, required keys present (no claude CLI needed) ──


def test_skill_frontmatter_parses_and_has_required_keys():
    """SKILL.md is well-formed: YAML frontmatter delimited by ---, with name + description."""
    assert SKILL_PATH.exists(), f"skill file missing at {SKILL_PATH}"

    text = SKILL_PATH.read_text()

    # Frontmatter must start with --- on line 1 and have a closing ---.
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None, "SKILL.md does not start with --- frontmatter delimiters"

    frontmatter = match.group(1)

    # Required keys per Claude Code skill spec.
    assert re.search(r"^name:\s*wiki-lint\s*$", frontmatter, re.MULTILINE), (
        "frontmatter missing or has wrong `name:` (expected 'wiki-lint')"
    )
    assert re.search(r"^description:\s*\S", frontmatter, re.MULTILINE), (
        "frontmatter missing `description:` field"
    )


# ── Test 2: smoke run against the seed fixture (claude CLI required) ──


@requires_claude_cli
def test_skill_runs_cleanly_against_seed_fixture(tmp_path: Path):
    """Running /wiki-lint against the minimal seed fixture exits 0 with non-empty output.

    We invoke claude in the seed-fixture's parent (repo root) but cd'd via a
    temp working directory copy so the skill operates against the fixture as
    if it were the wiki/. We just want a smoke test that the skill body
    executes without error against valid wiki shape.
    """
    work = tmp_path / "wiki"
    shutil.copytree(SEED_FIXTURE, work)
    (tmp_path / "wiki" / "lint-reports").mkdir(exist_ok=True)

    result = subprocess.run(
        ["claude", "-p", "/wiki-lint", "--max-turns", "5"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=300,
    )

    assert result.returncode == 0, (
        f"claude exit={result.returncode}; stderr=\n{result.stderr[:2000]}"
    )
    assert result.stdout.strip(), "claude produced empty stdout"


# ── Test 3: contradiction integration test (claude CLI required) ──


@requires_claude_cli
def test_skill_detects_intentional_contradiction(tmp_path: Path):
    """Lint output mentions both contradicting concept pages by filename.

    The fixture has scd2-row-hash.md saying 'dedup by row_hash' and
    scd2-primary-key.md (plus idealista-pipeline.md) saying 'dedup by primary
    key'. The lint should surface this contradiction by naming the pages
    involved.
    """
    work = tmp_path / "wiki"
    shutil.copytree(CONTRADICTION_FIXTURE, work)
    (tmp_path / "wiki" / "lint-reports").mkdir(exist_ok=True)

    result = subprocess.run(
        ["claude", "-p", "/wiki-lint", "--max-turns", "5"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"claude exit={result.returncode}; stderr=\n{result.stderr[:2000]}"
    )

    # The lint may write the report into the fixture's lint-reports/ dir
    # OR mention findings in stdout. Combine both into search corpus.
    reports_dir = tmp_path / "wiki" / "lint-reports"
    report_text = ""
    if reports_dir.exists():
        for report in reports_dir.glob("*.md"):
            report_text += report.read_text() + "\n"
    corpus = (result.stdout + "\n" + report_text).lower()

    # Both colliding-page filenames should appear somewhere in the lint output.
    assert "scd2-row-hash" in corpus, (
        "lint did not mention scd2-row-hash.md; corpus head:\n"
        + corpus[:2000]
    )
    assert ("scd2-primary-key" in corpus) or ("idealista-pipeline" in corpus), (
        "lint did not mention the contradicting page (scd2-primary-key or idealista-pipeline); "
        "corpus head:\n" + corpus[:2000]
    )
