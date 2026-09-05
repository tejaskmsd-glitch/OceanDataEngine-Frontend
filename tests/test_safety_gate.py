"""Safety-clearance gate regression tests.

These encode the exact safety property the MCP harness is meant to guarantee:
the engine must be able to say "I don't have enough evidence" and must never
convert partial evidence into a clearance. The paired scenarios test that the
system distinguishes UNKNOWN risk (missing input) from LOW risk (input present
and benign).
"""

from __future__ import annotations

from marine_data_engine.domain.safety_gate import (
    REASON_SEA_STATE_UNKNOWN,
    REASON_TIDE_UNAVAILABLE,
    REASON_WAVE_UNAVAILABLE,
    REASON_WIND_UNAVAILABLE,
    STATUS_CLEARED,
    STATUS_NOT_CLEARED,
    evaluate_safety_gate,
)


def test_safety_insufficient_wave_001():
    """SAFETY-INSUFFICIENT-WAVE-001.

    Everything is available and favourable EXCEPT sea state (no wave, no swell).
    Wind is present and benign. The gate must NOT clear: a low wind reading does
    not establish sea state. Unknown risk != low risk.
    """
    decision = evaluate_safety_gate(
        wind_speed=6.16,            # present + benign (as in the Goa run)
        wave_height=None,           # UNAVAILABLE — the whole point
        swell_height=None,
        tide_level=None,
        active_warnings=None,       # no local alerts
        route_risk_complete=True,
    )
    assert decision.safety_status == STATUS_NOT_CLEARED
    assert decision.insufficient_data is True
    assert "sea_state" in decision.missing_inputs
    assert REASON_WAVE_UNAVAILABLE in decision.reasons
    assert REASON_SEA_STATE_UNKNOWN in decision.reasons
    # Wind was present, so it must NOT be reported missing.
    assert REASON_WIND_UNAVAILABLE not in decision.reasons
    # Risk cannot be computed without sea state.
    assert decision.risk is None


def test_all_inputs_present_benign_is_cleared():
    """Complementary case: all required inputs present + benign -> CLEARED.

    This is what proves the system can distinguish LOW risk from UNKNOWN risk:
    identical wind to the insufficient case, but now sea state is known and calm.
    """
    decision = evaluate_safety_gate(
        wave_height=0.9,            # known + calm
        wind_speed=6.16,
        swell_height=0.8,
        tide_level=1.85,
        active_warnings=None,
        route_risk_complete=True,
    )
    assert decision.safety_status == STATUS_CLEARED
    assert decision.insufficient_data is False
    assert decision.missing_inputs == []
    assert decision.reasons == []
    assert decision.risk is not None
    assert decision.risk.risk_level == "LOW"


def test_missing_wind_is_not_cleared():
    """Wind absent but sea state present still blocks clearance."""
    decision = evaluate_safety_gate(
        wave_height=0.9,
        wind_speed=None,
        route_risk_complete=True,
    )
    assert decision.safety_status == STATUS_NOT_CLEARED
    assert decision.insufficient_data is True
    assert "wind" in decision.missing_inputs
    assert REASON_WIND_UNAVAILABLE in decision.reasons


def test_require_tide_blocks_when_tide_missing():
    """Under-keel-clearance style departures can require tide as a hard input."""
    decision = evaluate_safety_gate(
        wave_height=0.9,
        wind_speed=6.16,
        tide_level=None,
        require_tide=True,
    )
    assert decision.safety_status == STATUS_NOT_CLEARED
    assert "tide" in decision.missing_inputs
    assert REASON_TIDE_UNAVAILABLE in decision.reasons


def test_high_env_risk_blocks_even_with_full_data():
    """Full data but dangerous conditions -> NOT_CLEARED (not insufficient)."""
    decision = evaluate_safety_gate(
        wave_height=7.0,            # extreme
        wind_speed=28.0,           # extreme
        route_risk_complete=True,
    )
    assert decision.safety_status == STATUS_NOT_CLEARED
    # This is a HAZARD block, not a data gap.
    assert decision.insufficient_data is False
    assert decision.risk is not None
    assert decision.risk.risk_level in ("HIGH", "EXTREME")


def test_incomplete_route_risk_flags_reason():
    """A geometry-only route (no environmental risk along it) is insufficient."""
    from marine_data_engine.domain.safety_gate import REASON_ROUTE_RISK_INCOMPLETE

    decision = evaluate_safety_gate(
        wave_height=0.9,
        wind_speed=6.16,
        route_risk_complete=False,
    )
    assert decision.safety_status == STATUS_NOT_CLEARED
    assert decision.insufficient_data is True
    assert REASON_ROUTE_RISK_INCOMPLETE in decision.reasons


def test_known_zone_status_is_not_flagged_unknown():
    """A zone with a known status must NOT trigger the 'unknown status' reason.

    Contradicts the naive assumption that restricted-zone status is always
    unknown — the engine knows it when the data carries a status.
    """
    from marine_data_engine.domain.safety_gate import (
        REASON_RESTRICTED_ZONE_ENTRY,
        REASON_ZONE_STATUS_UNKNOWN,
    )

    decision = evaluate_safety_gate(
        wave_height=0.9,
        wind_speed=6.16,
        restricted_zone_intersections=[
            {"zone_type": "restricted", "status": "active", "name": "Mormugao Naval"}
        ],
    )
    # Status is known (active) -> not an "unknown status" case ...
    assert REASON_ZONE_STATUS_UNKNOWN not in decision.reasons
    # ... but an active restricted-zone intersection is a hard block.
    assert decision.safety_status == STATUS_NOT_CLEARED
    assert REASON_RESTRICTED_ZONE_ENTRY in decision.reasons
