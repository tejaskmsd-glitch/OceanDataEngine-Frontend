"""Safe operating window engine (prompt.md §12).

Given a time-ordered forecast series (wave heights, wind speeds) and any active
warning intervals, classify each forecast step into a :class:`TimeWindow` and
merge consecutive steps of the same classification into contiguous windows.

Per prompt §12, the classification must reflect the **entire window**, not just
its opening timestamp: a window is only FAVOURABLE if conditions stay favourable
across every sampled step it covers, and any warning overlapping the window
degrades it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .risk import RiskThresholds, assess_marine_risk

# Score cut points for window classification (share the risk 0-100 scale).
FAVOURABLE_MAX = 25.0
MODERATE_MAX = 50.0


@dataclass
class TimeWindow:
    """A contiguous forecast window with a single classification."""

    start: datetime
    end: datetime
    classification: str  # FAVOURABLE|MODERATE|HIGH_RISK
    risk_score: float
    conditions_summary: dict

    def as_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "classification": self.classification,
            "risk_score": round(self.risk_score, 2),
            "conditions_summary": self.conditions_summary,
        }


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _classify_score(score: float) -> str:
    if score <= FAVOURABLE_MAX:
        return "FAVOURABLE"
    if score <= MODERATE_MAX:
        return "MODERATE"
    return "HIGH_RISK"


def _warning_overlaps(start: datetime, end: datetime,
                      warnings_active: list[tuple[datetime, datetime]]) -> bool:
    for vf, vu in warnings_active:
        wf = _as_utc(vf)
        wu = _as_utc(vu)
        # Overlap if the step interval [start, end) intersects [wf, wu].
        if start <= wu and end >= wf:
            return True
    return False


def compute_safe_windows(
    *,
    forecast_times: list[datetime],
    wave_heights: list[float | None],
    wind_speeds: list[float | None],
    warnings_active: list[tuple[datetime, datetime]],
    thresholds: RiskThresholds | None = None,
    interval_hours: float = 3.0,
) -> list[TimeWindow]:
    """Classify each forecast step and merge like-classified steps into windows.

    Each step spans ``[forecast_times[i], forecast_times[i] + interval_hours)``
    (or up to the next timestamp if that is sooner). The step is scored with the
    marine risk engine using its wave/wind values; a warning overlapping the
    step forces at least HIGH_RISK. Consecutive steps that share a classification
    are merged so the returned windows cover the whole interval.

    Raises ``ValueError`` if the input series lengths disagree.
    """
    n = len(forecast_times)
    if not (len(wave_heights) == n and len(wind_speeds) == n):
        raise ValueError("forecast_times, wave_heights, wind_speeds must be equal length")
    if n == 0:
        return []

    thresholds = thresholds or RiskThresholds()
    warnings_active = warnings_active or []
    step = timedelta(hours=interval_hours)

    # Score each step individually first.
    steps: list[TimeWindow] = []
    for i in range(n):
        start = _as_utc(forecast_times[i])
        # Step end: either fixed interval or the next timestamp, whichever first.
        end = start + step
        if i + 1 < n:
            nxt = _as_utc(forecast_times[i + 1])
            if nxt > start:
                end = min(end, nxt)

        wave = wave_heights[i]
        wind = wind_speeds[i]
        assessment = assess_marine_risk(
            wave_height=wave,
            wind_speed=wind,
            thresholds=thresholds,
            valid_from=start,
            valid_until=end,
        )
        score = assessment.risk_score

        overlapping = _warning_overlaps(start, end, warnings_active)
        if overlapping:
            # A warning covering the window degrades it to at least HIGH_RISK.
            score = max(score, MODERATE_MAX + 25.0)

        classification = _classify_score(score)
        summary = {
            "wave_height": wave,
            "wind_speed": wind,
            "warning_active": overlapping,
        }
        steps.append(TimeWindow(start, end, classification, score, summary))

    # Merge consecutive steps that share a classification.
    merged: list[TimeWindow] = []
    for s in steps:
        if merged and merged[-1].classification == s.classification and \
                merged[-1].end >= s.start:
            prev = merged[-1]
            prev.end = s.end
            prev.risk_score = max(prev.risk_score, s.risk_score)
            # Summarize the worst conditions across the merged span.
            prev.conditions_summary = {
                "wave_height_max": _max_opt(
                    prev.conditions_summary.get("wave_height_max",
                                                prev.conditions_summary.get("wave_height")),
                    s.conditions_summary.get("wave_height"),
                ),
                "wind_speed_max": _max_opt(
                    prev.conditions_summary.get("wind_speed_max",
                                                prev.conditions_summary.get("wind_speed")),
                    s.conditions_summary.get("wind_speed"),
                ),
                "warning_active": bool(
                    prev.conditions_summary.get("warning_active")
                    or s.conditions_summary.get("warning_active")
                ),
            }
        else:
            merged.append(s)
    return merged


def _max_opt(a: float | None, b: float | None) -> float | None:
    vals = [v for v in (a, b) if v is not None]
    return max(vals) if vals else None
