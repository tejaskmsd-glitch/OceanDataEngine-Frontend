"""Configurable fishing suitability engine (prompt.md §11).

Scores how suitable a location is for fishing by combining oceanographic
productivity signals (sea-surface temperature, chlorophyll-a and their
anomalies, currents), operational safety (waves, wind), and proximity to an
official Potential Fishing Zone (PFZ) advisory. Ecological hazards and fishery
advisories can veto or penalize an otherwise favourable location.

IMPORTANT: the default weights and preferred ranges are general tropical
(Indian-Ocean-oriented) heuristics. They are **not** a validated stock model
and **must be calibrated** against catch data / domain expertise before
operational use. All weights and ranges are configurable via
:class:`SuitabilityWeights`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SuitabilityWeights:
    """Configurable weights and preferred ranges. Calibrate per fishery/region."""

    # Preferred SST band (deg C) for tropical pelagic species.
    sst_ideal_low: float = 26.0
    sst_ideal_high: float = 30.0
    sst_tolerance: float = 4.0  # deg C beyond the band before score -> 0

    # Chlorophyll-a (mg/m^3): higher productivity is better up to a bloom cap.
    chl_good: float = 0.3
    chl_excellent: float = 1.0
    chl_bloom_cap: float = 20.0  # HAB-scale; above this productivity is a hazard

    # Currents (m/s): moderate convergence is good; very strong is unfishable.
    current_ideal: float = 0.5
    current_max: float = 1.5

    # Safety ceilings (waves m, wind m/s) beyond which suitability collapses.
    wave_comfortable: float = 1.5
    wave_max: float = 3.0
    wind_comfortable: float = 8.0
    wind_max: float = 15.0

    # PFZ proximity (km): within this distance is a strong positive driver.
    pfz_near_km: float = 25.0
    pfz_far_km: float = 100.0

    # Component weights (relative importance).
    weight_sst: float = 1.2
    weight_chlorophyll: float = 1.3
    weight_anomaly: float = 0.6
    weight_current: float = 0.7
    weight_pfz: float = 1.5
    weight_safety: float = 1.0


@dataclass
class SuitabilityResult:
    """Fishing suitability outcome."""

    score: float  # 0-100
    classification: str  # EXCELLENT|GOOD|MODERATE|POOR|UNSUITABLE
    positive_drivers: list[str]
    negative_drivers: list[str]
    confidence: float | None
    sources: list[dict]

    def as_dict(self) -> dict:
        return {
            "score": round(self.score, 2),
            "classification": self.classification,
            "positive_drivers": list(self.positive_drivers),
            "negative_drivers": list(self.negative_drivers),
            "confidence": self.confidence,
            "sources": list(self.sources),
        }


def _valid(value: float | None) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))


def _classify(score: float) -> str:
    if score >= 80.0:
        return "EXCELLENT"
    if score >= 60.0:
        return "GOOD"
    if score >= 40.0:
        return "MODERATE"
    if score >= 20.0:
        return "POOR"
    return "UNSUITABLE"


def _sst_score(sst: float, w: SuitabilityWeights) -> float:
    """1.0 inside the ideal band, decaying linearly to 0 at +/- tolerance."""
    if w.sst_ideal_low <= sst <= w.sst_ideal_high:
        return 1.0
    dist = w.sst_ideal_low - sst if sst < w.sst_ideal_low else sst - w.sst_ideal_high
    if w.sst_tolerance <= 0:
        return 0.0
    return max(0.0, 1.0 - dist / w.sst_tolerance)


def _chl_score(chl: float, w: SuitabilityWeights) -> float:
    """Ramp up from 0 at chl=0 to 1.0 at ``chl_excellent``; penalize blooms."""
    if chl >= w.chl_bloom_cap:
        return 0.0
    if chl <= 0:
        return 0.0
    if chl >= w.chl_excellent:
        # Gentle taper toward the bloom cap.
        span = max(1e-6, w.chl_bloom_cap - w.chl_excellent)
        return max(0.3, 1.0 - 0.7 * (chl - w.chl_excellent) / span)
    if chl >= w.chl_good:
        span = max(1e-6, w.chl_excellent - w.chl_good)
        return 0.6 + 0.4 * (chl - w.chl_good) / span
    return 0.6 * (chl / max(1e-6, w.chl_good))


def _current_score(speed: float, w: SuitabilityWeights) -> float:
    """Peak at ``current_ideal``; 0 at rest and at/above ``current_max``."""
    if speed <= 0:
        return 0.3
    if speed >= w.current_max:
        return 0.0
    if speed <= w.current_ideal:
        return 0.3 + 0.7 * (speed / max(1e-6, w.current_ideal))
    span = max(1e-6, w.current_max - w.current_ideal)
    return max(0.0, 1.0 - (speed - w.current_ideal) / span)


def _safety_score(wave: float | None, wind: float | None, w: SuitabilityWeights) -> float | None:
    """Fraction of comfortable operating conditions (1.0 calm, 0.0 unsafe)."""
    parts: list[float] = []
    if _valid(wave):
        if wave <= w.wave_comfortable:
            parts.append(1.0)
        elif wave >= w.wave_max:
            parts.append(0.0)
        else:
            parts.append(1.0 - (wave - w.wave_comfortable) / (w.wave_max - w.wave_comfortable))
    if _valid(wind):
        if wind <= w.wind_comfortable:
            parts.append(1.0)
        elif wind >= w.wind_max:
            parts.append(0.0)
        else:
            parts.append(1.0 - (wind - w.wind_comfortable) / (w.wind_max - w.wind_comfortable))
    if not parts:
        return None
    return min(parts)  # the worst safety factor governs


def _pfz_score(distance_km: float, w: SuitabilityWeights) -> float:
    if distance_km <= w.pfz_near_km:
        return 1.0
    if distance_km >= w.pfz_far_km:
        return 0.0
    return 1.0 - (distance_km - w.pfz_near_km) / (w.pfz_far_km - w.pfz_near_km)


def assess_fishing_suitability(
    *,
    sst: float | None = None,
    chlorophyll: float | None = None,
    sst_anomaly: float | None = None,
    chlorophyll_anomaly: float | None = None,
    current_speed: float | None = None,
    wave_height: float | None = None,
    wind_speed: float | None = None,
    pfz_distance_km: float | None = None,
    ecological_hazards: list[str] | None = None,
    fishery_advisories: list[str] | None = None,
    weights: SuitabilityWeights | None = None,
    sources: list[dict] | None = None,
) -> SuitabilityResult:
    """Assess fishing suitability from oceanographic + safety inputs.

    Returns a 0-100 score. Each available component produces a 0..1 sub-score
    multiplied by its weight; the weighted mean forms the base score. Ecological
    hazards (HAB, oil spill, jellyfish bloom, coral bleaching) apply strong flat
    penalties and can drive the location to UNSUITABLE. ``confidence`` reflects
    how many of the productivity/safety inputs were actually present.
    """
    w = weights or SuitabilityWeights()
    positives: list[str] = []
    negatives: list[str] = []

    # (sub_score 0..1, weight, name)
    components: list[tuple[float, float, str]] = []

    if _valid(sst):
        s = _sst_score(sst, w)
        components.append((s, w.weight_sst, "sst"))
        if s >= 0.9:
            positives.append(f"SST {sst:g}C in ideal band")
        elif s <= 0.2:
            negatives.append(f"SST {sst:g}C outside preferred band")

    if _valid(chlorophyll):
        s = _chl_score(chlorophyll, w)
        components.append((s, w.weight_chlorophyll, "chlorophyll"))
        if chlorophyll >= w.chl_bloom_cap:
            negatives.append(f"chlorophyll {chlorophyll:g} at bloom/HAB scale")
        elif s >= 0.8:
            positives.append(f"high productivity (chl {chlorophyll:g} mg/m^3)")
        elif s <= 0.3:
            negatives.append(f"low productivity (chl {chlorophyll:g} mg/m^3)")

    # Anomalies: positive chlorophyll anomaly and mild warm SST anomaly favour
    # aggregation fronts; large anomalies are treated as neutral-to-negative.
    anom_parts: list[float] = []
    if _valid(chlorophyll_anomaly):
        if chlorophyll_anomaly > 0:
            anom_parts.append(min(1.0, 0.5 + chlorophyll_anomaly))
            positives.append(f"positive chlorophyll anomaly (+{chlorophyll_anomaly:g})")
        else:
            anom_parts.append(max(0.0, 0.5 + chlorophyll_anomaly))
    if _valid(sst_anomaly):
        # Small anomalies best; large magnitude reduces the sub-score.
        anom_parts.append(max(0.0, 1.0 - abs(sst_anomaly) / 3.0))
        if abs(sst_anomaly) >= 2.0:
            negatives.append(f"large SST anomaly ({sst_anomaly:+g}C)")
    if anom_parts:
        components.append((sum(anom_parts) / len(anom_parts), w.weight_anomaly, "anomaly"))

    if _valid(current_speed):
        s = _current_score(current_speed, w)
        components.append((s, w.weight_current, "current"))
        if current_speed >= w.current_max:
            negatives.append(f"strong current ({current_speed:g} m/s)")

    if _valid(pfz_distance_km):
        s = _pfz_score(pfz_distance_km, w)
        components.append((s, w.weight_pfz, "pfz"))
        if s >= 0.9:
            positives.append(f"within/near PFZ advisory ({pfz_distance_km:g} km)")
        elif s <= 0.1:
            negatives.append(f"far from any PFZ ({pfz_distance_km:g} km)")

    safety = _safety_score(wave_height, wind_speed, w)
    if safety is not None:
        components.append((safety, w.weight_safety, "safety"))
        if safety <= 0.2:
            negatives.append("unsafe sea/wind conditions")
        elif safety >= 0.9:
            positives.append("calm operating conditions")

    if components:
        total_w = sum(c[1] for c in components)
        base = 100.0 * sum(c[0] * c[1] for c in components) / total_w if total_w else 0.0
    else:
        base = 0.0
        negatives.append("SOURCE_GAP: no oceanographic/safety inputs supplied")

    score = base

    # Ecological hazards: strong flat penalties (can force UNSUITABLE).
    hazard_penalty = {
        "hab": 60.0,
        "harmful_algal_bloom": 60.0,
        "oil_spill": 80.0,
        "jellyfish_bloom": 25.0,
        "coral_bleaching": 15.0,
    }
    for hz in ecological_hazards or []:
        key = str(hz).lower().replace(" ", "_")
        pen = hazard_penalty.get(key, 20.0)
        score -= pen
        negatives.append(f"ecological hazard: {hz} [-{pen:g}]")

    # Fishery advisories (e.g. closed season, ban) apply a firm penalty.
    for adv in fishery_advisories or []:
        score -= 30.0
        negatives.append(f"fishery advisory in effect: {adv} [-30]")

    score = max(0.0, min(100.0, score))
    classification = _classify(score)

    # Confidence: fraction of the six primary inputs present.
    primary_present = sum(
        1 for v in (sst, chlorophyll, current_speed, wave_height, wind_speed, pfz_distance_km)
        if _valid(v)
    )
    confidence = round(primary_present / 6.0, 3) if primary_present else 0.0

    return SuitabilityResult(
        score=score,
        classification=classification,
        positive_drivers=positives,
        negative_drivers=negatives,
        confidence=confidence,
        sources=sources or [],
    )
