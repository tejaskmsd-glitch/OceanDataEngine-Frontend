"""Tests for the deterministic route risk service."""

from __future__ import annotations

from datetime import UTC, datetime

from marine_data_engine.services.routing import compute_safe_route

# Two points off the west coast of India (~ Mumbai to Goa area, offshore).
_START = (18.9, 72.8)
_END = (15.3, 73.7)


def test_partial_route_without_env_data():
    r = compute_safe_route(start=_START, end=_END, segment_km=100.0)
    assert r.status == "partial"
    assert r.total_distance_km > 300.0
    assert len(r.segments) >= 3
    assert r.geometry["type"] == "LineString"
    # First/last vertices match start/end (lon, lat order).
    assert abs(r.geometry["coordinates"][0][1] - _START[0]) < 0.01
    assert abs(r.geometry["coordinates"][-1][0] - _END[1]) < 0.01
    assert any("SOURCE_GAP" in w for w in r.warnings)


def test_duration_scales_with_speed():
    slow = compute_safe_route(start=_START, end=_END, vessel_speed_knots=5.0)
    fast = compute_safe_route(start=_START, end=_END, vessel_speed_knots=20.0)
    assert slow.estimated_duration_hours > fast.estimated_duration_hours


def test_env_sampler_produces_computed_status_and_risk():
    def rough_env(lat, lon, eta):
        return {"wave_height": 5.5, "wind_speed": 24.0, "current_speed": 1.2}

    r = compute_safe_route(
        start=_START, end=_END, segment_km=150.0, env_sampler=rough_env
    )
    assert r.status == "computed"
    assert r.route_risk_score > 50.0
    assert all(s.risk_score > 0 for s in r.segments)
    assert r.major_risk_drivers  # at least one driver identified


def test_zone_checker_populates_avoided_zones():
    def zone_hit(geometry):
        return [{"zone_uid": "z1", "name": "Test MPA"}]

    r = compute_safe_route(
        start=_START, end=_END, segment_km=200.0, zone_checker=zone_hit
    )
    assert "Test MPA" in r.avoided_zones
    assert all(s.penalties["zone_penalty"] == 20.0 for s in r.segments)


def test_departure_time_is_accepted():
    dep = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
    r = compute_safe_route(
        start=_START, end=_END, departure_time=dep, vessel_speed_knots=10.0
    )
    assert r.estimated_duration_hours is not None
    assert r.total_distance_km > 0
