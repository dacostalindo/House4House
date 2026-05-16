"""Tests for pipelines.common.geocoding.

Mocks `requests.get` — no live HTTP. Live-Nominatim integration is tested
end-to-end in Phase 5 of Activity 7 (the sce_geocode DAG run against real
Aveiro data).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pipelines.common.geocoding import (
    GeocodeResult,
    nominatim_geocode,
    nominatim_geocode_batch,
)

# A realistic Nominatim /search response for "Rua Direita 199, Aradas, Aveiro, Portugal"
SAMPLE_HIT = {
    "place_id": 404895,
    "osm_type": "way",
    "osm_id": 560475152,
    "lat": "40.6222382",
    "lon": "-8.6436987",
    "display_name": "Rua Direita, Quinta do Casal, Aradas, Aveiro, 3810-702, Portugal",
    "importance": 0.5833433333333332,
    "class": "highway",
    "type": "secondary",
}


def _mock_response(json_data, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    return resp


class TestNominatimGeocodeSingle:
    """Single forward-geocode behaviour."""

    def test_happy_path(self):
        with patch("pipelines.common.geocoding.requests.get") as mock_get:
            mock_get.return_value = _mock_response([SAMPLE_HIT])
            result = nominatim_geocode(
                "Rua Direita 199, Aradas, Aveiro, Portugal",
                url="http://nominatim:8080",
            )

        assert isinstance(result, GeocodeResult)
        assert result.lat == pytest.approx(40.6222382)
        assert result.lon == pytest.approx(-8.6436987)
        assert "Aradas" in result.display_name
        assert result.importance == pytest.approx(0.583, abs=0.01)
        assert result.raw is SAMPLE_HIT

    def test_request_params(self):
        with patch("pipelines.common.geocoding.requests.get") as mock_get:
            mock_get.return_value = _mock_response([SAMPLE_HIT])
            nominatim_geocode("Aveiro", url="http://nominatim:8080", timeout=15, limit=3)

        call = mock_get.call_args
        assert call.args == ("http://nominatim:8080/search",)
        assert call.kwargs["params"]["q"] == "Aveiro"
        assert call.kwargs["params"]["format"] == "json"
        assert call.kwargs["params"]["limit"] == 3
        assert call.kwargs["timeout"] == 15

    def test_empty_query_returns_none(self):
        with patch("pipelines.common.geocoding.requests.get") as mock_get:
            assert nominatim_geocode("") is None
            assert nominatim_geocode("   ") is None
            assert nominatim_geocode(None) is None  # type: ignore[arg-type]
        # No HTTP call should have been made
        mock_get.assert_not_called()

    def test_no_hits_returns_none(self):
        with patch("pipelines.common.geocoding.requests.get") as mock_get:
            mock_get.return_value = _mock_response([])
            assert nominatim_geocode("zzzzznonsense", url="http://nominatim:8080") is None

    def test_http_error_returns_none(self):
        with patch("pipelines.common.geocoding.requests.get") as mock_get:
            mock_get.side_effect = ConnectionError("boom")
            assert nominatim_geocode("Aveiro", url="http://nominatim:8080") is None

    def test_malformed_response_returns_none(self):
        with patch("pipelines.common.geocoding.requests.get") as mock_get:
            mock_get.return_value = _mock_response([{"display_name": "X"}])  # missing lat/lon
            assert nominatim_geocode("Aveiro", url="http://nominatim:8080") is None


class TestNominatimGeocodeBatch:
    """Batch generator: order, rate-limit, hit counting."""

    def test_preserves_keys_and_order(self):
        # Three queries: hit, no-hit, hit
        with patch("pipelines.common.geocoding.requests.get") as mock_get:
            mock_get.side_effect = [
                _mock_response([SAMPLE_HIT]),
                _mock_response([]),
                _mock_response([SAMPLE_HIT]),
            ]
            with patch("pipelines.common.geocoding.time.sleep"):  # skip sleep
                pairs = list(
                    nominatim_geocode_batch(
                        [("k1", "Aveiro"), ("k2", "zzz"), ("k3", "Porto")],
                        url="http://nominatim:8080",
                    )
                )

        assert [k for k, _ in pairs] == ["k1", "k2", "k3"]
        assert isinstance(pairs[0][1], GeocodeResult)
        assert pairs[1][1] is None
        assert isinstance(pairs[2][1], GeocodeResult)

    def test_rate_limit_sleep_called_per_request(self):
        with (
            patch("pipelines.common.geocoding.requests.get") as mock_get,
            patch("pipelines.common.geocoding.time.sleep") as mock_sleep,
        ):
            mock_get.return_value = _mock_response([SAMPLE_HIT])
            list(
                nominatim_geocode_batch(
                    [("k1", "a"), ("k2", "b"), ("k3", "c")],
                    url="http://nominatim:8080",
                    rate_limit_seconds=0.05,
                )
            )

        assert mock_sleep.call_count == 3
        assert all(call.args[0] == 0.05 for call in mock_sleep.call_args_list)

    def test_progress_callback(self):
        calls: list[tuple[int, int]] = []
        with (
            patch("pipelines.common.geocoding.requests.get") as mock_get,
            patch("pipelines.common.geocoding.time.sleep"),
        ):
            mock_get.return_value = _mock_response([SAMPLE_HIT])
            list(
                nominatim_geocode_batch(
                    [("k", "a")] * 5,
                    url="http://nominatim:8080",
                    progress_every=2,
                    progress_callback=lambda p, h: calls.append((p, h)),
                )
            )

        # Callback fired at processed=2, 4 (every 2)
        assert calls == [(2, 2), (4, 4)]

    def test_empty_input(self):
        with patch("pipelines.common.geocoding.requests.get") as mock_get:
            results = list(nominatim_geocode_batch([], url="http://nominatim:8080"))
        assert results == []
        mock_get.assert_not_called()

    def test_one_failure_does_not_stop_batch(self):
        with (
            patch("pipelines.common.geocoding.requests.get") as mock_get,
            patch("pipelines.common.geocoding.time.sleep"),
        ):
            mock_get.side_effect = [
                _mock_response([SAMPLE_HIT]),
                ConnectionError("boom"),
                _mock_response([SAMPLE_HIT]),
            ]
            results = list(
                nominatim_geocode_batch(
                    [("a", "x"), ("b", "y"), ("c", "z")],
                    url="http://nominatim:8080",
                )
            )

        assert [k for k, _ in results] == ["a", "b", "c"]
        assert results[0][1] is not None
        assert results[1][1] is None  # graceful no-hit on error
        assert results[2][1] is not None
