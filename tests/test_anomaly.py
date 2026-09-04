"""Tests for anomaly computation."""

from __future__ import annotations

from marine_data_engine.domain.anomaly import (
    compute_anomaly,
    compute_chlorophyll_anomaly,
    compute_sst_anomaly,
)


def test_generic_anomaly_zscore_and_percentile():
    r = compute_anomaly(12.0, 10.0, std=1.0)
    assert r.anomaly == 2.0
    assert r.classification == "HIGH_EXTREME"  # z = 2.0
    assert r.percentile is not None and r.percentile > 97.0


def test_generic_anomaly_without_std():
    r = compute_anomaly(9.0, 10.0)
    assert r.anomaly == -1.0
    assert r.classification == "LOW"
    assert r.percentile is None


def test_sst_anomaly_warm_and_cold_absolute():
    warm = compute_sst_anomaly(30.0, 28.0)
    cold = compute_sst_anomaly(26.5, 28.0)
    normal = compute_sst_anomaly(28.2, 28.0)
    assert warm.classification == "WARM"
    assert cold.classification == "COLD"
    assert normal.classification == "NORMAL"


def test_sst_anomaly_zscore_labels():
    r = compute_sst_anomaly(31.0, 28.0, baseline_std=1.0)  # z = 3
    assert r.classification == "WARM_EXTREME"


def test_chlorophyll_anomaly_relative():
    high = compute_chlorophyll_anomaly(0.6, 0.3)  # +100%
    low = compute_chlorophyll_anomaly(0.18, 0.3)  # -40%
    normal = compute_chlorophyll_anomaly(0.32, 0.3)
    assert high.classification == "HIGH"
    assert low.classification == "LOW"
    assert normal.classification == "NORMAL"
