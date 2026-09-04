"""Tests for the safe operating window engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from marine_data_engine.domain.safe_window import compute_safe_windows

_T0 = datetime(2026, 9, 4, 0, 0, tzinfo=UTC)


def _times(n: int, hours: float = 3.0) -> list[datetime]:
    return [_T0 + timedelta(hours=hours * i) for i in range(n)]


def test_calm_series_is_one_favourable_window():
    times = _times(4)
    windows = compute_safe_windows(
        forecast_times=times,
        wave_heights=[0.5, 0.6, 0.5, 0.4],
        wind_speeds=[3.0, 4.0, 3.0, 2.0],
        warnings_active=[],
    )
    assert len(windows) == 1
    assert windows[0].classification == "FAVOURABLE"
    assert windows[0].start == times[0]


def test_deteriorating_series_splits_windows():
    times = _times(4)
    windows = compute_safe_windows(
        forecast_times=times,
        wave_heights=[0.5, 0.6, 5.0, 6.0],
        wind_speeds=[3.0, 4.0, 22.0, 26.0],
        warnings_active=[],
    )
    classes = [w.classification for w in windows]
    assert classes[0] == "FAVOURABLE"
    assert "HIGH_RISK" in classes
    # Whole interval covered: last window ends after last timestamp.
    assert windows[-1].end > times[-1]


def test_warning_overlap_forces_high_risk():
    times = _times(3)
    # Warning covering the middle step even though seas are calm.
    warn = [(times[1], times[1] + timedelta(hours=3))]
    windows = compute_safe_windows(
        forecast_times=times,
        wave_heights=[0.5, 0.5, 0.5],
        wind_speeds=[3.0, 3.0, 3.0],
        warnings_active=warn,
    )
    # The step overlapping the warning must be HIGH_RISK.
    covering = [w for w in windows if w.start <= times[1] < w.end]
    assert covering and covering[0].classification == "HIGH_RISK"


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        compute_safe_windows(
            forecast_times=_times(3),
            wave_heights=[0.5, 0.5],
            wind_speeds=[3.0, 3.0, 3.0],
            warnings_active=[],
        )


def test_empty_series_returns_empty():
    assert compute_safe_windows(
        forecast_times=[], wave_heights=[], wind_speeds=[], warnings_active=[]
    ) == []
