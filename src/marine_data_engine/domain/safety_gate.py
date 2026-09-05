"""Deterministic marine safety-clearance gate.

This module turns the *interpretation* of "is this trip cleared to go?" into an
explicit, machine-checkable engine decision instead of leaving it to the
narrating agent. It exists to enforce one rule that an LLM must never be able
to bypass on its own:

    **Absence of evidence is not evidence of safety.**

The core distinction the gate makes — and the reason it exists — is:

    UNKNOWN RISK  (a required input is missing)   -> NOT_CLEARED (INSUFFICIENT_DATA)
    LOW RISK      (required inputs present, benign) -> CLEARED

A wind-only reading does **not** establish sea state, so a low wind value can
never, by itself, produce a clearance. The gate first checks that the required
evidence set is present; only if it is does it consult the computed
environmental risk.

Design principles (shared with :mod:`.risk`):

- **Deterministic & pure.** No I/O, no clock reads except via explicit inputs.
- **Explainable.** Every ``NOT_CLEARED`` carries structured, stable reason
  codes so downstream systems can branch on them and tests can assert them.
- **Conservative default.** When in doubt, do not clear.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .risk import RiskAssessment, RiskThresholds, assess_marine_risk
from .sea_state import SeaStateBand, parse_sea_state_category

# ── Decision statuses ──────────────────────────────────────────────────────
STATUS_CLEARED = "CLEARED"
STATUS_CLEARED_WITH_CAUTION = "CLEARED_WITH_CAUTION"
STATUS_NOT_CLEARED = "NOT_CLEARED"

# ── Stable, machine-readable reason codes ──────────────────────────────────
# Missing-evidence codes (drive an INSUFFICIENT_DATA NOT_CLEARED).
REASON_WAVE_UNAVAILABLE = "WAVE_FORECAST_UNAVAILABLE"
REASON_WIND_UNAVAILABLE = "WIND_DATA_UNAVAILABLE"
REASON_TIDE_UNAVAILABLE = "TIDE_DATA_UNAVAILABLE"
REASON_SEA_STATE_UNKNOWN = "SEA_STATE_UNKNOWN"
# Sea state established only from an authoritative *categorical* bulletin term
# (e.g. IMD "MODERATE TO ROUGH") rather than a measured/forecast height. This is
# informational, not a block, but it permanently caps the verdict at
# CLEARED_WITH_CAUTION — a word is not a measurement.
REASON_SEA_STATE_FROM_CATEGORY = "SEA_STATE_DERIVED_FROM_CATEGORY"
# A sea-state term was supplied but is not in the verified WMO 3700 vocabulary.
# Treated as missing evidence, never as calm water.
REASON_SEA_STATE_CATEGORY_UNRECOGNISED = "SEA_STATE_CATEGORY_UNRECOGNISED"
REASON_ROUTE_RISK_INCOMPLETE = "ENVIRONMENTAL_ROUTE_RISK_INCOMPLETE"
REASON_ZONE_STATUS_UNKNOWN = "RESTRICTED_ZONE_OPERATIONAL_STATUS_UNKNOWN"
# Hazard codes (drive a risk-based NOT_CLEARED even with full data).
REASON_HIGH_ENV_RISK = "ENVIRONMENTAL_RISK_TOO_HIGH"
REASON_ACTIVE_HAZARD = "ACTIVE_HAZARD_IN_AREA"
REASON_RESTRICTED_ZONE_ENTRY = "RESTRICTED_ZONE_INTERSECTION"

# Risk levels (from :func:`assess_marine_risk`) that block a clean clearance.
_BLOCKING_RISK_LEVELS = frozenset({"HIGH", "EXTREME"})
_CAUTION_RISK_LEVELS = frozenset({"MODERATE"})


@dataclass
class SafetyDecision:
    """The gate's structured verdict."""

    safety_status: str  # CLEARED | CLEARED_WITH_CAUTION | NOT_CLEARED
    insufficient_data: bool
    reasons: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    # The underlying risk assessment, when it could be computed (inputs present).
    risk: RiskAssessment | None = None
    notes: list[str] = field(default_factory=list)
    # Populated only when sea state was established from a categorical term.
    sea_state: SeaStateBand | None = None

    def as_dict(self) -> dict:
        return {
            "safety_status": self.safety_status,
            "insufficient_data": self.insufficient_data,
            "reason": list(self.reasons),
            "missing_inputs": list(self.missing_inputs),
            "risk": self.risk.as_dict() if self.risk is not None else None,
            "notes": list(self.notes),
            "sea_state": self.sea_state.as_dict() if self.sea_state is not None else None,
        }


def _present(value: float | None) -> bool:
    """True only for a real, finite number (0.0 counts as present)."""
    if value is None:
        return False
    try:
        return value == value  # NaN check without importing math
    except TypeError:
        return False


def evaluate_safety_gate(
    *,
    wave_height: float | None = None,
    wind_speed: float | None = None,
    tide_level: float | None = None,
    swell_height: float | None = None,
    wave_period: float | None = None,
    wind_gust: float | None = None,
    sea_state_category: str | None = None,
    rainfall: float | None = None,
    pressure_trend: float | None = None,
    active_warnings: list[dict] | None = None,
    cyclone_distance_km: float | None = None,
    restricted_zone_intersections: list[dict] | None = None,
    route_risk_complete: bool = True,
    require_tide: bool = False,
    thresholds: RiskThresholds | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    sources: list[dict] | None = None,
) -> SafetyDecision:
    """Return a deterministic ``SafetyDecision``.

    Clearance requires, at minimum, both a **sea-state** input (wave and/or
    swell height) and a **wind** input. If either is absent the gate returns
    ``NOT_CLEARED`` with ``insufficient_data=True`` — regardless of how benign
    any single available reading looks. This is what separates *unknown risk*
    from *low risk*.

    ``require_tide`` promotes tide data to a hard requirement (e.g. shallow-draft
    harbour departures / under-keel-clearance decisions).

    Parameters that describe the operating context (``restricted_zone_intersections``,
    ``route_risk_complete``) let a caller feed in geospatial findings so the gate
    can block on genuinely unresolved conditions — without the gate inventing an
    "unknown" for data it was never given.
    """
    reasons: list[str] = []
    missing: list[str] = []
    notes: list[str] = []

    has_wave = _present(wave_height)
    has_swell = _present(swell_height)
    has_wind = _present(wind_speed)
    has_tide = _present(tide_level)

    # ── 0. Categorical sea state (authoritative word, not a measurement) ───
    # Some bulletins publish only a WMO 3700 / Douglas term. It is accepted as
    # a *fallback* sea-state input when no measured or forecast height exists.
    # The band's upper bound is used so a coarse term can only ever make the
    # decision more pessimistic. Unverified vocabulary is rejected outright.
    sea_state: SeaStateBand | None = None
    derived_wave_height: float | None = None
    if not (has_wave or has_swell) and sea_state_category is not None:
        sea_state = parse_sea_state_category(sea_state_category)
        if sea_state is None:
            reasons.append(REASON_SEA_STATE_CATEGORY_UNRECOGNISED)
        else:
            derived_wave_height = sea_state.conservative_height_m

    has_derived_sea_state = derived_wave_height is not None

    # ── 1. Required-evidence gate (UNKNOWN vs LOW) ─────────────────────────
    # Sea state must be established by a wave/swell value or an authoritative
    # categorical term.
    if not (has_wave or has_swell or has_derived_sea_state):
        missing.append("sea_state")
        reasons.append(REASON_WAVE_UNAVAILABLE)
        reasons.append(REASON_SEA_STATE_UNKNOWN)
    elif has_derived_sea_state:
        reasons.append(REASON_SEA_STATE_FROM_CATEGORY)
        notes.append(
            "Sea state was derived from the authoritative categorical term "
            f"{sea_state.category!r} via {sea_state.labels} "
            f"(WMO 3700 band {sea_state.min_height_m}-{sea_state.max_height_m} m); "
            f"the conservative upper bound {sea_state.conservative_height_m} m was used. "
            "This is not a measured wave height."
        )
    if not has_wind:
        missing.append("wind")
        reasons.append(REASON_WIND_UNAVAILABLE)
    if require_tide and not has_tide:
        missing.append("tide")
        reasons.append(REASON_TIDE_UNAVAILABLE)
    if not route_risk_complete:
        reasons.append(REASON_ROUTE_RISK_INCOMPLETE)

    # Zone intersections whose operational status could not be resolved.
    # NOTE: a zone with a known ``status`` is NOT flagged as "unknown" — the
    # engine knows it. Only entries the caller explicitly marks unresolved
    # (status missing/None/"unknown") trigger the unknown-status reason.
    blocking_zone = False
    for z in restricted_zone_intersections or []:
        status = str(z.get("status") or "").strip().lower()
        ztype = str(z.get("zone_type") or z.get("type") or "").strip().lower()
        if status in ("", "unknown", "none"):
            if REASON_ZONE_STATUS_UNKNOWN not in reasons:
                reasons.append(REASON_ZONE_STATUS_UNKNOWN)
        # An active restricted / prohibited / border zone is a hard block.
        if status == "active" and ztype in (
            "restricted", "prohibited", "border", "eez",
        ):
            blocking_zone = True

    insufficient = bool(missing) or not route_risk_complete or (
        REASON_ZONE_STATUS_UNKNOWN in reasons
    )

    # ── 2. Compute environmental risk when the core inputs exist ───────────
    risk: RiskAssessment | None = None
    if (has_wave or has_swell or has_derived_sea_state) and has_wind:
        risk = assess_marine_risk(
            wave_height=wave_height if has_wave else derived_wave_height,
            wave_period=wave_period,
            swell_height=swell_height,
            wind_speed=wind_speed,
            wind_gust=wind_gust,
            rainfall=rainfall,
            pressure_trend=pressure_trend,
            active_warnings=active_warnings,
            cyclone_distance_km=cyclone_distance_km,
            thresholds=thresholds,
            valid_from=valid_from,
            valid_until=valid_until,
            sources=sources,
        )

    # ── 3. Hazard blocks that apply even with full data ────────────────────
    if active_warnings:
        reasons.append(REASON_ACTIVE_HAZARD)
    if blocking_zone:
        reasons.append(REASON_RESTRICTED_ZONE_ENTRY)
    if risk is not None and risk.risk_level in _BLOCKING_RISK_LEVELS:
        reasons.append(REASON_HIGH_ENV_RISK)

    # ── 4. Decide ──────────────────────────────────────────────────────────
    # Missing required evidence always wins: NOT_CLEARED / insufficient data.
    if insufficient:
        status = STATUS_NOT_CLEARED
        notes.append(
            "Clearance withheld: one or more required safety inputs are "
            "unavailable. Unknown risk is treated as unsafe, not as low risk."
        )
    elif (
        active_warnings
        or blocking_zone
        or (risk is not None and risk.risk_level in _BLOCKING_RISK_LEVELS)
    ):
        status = STATUS_NOT_CLEARED
        notes.append("Clearance withheld: an active hazard or high computed risk blocks departure.")
    elif risk is not None and risk.risk_level in _CAUTION_RISK_LEVELS:
        status = STATUS_CLEARED_WITH_CAUTION
        notes.append(
            "Conditions are marginal; proceed only with active monitoring and an abort plan."
        )
    elif has_derived_sea_state:
        # Inputs present and risk benign, but sea state came from a coarse
        # category rather than a measurement. Never award a full clearance on
        # that basis.
        status = STATUS_CLEARED_WITH_CAUTION
        notes.append(
            "Capped at CLEARED_WITH_CAUTION: sea state rests on a categorical "
            "bulletin term, not a measured or modelled wave height. Obtain a "
            "numeric sea-state source before treating this as a full clearance."
        )
    else:
        status = STATUS_CLEARED
        notes.append("Required inputs present and conditions assessed as low risk.")

    # De-duplicate reasons while preserving order.
    seen: set[str] = set()
    ordered_reasons = [r for r in reasons if not (r in seen or seen.add(r))]

    return SafetyDecision(
        safety_status=status,
        insufficient_data=insufficient,
        reasons=ordered_reasons,
        missing_inputs=missing,
        risk=risk,
        notes=notes,
        sea_state=sea_state,
    )
