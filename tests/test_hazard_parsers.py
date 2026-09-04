"""Tests for cyclone / tsunami hazard parsers (offline, deterministic)."""

from __future__ import annotations

import pytest

from marine_data_engine.sources.base import LiveSourceDisabledError
from marine_data_engine.sources.hazards import (
    CycloneFixtureAdapter,
    CycloneLiveAdapter,
    TsunamiFixtureAdapter,
    TsunamiLiveAdapter,
    parse_cyclone_bulletin,
    parse_tsunami_bulletin,
)


def test_parse_cyclone_bulletin(cyclone_json):
    cyclone = parse_cyclone_bulletin(cyclone_json)
    assert cyclone.cyclone_id == "BOB-04-2026"
    assert cyclone.name == "Cyclone Vayu"
    assert cyclone.center_lat == pytest.approx(15.4)
    assert cyclone.center_lon == pytest.approx(87.2)
    assert cyclone.issue_time is not None
    assert cyclone.movement_direction == pytest.approx(315.0)
    assert cyclone.movement_speed == pytest.approx(18.0)
    assert cyclone.central_pressure == pytest.approx(982.0)
    assert cyclone.max_sustained_wind == pytest.approx(120.0)
    assert cyclone.intensity_category == "Severe Cyclonic Storm"
    assert cyclone.track_geometry["type"] == "LineString"
    assert len(cyclone.track_geometry["coordinates"]) == 4
    # GeoJSON lon,lat order.
    assert cyclone.track_geometry["coordinates"][0] == [87.2, 15.4]


def test_cyclone_missing_center_raises():
    with pytest.raises(ValueError):
        parse_cyclone_bulletin(b'{"cyclone_id": "X"}')


def test_cyclone_fixture_adapter(cyclone_json):
    result = CycloneFixtureAdapter(cyclone_json).fetch()
    assert len(result.cyclones) == 1
    assert result.raw.provider == "IMD"
    assert result.raw.media_type == "application/json"


def test_parse_tsunami_bulletin(tsunami_json):
    tsunami = parse_tsunami_bulletin(tsunami_json)
    assert tsunami.event_id == "TSU-INCOIS-2026-0912"
    assert tsunami.earthquake_time is not None
    assert tsunami.eq_lat == pytest.approx(-6.5)
    assert tsunami.eq_lon == pytest.approx(95.3)
    assert tsunami.magnitude == pytest.approx(7.8)
    assert tsunami.depth == pytest.approx(25.0)
    assert tsunami.tsunami_status == "WATCH"
    assert tsunami.alert_level == "Warning"
    assert tsunami.affected_regions is not None
    assert "Tamil Nadu Coast" in tsunami.affected_regions


def test_tsunami_fixture_adapter(tsunami_json):
    result = TsunamiFixtureAdapter(tsunami_json).fetch()
    assert len(result.tsunamis) == 1
    assert result.raw.provider == "INCOIS"


def test_hazard_live_adapters_disabled():
    with pytest.raises(LiveSourceDisabledError):
        CycloneLiveAdapter().fetch()
    with pytest.raises(LiveSourceDisabledError):
        TsunamiLiveAdapter().fetch()
