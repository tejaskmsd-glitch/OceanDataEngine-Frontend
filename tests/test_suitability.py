"""Tests for the configurable fishing suitability engine."""

from __future__ import annotations

from marine_data_engine.domain.suitability import (
    SuitabilityWeights,
    assess_fishing_suitability,
)


def test_ideal_conditions_score_high():
    r = assess_fishing_suitability(
        sst=28.0,
        chlorophyll=1.2,
        current_speed=0.5,
        wave_height=0.8,
        wind_speed=5.0,
        pfz_distance_km=5.0,
    )
    assert r.score >= 80.0
    assert r.classification == "EXCELLENT"
    assert any("PFZ" in d for d in r.positive_drivers)


def test_cold_water_far_from_pfz_scores_low():
    r = assess_fishing_suitability(
        sst=18.0,
        chlorophyll=0.05,
        wave_height=2.5,
        wind_speed=12.0,
        pfz_distance_km=200.0,
    )
    assert r.score < 40.0
    assert r.classification in ("POOR", "UNSUITABLE")


def test_ecological_hazard_forces_unsuitable():
    good = assess_fishing_suitability(sst=28.0, chlorophyll=1.0, pfz_distance_km=5.0)
    hazard = assess_fishing_suitability(
        sst=28.0,
        chlorophyll=1.0,
        pfz_distance_km=5.0,
        ecological_hazards=["oil_spill"],
    )
    assert hazard.score < good.score
    assert any("oil_spill" in d for d in hazard.negative_drivers)


def test_confidence_reflects_inputs_present():
    few = assess_fishing_suitability(sst=28.0)
    many = assess_fishing_suitability(
        sst=28.0, chlorophyll=1.0, current_speed=0.4,
        wave_height=0.8, wind_speed=5.0, pfz_distance_km=5.0,
    )
    assert few.confidence < many.confidence
    assert many.confidence == 1.0


def test_weights_are_configurable():
    weights = SuitabilityWeights(sst_ideal_low=10.0, sst_ideal_high=14.0)
    tropical = assess_fishing_suitability(sst=28.0, weights=None)
    cold_pref = assess_fishing_suitability(sst=28.0, weights=weights)
    # With a cold-preferring config, warm SST should score worse.
    assert cold_pref.score < tropical.score


def test_no_inputs_reports_source_gap():
    r = assess_fishing_suitability()
    assert r.score == 0.0
    assert any("SOURCE_GAP" in d for d in r.negative_drivers)
