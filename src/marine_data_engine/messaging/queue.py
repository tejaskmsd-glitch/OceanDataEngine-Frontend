"""Work queue abstraction with priority isolation, retries, and DLQ.

Two backends:

- :class:`InMemoryQueue` — deterministic, dependency-free. Implements priority
  isolation, idempotent enqueue, attempt tracking, backoff scheduling, and
  dead-lettering. Used by tests and single-process local runs.
- :class:`JetStreamQueue` — NATS JetStream backend (async). Publishes to
  per-priority subjects and dead-letters after ``max_deliver`` attempts.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..db.enums import QueuePriority
from .subjects import PRIORITY_RANK, backoff_delay_seconds, dlq_subject, work_subject


@dataclass
class Message:
    """A unit of work on the queue."""

    subject: str
    priority: QueuePriority
    payload: dict
    idempotency_key: str
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    attempts: int = 0
    max_attempts: int = 5
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    not_before: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    last_error: str | None = None

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "subject": self.subject,
                "priority": self.priority.value,
                "payload": self.payload,
                "idempotency_key": self.idempotency_key,
                "message_id": self.message_id,
                "attempts": self.attempts,
                "max_attempts": self.max_attempts,
                "enqueued_at": self.enqueued_at.isoformat(),
            }
        ).encode("utf-8")


class InMemoryQueue:
    """Deterministic in-memory priority queue with retries and DLQ."""

    def __init__(self, *, backoff_base: float = 2.0, backoff_max: float = 300.0) -> None:
        self._pending: list[Message] = []
        self._dlq: list[Message] = []
        self._seen_keys: set[str] = set()
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max

    # -- producer -------------------------------------------------------- #
    def publish(
        self,
        *,
        priority: QueuePriority,
        payload: dict,
        idempotency_key: str,
        max_attempts: int = 5,
    ) -> Message | None:
        """Enqueue a message. Idempotent: duplicate keys are dropped."""
        if idempotency_key in self._seen_keys:
            return None
        self._seen_keys.add(idempotency_key)
        msg = Message(
            subject=f"work.{priority.value}",
            priority=priority,
            payload=payload,
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
        )
        self._pending.append(msg)
        return msg

    # -- consumer -------------------------------------------------------- #
    def _sort(self) -> None:
        # Strict priority isolation: higher-priority classes drain first, then
        # by readiness time, then by enqueue order.
        self._pending.sort(
            key=lambda m: (PRIORITY_RANK[m.priority], m.not_before, m.enqueued_at)
        )

    def next_ready(self, *, now: datetime | None = None) -> Message | None:
        """Return the highest-priority message that is ready to run."""
        now = now or datetime.now(tz=UTC)
        self._sort()
        for msg in self._pending:
            if msg.not_before <= now:
                return msg
        return None

    def ack(self, msg: Message) -> None:
        """Acknowledge successful processing; remove from the queue."""
        if msg in self._pending:
            self._pending.remove(msg)

    def nack(self, msg: Message, *, error: str, now: datetime | None = None) -> bool:
        """Record a failure. Returns True if dead-lettered.

        Applies exponential backoff with jitter; after ``max_attempts`` the
        message is moved to the DLQ.
        """
        now = now or datetime.now(tz=UTC)
        msg.attempts += 1
        msg.last_error = error
        if msg.attempts >= msg.max_attempts:
            if msg in self._pending:
                self._pending.remove(msg)
            self._dlq.append(msg)
            return True
        delay = backoff_delay_seconds(
            msg.attempts, base=self._backoff_base, maximum=self._backoff_max
        )
        from datetime import timedelta

        msg.not_before = now + timedelta(seconds=delay)
        return False

    # -- introspection --------------------------------------------------- #
    def depth(self, priority: QueuePriority | None = None) -> int:
        if priority is None:
            return len(self._pending)
        return sum(1 for m in self._pending if m.priority == priority)

    def dlq_depth(self, priority: QueuePriority | None = None) -> int:
        if priority is None:
            return len(self._dlq)
        return sum(1 for m in self._dlq if m.priority == priority)

    def dlq_messages(self) -> list[Message]:
        return list(self._dlq)


class JetStreamQueue:
    """NATS JetStream-backed queue (async).

    This is a thin production adapter. It is intentionally not exercised by the
    deterministic test suite (which uses :class:`InMemoryQueue`); it documents
    the JetStream contract: per-priority subjects, ``max_deliver`` redelivery,
    and DLQ publication on exhaustion.
    """

    def __init__(self, *, servers: str, stream_prefix: str, max_deliver: int = 5) -> None:
        self._servers = servers
        self._prefix = stream_prefix
        self._max_deliver = max_deliver
        self._nc = None
        self._js = None
        # Per-priority durable pull subscriptions, created by subscribe().
        self._subs: dict[QueuePriority, object] = {}
        self._running = False

    async def connect(self) -> None:
        import nats  # noqa: PLC0415

        self._nc = await nats.connect(self._servers)
        self._js = self._nc.jetstream()
        # Streams are declared per-priority so each has an isolated retention
        # and consumer configuration.
        from .subjects import WORK_PRIORITIES, dlq_subject, work_subject

        for pr in WORK_PRIORITIES:
            await self._js.add_stream(
                name=f"{self._prefix}_{pr.value}",
                subjects=[work_subject(self._prefix, pr), dlq_subject(self._prefix, pr)],
            )

    async def publish(self, *, priority: QueuePriority, message: Message) -> None:
        assert self._js is not None, "connect() must be called first"
        await self._js.publish(work_subject(self._prefix, priority), message.to_bytes())

    def publish_sync(
        self,
        *,
        priority: QueuePriority,
        payload: dict,
        idempotency_key: str,
        max_attempts: int = 5,
    ) -> Message:
        """Synchronous producer wrapper for use from sync code.

        Builds a :class:`Message` and publishes it, connecting on first use.
        Wraps the async publish in :func:`asyncio.run`. This is the production
        path: when NATS is reachable, events flow here instead of to the
        in-memory queue. Not for use inside an already-running event loop.
        """
        msg = Message(
            subject=work_subject(self._prefix, priority),
            priority=priority,
            payload=payload,
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
        )

        async def _run() -> None:
            if self._js is None:
                await self.connect()
            await self.publish(priority=priority, message=msg)

        asyncio.run(_run())
        return msg

    async def close(self) -> None:
        self._running = False
        if self._nc is not None:
            await self._nc.drain()

    # -- durable pull consumer ------------------------------------------ #
    async def subscribe(self, priority: QueuePriority, handler: Callable) -> None:
        """Create a durable pull subscriber for one priority stream.

        The durable name is derived from the priority so a restarted worker
        resumes from the same consumer cursor. ``handler`` is stored implicitly
        via :meth:`consume_loop`; this method only establishes the subscription.
        """
        assert self._js is not None, "connect() must be called first"
        from nats.js.api import ConsumerConfig  # noqa: PLC0415

        durable = f"{self._prefix}_{priority.value}_worker"
        # C1 fix: explicitly specify stream name to avoid
        # find_stream_name_by_subject timeout in NATS JetStream.
        stream_name = f"{self._prefix}_{priority.value}"
        sub = await self._js.pull_subscribe(
            subject=work_subject(self._prefix, priority),
            durable=durable,
            stream=stream_name,
            config=ConsumerConfig(max_deliver=self._max_deliver, ack_wait=30),
        )
        self._subs[priority] = sub

    async def _dispatch_one(
        self, msg, handlers: dict[str, Callable], priority: QueuePriority
    ) -> None:
        """Decode, dispatch, and ack/nack a single JetStream message."""
        try:
            envelope = json.loads(msg.data)
            payload = envelope.get("payload", envelope)
            event_type = payload.get("type", "")
            handler = handlers.get(event_type)
            if handler is None:
                # H15 fix: log unknown event types for observability.
                import logging  # noqa: PLC0415
                logging.getLogger("marine_data_engine.queue").warning(
                    "unknown event type %r on priority=%s — acked to avoid poison",
                    event_type, priority.value,
                )
                await msg.ack()
                return
            result = handler(payload)
            if asyncio.iscoroutine(result):
                await result
            await msg.ack()
        except Exception as exc:  # noqa: BLE001
            # Respect max_deliver: NAK for redelivery with backoff. JetStream
            # dead-letters (stops redelivery) once num_delivered > max_deliver.
            import logging as _logging  # noqa: PLC0415
            _dlog = _logging.getLogger("marine_data_engine.queue")
            meta = getattr(msg, "metadata", None)
            delivered = getattr(getattr(meta, "num_delivered", None), "real", None)
            num_delivered = delivered or 1
            delay = backoff_delay_seconds(num_delivered)
            # H14 fix: publish to DLQ when retries exhausted.
            if num_delivered >= self._max_deliver:
                try:
                    dlq_payload = {
                        "original": envelope,
                        "error": str(exc),
                        "attempts": num_delivered,
                    }
                    await self._js.publish(
                        dlq_subject(self._prefix, priority),
                        json.dumps(dlq_payload).encode("utf-8"),
                    )
                except Exception:  # noqa: BLE001
                    _dlog.error("DLQ publish failed for priority=%s", priority.value)
                await msg.ack()
                _dlog.warning(
                    "message dead-lettered: priority=%s type=%s attempts=%d error=%s",
                    priority.value, event_type, num_delivered, exc,
                )
                return
            try:
                await msg.nak(delay=delay)
            except TypeError:  # pragma: no cover - older client signature
                await msg.nak()

    async def consume_loop(
        self, handlers: dict[str, Callable], *, poll_interval: float = 0.5
    ) -> None:
        """Poll all priority consumers in strict priority order and dispatch.

        Higher-priority streams are fully drained before lower-priority ones are
        polled, preserving priority isolation. A heartbeat file is refreshed
        every iteration so the container HEALTHCHECK can observe liveness.
        """
        import pathlib  # noqa: PLC0415
        import time  # noqa: PLC0415

        from .subjects import WORK_PRIORITIES  # noqa: PLC0415

        for pr in WORK_PRIORITIES:
            if pr not in self._subs:
                await self.subscribe(pr, handlers)

        self._running = True
        heartbeat = pathlib.Path("/tmp/worker_heartbeat")  # noqa: S108
        while self._running:
            try:
                heartbeat.write_text(str(time.time()))
            except OSError:  # pragma: no cover - non-fatal
                pass
            did_work = False
            for pr in WORK_PRIORITIES:
                sub = self._subs.get(pr)
                if sub is None:
                    continue
                try:
                    msgs = await sub.fetch(batch=10, timeout=poll_interval)
                except Exception:  # noqa: BLE001 - timeout => no messages
                    msgs = []
                for msg in msgs:
                    did_work = True
                    await self._dispatch_one(msg, handlers, pr)
                if did_work:
                    # Re-poll from the top so newly-arrived critical work wins.
                    break
            if not did_work:
                await asyncio.sleep(poll_interval)

    def stop(self) -> None:
        """Request a clean exit from :meth:`consume_loop`."""
        self._running = False
