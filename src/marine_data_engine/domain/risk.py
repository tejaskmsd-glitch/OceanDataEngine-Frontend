"""Configurable marine risk engine (prompt.md §10).

Combines environmental forecast/observation factors (waves, swell, wind, gusts,
rainfall, pressure tendency) plus active warnings and cyclone proximity into a
single 0-100 risk score with a categorical level.

Design principles:

- **Deterministic & pure.** No I/O, no clock reads except via explicit inputs.
- **Configurable.** Every threshold lives on :class:`RiskThresholds` and can be
  overridden per vessel type. The default thresholds are conservative,
  general-purpose values and *must be calibrated per fleet/domain*.
- **Explainable.** Every factor records its own proportional contribution so
  the caller can surface the drivers, not just the score.
- **Missing-safe.** ``None`` inputs are skipped (they contribute nothing) rather
  than assumed benign; the returned assessment reflects only observed factors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

# Risk-level cut points on the 0-100 scale.
LEVEL_MODERATE = 25.0
LEVEL_HIGH = 50.0
LEVEL_EXTREME = 75.0

# Flat penalties (points) added for active warnings, keyed by normalized
# severity. Anything unknown gets the MODERATE penalty.
WARNING_SEVERITY_PENALTY: dict[str, float] = {
    "extreme": 45.0,
    "severe": 30.0,
    "moderate": 15.0,
    "minor": 7.0,
    "unknown": 15.0,
}

# Cyclone proximity penalty band (km -> flat penalty points).
CYCLONE_PROXIMITY_BANDS: tuple[tuple[float, float], ...] = (
    (100.0, 60.0),
    (300.0, 40.0),
    (500.0, 20.0),
    (800.0, 8.0),
)


@dataclass
class RiskFactor:
    """A single scored risk contributor."""

    name: str
    value: float | None
    threshold_low: float
    threshold_high: float
    weight: float = 1.0
    contribution: float = 0.0  # computed, 0..(100*weight-ish, pre-normalization)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "threshold_low": self.threshold_low,
            "threshold_high": self.threshold_high,
            "weight": self.weight,
            "contribution": round(self.contribution, 4),
        }


@dataclass
class RiskAssessment:
    """Aggregate marine risk assessment."""

    risk_score: float  # 0-100
    risk_level: str  # LOW|MODERATE|HIGH|EXTREME
    factors: list[RiskFactor]
    warnings: list[str]
    valid_from: datetime | None
    valid_until: datetime | None
    sources: list[dict]

    def as_dict(self) -> dict:
        return {
            "risk_score": round(self.risk_score, 2),
            "risk_level": self.risk_level,
            "factors": [f.as_dict() for f in self.factors],
            "warnings": list(self.warnings),
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "sources": list(self.sources),
        }


@dataclass
class RiskThresholds:
    """Per-vessel-type configurable thresholds.

    ``*_moderate`` is where a factor starts contributing risk (maps to the low
    end of the factor band); ``*_extreme`` maps to a full contribution. All
    values are in canonical units (metres, m/s, seconds, mm, hPa).
    """

    vessel_type: str = "default"

    # Significant wave height (m).
    wave_height_moderate: float = 2.0
    wave_height_high: float = 4.0
    wave_height_extreme: float = 6.0

    # Sustained wind speed (m/s).
    wind_speed_moderate: float = 10.0
    wind_speed_high: float = 17.0
    wind_speed_extreme: float = 25.0

    # Wind gust (m/s).
    gust_moderate: float = 13.0
    gust_high: float = 21.0
    gust_extreme: float = 30.0

    # Swell height (m).
    swell_height_moderate: float = 1.5
    swell_height_high: float = 3.0
    swell_height_extreme: float = 5.0

    # Short, steep seas: wave period below this (s) is hazardous.
    wave_period_min_comfortable: float = 6.0
    wave_period_min_dangerous: float = 3.0

    # Rainfall rate / accumulation proxy (mm) — reduces visibility.
    rainfall_moderate: float = 15.0
    rainfall_high: float = 50.0
    rainfall_extreme: float = 100.0

    # Pressure tendency (hPa over 3h): rapid falls indicate deteriorating wx.
    pressure_drop_moderate: float = 2.0
    pressure_drop_high: float = 4.0
    pressure_drop_extreme: float = 8.0

    # Per-factor weights (relative importance). Calibrate per fleet.
    weight_wave_height: float = 1.4
    weight_wind_speed: float = 1.2
    weight_gust: float = 0.8
    weight_swell: float = 1.0
    weight_wave_period: float = 0.6
    weight_rainfall: float = 0.5
    weight_pressure: float = 0.7


def _classify(score: float) -> str:
    if score >= LEVEL_EXTREME:
        return "EXTREME"
    if score >= LEVEL_HIGH:
        return "HIGH"
    if score >= LEVEL_MODERATE:
        return "MODERATE"
    return "LOW"


def _valid(value: float | None) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))


def _band_fraction(value: float, low: float, high: float) -> float:
    """Return 0..1 for how far ``value`` sits within/above ``[low, high]``.

    Below ``low`` -> 0. At/above ``high`` -> 1. Linear in between. ``high`` is
    treated as the "extreme" ceiling of the factor.
    """
    if high <= low:
        return 1.0 if value >= high else 0.0
    if value <= low:
        return 0.0
    if value >= high:
        return 1.0
    return (value - low) / (high - low)


def _inverse_band_fraction(value: float, comfortable: float, dangerous: float) -> float:
    """Like :func:`_band_fraction` but for "lower is worse" factors.

    At/above ``comfortable`` -> 0. At/below ``dangerous`` -> 1.
    """
    if comfortable <= dangerous:
        return 1.0 if value <= dangerous else 0.0
    if value >= comfortable:
        return 0.0
    if value <= dangerous:
        return 1.0
    return (comfortable - value) / (comfortable - dangerous)


def assess_marine_risk(
    *,
    wave_height: float | None = None,
    wave_period: float | None = None,
    swell_height: float | None = None,
    wind_speed: float | None = None,
    wind_gust: float | None = None,
    rainfall: float | None = None,
    pressure: float | None = None,
    pressure_trend: float | None = None,
    active_warnings: list[dict] | None = None,
    cyclone_distance_km: float | None = None,
    thresholds: RiskThresholds | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    sources: list[dict] | None = None,
) -> RiskAssessment:
    """Assess marine risk from available environmental factors and hazards.

    Each numeric factor contributes ``band_fraction * 100 * weight`` points; the
    weighted mean of contributing factors forms the environmental base score.
    Active warnings and cyclone proximity add flat penalties on top (capped at
    100). Factors whose inputs are ``None``/``NaN`` are skipped.

    ``pressure_trend`` is the pressure change (hPa) over the reporting window;
    negative values (falling pressure) drive risk. ``pressure`` alone is
    informational and does not score.
    """
    t = thresholds or RiskThresholds()
    factors: list[RiskFactor] = []
    warnings: list[str] = []

    def add_factor(
        name: str,
        value: float | None,
        low: float,
        high: float,
        weight: float,
        *,
        inverse: bool = False,
        danger: float | None = None,
    ) -> None:
        if not _valid(value):
            return
        if inverse and danger is not None:
            frac = _inverse_band_fraction(value, low, danger)
            fac = RiskFactor(name, value, danger, low, weight)
        else:
            frac = _band_fraction(value, low, high)
            fac = RiskFactor(name, value, low, high, weight)
        fac.contribution = frac * 100.0 * weight
        factors.append(fac)

    add_factor("wave_height", wave_height, t.wave_height_moderate,
               t.wave_height_extreme, t.weight_wave_height)
    add_factor("wind_speed", wind_speed, t.wind_speed_moderate,
               t.wind_speed_extreme, t.weight_wind_speed)
    add_factor("wind_gust", wind_gust, t.gust_moderate,
               t.gust_extreme, t.weight_gust)
    add_factor("swell_height", swell_height, t.swell_height_moderate,
               t.swell_height_extreme, t.weight_swell)
    add_factor("wave_period", wave_period, t.wave_period_min_comfortable,
               t.wave_period_min_comfortable, t.weight_wave_period,
               inverse=True, danger=t.wave_period_min_dangerous)
    add_factor("rainfall", rainfall, t.rainfall_moderate,
               t.rainfall_extreme, t.weight_rainfall)

    # Pressure tendency: use the magnitude of a *falling* trend.
    if _valid(pressure_trend) and pressure_trend < 0:
        drop = abs(pressure_trend)
        frac = _band_fraction(drop, t.pressure_drop_moderate, t.pressure_drop_extreme)
        fac = RiskFactor("pressure_trend", pressure_trend,
                         -t.pressure_drop_moderate, -t.pressure_drop_extreme,
                         t.weight_pressure)
        fac.contribution = frac * 100.0 * t.weight_pressure
        factors.append(fac)

    # Weighted mean of environmental factors -> base score (0..100).
    if factors:
        total_weight = sum(f.weight for f in factors)
        base = sum(f.contribution for f in factors) / total_weight if total_weight else 0.0
    else:
        base = 0.0
        warnings.append("SOURCE_GAP: no environmental factors supplied; score is warning-only")

    score = base

    # Flat penalties for active warnings.
    for w in active_warnings or []:
        severity = str(w.get("severity", "unknown")).lower()
        penalty = WARNING_SEVERITY_PENALTY.get(severity, WARNING_SEVERITY_PENALTY["unknown"])
        score += penalty
        label = w.get("event_type") or w.get("headline") or "warning"
        warnings.append(f"active warning ({severity}): {label} [+{penalty:g}]")

    # Cyclone proximity penalty (nearest matching band).
    if _valid(cyclone_distance_km):
        for radius, penalty in CYCLONE_PROXIMITY_BANDS:
            if cyclone_distance_km <= radius:
                score += penalty
                warnings.append(
                    f"cyclone within {cyclone_distance_km:g} km (<= {radius:g}) [+{penalty:g}]"
                )
                break

    score = max(0.0, min(100.0, score))
    level = _classify(score)

    # Highlight dominant environmental drivers.
    for f in sorted(factors, key=lambda x: x.contribution, reverse=True):
        if f.contribution >= 25.0:
            warnings.append(f"driver: {f.name} = {f.value:g}")

    return RiskAssessment(
        risk_score=score,
        risk_level=level,
        factors=factors,
        warnings=warnings,
        valid_from=valid_from,
        valid_until=valid_until,
        sources=sources or [],
    )
