"""Equivalence tests for the Pydantic config migration (Phase 2).

Each test imports a config singleton and asserts its `model_dump(mode="json")`
matches the fixture captured from the original @dataclass version.
"""

from __future__ import annotations

import pytest

from .conftest import load_fixture


@pytest.mark.parametrize(
    ("fixture_name", "module_path", "var_name"),
    [
        # Tracked configs migrated as part of Phase 2.
        # New configs (apa, crus_ogc, lidar, lneg, srup_ogc) get their own
        # parametrize entries when their owning WIP commits land.
        # `crus` (legacy WFS per-município path) was retired 2026-05-13 in favor of
        # the OGC API (`pipelines/gis/crus_ogc/`); the crus fixture is preserved
        # under fixtures/_retired/ as historical record.
        ("idealista", "pipelines.portals.idealista.idealista_config", "IDEALISTA_CONFIG"),
        ("srup", "pipelines.gis.srup.srup_config", "SRUP_CONFIG"),
        ("cadastro", "pipelines.gis.cadastro.cadastro_config", "CADASTRO_CONFIG"),
    ],
)
def test_config_matches_fixture(fixture_name: str, module_path: str, var_name: str):
    """Pydantic-migrated config produces same resolved values as @dataclass version."""
    import importlib

    module = importlib.import_module(module_path)
    config = getattr(module, var_name)
    expected = load_fixture(fixture_name)
    actual = config.model_dump(mode="json")
    assert actual == expected, (
        f"Config drift for {fixture_name}: "
        f"the Pydantic version produces different output than the fixture."
    )
