"""Per-config equivalence tests.

Each config file in pipelines/**/*_config.py was migrated from @dataclass
to Pydantic BaseModel. The tests in this directory load the post-migration
BaseModel singleton and assert its model_dump(mode="json") matches a fixture
captured BEFORE the migration (from the @dataclass version).

If a test fails, it means the Pydantic migration produced different resolved
values than the original @dataclass — e.g., a default coerced differently or
a field got renamed. Investigate before merging.

Fixtures live under tests/configs/fixtures/<name>.json. They are committed
artifacts, not regenerated automatically; if you intentionally change a
config's defaults, regenerate the fixture and review the diff.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "configs" / "fixtures"

# `pipelines.*` is made importable via [tool.pytest.ini_options] pythonpath
# in the root pyproject.toml — no per-conftest sys.path manipulation needed.


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())
