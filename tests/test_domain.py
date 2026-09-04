"""Unit tests for deterministic domain logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from marine_data_engine.db.enums import QCStatus
from marine_data_engine.domain.crs import (
    ensure_wgs84_point,
    reproject_bbox,
    validate_wgs84_bounds,
)
from marine_data_engine.domain.crs import (
    normalize_longitude as crs_normalize_longitude,
)
from marine_data_engine.domain.freshness import compute_freshness
from marine_data_engine.domain.geo import (
    bearing_deg,
    geometry_centroid,
    haversine_km,
    normalize_longitude,
    point_in_geometry,
)
from marine_data_engine.domain.idempotency import make_idempotency_key
from marine_data_engine.domain.qc import qc_geometry_record, qc_observation

_SQUARE = {
    "type": "Polygon",
    "coordinates": [[[73.4, 15.55], [73.6, 15.55], [73.6, 15.35], [73.4, 15.35], [73.4, 15.55]]],
}


def test_haversine_known_distance():
    # ~111 km per degree of latitude near the equator.
    d = haversine_km(0.0, 0.0, 1.0, 0.0)
    assert 110.0 < d < 112.0


def test_bearing_due_east_is_90():
    assert abs(bearing_deg(0.0, 0.0, 0.0, 1.0) - 90.0) < 0.5


def test_normalize_longitude():
    assert normalize_longitude(190.0) == -170.0
    assert normalize_longitude(73.5) == 73.5


def test_centroid_and_point_in_polygon():
    lat, lon = geometry_centroid(_SQUARE)
    assert 15.3 < lat < 15.6
    assert 73.4 < lon < 73.6
    assert point_in_geometry(15.45, 73.5, _SQUARE) is True
    assert point_in_geometry(0.0, 0.0, _SQUARE) is False


def test_freshness_fresh_and_stale():
    now = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    fresh = compute_freshness(
        now - timedelta(minutes=30), now=now, expected_update_interval_s=3600
    )
    assert fresh.is_stale is False
    assert fresh.freshness_score > 0.0

    stale = compute_freshness(
        now - timedelta(hours=10), now=now, expected_update_interval_s=3600, stale_multiplier=3.0
    )
    assert stale.is_stale is True
    assert stale.freshness_score == 0.0


def test_freshness_none_reference_is_stale():
    fr = compute_freshness(None, expected_update_interval_s=3600)
    assert fr.is_stale is True
    assert fr.freshness_score == 0.0


def test_idempotency_stable_and_distinct():
    a = make_idempotency_key("IMD", "imd_cap", "X1", None)
    b = make_idempotency_key("IMD", "imd_cap", "X1", None)
    c = make_idempotency_key("IMD", "imd_cap", "X2", None)
    assert a == b
    assert a != c


def test_qc_observation_accept_and_outlier():
    now = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    ok = qc_observation(
        parameter="sea_surface_temperature",
        value=28.0,
        latitude=15.0,
        longitude=73.0,
        observed_at=now - timedelta(hours=1),
        now=now,
    )
    assert ok.status == QCStatus.ACCEPTED

    outlier = qc_observation(
        parameter="sea_surface_temperature",
        value=999.0,
        latitude=15.0,
        longitude=73.0,
        observed_at=now - timedelta(hours=1),
        now=now,
    )
    assert outlier.status == QCStatus.QUARANTINED
    assert outlier.outlier_flag is True


def test_qc_observation_rejects_future_and_bad_coords():
    now = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    future = qc_observation(
        parameter="wind_speed",
        value=5.0,
        latitude=15.0,
        longitude=73.0,
        observed_at=now + timedelta(hours=1),
        now=now,
    )
    assert future.status == QCStatus.REJECTED

    bad = qc_observation(
        parameter="wind_speed",
        value=5.0,
        latitude=999.0,
        longitude=73.0,
        observed_at=now,
        now=now,
    )
    assert bad.status == QCStatus.REJECTED


def test_qc_geometry_window_ordering():
    now = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    bad = qc_geometry_record(
        geometry=_SQUARE, valid_from=now, valid_until=now - timedelta(hours=1)
    )
    assert bad.status == QCStatus.REJECTED
    good = qc_geometry_record(
        geometry=_SQUARE, valid_from=now, valid_until=now + timedelta(hours=1)
    )
    assert good.status == QCStatus.ACCEPTED


# --------------------------------------------------------------------------- #
# CRS normalization
# --------------------------------------------------------------------------- #
def test_crs_normalize_longitude_wraps():
    assert crs_normalize_longitude(190.0) == -170.0
    assert crs_normalize_longitude(360.0) == 0.0
    assert crs_normalize_longitude(73.5) == 73.5


def test_crs_validate_wgs84_bounds():
    assert validate_wgs84_bounds(15.0, 73.5) is True
    assert validate_wgs84_bounds(91.0, 73.5) is False
    assert validate_wgs84_bounds(15.0, 181.0) is False
    assert validate_wgs84_bounds(None, 73.5) is False


def test_crs_ensure_wgs84_point_normalizes_lon():
    lat, lon = ensure_wgs84_point(15.0, 190.0)
    assert lat == 15.0
    assert lon == -170.0


def test_crs_ensure_wgs84_point_rejects_bad_lat():
    import pytest

    with pytest.raises(ValueError):
        ensure_wgs84_point(95.0, 73.5)


def test_crs_reproject_bbox_roundtrip_mercator():
    wgs = (73.0, 15.0, 74.0, 16.0)
    merc = reproject_bbox(wgs, "EPSG:4326", "EPSG:3857")
    back = reproject_bbox(merc, "EPSG:3857", "EPSG:4326")
    for a, b in zip(wgs, back, strict=True):
        assert abs(a - b) < 1e-6
    # Identity when CRS match.
    assert reproject_bbox(wgs, "EPSG:4326", "EPSG:4326") == wgs
