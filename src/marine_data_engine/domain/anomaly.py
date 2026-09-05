"""Anomaly computation.

Compares a current value against a configurable climatological baseline and,
when a standard deviation is supplied, expresses the departure as a z-score and
approximate percentile.

BASELINE PROVENANCE: the baseline mean/std are inputs, not constants. Real
climatological baselines must be accumulated over a multi-year record per
parameter, location, and season. The defaults used by callers are provisional
and must be replaced with observed climatology before operational use.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# z-score magnitude at which a departure is called an anomaly.
_Z_MODERATE = 1.0
_Z_STRONG = 2.0

# Fallback absolute thresholds (used when no std is provided).
_SST_ABS_WARM = 1.0  # deg C above baseline
_SST_ABS_COOL = -1.0
_CHL_REL_HIGH = 0.5  # +50% of baseline
_CHL_REL_LOW = -0.3  # -30% of baseline


@dataclass
class AnomalyResult:
    """Result of an anomaly computation."""

    current_value: float
    baseline_value: float
    anomaly: float
    percentile: float | None
    classification: str  # NORMAL|WARM|COLD|HIGH|LOW (+ *_EXTREME variants)

    def as_dict(self) -> dict:
        return {
            "current_value": self.current_value,
            "baseline_value": self.baseline_value,
            "anomaly": round(self.anomaly, 6),
            "percentile": (round(self.percentile, 3) if self.percentile is not None else None),
            "classification": self.classification,
        }


def _normal_cdf(z: float) -> float:
    """Standard-normal CDF via the error function (0..1)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def compute_anomaly(current: float, baseline: float, std: float | None = None) -> AnomalyResult:
    """Compute a generic anomaly (``current - baseline``).

    When ``std`` is a positive number, the percentile is derived from the
    z-score against a normal climatology and the classification uses z-score
    bands (HIGH/LOW, with ``*_EXTREME`` past 2 sigma). Without ``std`` the
    result carries the raw anomaly and a NORMAL/HIGH/LOW label based on sign.
    """
    anomaly = current - baseline
    percentile: float | None = None

    if std is not None and std > 0 and not (isinstance(std, float) and math.isnan(std)):
        z = anomaly / std
        percentile = round(_normal_cdf(z) * 100.0, 3)
        if z >= _Z_STRONG:
            classification = "HIGH_EXTREME"
        elif z >= _Z_MODERATE:
            classification = "HIGH"
        elif z <= -_Z_STRONG:
            classification = "LOW_EXTREME"
        elif z <= -_Z_MODERATE:
            classification = "LOW"
        else:
            classification = "NORMAL"
    else:
        if anomaly > 0:
            classification = "HIGH"
        elif anomaly < 0:
            classification = "LOW"
        else:
            classification = "NORMAL"

    return AnomalyResult(
        current_value=current,
        baseline_value=baseline,
        anomaly=anomaly,
        percentile=percentile,
        classification=classification,
    )


def compute_sst_anomaly(
    sst: float, baseline_sst: float, baseline_std: float | None = None
) -> AnomalyResult:
    """SST anomaly with WARM/COLD labelling.

    Uses z-score bands when ``baseline_std`` is provided; otherwise falls back to
    absolute departure thresholds (``>= +1C`` WARM, ``<= -1C`` COLD).
    """
    result = compute_anomaly(sst, baseline_sst, baseline_std)
    if baseline_std is not None and baseline_std > 0:
        mapping = {
            "HIGH_EXTREME": "WARM_EXTREME",
            "HIGH": "WARM",
            "LOW_EXTREME": "COLD_EXTREME",
            "LOW": "COLD",
            "NORMAL": "NORMAL",
        }
        result.classification = mapping[result.classification]
    else:
        if result.anomaly >= _SST_ABS_WARM:
            result.classification = "WARM"
        elif result.anomaly <= _SST_ABS_COOL:
            result.classification = "COLD"
        else:
            result.classification = "NORMAL"
    return result


def compute_chlorophyll_anomaly(
    chl: float, baseline_chl: float, baseline_std: float | None = None
) -> AnomalyResult:
    """Chlorophyll anomaly with HIGH/LOW (bloom/oligotrophic) labelling.

    Uses z-score bands when ``baseline_std`` is provided; otherwise falls back to
    a relative departure from the baseline (``>= +50%`` HIGH, ``<= -30%`` LOW).
    """
    result = compute_anomaly(chl, baseline_chl, baseline_std)
    if baseline_std is not None and baseline_std > 0:
        return result  # HIGH/LOW/*_EXTREME/NORMAL already meaningful
    if baseline_chl > 0:
        rel = result.anomaly / baseline_chl
        if rel >= _CHL_REL_HIGH:
            result.classification = "HIGH"
        elif rel <= _CHL_REL_LOW:
            result.classification = "LOW"
        else:
            result.classification = "NORMAL"
    return result


# --------------------------------------------------------------------------- #
# Multi-parameter synthesis (Marine Heatwave detection + combined impact)
# --------------------------------------------------------------------------- #

# Marine Heatwave categories by SST anomaly magnitude (deg C above baseline),
# after Hobday et al. style banding (provisional; calibrate per region/season).
_MHW_CATEGORIES: tuple[tuple[float, str], ...] = (
    (4.0, "IV_EXTREME"),
    (3.0, "III_SEVERE"),
    (2.0, "II_STRONG"),
    (1.0, "I_MODERATE"),
)


def _mhw_category(sst_anomaly: float) -> str | None:
    """Return the MHW category label for a positive SST anomaly, else None."""
    for threshold, label in _MHW_CATEGORIES:
        if sst_anomaly >= threshold:
            return label
    return None


@dataclass
class AnomalyDetectionSummary:
    """Aggregate multi-parameter anomaly synthesis.

    Wraps per-parameter :class:`AnomalyResult` values and derives higher-level
    findings — Marine Heatwave (MHW) category from the SST anomaly and a plain
    list of human-readable drivers — plus an overall status.
    """

    anomalies: dict[str, AnomalyResult]
    drivers: list[str]
    mhw_detected: bool
    mhw_category: str | None
    status: str  # NORMAL | ANOMALY_DETECTED

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "mhw_detected": self.mhw_detected,
            "mhw_category": self.mhw_category,
            "drivers": list(self.drivers),
            "anomalies": {k: v.as_dict() for k, v in self.anomalies.items()},
        }


def detect_anomalies(
    current_values: dict[str, float],
    baselines: dict[str, float],
    stds: dict[str, float] | None = None,
) -> AnomalyDetectionSummary:
    """Analyze multi-parameter departures against climatological baselines.

    Detects extreme events such as Marine Heatwaves (MHW) and oligotrophic
    chlorophyll depletion, synthesizing their combined impact on fisheries
    productivity. Only parameters present in BOTH ``current_values`` and
    ``baselines`` are evaluated; unknown parameters use the generic anomaly.
    """
    stds = stds or {}
    anomalies: dict[str, AnomalyResult] = {}
    drivers: list[str] = []
    mhw_detected = False
    mhw_category: str | None = None

    for param, current in current_values.items():
        if param not in baselines:
            continue
        baseline = baselines[param]
        std = stds.get(param)

        if param == "sst":
            res = compute_sst_anomaly(current, baseline, std)
            if res.anomaly > 0:
                cat = _mhw_category(res.anomaly)
                if cat is not None:
                    mhw_detected = True
                    mhw_category = cat
                    drivers.append(
                        f"Marine Heatwave (category {cat}): SST "
                        f"{res.anomaly:+.2f} degC vs baseline"
                    )
            if res.classification not in ("NORMAL",):
                drivers.append(f"SST {res.classification} ({res.anomaly:+.2f} degC)")
        elif param in ("chlorophyll", "chlorophyll_a", "chl"):
            res = compute_chlorophyll_anomaly(current, baseline, std)
            if res.classification == "LOW":
                drivers.append(
                    "Oligotrophic depletion: chlorophyll below baseline "
                    "(reduced productivity)"
                )
            elif res.classification not in ("NORMAL",):
                drivers.append(f"Chlorophyll {res.classification} ({res.anomaly:+.4f})")
        else:
            res = compute_anomaly(current, baseline, std)
            if res.classification not in ("NORMAL",):
                drivers.append(f"{param} {res.classification} ({res.anomaly:+.4f})")

        anomalies[param] = res

    status = "ANOMALY_DETECTED" if drivers else "NORMAL"
    return AnomalyDetectionSummary(
        anomalies=anomalies,
        drivers=drivers,
        mhw_detected=mhw_detected,
        mhw_category=mhw_category,
        status=status,
    )
