"""Canonical enumerations shared across models, schemas, and services."""

from __future__ import annotations

from enum import StrEnum


class QCStatus(StrEnum):
    """Quality-control disposition for a record."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"
    UNKNOWN = "unknown"


class DatasetStatus(StrEnum):
    """Operational status of a registered dataset."""

    HEALTHY = "healthy"
    STALE = "stale"
    DEGRADED = "degraded"
    FAILED = "failed"
    DISABLED = "disabled"


class JobStatus(StrEnum):
    """Lifecycle status for ingestion/processing jobs."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    DEAD_LETTER = "dead_letter"


class QueuePriority(StrEnum):
    """Priority isolation classes for the work queue.

    Ordered from most to least urgent. Critical alerts must never be blocked
    by low-priority archival/backfill work.
    """

    CRITICAL_ALERTS = "critical_alerts"
    REALTIME_OBSERVATIONS = "realtime_observations"
    NORMAL_INGESTION = "normal_ingestion"
    SCIENTIFIC = "scientific"
    BACKFILL_ARCHIVE = "backfill_archive"


class Severity(StrEnum):
    """Normalized alert severity (CAP-aligned)."""

    UNKNOWN = "unknown"
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"
    EXTREME = "extreme"


class Certainty(StrEnum):
    """Normalized CAP certainty."""

    UNKNOWN = "unknown"
    UNLIKELY = "unlikely"
    POSSIBLE = "possible"
    LIKELY = "likely"
    OBSERVED = "observed"


class Urgency(StrEnum):
    """Normalized CAP urgency."""

    UNKNOWN = "unknown"
    PAST = "past"
    FUTURE = "future"
    EXPECTED = "expected"
    IMMEDIATE = "immediate"
