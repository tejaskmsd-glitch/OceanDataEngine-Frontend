"""Unit tests for domain event factories."""

from __future__ import annotations

from datetime import UTC, datetime

from marine_data_engine.domain.events import (
    alert_created,
    alert_expired,
    alert_updated,
    dataset_updated,
    pfz_updated,
    processing_completed,
    processing_failed,
    processing_started,
)

_TS = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def _assert_utc_iso(value: str) -> None:
    """Assert a string parses as a UTC ISO-8601 timestamp."""
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_alert_created():
    ev = alert_created("A1", "cyclone", "extreme", "Big storm", _TS)
    assert ev["type"] == "alert.created"
    assert ev["alert_uid"] == "A1"
    assert ev["event_type"] == "cyclone"
    assert ev["severity"] == "extreme"
    assert ev["headline"] == "Big storm"
    assert ev["issued_at"] == _TS.isoformat()
    _assert_utc_iso(ev["timestamp"])


def test_alert_created_none_issued_at():
    ev = alert_created("A1", "cyclone", "extreme", None, None)
    assert ev["headline"] is None
    assert ev["issued_at"] is None


def test_alert_updated():
    ev = alert_updated("A1", {"severity": "severe"})
    assert ev["type"] == "alert.updated"
    assert ev["alert_uid"] == "A1"
    assert ev["changes"] == {"severity": "severe"}
    _assert_utc_iso(ev["timestamp"])


def test_alert_expired():
    ev = alert_expired("A1", _TS)
    assert ev["type"] == "alert.expired"
    assert ev["expired_at"] == _TS.isoformat()
    _assert_utc_iso(ev["timestamp"])


def test_pfz_updated():
    ev = pfz_updated("P1", "Goa", _TS, _TS)
    assert ev["type"] == "pfz.updated"
    assert ev["pfz_uid"] == "P1"
    assert ev["region"] == "Goa"
    assert ev["valid_from"] == _TS.isoformat()
    assert ev["valid_until"] == _TS.isoformat()
    _assert_utc_iso(ev["timestamp"])


def test_pfz_updated_none_fields():
    ev = pfz_updated("P1", None, None, None)
    assert ev["region"] is None
    assert ev["valid_from"] is None
    assert ev["valid_until"] is None


def test_dataset_updated():
    ev = dataset_updated("incois_sst", "healthy", _TS)
    assert ev["type"] == "dataset.updated"
    assert ev["dataset_key"] == "incois_sst"
    assert ev["status"] == "healthy"
    assert ev["last_success_at"] == _TS.isoformat()
    _assert_utc_iso(ev["timestamp"])


def test_processing_started():
    ev = processing_started("J1", "incois_sst", "normalize_sst")
    assert ev["type"] == "processing.started"
    assert ev["job_uid"] == "J1"
    assert ev["dataset_key"] == "incois_sst"
    assert ev["job_type"] == "normalize_sst"
    _assert_utc_iso(ev["timestamp"])


def test_processing_completed():
    ev = processing_completed("J1", "incois_sst", 10, 2, 1500)
    assert ev["type"] == "processing.completed"
    assert ev["records_accepted"] == 10
    assert ev["records_rejected"] == 2
    assert ev["duration_ms"] == 1500
    _assert_utc_iso(ev["timestamp"])


def test_processing_completed_none_duration():
    ev = processing_completed("J1", "incois_sst", 0, 0, None)
    assert ev["duration_ms"] is None


def test_processing_failed():
    ev = processing_failed("J1", "incois_sst", "boom")
    assert ev["type"] == "processing.failed"
    assert ev["error"] == "boom"
    _assert_utc_iso(ev["timestamp"])
