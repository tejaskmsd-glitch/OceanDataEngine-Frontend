"""CRS normalization. Canonical output CRS is WGS84 (EPSG:4326).

Pure-Python, dependency-free helpers used to bring vector/point geometry into
the canonical WGS84 frame before it is stored or queried. Heavy raster
reprojection (grids, NetCDF, GeoTIFF) is out of scope here and is performed by
the processing workers using ``pyproj``/GDAL; this module only handles the
common lightweight cases (longitude wrapping, bounds validation, and a linear
axis-aligned bbox reprojection between a small set of known frames).
"""

from __future__ import annotations

import math

# Canonical output CRS for the whole data layer.
WGS84 = "EPSG:4326"

# Web Mercator constants (EPSG:3857). ``R`` is the spherical radius used by the
# de-facto Web Mercator definition (WGS84 semi-major axis).
_MERCATOR_R = 6378137.0
_MERCATOR_MAX_LAT = 85.05112878  # latitude at which Web Mercator y = +/- R*pi


def _is_missing(value: float | None) -> bool:
    """Return True for ``None``/``NaN`` sentinels that must pass through."""
    if value is None:
        return True
    return isinstance(value, float) and math.isnan(value)


def _canonical_crs(crs: str) -> str:
    """Normalize a CRS identifier to an ``EPSG:<code>`` string.

    Accepts ``"EPSG:4326"``, ``"epsg:4326"``, ``"4326"``, ``"WGS84"`` and the
    OGC URN form ``"urn:ogc:def:crs:EPSG::4326"``. Unknown values are returned
    upper-cased and stripped so callers can still compare them.
    """
    if not crs:
        raise ValueError("CRS identifier must be a non-empty string")
    c = crs.strip()
    upper = c.upper()
    aliases = {
        "WGS84": "EPSG:4326",
        "WGS 84": "EPSG:4326",
        "CRS84": "EPSG:4326",
        "EPSG:4326": "EPSG:4326",
        "EPSG:3857": "EPSG:3857",
        "EPSG:900913": "EPSG:3857",
        "EPSG:3395": "EPSG:3395",
    }
    if upper in aliases:
        return aliases[upper]
    # Bare numeric code.
    if c.isdigit():
        return f"EPSG:{c}"
    # OGC URN form: urn:ogc:def:crs:EPSG::4326
    if "EPSG" in upper and "::" in upper:
        code = upper.rsplit("::", 1)[-1]
        if code.isdigit():
            return f"EPSG:{code}"
    return upper


def normalize_longitude(lon: float) -> float:
    """Normalize longitude to the WGS84 range ``-180..180``.

    Uses ``((lon + 180) mod 360) - 180`` so that 190 -> -170 and 360 -> 0.
    ``None``/``NaN`` pass through unchanged. This mirrors
    :func:`marine_data_engine.domain.units.normalize_longitude`.
    """
    if _is_missing(lon):
        return lon
    return ((lon + 180.0) % 360.0) - 180.0


def validate_wgs84_bounds(lat: float, lon: float) -> bool:
    """Return True if ``(lat, lon)`` are finite and within WGS84 bounds.

    Latitude must lie in ``[-90, 90]`` and longitude in ``[-180, 180]``.
    ``None``/``NaN`` are considered invalid (unlike the pass-through helpers,
    this is a boolean validator).
    """
    if _is_missing(lat) or _is_missing(lon):
        return False
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def ensure_wgs84_point(lat: float, lon: float) -> tuple[float, float]:
    """Return a WGS84 ``(lat, lon)`` point with the longitude normalized.

    Longitude is wrapped into ``-180..180``. The resulting point is validated
    against WGS84 bounds; an out-of-range latitude raises ``ValueError`` because
    latitude cannot be safely wrapped without changing the point's meaning.
    """
    if _is_missing(lat) or _is_missing(lon):
        raise ValueError("latitude/longitude must not be None or NaN")
    norm_lon = normalize_longitude(lon)
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"latitude {lat} outside WGS84 range [-90, 90]")
    return (float(lat), float(norm_lon))


def _lonlat_to_mercator(lon: float, lat: float) -> tuple[float, float]:
    """Project a WGS84 lon/lat to Web Mercator (EPSG:3857) metres."""
    lat = max(-_MERCATOR_MAX_LAT, min(_MERCATOR_MAX_LAT, lat))
    x = math.radians(lon) * _MERCATOR_R
    y = math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)) * _MERCATOR_R
    return (x, y)


def _mercator_to_lonlat(x: float, y: float) -> tuple[float, float]:
    """Inverse Web Mercator (EPSG:3857) metres to WGS84 lon/lat."""
    lon = math.degrees(x / _MERCATOR_R)
    lat = math.degrees(2.0 * math.atan(math.exp(y / _MERCATOR_R)) - math.pi / 2.0)
    return (lon, lat)


def reproject_bbox(
    bbox: tuple, from_crs: str, to_crs: str = "EPSG:4326"
) -> tuple:
    """Lightweight bbox reprojection. Full raster reprojection uses pyproj/GDAL.

    ``bbox`` is ``(minx, miny, maxx, maxy)`` in ``from_crs`` axis order
    (x=lon/easting, y=lat/northing). Returns the axis-aligned bounding box in
    ``to_crs``.

    Supported frames: WGS84 (EPSG:4326) and Web Mercator (EPSG:3857). Because
    the Mercator transform is monotonic per-axis, transforming the two corners
    is sufficient for an axis-aligned box. For any other CRS pair this raises
    ``NotImplementedError`` — reprojecting arbitrary CRSs (and rasters) requires
    ``pyproj``/GDAL which is intentionally not a dependency of this module.
    """
    if bbox is None or len(bbox) != 4:
        raise ValueError("bbox must be a 4-tuple (minx, miny, maxx, maxy)")
    minx, miny, maxx, maxy = (float(v) for v in bbox)
    if minx > maxx or miny > maxy:
        raise ValueError("bbox min values must not exceed max values")

    src = _canonical_crs(from_crs)
    dst = _canonical_crs(to_crs)

    if src == dst:
        return (minx, miny, maxx, maxy)

    if src == "EPSG:4326" and dst == "EPSG:3857":
        x0, y0 = _lonlat_to_mercator(minx, miny)
        x1, y1 = _lonlat_to_mercator(maxx, maxy)
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    if src == "EPSG:3857" and dst == "EPSG:4326":
        lon0, lat0 = _mercator_to_lonlat(minx, miny)
        lon1, lat1 = _mercator_to_lonlat(maxx, maxy)
        return (min(lon0, lon1), min(lat0, lat1), max(lon0, lon1), max(lat0, lat1))

    raise NotImplementedError(
        f"bbox reprojection {src} -> {dst} is not supported without pyproj/GDAL; "
        "use the raster processing pipeline for arbitrary CRS transforms"
    )
