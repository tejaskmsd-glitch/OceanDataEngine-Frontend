"""Queue subjects, priority isolation, and backoff/DLQ semantics.

Priority isolation is achieved by giving each :class:`QueuePriority` class its
own JetStream subject (and, in production, its own stream/consumer with its own
worker pool). This guarantees that low-priority backfill/archive work can never
block critical alert delivery.

Subjects (prefix ``MARINE`` configurable):

    work.<priority>            work items awaiting processing
    work.<priority>.dlq        dead-letter for exhausted retries
    events.alerts              alert.* lifecycle events (fan-out to WS)
    events.datasets            dataset/processing status events

Dead-letter semantics: after ``max_deliver`` failed attempts a message is
published to the matching ``.dlq`` subject with its failure metadata and is not
redelivered on the primary subject.
"""

from __future__ import annotations

import random

from ..db.enums import QueuePriority

WORK_PRIORITIES: tuple[QueuePriority, ...] = (
    QueuePriority.CRITICAL_ALERTS,
    QueuePriority.REALTIME_OBSERVATIONS,
    QueuePriority.NORMAL_INGESTION,
    QueuePriority.SCIENTIFIC,
    QueuePriority.BACKFILL_ARCHIVE,
)

# Lower number == higher urgency (used for ordered draining in-memory).
PRIORITY_RANK: dict[QueuePriority, int] = {p: i for i, p in enumerate(WORK_PRIORITIES)}


def work_subject(prefix: str, priority: QueuePriority) -> str:
    return f"{prefix}.work.{priority.value}"


def dlq_subject(prefix: str, priority: QueuePriority) -> str:
    return f"{prefix}.work.{priority.value}.dlq"


EVENTS_ALERTS = "events.alerts"
EVENTS_DATASETS = "events.datasets"


def events_subject(prefix: str, name: str) -> str:
    return f"{prefix}.{name}"


def backoff_delay_seconds(
    attempt: int,
    *,
    base: float = 2.0,
    maximum: float = 300.0,
    jitter: bool = True,
) -> float:
    """Exponential backoff with full jitter.

    attempt is 1-based (first retry => attempt=1).
    """
    raw = min(maximum, base * (2 ** max(0, attempt - 1)))
    if jitter:
        return random.uniform(0, raw)
    return raw
