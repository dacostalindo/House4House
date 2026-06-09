"""Unit tests for the imovirtual dlt source — pure functions only (no network).

Fixtures are trimmed from live API responses captured 2026-06-05 (JC Barrocas
development + its T3 unit + an Oliveira de Azeméis terreno). The highest-risk
functions are _stable_hash (false versions inflate price_change_count) and the
characteristics-pivot normalizers (where the dev `total_units` correction lives).

Run inside the Airflow container (dlt available):
    docker compose exec airflow-scheduler pytest /opt/airflow/dags/pipelines/portals/imovirtual/tests/

Or in a local venv with dlt installed:
    pip install "dlt[postgres]~=1.25.0" pytest
    PYTHONPATH=. pytest pipelines/portals/imovirtual/tests/
"""

from __future__ import annotations

import pytest

from pipelines.portals.imovirtual.source import (
    DEVELOPMENTS_JSON_COLUMNS,
    DEVELOPMENTS_VERSION_COLUMNS,
    PLOTS_VERSION_COLUMNS,
    UNITS_JSON_COLUMNS,
    UNITS_VERSION_COLUMNS,
    _admin_from_reverse,
    _canonicalize,
    _coords,
    _normalize_development,
    _normalize_plot,
    _normalize_unit,
    _pivot_characteristics,
    _stable_hash,
    _top_info,
)

# ---------------------------------------------------------------------------
# Fixtures (trimmed live payloads)
# ---------------------------------------------------------------------------
DEV_AD = {
    "id": 18987537,
    "title": "JC Barrocas",
    "slug": "jc-barrocas-ID1hFvB",
    "url": "https://www.imovirtual.com/pt/empreendimento/jc-barrocas-ID1hFvB",
    "status": "active",
    "adCategory": {"id": 11, "name": "FLAT", "type": "INVESTMENT"},
    "createdAt": "2025-12-18T17:10:31Z",
    "modifiedAt": "2026-03-05T12:53:20Z",
    "location": {
        "coordinates": {"latitude": 40.641052, "longitude": -8.609025},
        "reverseGeocoding": {
            "locations": [
                {"locationLevel": "district", "name": "Aveiro"},
                {"locationLevel": "council", "name": "Aveiro"},
                {"locationLevel": "parish", "name": "Esgueira"},
            ]
        },
        "address": {"street": {"name": "Rua Doutor José Pereira Tavares", "number": None}},
    },
    "characteristics": [
        {"key": "price_per_m_from", "value": "4391"},
        {"key": "area_from", "value": "82"},
        {"key": "area_to", "value": "136"},
        {"key": "state", "value": "in_building"},
        {"key": "offered_estates_type", "value": "flats"},
        {"key": "number_of_properties", "value": "20"},
    ],
    "topInformation": [
        {"label": "number_of_adverts", "values": ["11"], "unit": ""},
        {"label": "number_of_units_in_project", "values": ["20"], "unit": ""},
    ],
    "additionalInformation": [
        {"label": "advertiser_type", "values": ["developer"], "unit": ""},
        {"label": "security", "values": ["alarm", "monitoring"], "unit": ""},
        {"label": "extra_spaces", "values": ["terrace", "garage"], "unit": ""},
        {"label": "project_amenities", "values": ["pool"], "unit": ""},
        {"label": "rooms_number_range", "values": ["T0", "T1", "T2"], "unit": ""},
    ],
    "paginatedUnits": {"pagination": {"page": 1, "totalPages": 2, "totalResults": 11}},
    "owner": {"id": 5227621, "name": "Sucesso Acontece - Unipessoal Limitada", "type": "developer"},
    "images": [{"thumbnail": "https://x/y.jpg"}],
    "floorPlans": None,
    "unitGroups": {"unitsGroupBy": "ROOMS_NUMBER", "items": [{"groupId": "3", "count": 7}]},
}

UNIT_ITEM = {
    "id": 18987615,
    "url": "https://www.imovirtual.com/pt/anuncio/apartamento-t3-barrocas-ID1hFxR",
    "title": "",
    "status": "",
    "adCategory": {"id": 101, "name": "FLAT", "type": "SELL"},
    "location": {"coordinates": {"latitude": 0, "longitude": 0}},
    "characteristics": [
        {"key": "price", "value": "593250"},
        {"key": "price_per_m", "value": "4999"},
        {"key": "m", "value": "118.67"},
        {"key": "market", "value": "primary"},
        {"key": "energy_certificate", "value": "a"},
        {"key": "building_type", "value": "block"},
        {"key": "floor_no", "value": "floor_1"},
        {"key": "construction_status", "value": "to_completion"},
        {"key": "windows_type", "value": "plastic"},
        {"key": "heating", "value": "urban"},
        {"key": "rooms_num", "value": "4"},
        {"key": "building_floors_num", "value": "6"},
        {"key": "build_year", "value": "2024"},
        {"key": "terrain_area", "value": "1011"},
        {"key": "free_from", "value": "2027-09-30"},
    ],
    "images": [{"thumbnail": "https://x/u.jpg"}],
    "floorPlans": ["https://x/p.jpg"],
    # Pass-3 fields merged into the embedded item by _ensure_dev_payload.
    "additionalInformation": [
        {"label": "bathrooms_num", "values": ["2"], "unit": ""},
        {"label": "extras_types", "values": ["garage", "lift", "air_conditioning"], "unit": ""},
        {"label": "security_types", "values": ["monitoring"], "unit": ""},
        {"label": "advertiser_type", "values": ["developer"], "unit": ""},
    ],
}

PLOT_AD = {
    "id": 19172848,
    "title": "Terreno Rústico  Venda em São Roque,Oliveira de Azeméis",
    "slug": "terreno-rustico-venda-em-sao-roque-oliveira-de-azemeis-ID1irJu",
    "status": "active",
    "adCategory": {"id": 401, "name": "TERRAIN", "type": "SELL"},
    "location": {
        "coordinates": {"latitude": 40.872704, "longitude": -8.467455},
        "reverseGeocoding": {
            "locations": [
                {"locationLevel": "district", "name": "Aveiro"},
                {"locationLevel": "council", "name": "Oliveira de Azeméis"},
                {"locationLevel": "parish", "name": "São Roque"},
            ]
        },
        "address": {"street": {"name": None}},
    },
    "characteristics": [
        {"key": "price", "value": "55000"},
        {"key": "price_per_m", "value": "37"},
        {"key": "m", "value": "1490"},
        {"key": "type", "value": "agricultural"},
    ],
    "owner": {"type": "agency"},
    "images": [],
    "additionalInformation": [
        {"label": "advertiser_type", "values": ["agency"], "unit": ""},
        {"label": "access_types", "values": ["paved", "private"], "unit": ""},
        {"label": "media_types", "values": ["water", "electricity"], "unit": ""},
        {"label": "vicinity_types", "values": ["forest"], "unit": ""},
    ],
}


# ---------------------------------------------------------------------------
# _stable_hash
# ---------------------------------------------------------------------------
class TestStableHash:
    def test_deterministic(self):
        row = {"a": 1, "b": "x", "c": True}
        assert _stable_hash(row, ("a", "b", "c")) == _stable_hash(row, ("a", "b", "c"))

    def test_int_and_float_collide(self):
        assert _stable_hash({"p": 1000}, ("p",)) == _stable_hash({"p": 1000.0}, ("p",))

    def test_bool_not_coerced_to_number(self):
        assert _stable_hash({"p": True}, ("p",)) != _stable_hash({"p": 1}, ("p",))

    def test_missing_key_is_none(self):
        assert _stable_hash({}, ("p",)) == _stable_hash({"p": None}, ("p",))

    def test_changed_value_changes_hash(self):
        assert _stable_hash({"p": "1"}, ("p",)) != _stable_hash({"p": "2"}, ("p",))

    def test_non_scalar_raises(self):
        with pytest.raises(TypeError):
            _stable_hash({"p": [1, 2]}, ("p",))


class TestCanonicalize:
    def test_int_to_float(self):
        assert _canonicalize(5) == 5.0

    def test_bool_stays_bool(self):
        assert _canonicalize(True) is True

    def test_str_passthrough(self):
        assert _canonicalize("x") == "x"

    def test_none_passthrough(self):
        assert _canonicalize(None) is None


# ---------------------------------------------------------------------------
# characteristics pivot + admin geography
# ---------------------------------------------------------------------------
class TestPivotCharacteristics:
    def test_pivots_key_value(self):
        out = _pivot_characteristics([{"key": "price", "value": "100"}])
        assert out == {"price": "100"}

    def test_empty_and_none(self):
        assert _pivot_characteristics(None) == {}
        assert _pivot_characteristics([]) == {}

    def test_skips_entries_without_key(self):
        assert _pivot_characteristics([{"value": "x"}]) == {}


class TestAdminFromReverse:
    def test_maps_levels_to_pt_admin(self):
        out = _admin_from_reverse(DEV_AD["location"])
        assert out == {"distrito": "Aveiro", "concelho": "Aveiro", "parish": "Esgueira"}

    def test_empty_location(self):
        assert _admin_from_reverse({}) == {"distrito": None, "concelho": None, "parish": None}


class TestCoords:
    def test_real_coords(self):
        assert _coords(DEV_AD["location"]) == (40.641052, -8.609025)

    def test_zero_coords_become_none(self):
        # units report (0, 0) — they have no own pin
        assert _coords(UNIT_ITEM["location"]) == (None, None)


class TestTopInfo:
    def test_reads_label(self):
        assert _top_info(DEV_AD, "number_of_units_in_project") == "20"
        assert _top_info(DEV_AD, "number_of_adverts") == "11"

    def test_missing_label(self):
        assert _top_info(DEV_AD, "nonexistent") is None


# ---------------------------------------------------------------------------
# Normalizers
# ---------------------------------------------------------------------------
class TestNormalizeDevelopment:
    def test_pk_and_identity(self):
        rec = _normalize_development(DEV_AD)
        assert rec["development_id"] == 18987537
        assert rec["name"] == "JC Barrocas"
        assert rec["category_type"] == "INVESTMENT"

    def test_total_units_is_project_total_not_listed(self):
        # THE correction: total_units = project size (20), NOT advert count (11).
        rec = _normalize_development(DEV_AD)
        assert rec["total_units"] == "20"
        assert rec["listed_units_count"] == 11

    def test_admin_geography_from_reverse(self):
        rec = _normalize_development(DEV_AD)
        assert rec["concelho"] == "Aveiro"
        assert rec["parish"] == "Esgueira"

    def test_dev_level_coords(self):
        rec = _normalize_development(DEV_AD)
        assert rec["gps_lat"] == 40.641052

    def test_promoter_and_raw_json(self):
        rec = _normalize_development(DEV_AD)
        assert rec["promoter_id"] == 5227621
        assert rec["raw_json"] is DEV_AD

    def test_additional_info_plucked(self):
        rec = _normalize_development(DEV_AD)
        assert rec["advertiser_type"] == "developer"
        assert rec["security"] == ["alarm", "monitoring"]
        assert rec["extra_spaces"] == ["terrace", "garage"]
        assert rec["project_amenities"] == ["pool"]
        assert rec["rooms_number_range"] == ["T0", "T1", "T2"]


class TestNormalizeUnit:
    def test_pk_and_fk(self):
        rec = _normalize_unit(UNIT_ITEM, development_id=18987537)
        assert rec["unit_id"] == 18987615
        assert rec["development_id"] == 18987537  # FK minted from parent

    def test_characteristics_pivoted(self):
        rec = _normalize_unit(UNIT_ITEM, development_id=18987537)
        assert rec["price"] == "593250"
        assert rec["area_m"] == "118.67"
        assert rec["rooms_num"] == "4"
        assert rec["energy_certificate"] == "a"

    def test_empty_title_status_become_none(self):
        rec = _normalize_unit(UNIT_ITEM, development_id=1)
        assert rec["title"] is None
        assert rec["status"] is None

    def test_floor_plans_plucked(self):
        rec = _normalize_unit(UNIT_ITEM, development_id=1)
        assert rec["floor_plans"] == ["https://x/p.jpg"]

    def test_extended_characteristics_plucked(self):
        rec = _normalize_unit(UNIT_ITEM, development_id=1)
        assert rec["build_year"] == "2024"
        assert rec["terrain_area_m"] == "1011"
        assert rec["free_from"] == "2027-09-30"

    def test_pass3_additional_info_plucked(self):
        rec = _normalize_unit(UNIT_ITEM, development_id=1)
        assert rec["bathrooms_num"] == "2"
        assert rec["extras_types"] == ["garage", "lift", "air_conditioning"]
        assert rec["security_types"] == ["monitoring"]
        assert rec["advertiser_type"] == "developer"

    def test_pass3_fields_none_when_no_additional_info(self):
        # When _ensure_dev_payload's Pass-3 fetch fails, the embedded item never
        # gets `additionalInformation` merged in — fields should be None, not crash.
        bare = {**UNIT_ITEM}
        bare.pop("additionalInformation", None)
        rec = _normalize_unit(bare, development_id=1)
        assert rec["bathrooms_num"] is None
        assert rec["extras_types"] is None
        assert rec["security_types"] is None
        assert rec["advertiser_type"] is None


class TestNormalizePlot:
    def test_pk_and_classification(self):
        rec = _normalize_plot(PLOT_AD)
        assert rec["listing_id"] == 19172848
        assert rec["classification"] == "agricultural"

    def test_price_area_coords(self):
        rec = _normalize_plot(PLOT_AD)
        assert rec["price"] == "55000"
        assert rec["area_m"] == "1490"
        assert rec["gps_lat"] == 40.872704

    def test_admin_geography(self):
        rec = _normalize_plot(PLOT_AD)
        assert rec["concelho"] == "Oliveira de Azeméis"

    def test_additional_info_plucked(self):
        rec = _normalize_plot(PLOT_AD)
        assert rec["advertiser_type"] == "agency"
        assert rec["access_types"] == ["paved", "private"]
        assert rec["media_types"] == ["water", "electricity"]
        assert rec["vicinity_types"] == ["forest"]


# ---------------------------------------------------------------------------
# Version-column tripwires — guard SCD2 quality
# ---------------------------------------------------------------------------
class TestVersionColumnLists:
    def test_no_json_columns_in_version_tuples(self):
        for vcols, jcols in (
            (DEVELOPMENTS_VERSION_COLUMNS, DEVELOPMENTS_JSON_COLUMNS),
            (UNITS_VERSION_COLUMNS, UNITS_JSON_COLUMNS),
        ):
            assert not (set(vcols) & set(jcols))

    def test_price_signal_present(self):
        assert "price_per_m_from" in DEVELOPMENTS_VERSION_COLUMNS
        assert "price" in UNITS_VERSION_COLUMNS
        assert "price" in PLOTS_VERSION_COLUMNS

    def test_version_columns_are_hashable_scalars(self):
        # every version row built from fixtures must hash without raising
        dev = _normalize_development(DEV_AD)
        unit = _normalize_unit(UNIT_ITEM, development_id=1)
        plot = _normalize_plot(PLOT_AD)
        assert _stable_hash(dev, DEVELOPMENTS_VERSION_COLUMNS)
        assert _stable_hash(unit, UNITS_VERSION_COLUMNS)
        assert _stable_hash(plot, PLOTS_VERSION_COLUMNS)
