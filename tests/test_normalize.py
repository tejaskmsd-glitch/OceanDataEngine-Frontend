"""Tests for parameter normalization helpers."""

from __future__ import annotations

import pytest

from marine_data_engine.domain.normalize import (
    normalize_pressure,
    normalize_sst,
    normalize_wave_direction,
    normalize_wind,
)


def test_normalize_sst_kelvin_to_celsius():
    value, unit = normalize_sst(300.0, "K")
    assert unit == "degC"
    assert value == pytest.approx(26.85)
    assert normalize_sst(300.0, "KELVIN")[0] == pytest.approx(26.85)


def test_normalize_sst_celsius_passthrough():
    assert normalize_sst(28.0, "degC") == (28.0, "degC")
    assert normalize_sst(28.0, "C") == (28.0, "degC")


def test_normalize_wind_knots_to_ms():
    value, unit = normalize_wind(10.0, "knots")
    assert unit == "m/s"
    assert value == pytest.approx(5.14444)
    for u in ("kn", "kt", "kts", "KNOTS"):
        assert normalize_wind(10.0, u)[0] == pytest.approx(5.14444)


def test_normalize_wind_ms_passthrough():
    assert normalize_wind(5.0, "m/s") == (5.0, "m/s")


def test_normalize_pressure_pascal_to_hpa():
    value, unit = normalize_pressure(101325.0, "Pa")
    assert unit == "hPa"
    assert value == pytest.approx(1013.25)
    assert normalize_pressure(101325.0, "PASCAL")[0] == pytest.approx(1013.25)


def test_normalize_pressure_hpa_passthrough():
    assert normalize_pressure(1008.0, "hPa") == (1008.0, "hPa")


def test_normalize_wave_direction_unknown_convention():
    assert normalize_wave_direction(200.0, None) == (200.0, "UNKNOWN")
    assert normalize_wave_direction(200.0, "UNKNOWN") == (200.0, "UNKNOWN")


def test_normalize_wave_direction_known_convention_wraps():
    value, convention = normalize_wave_direction(370.0, "meteorological")
    assert convention == "meteorological"
    assert value == pytest.approx(10.0)
