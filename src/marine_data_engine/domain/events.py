"""Domain event factories.

Pure functions that build the JSON-serialisable event payloads published on the
queue / NATS JetStream ``events.*`` subjects and fanned out to WebSocket
subscribers. Each factory returns a plain ``dict`` with:

- ``type``: one of the documented event names (see below),
- ``timestamp``: the event creation time as a UTC ISO-8601 string,
- plus the event-specific fields.

Documented event names (messaging contract):

    alert.created, alert.updated, alert.expired,
    pfz.updated,
    dataset.updated,
    processing.started, processing.completed, processing.failed
"""

from __future__ import annotations

from datetime import UTC, datetime


def _now_iso() -> str:
    """Current time as a UTC ISO-8601 string."""
    return datetime.now(tz=UTC).isoformat()


def _iso(value: datetime | None) -> str | None:
    """Serialise an optional datetime to ISO-8601 (``None`` passes through)."""
    return value.isoformat() if value is not None else None


def alert_created(
    alert_uid: str,
    event_type: str,
    severity: str,
    headline: str | None,
    issued_at: datetime | None,
) -> dict:
    """Build an ``alert.created`` event."""
    return {
        "type": "alert.created",
        "timestamp": _now_iso(),
        "alert_uid": alert_uid,
        "event_type": event_type,
        "severity": severity,
        "headline": headline,
        "issued_at": _iso(issued_at),
    }


def alert_updated(alert_uid: str, changes: dict) -> dict:
    """Build an ``alert.updated`` event carrying the changed fields."""
    return {
        "type": "alert.updated",
        "timestamp": _now_iso(),
        "alert_uid": alert_uid,
        "changes": changes,
    }


def alert_expired(alert_uid: str, expired_at: datetime) -> dict:
    """Build an ``alert.expired`` event."""
    return {
        "type": "alert.expired",
        "timestamp": _now_iso(),
        "alert_uid": alert_uid,
        "expired_at": _iso(expired_at),
    }


def pfz_updated(
    pfz_uid: str,
    region: str | None,
    valid_from: datetime | None,
    valid_until: datetime | None,
) -> dict:
    """Build a ``pfz.updated`` event."""
    return {
        "type": "pfz.updated",
        "timestamp": _now_iso(),
        "pfz_uid": pfz_uid,
        "region": region,
        "valid_from": _iso(valid_from),
        "valid_until": _iso(valid_until),
    }


def observation_ingested(
    station_id: str,
    parameter: str,
    value: float | None,
    unit: str | None,
    observed_at: datetime | None,
) -> dict:
    """Build an ``observation.ingested`` event."""
    return {
        "type": "observation.ingested",
        "timestamp": _now_iso(),
        "station_id": station_id,
        "parameter": parameter,
        "value": value,
        "unit": unit,
        "observed_at": _iso(observed_at),
    }


def dataset_updated(
    dataset_key: str, status: str, last_success_at: datetime | None
) -> dict:
    """Build a ``dataset.updated`` event."""
    return {
        "type": "dataset.updated",
        "timestamp": _now_iso(),
        "dataset_key": dataset_key,
        "status": status,
        "last_success_at": _iso(last_success_at),
    }


def processing_started(job_uid: str, dataset_key: str, job_type: str) -> dict:
    """Build a ``processing.started`` event."""
    return {
        "type": "processing.started",
        "timestamp": _now_iso(),
        "job_uid": job_uid,
        "dataset_key": dataset_key,
        "job_type": job_type,
    }


def processing_completed(
    job_uid: str,
    dataset_key: str,
    records_accepted: int,
    records_rejected: int,
    duration_ms: int | None,
) -> dict:
    """Build a ``processing.completed`` event."""
    return {
        "type": "processing.completed",
        "timestamp": _now_iso(),
        "job_uid": job_uid,
        "dataset_key": dataset_key,
        "records_accepted": records_accepted,
        "records_rejected": records_rejected,
        "duration_ms": duration_ms,
    }


def processing_failed(job_uid: str, dataset_key: str, error: str) -> dict:
    """Build a ``processing.failed`` event."""
    return {
        "type": "processing.failed",
        "timestamp": _now_iso(),
        "job_uid": job_uid,
        "dataset_key": dataset_key,
        "error": error,
    }
