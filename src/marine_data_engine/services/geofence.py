"""Geofence service.

Point-in-zone, nearby-zone, and route-intersection checks against operator-
configured :class:`~marine_data_engine.db.models.MarineZone` polygons. Geometry
predicates use Shapely (the same portable path as the query layer); in
production these map to PostGIS ``ST_Contains``/``ST_DWithin``/``ST_Intersects``.

Marine zones (EEZ, restricted areas, MPAs, operational zones) are **not**
provided by IMD/INCOIS/MOSDAC — they are loaded only from operator-configured
authoritative GIS sources. When no zones are loaded, every function returns an
empty result annotated with a ``SOURCE_GAP`` warning so callers never mistake
"no zones configured" for "point is clear".
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import MarineZone
from ..domain.geo import load_geometry, nearest_geometry_distance_km, point_in_geometry

SOURCE_GAP_NO_ZONES = (
    "SOURCE_GAP: no marine zones are loaded; geofence checks are inconclusive. "
    "Zones must be provided from operator-configured authoritative GIS sources."
)


def _zones_loaded(session: Session) -> bool:
    return session.execute(select(func.count()).select_from(MarineZone)).scalar_one() > 0


def _zone_summary(zone: MarineZone, *, distance_km: float | None, inside: bool | None) -> dict:
    return {
        "zone_uid": zone.zone_uid,
        "zone_type": zone.zone_type,
        "name": zone.name,
        "status": zone.status,
        "restriction": zone.restriction,
        "authority": zone.authority,
        "distance_km": round(distance_km, 3) if distance_km is not None else None,
        "inside": inside,
        "effective_from": zone.effective_from,
        "effective_until": zone.effective_until,
        "source": zone.source,
        "source_dataset": zone.source_dataset,
        "source_url": zone.source_url,
        "retrieved_at": zone.retrieved_at,
        "source_metadata": zone.source_metadata,
    }


def _effective(zone: MarineZone, at: datetime) -> bool:
    start = zone.effective_from
    end = zone.effective_until
    if start is not None:
        start = start if start.tzinfo else start.replace(tzinfo=UTC)
        if at < start:
            return False
    if end is not None:
        end = end if end.tzinfo else end.replace(tzinfo=UTC)
        if at > end:
            return False
    return True


def zone_coverage(session: Session) -> dict:
    """Report loaded authoritative coverage independently by zone category."""
    groups = {
        "eez_boundary": {"eez", "boundary", "international_boundary"},
        "marine_protected_area": {"mpa", "marine_protected_area", "protected"},
        "restricted_area": {"restricted", "no_fishing", "exclusion"},
        "naval_firing_area": {"naval", "firing_range", "naval_firing_range"},
    }
    counts = {name: 0 for name in groups}
    now = datetime.now(tz=UTC)
    for zone in session.execute(select(MarineZone)).scalars():
        if not _effective(zone, now):
            continue
        normalized = (zone.zone_type or "").strip().lower()
        for name, aliases in groups.items():
            if normalized in aliases:
                counts[name] += 1
    return {
        name: {
            "status": "available" if count else "not_loaded",
            "feature_count": count,
        }
        for name, count in counts.items()
    }


def check_point_in_zones(session: Session, lat: float, lon: float) -> list[dict]:
    """Return marine zones whose polygon contains the point.

    Each result carries ``inside=True`` and ``distance_km=0.0``. Returns a
    single-element ``SOURCE_GAP`` sentinel when no zones are loaded.
    """
    if not _zones_loaded(session):
        return [{"warning": SOURCE_GAP_NO_ZONES, "source_gap": True}]

    out: list[dict] = []
    now = datetime.now(tz=UTC)
    for zone in session.execute(select(MarineZone)).scalars():
        if zone.geometry is None or not _effective(zone, now):
            continue
        try:
            if point_in_geometry(lat, lon, zone.geometry):
                out.append(_zone_summary(zone, distance_km=0.0, inside=True))
        except Exception:  # noqa: BLE001 — skip malformed geometry defensively
            continue
    return out


def find_nearby_zones(session: Session, lat: float, lon: float, radius_km: float) -> list[dict]:
    """Return marine zones within ``radius_km`` (containment => distance 0).

    Distance uses the nearest point on the actual source geometry. Sorted
    nearest-first. Returns a ``SOURCE_GAP`` sentinel when no zones are loaded.
    """
    if not _zones_loaded(session):
        return [{"warning": SOURCE_GAP_NO_ZONES, "source_gap": True}]

    out: list[dict] = []
    now = datetime.now(tz=UTC)
    for zone in session.execute(select(MarineZone)).scalars():
        if zone.geometry is None or not _effective(zone, now):
            continue
        try:
            distance = nearest_geometry_distance_km(lat, lon, zone.geometry)
            inside = point_in_geometry(lat, lon, zone.geometry)
        except Exception:  # noqa: BLE001
            continue
        if distance > radius_km:
            continue
        out.append(_zone_summary(zone, distance_km=distance, inside=inside))
    out.sort(key=lambda r: r["distance_km"] if r["distance_km"] is not None else float("inf"))
    return out


def find_route_intersections(session: Session, geometry: dict) -> list[dict]:
    """Return marine zones intersecting the supplied GeoJSON geometry.

    ``geometry`` is typically a route ``LineString``. Raises ``ValueError`` on
    an invalid geometry. Returns a ``SOURCE_GAP`` sentinel when no zones are
    loaded.
    """
    try:
        probe = load_geometry(geometry)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid geometry: {exc}") from exc

    if not _zones_loaded(session):
        return [{"warning": SOURCE_GAP_NO_ZONES, "source_gap": True}]

    out: list[dict] = []
    now = datetime.now(tz=UTC)
    for zone in session.execute(select(MarineZone)).scalars():
        if zone.geometry is None or not _effective(zone, now):
            continue
        try:
            zgeom = load_geometry(zone.geometry)
        except Exception:  # noqa: BLE001
            continue
        if probe.intersects(zgeom):
            out.append(_zone_summary(zone, distance_km=0.0, inside=None))
    return out
