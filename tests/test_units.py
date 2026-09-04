"""Unit tests for the pure unit-conversion framework."""

from __future__ import annotations

import math

import pytest

from marine_data_engine.domain.units import (
    celsius_to_kelvin,
    direction_from_uv,
    hpa_to_pascal,
    kelvin_to_celsius,
    knots_to_ms,
    ms_to_knots,
    normalize_longitude,
    pascal_to_hpa,
    speed_from_uv,
)


def test_kelvin_celsius_roundtrip():
    assert kelvin_to_celsius(273.15) == pytest.approx(0.0)
    assert kelvin_to_celsius(300.0) == pytest.approx(26.85)
    assert celsius_to_kelvin(0.0) == pytest.approx(273.15)
    assert celsius_to_kelvin(-273.15) == pytest.approx(0.0)
    # Roundtrip.
    assert kelvin_to_celsius(celsius_to_kelvin(15.0)) == pytest.approx(15.0)


def test_knots_ms_roundtrip():
    assert knots_to_ms(1.0) == pytest.approx(0.514444)
    assert knots_to_ms(0.0) == 0.0
    assert ms_to_knots(0.514444) == pytest.approx(1.0)
    assert ms_to_knots(knots_to_ms(10.0)) == pytest.approx(10.0)


def test_pressure_conversions():
    assert pascal_to_hpa(101325.0) == pytest.approx(1013.25)
    assert hpa_to_pascal(1013.25) == pytest.approx(101325.0)
    assert pascal_to_hpa(0.0) == 0.0
    assert hpa_to_pascal(pascal_to_hpa(98000.0)) == pytest.approx(98000.0)


def test_normalize_longitude():
    assert normalize_longitude(190.0) == pytest.approx(-170.0)
    assert normalize_longitude(73.5) == pytest.approx(73.5)
    assert normalize_longitude(360.0) == pytest.approx(0.0)
    assert normalize_longitude(0.0) == pytest.approx(0.0)
    assert normalize_longitude(-190.0) == pytest.approx(170.0)


def test_negative_and_large_values():
    assert kelvin_to_celsius(-100.0) == pytest.approx(-373.15)
    assert celsius_to_kelvin(1e6) == pytest.approx(1e6 + 273.15)
    assert knots_to_ms(-5.0) == pytest.approx(-2.57222)
    assert pascal_to_hpa(-100.0) == pytest.approx(-1.0)


def test_none_passthrough():
    assert kelvin_to_celsius(None) is None
    assert celsius_to_kelvin(None) is None
    assert knots_to_ms(None) is None
    assert ms_to_knots(None) is None
    assert pascal_to_hpa(None) is None
    assert hpa_to_pascal(None) is None
    assert normalize_longitude(None) is None
    assert speed_from_uv(None, 1.0) is None
    assert speed_from_uv(1.0, None) is None
    assert direction_from_uv(None, 1.0) is None


def test_nan_passthrough():
    nan = float("nan")
    assert math.isnan(kelvin_to_celsius(nan))
    assert math.isnan(celsius_to_kelvin(nan))
    assert math.isnan(knots_to_ms(nan))
    assert math.isnan(normalize_longitude(nan))
    assert speed_from_uv(nan, 1.0) is None
    assert direction_from_uv(1.0, nan) is None


def test_speed_from_uv():
    assert speed_from_uv(3.0, 4.0) == pytest.approx(5.0)
    assert speed_from_uv(0.0, 0.0) == 0.0
    assert speed_from_uv(-3.0, -4.0) == pytest.approx(5.0)
    assert speed_from_uv(1.0, 0.0) == pytest.approx(1.0)


def test_direction_from_uv_oceanographic():
    # Oceanographic = direction the current flows TO.
    assert direction_from_uv(0.0, 1.0) == pytest.approx(0.0)  # northward
    assert direction_from_uv(1.0, 0.0) == pytest.approx(90.0)  # eastward
    assert direction_from_uv(0.0, -1.0) == pytest.approx(180.0)  # southward
    assert direction_from_uv(-1.0, 0.0) == pytest.approx(270.0)  # westward


def test_direction_from_uv_meteorological():
    # Meteorological = direction the wind comes FROM (heading + 180).
    # Wind blowing eastward (u>0) comes from the west => 270.
    assert direction_from_uv(1.0, 0.0, convention="meteorological") == pytest.approx(270.0)
    # Wind blowing northward comes from the south => 180.
    assert direction_from_uv(0.0, 1.0, convention="meteorological") == pytest.approx(180.0)


def test_direction_from_uv_invalid_convention():
    with pytest.raises(ValueError):
        direction_from_uv(1.0, 1.0, convention="nautical")
