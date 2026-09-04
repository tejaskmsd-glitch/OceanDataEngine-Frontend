"""Unit conversion framework.

Pure, dependency-free conversions between the units used by upstream marine
sources and the canonical units stored in the data layer. Every function is a
deterministic scalar transform with no external libraries.

Edge-case contract shared by all functions:

- ``None`` is passed through unchanged (missing values stay missing).
- ``NaN`` is passed through unchanged (never coerced to a number).

Canonical units (source_mapping §7):

- temperature: degrees Celsius
- speed: metres per second
- pressure: hectopascals (hPa == millibars)
- longitude: -180..180 (WGS84)
- direction: degrees 0..360
"""

from __future__ import annotations

import math

# Conversion factors.
KELVIN_OFFSET = 273.15
KNOTS_TO_MS_FACTOR = 0.514444  # 1 knot = 1 nautical mile/hour = 0.514444 m/s
PA_PER_HPA = 100.0  # 1 hPa = 100 Pa


def _passthrough(value: float | None) -> bool:
    """Return True if ``value`` is a missing/NaN sentinel to pass through."""
    if value is None:
        return True
    return isinstance(value, float) and math.isnan(value)


def kelvin_to_celsius(k: float | None) -> float | None:
    """Convert Kelvin to Celsius (C = K - 273.15)."""
    if _passthrough(k):
        return k
    return k - KELVIN_OFFSET


def celsius_to_kelvin(c: float | None) -> float | None:
    """Convert Celsius to Kelvin (K = C + 273.15)."""
    if _passthrough(c):
        return c
    return c + KELVIN_OFFSET


def knots_to_ms(knots: float | None) -> float | None:
    """Convert knots to metres per second (1 kt = 0.514444 m/s)."""
    if _passthrough(knots):
        return knots
    return knots * KNOTS_TO_MS_FACTOR


def ms_to_knots(ms: float | None) -> float | None:
    """Convert metres per second to knots (1 m/s = 1 / 0.514444 kt)."""
    if _passthrough(ms):
        return ms
    return ms / KNOTS_TO_MS_FACTOR


def pascal_to_hpa(pa: float | None) -> float | None:
    """Convert pascals to hectopascals (1 hPa = 100 Pa)."""
    if _passthrough(pa):
        return pa
    return pa / PA_PER_HPA


def hpa_to_pascal(hpa: float | None) -> float | None:
    """Convert hectopascals to pascals (1 hPa = 100 Pa)."""
    if _passthrough(hpa):
        return hpa
    return hpa * PA_PER_HPA


def normalize_longitude(lon: float | None) -> float | None:
    """Normalize longitude from 0..360 to -180..180 (WGS84).

    Uses ``((lon + 180) mod 360) - 180`` so that, e.g., 190 -> -170 and
    360 -> 0. Values already in -180..180 are returned unchanged.
    """
    if _passthrough(lon):
        return lon
    return ((lon + 180.0) % 360.0) - 180.0


def speed_from_uv(u: float | None, v: float | None) -> float | None:
    """Return the vector magnitude sqrt(u**2 + v**2) of a u/v pair.

    ``None``/``NaN`` in either component passes through as a missing result.
    """
    if _passthrough(u) or _passthrough(v):
        return None
    return math.sqrt(u * u + v * v)


def direction_from_uv(
    u: float | None, v: float | None, convention: str = "oceanographic"
) -> float | None:
    """Return the direction (degrees, 0..360) of a u/v vector.

    Conventions:

    - ``oceanographic`` (default): the direction the current flows **to**
      (i.e. the vector heading). East-going (u>0, v=0) => 90.
    - ``meteorological``: the direction the wind comes **from** (the vector
      heading rotated 180 degrees). A wind blowing toward the east (u>0, v=0)
      comes from the west => 270.

    ``None``/``NaN`` in either component passes through as a missing result.
    ``convention`` must be one of the two supported values.
    """
    if convention not in ("oceanographic", "meteorological"):
        raise ValueError(f"unknown convention: {convention!r}")
    if _passthrough(u) or _passthrough(v):
        return None
    # atan2(u, v) gives the compass heading (clockwise from north) the vector
    # points toward: due-east (u>0, v=0) -> 90, due-north (u=0, v>0) -> 0.
    heading = (math.degrees(math.atan2(u, v)) + 360.0) % 360.0
    if convention == "meteorological":
        return (heading + 180.0) % 360.0
    return heading
