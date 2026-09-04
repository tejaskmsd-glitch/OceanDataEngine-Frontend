"""Parameter normalization: source-specific values -> canonical form.

Thin, dependency-free helpers that map a raw ``(value, unit)`` pair from an
upstream source into the canonical unit used by the data layer. They build on
the pure scalar conversions in :mod:`marine_data_engine.domain.units`.

Canonical units (source_mapping §7):
    temperature  -> degC
    wind speed   -> m/s
    pressure     -> hPa
    direction    -> degrees 0..360
"""

from __future__ import annotations

from .units import kelvin_to_celsius, knots_to_ms, pascal_to_hpa


def normalize_sst(value: float, unit: str) -> tuple[float, str]:
    """Normalize sea-surface / air temperature to degC.

    Kelvin inputs are converted; anything else is assumed already Celsius.
    """
    if unit.upper() in ("K", "KELVIN"):
        return (kelvin_to_celsius(value), "degC")
    return (value, "degC")


def normalize_wind(value: float, unit: str) -> tuple[float, str]:
    """Normalize wind speed to m/s. Knots are converted; else passthrough."""
    if unit.lower() in ("knots", "knot", "kn", "kt", "kts"):
        return (knots_to_ms(value), "m/s")
    return (value, "m/s")


def normalize_pressure(value: float, unit: str) -> tuple[float, str]:
    """Normalize pressure to hPa. Pascals are converted; else passthrough."""
    if unit.upper() in ("PA", "PASCAL", "PASCALS"):
        return (pascal_to_hpa(value), "hPa")
    return (value, "hPa")


def normalize_wave_direction(value: float, convention: str | None) -> tuple[float, str | None]:
    """Normalize a wave/current direction.

    When the direction convention is unknown, the value is returned unchanged
    with convention ``"UNKNOWN"`` (never silently forced into a range whose
    meaning we cannot attest). With a known convention the value is wrapped to
    0..360.
    """
    if convention is None or convention.upper() == "UNKNOWN":
        return (value, "UNKNOWN")
    return (value % 360.0, convention)
