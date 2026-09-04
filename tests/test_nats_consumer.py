"""Tests for the JetStream consumer loop and worker heartbeat.

These exercise :meth:`JetStreamQueue.consume_loop` dispatch logic with mock
JetStream messages — no real NATS broker is required.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from marine_data_engine.db.enums import QueuePriority
from marine_data_engine.messaging.queue import JetStreamQueue
from marine_data_engine.messaging.subjects import WORK_PRIORITIES


class _FakeMsg:
    """A stand-in for a JetStream message with ack/nak tracking."""

    def __init__(self, payload: dict, *, num_delivered: int = 1) -> None:
        import json

        self.data = json.dumps({"payload": payload}).encode("utf-8")
        self.acked = False
        self.naked = False
        self.nak_delay = None

        class _Meta:
            def __init__(self, n):
                self.num_delivered = n

        self.metadata = _Meta(num_delivered)

    async def ack(self) -> None:
        self.acked = True

    async def nak(self, delay=None) -> None:
        self.naked = True
        self.nak_delay = delay


def _new_queue() -> JetStreamQueue:
    return JetStreamQueue(servers="nats://localhost:4222", stream_prefix="TEST", max_deliver=3)


def test_dispatch_routes_by_event_type():
    q = _new_queue()
    seen = []
    handlers = {"alert.created": lambda p: seen.append(p)}
    msg = _FakeMsg({"type": "alert.created", "alert_uid": "A1"})

    asyncio.run(q._dispatch_one(msg, handlers, QueuePriority.CRITICAL_ALERTS))

    assert msg.acked is True
    assert seen == [{"type": "alert.created", "alert_uid": "A1"}]


def test_unknown_event_type_is_acked_not_nakked():
    q = _new_queue()
    msg = _FakeMsg({"type": "does.not.exist"})

    asyncio.run(q._dispatch_one(msg, {}, QueuePriority.NORMAL_INGESTION))

    # Unknown types are acked (not redelivered) so they never poison the stream.
    assert msg.acked is True
    assert msg.naked is False


def test_handler_exception_naks_with_backoff():
    q = _new_queue()

    def boom(_payload):
        raise ValueError("handler failed")

    msg = _FakeMsg({"type": "alert.created"}, num_delivered=2)
    asyncio.run(q._dispatch_one(msg, {"alert.created": boom}, QueuePriority.CRITICAL_ALERTS))

    assert msg.acked is False
    assert msg.naked is True
    assert msg.nak_delay is not None
    assert msg.nak_delay >= 0


def test_async_handler_is_awaited():
    q = _new_queue()
    seen = []

    async def async_handler(payload):
        seen.append(payload["type"])

    msg = _FakeMsg({"type": "processing.completed"})
    asyncio.run(q._dispatch_one(msg, {"processing.completed": async_handler}, WORK_PRIORITIES[0]))

    assert seen == ["processing.completed"]
    assert msg.acked is True


def test_consume_loop_dispatches_and_writes_heartbeat():
    """Drive consume_loop with a fake JetStream that yields one batch then stops."""
    q = _new_queue()
    processed: list[str] = []

    handlers = {"alert.created": lambda p: processed.append(p["alert_uid"])}

    class _FakeSub:
        def __init__(self):
            self._batches = [[_FakeMsg({"type": "alert.created", "alert_uid": "A1"})]]

        async def fetch(self, batch=10, timeout=0.5):  # noqa: ARG002
            if self._batches:
                return self._batches.pop(0)
            # No more messages: stop the loop after first idle poll.
            q.stop()
            return []

    # Pre-populate subscriptions so consume_loop does not call subscribe().
    for pr in WORK_PRIORITIES:
        q._subs[pr] = _FakeSub()

    heartbeat = Path("/tmp/worker_heartbeat")  # noqa: S108
    if heartbeat.exists():
        heartbeat.unlink()

    asyncio.run(q.consume_loop(handlers, poll_interval=0.01))

    assert "A1" in processed
    assert heartbeat.exists()
    assert float(heartbeat.read_text()) > 0
