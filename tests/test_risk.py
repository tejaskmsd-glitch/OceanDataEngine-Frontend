"""Tests for the configurable marine risk engine."""

from __future__ import annotations

from datetime import UTC, datetime

from marine_data_engine.domain.risk import (
    RiskThresholds,
    assess_marine_risk,
)


def test_calm_conditions_are_low_risk():
    a = assess_marine_risk(wave_height=0.5, wind_speed=3.0, swell_height=0.5)
    assert a.risk_level == "LOW"
    assert a.risk_score < 25.0


def test_severe_seas_escalate_score():
    calm = assess_marine_risk(wave_height=1.0, wind_speed=5.0)
    rough = assess_marine_risk(wave_height=5.5, wind_speed=24.0, wind_gust=29.0)
    assert rough.risk_score > calm.risk_score
    assert rough.risk_level in ("HIGH", "EXTREME")


def test_extreme_wave_and_wind_is_extreme():
    a = assess_marine_risk(wave_height=6.5, wind_speed=26.0, wind_gust=31.0)
    assert a.risk_level == "EXTREME"
    assert a.risk_score >= 75.0


def test_active_warning_adds_flat_penalty():
    base = assess_marine_risk(wave_height=1.0, wind_speed=5.0)
    with_warning = assess_marine_risk(
        wave_height=1.0,
        wind_speed=5.0,
        active_warnings=[{"severity": "severe", "event_type": "cyclone_warning"}],
    )
    assert with_warning.risk_score == base.risk_score + 30.0
    assert any("cyclone_warning" in w for w in with_warning.warnings)


def test_thresholds_are_configurable():
    strict = RiskThresholds(
        vessel_type="small_craft",
        wave_height_moderate=0.5,
        wave_height_high=1.0,
        wave_height_extreme=2.0,
    )
    default_a = assess_marine_risk(wave_height=2.0)
    strict_a = assess_marine_risk(wave_height=2.0, thresholds=strict)
    assert strict_a.risk_score > default_a.risk_score


def test_no_inputs_reports_source_gap():
    a = assess_marine_risk()
    assert a.risk_score == 0.0
    assert any("SOURCE_GAP" in w for w in a.warnings)


def test_valid_window_and_sources_passthrough():
    vf = datetime(2026, 9, 4, 0, 0, tzinfo=UTC)
    vu = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
    a = assess_marine_risk(
        wave_height=1.0, valid_from=vf, valid_until=vu, sources=[{"provider": "INCOIS"}]
    )
    d = a.as_dict()
    assert d["valid_from"] == vf.isoformat()
    assert d["sources"] == [{"provider": "INCOIS"}]
