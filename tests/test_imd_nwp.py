"""Tests for the IMD NWP marine forecast adapter."""

from __future__ import annotations

import pytest

from marine_data_engine.sources.base import (
    AuthenticationRequiredError,
    LiveSourceDisabledError,
)
from marine_data_engine.sources.imd_nwp import (
    IMDNwpAdapter,
    IMDNwpFixtureAdapter,
    parse_nwp_forecast,
)


def test_parse_nwp_forecast_fans_out_parameters(imd_nwp_json):
    forecasts = parse_nwp_forecast(imd_nwp_json)
    # 3 points x 5 parameters each = 15 forecast records.
    assert len(forecasts) == 15
    params = {f.parameter for f in forecasts}
    assert params == {
        "wind_speed",
        "wind_direction",
        "mslp",
        "rainfall",
        "significant_wave_height",
    }
    wind = next(f for f in forecasts if f.parameter == "wind_speed")
    assert wind.unit == "m/s"
    assert wind.model_name == "IMD-GFS"
    assert wind.valid_from is not None
    assert wind.latitude is not None


def test_fixture_adapter_fetch_returns_forecasts(imd_nwp_json):
    result = IMDNwpFixtureAdapter(imd_nwp_json).fetch()
    assert result.raw.provider == "IMD"
    assert result.raw.dataset == "imd_nwp"
    assert len(result.forecasts) == 15


def test_fixture_marine_forecast_helper(imd_nwp_json):
    forecasts = IMDNwpFixtureAdapter(imd_nwp_json).fetch_marine_forecast()
    assert all(f.provider == "IMD" for f in forecasts)


def test_live_adapter_disabled_by_default():
    with pytest.raises(LiveSourceDisabledError):
        IMDNwpAdapter().fetch()


def test_live_adapter_requires_token_when_enabled():
    adapter = IMDNwpAdapter(token="")
    adapter.live_enabled = True
    with pytest.raises(AuthenticationRequiredError):
        adapter.fetch()
    with pytest.raises(AuthenticationRequiredError):
        adapter.fetch_marine_forecast()
