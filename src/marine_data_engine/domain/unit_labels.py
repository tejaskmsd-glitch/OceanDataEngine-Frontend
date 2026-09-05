"""Resolution of source-declared unit *labels* to canonical unit names.

This module is deliberately separate from :mod:`.units`, which owns numeric
**conversions** (Kelvin to Celsius, knots to m/s). The concern here is upstream
**spelling**: deciding whether the string a provider wrote denotes the unit a
parameter requires. No arithmetic happens in this module.

Why it exists
-------------
Source adapters must refuse data whose unit they cannot verify: silently
assuming metres when a provider meant feet is exactly the class of error that
turns a safety engine into a hazard. But strictness applied to spelling rather
than to meaning is its own failure mode -- it rejects perfectly well-specified
data because the provider wrote ``Meters`` instead of ``m``.

Two live examples from real Indian sources drive this:

* INCOIS OON buoy charts label significant wave height ``Meters``. A strict
  whitelist expecting ``m`` quarantined those values, degrading a dataset that
  was in fact unambiguous.
* INCOIS THREDDS WaveWatch III publishes an **empty** CF ``units`` attribute
  (``units=""``); the unit appears only inside the human-readable ``long_name``,
  e.g. ``"Wave height (m)"``, ``"Mean Per Tm (s)"``, ``"Wind U (m/s)"``.

So two questions are kept apart, because conflating them is what caused the bug:

1. *What did the provider say the unit is?* -- spelling, solved by an explicit
   synonym table. Anything absent from the table is **unknown**, never guessed.
2. *Is that the unit this parameter requires?* -- semantics, solved by
   :func:`require_unit`, which raises when the resolved unit is not the expected
   canonical one.

Membership rule for the synonym table: a synonym may appear **only if** it
denotes the identical physical quantity, so substituting it requires no
arithmetic. Relabelling ``Meters`` to ``m`` is safe. Scale-different labels
(feet, knots, centimetres) are intentionally excluded -- converting those is a
parser's job, where the factor is explicit and reviewable, using :mod:`.units`.
"""

from __future__ import annotations

import re

__all__ = [
    "UnitContractError",
    "UnknownUnitError",
    "canonical_unit",
    "extract_unit_from_long_name",
    "require_unit",
]


class UnknownUnitError(ValueError):
    """Raised when a source-declared unit label cannot be resolved at all."""


class UnitContractError(ValueError):
    """Raised when a resolved unit is not the unit the parameter requires."""


_SYNONYMS: dict[str, frozenset[str]] = {
    "m": frozenset({"m", "meter", "meters", "metre", "metres", "m.", "[m]"}),
    "s": frozenset({"s", "sec", "secs", "second", "seconds", "[s]"}),
    "m/s": frozenset(
        {
            "m/s",
            "m s-1",
            "m s^-1",
            "m.s-1",
            "ms-1",
            "meter/second",
            "meters/second",
            "metre/second",
            "metres/second",
            "[m/s]",
        }
    ),
    "deg": frozenset({"deg", "degree", "degrees", "deg.", "degs", "[deg]"}),
    "degrees_north": frozenset({"degrees_north", "degree_north"}),
    "degrees_east": frozenset({"degrees_east", "degree_east"}),
    "hz": frozenset({"hz", "hertz", "s-1", "[hz]"}),
    "rad": frozenset({"rad", "radian", "radians", "[rad]"}),
    "hpa": frozenset(
        {"hpa", "hectopascal", "hectopascals", "mbar", "millibar", "millibars"}
    ),
    "degc": frozenset(
        {
            "degc",
            "deg_c",
            "deg c",
            "degree_celsius",
            "degrees_celsius",
            "celsius",
            "c",
            "\u00b0c",
        }
    ),
    "mm": frozenset(
        {"mm", "millimeter", "millimeters", "millimetre", "millimetres"}
    ),
    "1": frozenset({"1", "-", "none", "dimensionless", "unitless", ""}),
}

_LOOKUP: dict[str, str] = {
    syn: canon for canon, syns in _SYNONYMS.items() for syn in syns
}

# Trailing "(...)" group of a CF long_name, e.g. "Wave height (m)" -> "m".
_LONG_NAME_UNIT = re.compile(r"\(([^()]{1,20})\)\s*$")


def canonical_unit(label: str | None) -> str:
    """Resolve a source-declared unit *label* to its canonical form.

    Raises :class:`UnknownUnitError` when the label is not a recognised
    synonym; an unrecognised unit is never coerced or defaulted, so the caller
    fails closed.

    ``None`` is rejected rather than treated as dimensionless, because a missing
    unit and an explicitly dimensionless quantity are different claims. Pass
    ``"1"`` for a genuinely dimensionless value.
    """
    if label is None:
        raise UnknownUnitError("unit label is None; refusing to assume a unit")
    key = label.strip().lower()
    try:
        return _LOOKUP[key]
    except KeyError:
        raise UnknownUnitError(
            f"unrecognised unit label {label!r}; refusing to guess. Add a "
            f"synonym only if it denotes the identical quantity."
        ) from None


def extract_unit_from_long_name(long_name: str | None) -> str:
    """Resolve the unit from a trailing parenthesised group in *long_name*.

    INCOIS THREDDS WaveWatch III leaves the CF ``units`` attribute empty and
    states the unit only in ``long_name`` (``"Wave height (m)"``). Reading it
    from there is a documented, checkable pattern rather than an assumption --
    but it must still be an explicit parenthesised group at the end of the
    string, and its contents must still resolve via :func:`canonical_unit`.

    Raises :class:`UnknownUnitError` if no trailing group is present or its
    contents are not a recognised unit.
    """
    if not long_name:
        raise UnknownUnitError(
            "long_name is empty; no unit can be established for this variable"
        )
    match = _LONG_NAME_UNIT.search(long_name)
    if match is None:
        raise UnknownUnitError(
            f"long_name {long_name!r} has no trailing '(unit)' group; "
            f"refusing to infer a unit"
        )
    return canonical_unit(match.group(1))


def require_unit(label: str | None, expected: str, *, context: str = "") -> str:
    """Resolve *label* and assert it is the *expected* canonical unit.

    Returns the canonical unit on success. Raises :class:`UnitContractError`
    when the source's unit is recognised but is not the one this parameter
    requires -- a genuine upstream contract change that must stop ingestion
    rather than be accepted silently.
    """
    resolved = canonical_unit(label)
    want = expected.strip().lower()
    if resolved != want:
        where = f" for {context}" if context else ""
        raise UnitContractError(
            f"unit contract violation{where}: source declared {label!r} "
            f"(resolved {resolved!r}) but {want!r} is required"
        )
    return resolved
