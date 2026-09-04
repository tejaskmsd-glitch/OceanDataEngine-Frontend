"""Deterministic route risk service (prompt.md §13).

Computes a great-circle (geodesic) route between two WGS84 points, splits it
into fixed-length segments, and scores each segment with the marine risk engine
using whatever environmental data is supplied per segment. The output is fully
explainable: per-segment penalties, aggregate route risk, avoided zones, and the
dominant risk drivers.

This is a **deterministic** router, not an optimizer: it does not search
alternative paths. Without environmental data it still returns the geodesic
route with a ``partial`` status and explicit warnings so the caller knows the
score is geometry-only. Environmental sampling and zone avoidance are wired
through optional callables so the service stays pure and testable offline.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..domain.crs import ensure_wgs84_point
from ..domain.geo import haversine_km
from ..domain.risk import RiskThresholds, assess_marine_risk

# 1 knot = 1.852 km/h.
KM_PER_NM = 1.852
# Default segment length (km) when splitting the route.
DEFAULT_SEGMENT_KM = 50.0

# Keyword arguments of ``assess_marine_risk`` that an env sampler may provide.
_RISK_FACTOR_KEYS = frozenset(
    {
        "wave_height",
        "wave_period",
        "swell_height",
        "wind_speed",
        "wind_gust",
        "rainfall",
        "pressure",
        "pressure_trend",
        "active_warnings",
        "cyclone_distance_km",
    }
)

# Type of the optional per-point environment sampler. Given (lat, lon, eta) it
# returns a dict of environmental factors accepted by ``assess_marine_risk``.
EnvSampler = Callable[[float, float, "datetime | None"], dict]
# Type of the optional zone checker. Given a GeoJSON LineString it returns a
# list of zone summaries (dicts with at least ``zone_uid``/``name``).
ZoneChecker = Callable[[dict], list[dict]]


@dataclass
class RouteSegment:
    """One leg of a route with its risk breakdown."""

    start: tuple[float, float]
    end: tuple[float, float]
    distance_km: float
    travel_time_hours: float | None
    risk_score: float
    penalties: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "start": list(self.start),
            "end": list(self.end),
            "distance_km": round(self.distance_km, 3),
            "travel_time_hours": (
                round(self.travel_time_hours, 3)
                if self.travel_time_hours is not None else None
            ),
            "risk_score": round(self.risk_score, 2),
            "penalties": self.penalties,
        }


@dataclass
class RouteResult:
    """Full route computation result."""

    geometry: dict  # GeoJSON LineString
    total_distance_km: float
    estimated_duration_hours: float | None
    route_risk_score: float
    segments: list[RouteSegment]
    avoided_zones: list[str]
    major_risk_drivers: list[str]
    sources: list[dict]
    status: str  # 'computed' | 'partial' | 'unavailable'
    warnings: list[str]

    def as_dict(self) -> dict:
        return {
            "geometry": self.geometry,
            "total_distance_km": round(self.total_distance_km, 3),
            "estimated_duration_hours": (
                round(self.estimated_duration_hours, 3)
                if self.estimated_duration_hours is not None else None
            ),
            "route_risk_score": round(self.route_risk_score, 2),
            "segments": [s.as_dict() for s in self.segments],
            "avoided_zones": list(self.avoided_zones),
            "major_risk_drivers": list(self.major_risk_drivers),
            "sources": list(self.sources),
            "status": self.status,
            "warnings": list(self.warnings),
        }


def _interpolate_great_circle(
    lat1: float, lon1: float, lat2: float, lon2: float, fraction: float
) -> tuple[float, float]:
    """Point at ``fraction`` (0..1) along the great circle between two points."""
    phi1, lam1 = math.radians(lat1), math.radians(lon1)
    phi2, lam2 = math.radians(lat2), math.radians(lon2)

    # Angular distance between the points.
    d = 2.0 * math.asin(
        math.sqrt(
            math.sin((phi2 - phi1) / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin((lam2 - lam1) / 2.0) ** 2
        )
    )
    if d == 0:
        return (lat1, lon1)

    a = math.sin((1.0 - fraction) * d) / math.sin(d)
    b = math.sin(fraction * d) / math.sin(d)
    x = a * math.cos(phi1) * math.cos(lam1) + b * math.cos(phi2) * math.cos(lam2)
    y = a * math.cos(phi1) * math.sin(lam1) + b * math.cos(phi2) * math.sin(lam2)
    z = a * math.sin(phi1) + b * math.sin(phi2)
    phi = math.atan2(z, math.sqrt(x * x + y * y))
    lam = math.atan2(y, x)
    return (math.degrees(phi), math.degrees(lam))


def _penalties_from_assessment(assessment) -> dict:
    """Bucket factor contributions into the documented penalty categories."""
    buckets = {
        "wave_penalty": 0.0,
        "wind_penalty": 0.0,
        "current_penalty": 0.0,
        "hazard_penalty": 0.0,
        "zone_penalty": 0.0,
    }
    for f in assessment.factors:
        if f.name in ("wave_height", "swell_height", "wave_period"):
            buckets["wave_penalty"] += f.contribution
        elif f.name in ("wind_speed", "wind_gust", "pressure_trend", "rainfall"):
            buckets["wind_penalty"] += f.contribution
    # Warning/cyclone penalties fold into hazard.
    if assessment.warnings:
        buckets["hazard_penalty"] = max(0.0, assessment.risk_score - sum(
            f.contribution for f in assessment.factors) / max(1, len(assessment.factors)))
    return {k: round(v, 3) for k, v in buckets.items()}


def compute_safe_route(
    *,
    start: tuple[float, float],
    end: tuple[float, float],
    departure_time: datetime | None = None,
    vessel_type: str = "default",
    vessel_speed_knots: float = 10.0,
    thresholds: RiskThresholds | None = None,
    segment_km: float = DEFAULT_SEGMENT_KM,
    env_sampler: EnvSampler | None = None,
    zone_checker: ZoneChecker | None = None,
    sources: list[dict] | None = None,
) -> RouteResult:
    """Compute a deterministic great-circle route split into risk-scored segments.

    ``start``/``end`` are ``(lat, lon)`` WGS84 points. The route is divided into
    legs of at most ``segment_km``. If ``env_sampler`` is provided, each segment
    midpoint is sampled and scored with the marine risk engine; otherwise the
    route is returned with a ``partial`` status and geometry-only scoring.

    ``zone_checker`` (e.g. a wrapper around the geofence service) reports zones
    the route intersects; their names populate ``avoided_zones`` and add a flat
    zone penalty to affected segments.
    """
    thresholds = thresholds or RiskThresholds()
    thresholds.vessel_type = vessel_type
    warnings: list[str] = []

    slat, slon = ensure_wgs84_point(*start)
    elat, elon = ensure_wgs84_point(*end)

    total_km = haversine_km(slat, slon, elat, elon)
    if total_km == 0:
        warnings.append("start and end are identical; zero-length route")

    n_segments = max(1, math.ceil(total_km / segment_km)) if segment_km > 0 else 1

    speed_kmh = vessel_speed_knots * KM_PER_NM if vessel_speed_knots > 0 else None
    total_duration_h = (total_km / speed_kmh) if speed_kmh else None

    # Build ordered vertices along the great circle.
    vertices: list[tuple[float, float]] = []
    for i in range(n_segments + 1):
        frac = i / n_segments
        vertices.append(_interpolate_great_circle(slat, slon, elat, elon, frac))

    geometry = {
        "type": "LineString",
        # GeoJSON is (lon, lat) order.
        "coordinates": [[round(lon, 6), round(lat, 6)] for lat, lon in vertices],
    }

    # Zone intersections (whole-route probe).
    avoided_zones: list[str] = []
    intersecting: list[dict] = []
    if zone_checker is not None:
        try:
            intersecting = [z for z in zone_checker(geometry) if not z.get("source_gap")]
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"zone check failed: {exc}")
        for z in intersecting:
            name = z.get("name") or z.get("zone_uid")
            if name and name not in avoided_zones:
                avoided_zones.append(name)
        if any(z.get("source_gap") for z in (intersecting or [])):
            warnings.append("SOURCE_GAP: no marine zones loaded; route not screened for zones")

    segments: list[RouteSegment] = []
    driver_totals: dict[str, float] = {}
    have_env = env_sampler is not None
    cumulative_h = 0.0

    for i in range(n_segments):
        a = vertices[i]
        b = vertices[i + 1]
        seg_km = haversine_km(a[0], a[1], b[0], b[1])
        seg_h = (seg_km / speed_kmh) if speed_kmh else None
        eta = None
        if departure_time is not None and speed_kmh:
            eta = departure_time + timedelta(hours=cumulative_h + (seg_h or 0.0) / 2.0)

        penalties = {
            "wave_penalty": 0.0,
            "wind_penalty": 0.0,
            "current_penalty": 0.0,
            "hazard_penalty": 0.0,
            "zone_penalty": 0.0,
        }
        risk_score = 0.0

        if have_env:
            mid = _interpolate_great_circle(a[0], a[1], b[0], b[1], 0.5)
            try:
                env = env_sampler(mid[0], mid[1], eta) or {}
            except Exception as exc:  # noqa: BLE001
                env = {}
                warnings.append(f"env sample failed on segment {i}: {exc}")
            # ``current_speed`` is not a marine-risk factor; it is scored into
            # the current penalty separately below.
            risk_env = {k: v for k, v in env.items() if k in _RISK_FACTOR_KEYS}
            assessment = assess_marine_risk(thresholds=thresholds, **risk_env)
            risk_score = assessment.risk_score
            penalties.update(_penalties_from_assessment(assessment))
            if env.get("current_speed") is not None:
                cs = env["current_speed"]
                cur_pen = round(min(100.0, max(0.0, (cs - 0.5) * 40.0)), 3)
                penalties["current_penalty"] = cur_pen
                risk_score = min(100.0, risk_score + cur_pen * 0.3)
            for f in assessment.factors:
                driver_totals[f.name] = driver_totals.get(f.name, 0.0) + f.contribution

        # Flat zone penalty if any zone intersects the route.
        if avoided_zones:
            penalties["zone_penalty"] = 20.0
            risk_score = min(100.0, risk_score + 20.0)

        segments.append(
            RouteSegment(
                start=a,
                end=b,
                distance_km=seg_km,
                travel_time_hours=seg_h,
                risk_score=risk_score,
                penalties=penalties,
            )
        )
        if seg_h:
            cumulative_h += seg_h

    # Aggregate route risk = max segment risk (a route is as risky as its worst
    # leg) blended with the mean to avoid single-point domination.
    if segments:
        max_risk = max(s.risk_score for s in segments)
        mean_risk = sum(s.risk_score for s in segments) / len(segments)
        route_risk = round(0.6 * max_risk + 0.4 * mean_risk, 2)
    else:
        route_risk = 0.0

    major_drivers = [
        name for name, _ in sorted(driver_totals.items(), key=lambda kv: kv[1], reverse=True)
        if driver_totals[name] > 0
    ][:5]

    if not have_env:
        status = "partial"
        warnings.append(
            "SOURCE_GAP: no environmental data sampler supplied; returning geodesic "
            "route with geometry-only scoring"
        )
    else:
        status = "computed"

    return RouteResult(
        geometry=geometry,
        total_distance_km=total_km,
        estimated_duration_hours=total_duration_h,
        route_risk_score=route_risk,
        segments=segments,
        avoided_zones=avoided_zones,
        major_risk_drivers=major_drivers,
        sources=sources or [],
        status=status,
        warnings=warnings,
    )
