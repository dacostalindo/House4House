"""Unit tests for the zome dlt source — focuses on _stable_hash because it's
the highest-risk pure function in the pipeline. False versions on day N would
inflate price_change_count downstream.

Run inside the Airflow container (dlt available):
    docker compose exec airflow-scheduler pytest /opt/airflow/dags/pipelines/api/zome/tests/

Or in a local venv with dlt installed:
    pip install "dlt[postgres]~=1.25.0" pytest
    PYTHONPATH=. pytest pipelines/api/zome/tests/
"""

from __future__ import annotations

import pytest

from pipelines.api.zome.source import (
    DEVELOPMENTS_VERSION_COLUMNS,
    LISTINGS_VERSION_COLUMNS,
    _canonicalize,
    _normalize_development,
    _normalize_listing,
    _stable_hash,
)


# ---------------------------------------------------------------------------
# _stable_hash — determinism + canonicalization
# ---------------------------------------------------------------------------

class TestStableHash:
    def test_same_input_same_hash(self):
        row = {"a": 1, "b": "x", "c": True}
        cols = ("a", "b", "c")
        assert _stable_hash(row, cols) == _stable_hash(row, cols)

    def test_int_and_float_collide_for_same_value(self):
        # PostgREST sometimes serializes 1000 vs 1000.0 inconsistently.
        # Our row_hash MUST treat them as equivalent or every numeric column
        # generates spurious SCD2 versions on day N.
        row_int = {"price": 1_090_000}
        row_flt = {"price": 1_090_000.0}
        cols = ("price",)
        assert _stable_hash(row_int, cols) == _stable_hash(row_flt, cols)

    def test_bool_not_coerced_to_numeric(self):
        # Critical: bool is a subclass of int in Python.
        # _canonicalize must NOT cast True/False to 1.0/0.0.
        row_bool = {"flag": True}
        row_int = {"flag": 1}
        cols = ("flag",)
        assert _stable_hash(row_bool, cols) != _stable_hash(row_int, cols)

    def test_none_handled(self):
        row = {"a": None, "b": 1}
        cols = ("a", "b")
        # No exception, deterministic
        h = _stable_hash(row, cols)
        assert isinstance(h, str)
        assert len(h) == 64  # sha256 hex

    def test_missing_key_treated_as_none(self):
        row1 = {"a": 1}                       # b missing
        row2 = {"a": 1, "b": None}            # b explicitly None
        cols = ("a", "b")
        assert _stable_hash(row1, cols) == _stable_hash(row2, cols)

    def test_only_listed_columns_count(self):
        row1 = {"a": 1, "ignored": "x"}
        row2 = {"a": 1, "ignored": "y"}
        cols = ("a",)
        assert _stable_hash(row1, cols) == _stable_hash(row2, cols)

    def test_changed_relevant_column_changes_hash(self):
        row1 = {"a": 1, "b": 2}
        row2 = {"a": 1, "b": 3}
        cols = ("a", "b")
        assert _stable_hash(row1, cols) != _stable_hash(row2, cols)

    def test_non_scalar_raises(self):
        row = {"bad": [1, 2, 3]}
        with pytest.raises(TypeError, match="non-scalar"):
            _stable_hash(row, ("bad",))

    def test_dict_value_raises(self):
        # Defensive: a JSONB field accidentally added to version_cols would
        # silently destroy SCD2 quality. The whitelist must catch this.
        row = {"bad": {"k": "v"}}
        with pytest.raises(TypeError, match="non-scalar"):
            _stable_hash(row, ("bad",))


class TestCanonicalize:
    def test_int_to_float(self):
        assert _canonicalize(1_090_000) == 1_090_000.0
        assert isinstance(_canonicalize(1_090_000), float)

    def test_float_passes_through(self):
        assert _canonicalize(1_090_000.0) == 1_090_000.0

    def test_bool_passes_through_as_bool(self):
        assert _canonicalize(True) is True
        assert _canonicalize(False) is False

    def test_str_passes_through(self):
        assert _canonicalize("Available") == "Available"

    def test_none_passes_through(self):
        assert _canonicalize(None) is None


# ---------------------------------------------------------------------------
# Normalization — id rename + listings-specific rename map + raw_json capture
# ---------------------------------------------------------------------------

class TestNormalizeListing:
    def test_id_renamed_to_listing_id(self):
        out = _normalize_listing({"id": 12345, "precoimovel": "100.000"})
        assert out["listing_id"] == 12345
        assert "id" not in out

    def test_localizacao_renamed(self):
        out = _normalize_listing({
            "id": 1,
            "localizacaolevel1imovel": "Lisboa",
            "localizacaolevel2imovel": "Cascais",
            "localizacaolevel3imovel": "Estoril",
        })
        assert out["localizacaolevel1"] == "Lisboa"
        assert out["localizacaolevel2"] == "Cascais"
        assert out["localizacaolevel3"] == "Estoril"
        assert "localizacaolevel1imovel" not in out

    def test_url_detail_renamed(self):
        out = _normalize_listing({"id": 1, "url_detail_view_website": "https://x.com/1"})
        assert out["url_detail"] == "https://x.com/1"
        assert "url_detail_view_website" not in out

    def test_raw_json_preserves_original(self):
        # raw_json should hold the unmodified API response — useful for replay.
        original = {"id": 1, "localizacaolevel1imovel": "Porto", "weird_field": 42}
        out = _normalize_listing(original)
        assert out["raw_json"] == original

    def test_input_not_mutated(self):
        original = {"id": 1, "localizacaolevel1imovel": "Porto"}
        snapshot = dict(original)
        _normalize_listing(original)
        assert original == snapshot


class TestNormalizeDevelopment:
    def test_id_renamed_to_venture_id(self):
        out = _normalize_development({"id": 99, "nome": "Quinta do Sol"})
        assert out["venture_id"] == 99
        assert "id" not in out

    def test_raw_json_preserves_original(self):
        original = {"id": 99, "nome": "Quinta", "imoveisdisponiveis": 5}
        out = _normalize_development(original)
        assert out["raw_json"] == original


# ---------------------------------------------------------------------------
# Sanity check on the version-column lists themselves
# ---------------------------------------------------------------------------

class TestVersionColumnLists:
    def test_no_jsonb_columns_in_listings_version(self):
        # Tripwire: never include array/JSON columns in version_cols.
        forbidden = {"gallery", "raw_json", "descricaocompleta", "video", "virtualreality"}
        assert not (set(LISTINGS_VERSION_COLUMNS) & forbidden), (
            "JSONB columns must not be in LISTINGS_VERSION_COLUMNS — they reorder spuriously"
        )

    def test_no_jsonb_columns_in_developments_version(self):
        forbidden = {"gallery", "raw_json", "descricaocompleta", "video", "virtualreality"}
        assert not (set(DEVELOPMENTS_VERSION_COLUMNS) & forbidden)

    def test_no_id_in_version_columns(self):
        # Identifiers should never trigger version churn.
        for forbidden_id in ("id", "listing_id", "venture_id", "_dlt_load_id", "_dlt_id"):
            assert forbidden_id not in LISTINGS_VERSION_COLUMNS
            assert forbidden_id not in DEVELOPMENTS_VERSION_COLUMNS

    def test_price_in_both_lists(self):
        # If price tracking ever silently drops out, lifecycle measures break.
        assert "precosemformatacao" in LISTINGS_VERSION_COLUMNS
        assert "precosemformatacao" in DEVELOPMENTS_VERSION_COLUMNS
