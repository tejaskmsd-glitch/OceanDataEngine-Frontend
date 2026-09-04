"""Queue priority isolation, retry/backoff, DLQ, and worker tests."""

from __future__ import annotations

from marine_data_engine.db.enums import QueuePriority
from marine_data_engine.messaging.queue import InMemoryQueue
from marine_data_engine.messaging.subjects import backoff_delay_seconds
from marine_data_engine.worker.runtime import Worker


def test_priority_isolation_orders_critical_first():
    q = InMemoryQueue(backoff_base=0.0, backoff_max=0.0)
    q.publish(priority=QueuePriority.BACKFILL_ARCHIVE, payload={"type": "x"}, idempotency_key="a")
    q.publish(priority=QueuePriority.CRITICAL_ALERTS, payload={"type": "x"}, idempotency_key="b")
    q.publish(priority=QueuePriority.NORMAL_INGESTION, payload={"type": "x"}, idempotency_key="c")

    first = q.next_ready()
    assert first.priority == QueuePriority.CRITICAL_ALERTS


def test_enqueue_is_idempotent():
    q = InMemoryQueue()
    m1 = q.publish(priority=QueuePriority.NORMAL_INGESTION, payload={}, idempotency_key="dup")
    m2 = q.publish(priority=QueuePriority.NORMAL_INGESTION, payload={}, idempotency_key="dup")
    assert m1 is not None
    assert m2 is None
    assert q.depth() == 1


def test_backoff_is_monotonic_without_jitter():
    d1 = backoff_delay_seconds(1, base=2.0, jitter=False)
    d2 = backoff_delay_seconds(2, base=2.0, jitter=False)
    d3 = backoff_delay_seconds(3, base=2.0, jitter=False)
    assert d1 < d2 < d3
    assert backoff_delay_seconds(20, base=2.0, maximum=300.0, jitter=False) == 300.0


def test_retry_then_dead_letter():
    q = InMemoryQueue(backoff_base=0.0, backoff_max=0.0)
    q.publish(
        priority=QueuePriority.NORMAL_INGESTION,
        payload={"type": "boom"},
        idempotency_key="k",
        max_attempts=3,
    )

    def handler(_payload):
        raise ValueError("always fails")

    worker = Worker(q, {"boom": handler})
    # 3 attempts: first two retry, third dead-letters.
    worker.run_once()
    assert q.dlq_depth() == 0
    worker.run_once()
    assert q.dlq_depth() == 0
    worker.run_once()
    assert q.dlq_depth(QueuePriority.NORMAL_INGESTION) == 1
    assert q.depth() == 0


def test_worker_success_acks():
    q = InMemoryQueue()
    processed = []
    q.publish(
        priority=QueuePriority.NORMAL_INGESTION,
        payload={"type": "ok", "v": 1},
        idempotency_key="k",
    )
    worker = Worker(q, {"ok": lambda p: processed.append(p["v"])})
    count = worker.drain()
    assert count == 1
    assert processed == [1]
    assert q.depth() == 0
