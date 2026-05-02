"""Unit tests for the JLL dlt source — focuses on _stable_hash, normalization,
and version column validation.

Run inside the Airflow container (dlt available):
    docker compose exec airflow-scheduler pytest /opt/airflow/dags/pipelines/portals/jll/tests/

Or in a local venv with dlt installed:
    pip install "dlt[postgres]~=1.25.0" pytest
    PYTHONPATH=. pytest pipelines/portals/jll/tests/
"""

from __future__ import annotations

import pytest

from pipelines.portals.jll.source import (
    DEVELOPMENTS_JSON_COLUMNS,
    DEVELOPMENTS_VERSION_COLUMNS,
    LISTINGS_JSON_COLUMNS,
    LISTINGS_VERSION_COLUMNS,
    _canonicalize,
    _normalize_development,
    _normalize_listing,
    _stable_hash,
    _to_snake,
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
        row_int = {"price_value": 463_000}
        row_flt = {"price_value": 463_000.0}
        cols = ("price_value",)
        assert _stable_hash(row_int, cols) == _stable_hash(row_flt, cols)

    def test_bool_not_coerced_to_numeric(self):
        row_bool = {"flag": True}
        row_int = {"flag": 1}
        cols = ("flag",)
        assert _stable_hash(row_bool, cols) != _stable_hash(row_int, cols)

    def test_none_handled(self):
        row = {"a": None, "b": 1}
        cols = ("a", "b")
        h = _stable_hash(row, cols)
        assert isinstance(h, str)
        assert len(h) == 64  # sha256 hex

    def test_missing_key_treated_as_none(self):
        row1 = {"a": 1}
        row2 = {"a": 1, "b": None}
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
        row = {"bad": {"k": "v"}}
        with pytest.raises(TypeError, match="non-scalar"):
            _stable_hash(row, ("bad",))


class TestCanonicalize:
    def test_int_to_float(self):
        assert _canonicalize(463_000) == 463_000.0
        assert isinstance(_canonicalize(463_000), float)

    def test_float_passes_through(self):
        assert _canonicalize(463_000.0) == 463_000.0

    def test_bool_passes_through_as_bool(self):
        assert _canonicalize(True) is True
        assert _canonicalize(False) is False

    def test_str_passes_through(self):
        assert _canonicalize("Available") == "Available"

    def test_none_passes_through(self):
        assert _canonicalize(None) is None


# ---------------------------------------------------------------------------
# CamelCase → snake_case
# ---------------------------------------------------------------------------

class TestToSnake:
    def test_simple(self):
        assert _to_snake("GPSLat") == "gps_lat"

    def test_camel(self):
        assert _to_snake("AvailabilityID") == "availability_id"

    def test_already_snake(self):
        assert _to_snake("already_snake") == "already_snake"

    def test_single_word(self):
        assert _to_snake("Name") == "name"

    def test_consecutive_upper(self):
        assert _to_snake("HTMLParser") == "html_parser"

    def test_id_field(self):
        assert _to_snake("ID") == "id"


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

class TestNormalizeDevelopment:
    def test_id_renamed_to_development_id(self):
        out = _normalize_development({"ID": 23379273, "Name": "AURYA VISTA"})
        assert out["development_id"] == 23379273
        assert "i_d" not in out

    def test_camel_to_snake(self):
        out = _normalize_development({
            "ID": 1, "GPSLat": 38.8, "GPSLon": -9.1,
            "TotalFractions": 30, "AvailabilityID": 2,
        })
        assert out["gps_lat"] == 38.8
        assert out["gps_lon"] == -9.1
        assert out["total_fractions"] == 30
        assert out["availability_id"] == 2

    def test_raw_json_preserves_original(self):
        original = {"ID": 99, "Name": "Test", "TotalFractions": 5}
        out = _normalize_development(original)
        assert out["raw_json"] == original


class TestNormalizeListing:
    def test_id_renamed_to_listing_id(self):
        out = _normalize_listing({
            "ID": 23379286, "Rooms": 2, "PropertyBusiness": [],
        })
        assert out["listing_id"] == 23379286
        assert "i_d" not in out

    def test_price_flattened(self):
        out = _normalize_listing({
            "ID": 1,
            "PropertyBusiness": [{
                "BusinessName": "Sale",
                "Prices": [{
                    "PriceValue": 463000,
                    "FormattedPrice": "463\u00a0000 €",
                    "CurrencyISO": "EUR",
                    "MarketValue": 0,
                }],
            }],
        })
        assert out["price_value"] == 463000
        assert out["formatted_price"] == "463\u00a0000 €"
        assert out["currency_iso"] == "EUR"
        assert out["business_name"] == "Sale"

    def test_empty_property_business(self):
        out = _normalize_listing({"ID": 1, "PropertyBusiness": []})
        assert out["price_value"] == 0
        assert out["formatted_price"] == ""

    def test_raw_json_preserves_original(self):
        original = {"ID": 1, "Rooms": 3, "PropertyBusiness": []}
        out = _normalize_listing(original)
        assert out["raw_json"] == original

    def test_input_not_mutated(self):
        original = {"ID": 1, "Rooms": 3, "PropertyBusiness": []}
        snapshot = dict(original)
        _normalize_listing(original)
        assert original == snapshot


# ---------------------------------------------------------------------------
# Version column sanity checks
# ---------------------------------------------------------------------------

class TestVersionColumnLists:
    def test_no_json_columns_in_listings_version(self):
        forbidden = set(LISTINGS_JSON_COLUMNS)
        assert not (set(LISTINGS_VERSION_COLUMNS) & forbidden), (
            "JSON columns must not be in LISTINGS_VERSION_COLUMNS"
        )

    def test_no_json_columns_in_developments_version(self):
        forbidden = set(DEVELOPMENTS_JSON_COLUMNS)
        assert not (set(DEVELOPMENTS_VERSION_COLUMNS) & forbidden)

    def test_no_id_in_version_columns(self):
        for forbidden_id in ("id", "listing_id", "development_id", "_dlt_load_id", "_dlt_id"):
            assert forbidden_id not in LISTINGS_VERSION_COLUMNS
            assert forbidden_id not in DEVELOPMENTS_VERSION_COLUMNS

    def test_price_in_listings(self):
        assert "price_value" in LISTINGS_VERSION_COLUMNS

    def test_price_range_in_developments(self):
        assert "min_property_formatted_price" in DEVELOPMENTS_VERSION_COLUMNS
        assert "max_property_formatted_price" in DEVELOPMENTS_VERSION_COLUMNS
