"""Tests for the INCOIS tide gauge adapter."""

from __future__ import annotations

import pytest

from marine_data_engine.sources.base import LiveSourceDisabledError
from marine_data_engine.sources.incois_tide import (
    INCOISTideFixtureAdapter,
    INCOISTideLiveAdapter,
    parse_tide_observations,
)


def test_parse_tide_observations(tide_json):
    obs = parse_tide_observations(tide_json)
    assert len(obs) == 3
    first = obs[0]
    assert first.station_id == "TG_VISAKHAPATNAM"
    assert first.parameter == "water_level"
    assert first.unit == "m"
    assert first.station_type == "tide_gauge"
    assert first.value == 1.42
    assert first.observed_at is not None
    assert first.provider == "INCOIS"


def test_fixture_adapter_fetch(tide_json):
    result = INCOISTideFixtureAdapter(tide_json).fetch()
    assert result.raw.dataset == "incois_tide"
    assert len(result.observations) == 3
    assert all(o.parameter == "water_level" for o in result.observations)


def test_live_adapter_disabled():
    with pytest.raises(LiveSourceDisabledError):
        INCOISTideLiveAdapter().fetch()
