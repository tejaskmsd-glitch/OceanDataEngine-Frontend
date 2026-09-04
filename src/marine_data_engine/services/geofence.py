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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import MarineZone
from ..domain.geo import geometry_centroid, haversine_km, load_geometry, point_in_geometry

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
        "source_url": zone.source_url,
    }


def check_point_in_zones(session: Session, lat: float, lon: float) -> list[dict]:
    """Return marine zones whose polygon contains the point.

    Each result carries ``inside=True`` and ``distance_km=0.0``. Returns a
    single-element ``SOURCE_GAP`` sentinel when no zones are loaded.
    """
    if not _zones_loaded(session):
        return [{"warning": SOURCE_GAP_NO_ZONES, "source_gap": True}]

    out: list[dict] = []
    for zone in session.execute(select(MarineZone)).scalars():
        if zone.geometry is None:
            continue
        try:
            if point_in_geometry(lat, lon, zone.geometry):
                out.append(_zone_summary(zone, distance_km=0.0, inside=True))
        except Exception:  # noqa: BLE001 — skip malformed geometry defensively
            continue
    return out


def find_nearby_zones(session: Session, lat: float, lon: float, radius_km: float) -> list[dict]:
    """Return marine zones within ``radius_km`` (containment => distance 0).

    Distance uses point-in-polygon first, then a centroid haversine stand-in for
    PostGIS polygon distance. Sorted nearest-first. Returns a ``SOURCE_GAP``
    sentinel when no zones are loaded.
    """
    if not _zones_loaded(session):
        return [{"warning": SOURCE_GAP_NO_ZONES, "source_gap": True}]

    out: list[dict] = []
    for zone in session.execute(select(MarineZone)).scalars():
        if zone.geometry is None:
            continue
        try:
            if point_in_geometry(lat, lon, zone.geometry):
                distance = 0.0
                inside = True
            else:
                clat, clon = geometry_centroid(zone.geometry)
                distance = haversine_km(lat, lon, clat, clon)
                inside = False
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
    for zone in session.execute(select(MarineZone)).scalars():
        if zone.geometry is None:
            continue
        try:
            zgeom = load_geometry(zone.geometry)
        except Exception:  # noqa: BLE001
            continue
        if probe.intersects(zgeom):
            out.append(_zone_summary(zone, distance_km=0.0, inside=None))
    return out
