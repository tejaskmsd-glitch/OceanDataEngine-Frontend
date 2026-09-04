"""Tests for the IMD buoy HTML parser (offline, deterministic)."""

from __future__ import annotations

import pytest

from marine_data_engine.sources.base import LiveSourceDisabledError
from marine_data_engine.sources.imd_buoy import (
    BuoyStructureError,
    IMDBuoyFixtureAdapter,
    IMDBuoyLiveAdapter,
    parse_buoy_html,
)


def test_parse_buoy_html_extracts_all_parameters(buoy_html):
    observations = parse_buoy_html(buoy_html, source_url="fixture://imd/buoy")
    # 2 rows x (wind_speed, wind_direction, pressure, temperature, wave_height)
    assert len(observations) == 10

    stations = {o.station_id for o in observations}
    assert stations == {"BD08", "AD07"}

    params = {o.parameter for o in observations}
    assert params == {
        "wind_speed",
        "wind_direction",
        "sea_level_pressure",
        "sea_surface_temperature",
        "significant_wave_height",
    }

    for o in observations:
        assert o.station_type == "buoy"
        assert o.observed_at is not None
        assert o.latitude is not None and o.longitude is not None


def test_buoy_wind_speed_normalized_to_ms(buoy_html):
    observations = parse_buoy_html(buoy_html)
    wind = next(
        o for o in observations if o.station_id == "BD08" and o.parameter == "wind_speed"
    )
    # 12.5 knots -> m/s
    assert wind.unit == "m/s"
    assert wind.value == pytest.approx(12.5 * 0.514444, rel=1e-6)


def test_buoy_pressure_and_temperature_units(buoy_html):
    observations = parse_buoy_html(buoy_html)
    pressure = next(o for o in observations if o.parameter == "sea_level_pressure")
    temp = next(o for o in observations if o.parameter == "sea_surface_temperature")
    assert pressure.unit == "hPa"
    assert temp.unit == "degC"


def test_buoy_fixture_adapter_fetch(buoy_html):
    result = IMDBuoyFixtureAdapter(buoy_html).fetch()
    assert len(result.observations) == 10
    assert result.raw.provider == "IMD"
    assert result.raw.media_type == "text/html"
    assert result.raw.ext == "html"


def test_buoy_canary_on_unrecognized_structure():
    bad_html = b"<html><body><table><tr><th>Foo</th><th>Bar</th></tr>"
    bad_html += b"<tr><td>1</td><td>2</td></tr></table></body></html>"
    with pytest.raises(BuoyStructureError):
        parse_buoy_html(bad_html)


def test_buoy_canary_on_no_table():
    with pytest.raises(BuoyStructureError):
        parse_buoy_html(b"<html><body><p>no table here</p></body></html>")


def test_buoy_live_adapter_disabled():
    with pytest.raises(LiveSourceDisabledError):
        IMDBuoyLiveAdapter("BD08").fetch()
