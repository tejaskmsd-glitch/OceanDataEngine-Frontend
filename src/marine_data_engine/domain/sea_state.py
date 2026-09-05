"""Categorical sea-state vocabulary and its published WMO height bands.

Why this module exists
----------------------
Some authoritative marine bulletins (notably IMD coastal and sea-area
bulletins) publish sea state as a **word** — ``MODERATE``, ``ROUGH``,
``MODERATE TO ROUGH`` — and never as a wave height in metres. The engine
refuses to invent a wave height, but it must also not throw away a real,
authoritative statement about the sea.

The resolution is to treat the *category* as the primary truth and to expose
its height band strictly as a **documented standard mapping**, not as a
measurement:

    WMO Code table 3700 (sea state) / Douglas sea scale

Rules enforced here
-------------------
- The verbatim source term is always retained (:attr:`SeaStateBand.category`).
- The band is a closed interval from the published table. It is never
  narrowed to a single "best guess" value.
- Consumers that need a scalar must use :attr:`SeaStateBand.conservative_height_m`
  (the band's **upper** bound), so a coarse category can only ever make a
  safety decision more pessimistic, never less.
- Unknown or unparseable vocabulary returns ``None``. It is *not* mapped to a
  default, and it must be treated by callers as missing evidence.
- A derived band must never be persisted or reported as an observed wave
  height. Provenance is fixed to :data:`DERIVATION_BASIS`.

This module is pure: no I/O, no clock reads.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Stable provenance marker for any value produced from a category.
DERIVATION_BASIS = "WMO_CODE_3700_DOUGLAS_SEA_SCALE"

#: Provenance tag distinguishing derived values from measurements.
PROVENANCE_BULLETIN_DERIVED = "bulletin_derived"

# WMO Code table 3700 — sea state code: (label, lower bound m, upper bound m).
# The final code is open-ended upward; a finite sentinel upper bound is used so
# the conservative bound remains a real number, and ``open_ended`` records that
# the true upper limit is unbounded.
_WMO_3700: dict[int, tuple[str, float, float]] = {
    0: ("calm_glassy", 0.0, 0.0),
    1: ("calm_rippled", 0.0, 0.1),
    2: ("smooth", 0.1, 0.5),
    3: ("slight", 0.5, 1.25),
    4: ("moderate", 1.25, 2.5),
    5: ("rough", 2.5, 4.0),
    6: ("very_rough", 4.0, 6.0),
    7: ("high", 6.0, 9.0),
    8: ("very_high", 9.0, 14.0),
    9: ("phenomenal", 14.0, 14.0),
}

#: Source vocabulary -> WMO 3700 code. Keys are normalised (see
#: :func:`_normalise`). Only terms actually observed in authoritative bulletin
#: vocabulary are listed; anything else is rejected rather than guessed.
_TERM_TO_CODE: dict[str, int] = {
    "calm": 0,
    "calm glassy": 0,
    "glassy": 0,
    "calm rippled": 1,
    "rippled": 1,
    "smooth": 2,
    "smooth wavelets": 2,
    "wavelets": 2,
    "slight": 3,
    "moderate": 4,
    "rough": 5,
    "very rough": 6,
    "high": 7,
    "very high": 8,
    "phenomenal": 9,
}

# Separators used by bulletins to express a spanning category, e.g.
# "MODERATE TO ROUGH", "MODERATE-ROUGH", "MODERATE BECOMING ROUGH".
_SPAN_SEPARATORS = (
    " becoming ",
    " to ",
    " or ",
    "/",
    "-",
)


@dataclass(frozen=True)
class SeaStateBand:
    """A categorical sea state plus its published height interval."""

    category: str
    """Verbatim source term, whitespace-normalised but not reworded."""

    normalised: str
    """Lower-cased comparison form of :attr:`category`."""

    codes: tuple[int, ...]
    """WMO 3700 code(s) the term spans, ascending."""

    labels: tuple[str, ...]
    """Canonical WMO label(s) for :attr:`codes`."""

    min_height_m: float
    """Lower bound of the published band, in metres."""

    max_height_m: float
    """Upper bound of the published band, in metres."""

    open_ended: bool = False
    """True when the published band has no finite upper limit."""

    @property
    def conservative_height_m(self) -> float:
        """Upper bound — the only scalar safe for a safety decision."""
        return self.max_height_m

    def as_dict(self) -> dict:
        """Serialise for persistence in source metadata / evidence."""
        return {
            "sea_state_category": self.category,
            "sea_state_normalised": self.normalised,
            "wmo_3700_codes": list(self.codes),
            "wmo_3700_labels": list(self.labels),
            "derived_height_band_m": [self.min_height_m, self.max_height_m],
            "derived_conservative_height_m": self.conservative_height_m,
            "derivation_basis": DERIVATION_BASIS,
            "provenance": PROVENANCE_BULLETIN_DERIVED,
            "is_measurement": False,
        }


def _normalise(term: str) -> str:
    """Lower-case, collapse whitespace, drop trailing punctuation."""
    cleaned = " ".join(str(term or "").split()).strip().lower()
    return cleaned.rstrip(".;,:").strip()


def _split_span(normalised: str) -> list[str]:
    """Split a spanning category into its component terms.

    ``"moderate to rough"`` -> ``["moderate", "rough"]``. A term containing no
    known separator is returned unchanged as a single element.
    """
    for sep in _SPAN_SEPARATORS:
        if sep in normalised:
            parts = [p.strip() for p in normalised.split(sep)]
            return [p for p in parts if p]
    return [normalised]


def parse_sea_state_category(term: str | None) -> SeaStateBand | None:
    """Map an authoritative sea-state term to its published WMO band.

    Returns ``None`` for empty input or vocabulary that is not in the verified
    table. ``None`` means *unknown*, and callers must treat it as missing
    evidence — never as calm water.

    ``"MODERATE TO ROUGH"`` yields the union of both bands (1.25 m .. 4.0 m),
    so the conservative bound reflects the worst sea the bulletin allows for.
    """
    if term is None:
        return None
    category = " ".join(str(term).split()).strip()
    if not category:
        return None

    normalised = _normalise(category)
    if not normalised:
        return None

    parts = _split_span(normalised)
    codes: list[int] = []
    for part in parts:
        code = _TERM_TO_CODE.get(part)
        if code is None:
            # Unverified vocabulary: refuse rather than approximate.
            return None
        codes.append(code)

    if not codes:
        return None

    ordered = tuple(sorted(set(codes)))
    lower = min(_WMO_3700[c][1] for c in ordered)
    upper = max(_WMO_3700[c][2] for c in ordered)
    labels = tuple(_WMO_3700[c][0] for c in ordered)
    return SeaStateBand(
        category=category,
        normalised=normalised,
        codes=ordered,
        labels=labels,
        min_height_m=lower,
        max_height_m=upper,
        open_ended=9 in ordered,
    )


def known_sea_state_terms() -> tuple[str, ...]:
    """Verified single-term vocabulary, for diagnostics and error messages."""
    return tuple(sorted(_TERM_TO_CODE))
