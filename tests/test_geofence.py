"""Tests for the geofence service (in-memory marine zones)."""

from __future__ import annotations

from marine_data_engine.db.models import MarineZone
from marine_data_engine.services.geofence import (
    check_point_in_zones,
    find_nearby_zones,
    find_route_intersections,
)

# A small square zone around (15.45N, 73.5E) off Goa.
_SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [[73.4, 15.55], [73.6, 15.55], [73.6, 15.35], [73.4, 15.35], [73.4, 15.55]]
    ],
}


def _add_zone(session, uid: str = "zone-goa-restricted") -> None:
    session.add(
        MarineZone(
            zone_uid=uid,
            zone_type="restricted",
            name="Goa Restricted Area",
            status="active",
            restriction="no fishing",
            authority="Test Authority",
            geometry=_SQUARE,
        )
    )
    session.commit()


def test_no_zones_returns_source_gap(db_session):
    result = check_point_in_zones(db_session, 15.45, 73.5)
    assert len(result) == 1
    assert result[0].get("source_gap") is True
    assert "SOURCE_GAP" in result[0]["warning"]


def test_point_inside_zone_detected(db_session):
    _add_zone(db_session)
    inside = check_point_in_zones(db_session, 15.45, 73.5)
    assert len(inside) == 1
    assert inside[0]["zone_uid"] == "zone-goa-restricted"
    assert inside[0]["inside"] is True

    outside = check_point_in_zones(db_session, 10.0, 60.0)
    assert outside == []


def test_find_nearby_zones_by_radius(db_session):
    _add_zone(db_session)
    near = find_nearby_zones(db_session, 15.45, 73.5, radius_km=10.0)
    assert len(near) == 1
    assert near[0]["distance_km"] == 0.0  # containment

    far = find_nearby_zones(db_session, 20.0, 73.5, radius_km=50.0)
    assert far == []


def test_route_intersection_detected(db_session):
    _add_zone(db_session)
    line = {
        "type": "LineString",
        "coordinates": [[73.3, 15.45], [73.7, 15.45]],  # crosses the square
    }
    hits = find_route_intersections(db_session, line)
    assert len(hits) == 1
    assert hits[0]["zone_uid"] == "zone-goa-restricted"


def test_route_intersection_no_zones_source_gap(db_session):
    line = {"type": "LineString", "coordinates": [[73.3, 15.45], [73.7, 15.45]]}
    result = find_route_intersections(db_session, line)
    assert result[0].get("source_gap") is True
