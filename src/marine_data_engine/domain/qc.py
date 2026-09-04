"""Quality-control engine.

Implements the pipeline described in the requirements: schema validation,
physical-range validation, temporal consistency, spatial consistency, and
quality scoring, producing an accepted/rejected/quarantined disposition.

Suspicious records are never silently discarded — every evaluation yields a
:class:`QCResult` with per-check outcomes and a reason, suitable for a
``DataQualityRecord`` audit row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..db.enums import QCStatus

# Physical plausibility ranges per canonical parameter (from source_mapping §7).
PHYSICAL_RANGES: dict[str, tuple[float, float]] = {
    "sea_surface_temperature": (-2.0, 40.0),
    "chlorophyll_a": (0.0, 100.0),
    "current_u": (-5.0, 5.0),
    "current_v": (-5.0, 5.0),
    "current_speed": (0.0, 10.0),
    "significant_wave_height": (0.0, 30.0),
    "wave_period": (0.0, 30.0),
    "wave_direction": (0.0, 360.0),
    "swell_height": (0.0, 30.0),
    "sea_surface_salinity": (0.0, 45.0),
    "wind_speed": (0.0, 120.0),
    "wind_direction": (0.0, 360.0),
    "wind_u": (-90.0, 90.0),
    "wind_v": (-90.0, 90.0),
    "gust_speed": (0.0, 120.0),
    "rainfall_rate": (0.0, 500.0),
    "rainfall_accumulation": (0.0, 2000.0),
    "sea_level_pressure": (850.0, 1085.0),
    "station_pressure": (500.0, 1085.0),
    "humidity": (0.0, 100.0),
    "water_level": (-15.0, 15.0),
}


@dataclass
class QCCheck:
    """One QC check outcome."""

    name: str
    passed: bool
    detail: str | None = None

    def as_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class QCResult:
    """Aggregate QC result for one record."""

    status: QCStatus
    score: float
    checks: list[QCCheck] = field(default_factory=list)
    reason: str | None = None
    missing_flag: bool = False
    outlier_flag: bool = False
    interpolated_flag: bool = False

    def as_dict(self) -> dict:
        return {
            "status": self.status.value,
            "score": self.score,
            "checks": [c.as_dict() for c in self.checks],
            "reason": self.reason,
            "missing_flag": self.missing_flag,
            "outlier_flag": self.outlier_flag,
            "interpolated_flag": self.interpolated_flag,
        }


def _valid_lat(lat: float | None) -> bool:
    return lat is not None and -90.0 <= lat <= 90.0


def _valid_lon(lon: float | None) -> bool:
    return lon is not None and -180.0 <= lon <= 180.0


def qc_observation(
    *,
    parameter: str,
    value: float | None,
    latitude: float | None,
    longitude: float | None,
    observed_at: datetime | None,
    now: datetime | None = None,
    interpolated: bool = False,
) -> QCResult:
    """Run QC on a scalar observation/forecast value."""
    now = now or datetime.now(tz=UTC)
    checks: list[QCCheck] = []
    missing = value is None
    outlier = False

    # Schema / presence.
    checks.append(QCCheck("schema", parameter is not None and parameter != "", None))

    # Missing value handling.
    if missing:
        checks.append(QCCheck("value_present", False, "value is null"))
    else:
        checks.append(QCCheck("value_present", True))

        # Physical range check.
        rng = PHYSICAL_RANGES.get(parameter)
        if rng is not None:
            lo, hi = rng
            in_range = lo <= value <= hi
            outlier = not in_range
            checks.append(
                QCCheck(
                    "physical_range",
                    in_range,
                    None if in_range else f"{value} outside [{lo}, {hi}]",
                )
            )
        else:
            checks.append(QCCheck("physical_range", True, "no range configured"))

    # Spatial consistency (coordinates optional but must be valid when present).
    if latitude is not None or longitude is not None:
        spatial_ok = _valid_lat(latitude) and _valid_lon(longitude)
        checks.append(
            QCCheck("spatial", spatial_ok, None if spatial_ok else "coordinates out of range")
        )

    # Temporal consistency (no future observations beyond small clock skew).
    if observed_at is not None:
        ref = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=UTC)
        future_skew_s = (ref - now).total_seconds()
        temporal_ok = future_skew_s <= 300  # allow 5 min skew
        checks.append(
            QCCheck(
                "temporal",
                temporal_ok,
                None if temporal_ok else "observation in the future",
            )
        )

    return _finalize(checks, missing=missing, outlier=outlier, interpolated=interpolated)


def qc_geometry_record(*, geometry: dict | None, valid_from, valid_until) -> QCResult:
    """Run QC on a geometry-bearing record (alert, PFZ, advisory, zone)."""
    checks: list[QCCheck] = []
    missing = geometry is None

    if missing:
        checks.append(QCCheck("geometry_present", False, "no geometry"))
    else:
        try:
            from .geo import load_geometry

            geom = load_geometry(geometry)
            checks.append(QCCheck("geometry_valid", geom.is_valid or not geom.is_empty))
        except Exception as exc:  # noqa: BLE001
            checks.append(QCCheck("geometry_valid", False, f"invalid geometry: {exc}"))

    # Validity window ordering.
    if valid_from and valid_until:
        vf = valid_from if valid_from.tzinfo else valid_from.replace(tzinfo=UTC)
        vu = valid_until if valid_until.tzinfo else valid_until.replace(tzinfo=UTC)
        ordered = vu >= vf
        checks.append(
            QCCheck(
                "validity_window", ordered,
                None if ordered else "valid_until before valid_from",
            )
        )

    return _finalize(checks, missing=missing, outlier=False, interpolated=False)


def _finalize(
    checks: list[QCCheck], *, missing: bool, outlier: bool, interpolated: bool
) -> QCResult:
    """Score checks and assign a disposition.

    - Any hard-failed structural check (schema/spatial/temporal/geometry/window)
      => REJECTED.
    - A physical-range failure (outlier) => QUARANTINED (kept for audit).
    - Missing value with otherwise-valid metadata => QUARANTINED.
    - Otherwise ACCEPTED.
    """
    hard_fail_names = {
        "schema",
        "spatial",
        "temporal",
        "geometry_valid",
        "validity_window",
    }
    failed = [c for c in checks if not c.passed]
    total = max(1, len(checks))
    score = round(1.0 - (len(failed) / total), 4)

    hard_failed = [c for c in failed if c.name in hard_fail_names]
    if hard_failed:
        status = QCStatus.REJECTED
        reason = "; ".join(c.detail or c.name for c in hard_failed)
    elif outlier or missing:
        status = QCStatus.QUARANTINED
        reason = "; ".join(c.detail or c.name for c in failed) or "quarantined"
    else:
        status = QCStatus.ACCEPTED
        reason = None

    return QCResult(
        status=status,
        score=score,
        checks=checks,
        reason=reason,
        missing_flag=missing,
        outlier_flag=outlier,
        interpolated_flag=interpolated,
    )
