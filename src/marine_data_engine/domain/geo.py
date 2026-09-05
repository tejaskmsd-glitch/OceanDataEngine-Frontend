"""Deterministic geospatial helpers.

Distances use the geodesic haversine formula (WGS84 mean radius). Geometry
validation and centroid computation use Shapely. In production, spatial
predicates and nearest-neighbour queries run in PostGIS; these helpers provide
a portable, deterministic implementation for the query layer and tests.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two WGS84 points."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial geodesic bearing (degrees, 0..360) from point 1 to point 2."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(rlat2)
    y = math.cos(rlat1) * math.sin(rlat2) - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def load_geometry(geojson: dict[str, Any]) -> BaseGeometry:
    """Load and validate a GeoJSON geometry into a Shapely geometry."""
    geom = shape(geojson)
    if not geom.is_valid:
        # buffer(0) is a standard Shapely trick to repair minor invalidity.
        geom = geom.buffer(0)
    return geom


def geometry_bbox(geojson: dict[str, Any]) -> tuple[float, float, float, float]:
    """Return (minx, miny, maxx, maxy) for a GeoJSON geometry."""
    geom = load_geometry(geojson)
    return tuple(geom.bounds)  # type: ignore[return-value]


def geometry_centroid(geojson: dict[str, Any]) -> tuple[float, float]:
    """Return (lat, lon) centroid of a GeoJSON geometry."""
    geom = load_geometry(geojson)
    c = geom.centroid
    return (c.y, c.x)


def point_in_geometry(lat: float, lon: float, geojson: dict[str, Any]) -> bool:
    """Return True when the point is inside or on the geometry boundary."""
    from shapely.geometry import Point

    return load_geometry(geojson).covers(Point(lon, lat))


def nearest_geometry_distance_km(
    lat: float, lon: float, geojson: dict[str, Any]
) -> float:
    """Geodesic distance to the nearest point on a GeoJSON geometry.

    Shapely finds the nearest coordinate in the source CRS; haversine then
    computes the WGS84 distance. Points covered by a polygon/line/point return
    zero. This portable implementation mirrors ``ST_Distance`` semantics more
    faithfully than centroid distance for large polygons and long lines.
    """
    from shapely.geometry import Point
    from shapely.ops import nearest_points

    probe = Point(lon, lat)
    geometry = load_geometry(geojson)
    if geometry.covers(probe):
        return 0.0
    _probe_nearest, geometry_nearest = nearest_points(probe, geometry)
    return haversine_km(lat, lon, geometry_nearest.y, geometry_nearest.x)


# normalize_longitude now lives in :mod:`marine_data_engine.domain.units`;
# re-exported here as an alias for backward compatibility.
from .units import normalize_longitude  # noqa: E402,F401
