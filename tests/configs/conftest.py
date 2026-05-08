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
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "configs" / "fixtures"

# Make `pipelines.*` importable without an editable install.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())
