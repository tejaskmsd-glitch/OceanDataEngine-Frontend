"""Worker runtime.

A single-process worker that drains the priority-isolated queue. Higher-priority
classes are always served first; failed handlers are retried with exponential
backoff and dead-lettered after exhausting attempts. This runtime is
deterministic and drives the in-memory queue used by tests; the production
deployment binds the same handler dispatch to a JetStream consumer.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from ..db.enums import JobStatus
from ..logging_config import get_logger
from ..messaging.queue import InMemoryQueue, Message
from ..messaging.subjects import WORK_PRIORITIES
from ..metrics import DLQ_DEPTH, JOB_TOTAL, QUEUE_DEPTH

log = get_logger("worker")

# A handler receives a message payload and either returns (success) or raises.
Handler = Callable[[dict], None]

# --------------------------------------------------------------------------- #
# Default event-type handlers.
#
# The worker dispatches on the ``type`` field of each message payload. These
# default handlers log the event; production deployments override them with
# concrete side effects (WS fan-out, dataset-status updates, etc.). Every
# documented domain event has an entry so no message dead-letters purely for a
# missing handler.
# --------------------------------------------------------------------------- #


def _log_event(kind: str) -> Handler:
    def _handler(payload: dict) -> None:
        log.info(
            "event_received",
            event_type=kind,
            **{k: v for k, v in payload.items() if k != "type"},
        )

    return _handler


def default_handlers() -> dict[str, Handler]:
    """Return the default handler registry keyed by event ``type``."""
    return {
        "alert.created": _log_event("alert.created"),
        "alert.updated": _log_event("alert.updated"),
        "alert.expired": _log_event("alert.expired"),
        "pfz.updated": _log_event("pfz.updated"),
        "dataset.updated": _log_event("dataset.updated"),
        "processing.started": _log_event("processing.started"),
        "processing.completed": _log_event("processing.completed"),
        "processing.failed": _log_event("processing.failed"),
    }


class Worker:
    """Priority-draining worker for the in-memory queue."""

    def __init__(self, queue: InMemoryQueue, handlers: dict[str, Handler]) -> None:
        self.queue = queue
        self.handlers = handlers

    def _update_metrics(self) -> None:
        for pr in WORK_PRIORITIES:
            QUEUE_DEPTH.labels(pr.value).set(self.queue.depth(pr))
            DLQ_DEPTH.labels(pr.value).set(self.queue.dlq_depth(pr))

    def _dispatch(self, msg: Message) -> None:
        handler = self.handlers.get(msg.payload.get("type", ""))
        if handler is None:
            raise KeyError(f"no handler for event type {msg.payload.get('type')!r}")
        handler(msg.payload)

    def run_once(self, *, now: datetime | None = None) -> bool:
        """Process a single ready message. Returns False if nothing was ready."""
        now = now or datetime.now(tz=UTC)
        msg = self.queue.next_ready(now=now)
        if msg is None:
            self._update_metrics()
            return False
        try:
            self._dispatch(msg)
            self.queue.ack(msg)
            JOB_TOTAL.labels(msg.payload.get("type", "unknown"), JobStatus.SUCCEEDED.value).inc()
        except Exception as exc:  # noqa: BLE001
            dead = self.queue.nack(msg, error=str(exc), now=now)
            status = JobStatus.DEAD_LETTER.value if dead else JobStatus.RETRYING.value
            JOB_TOTAL.labels(msg.payload.get("type", "unknown"), status).inc()
            log.warning(
                "job_failed",
                message_id=msg.message_id,
                priority=msg.priority.value,
                attempts=msg.attempts,
                dead_lettered=dead,
                error_code=type(exc).__name__,
                error=str(exc),
            )
        finally:
            self._update_metrics()
        return True

    def drain(self, *, max_iterations: int = 10_000, now: datetime | None = None) -> int:
        """Process all currently-ready messages. Returns count processed."""
        processed = 0
        for _ in range(max_iterations):
            if not self.run_once(now=now):
                break
            processed += 1
        return processed


def _write_heartbeat() -> None:
    """Touch the heartbeat file the container HEALTHCHECK inspects."""
    import time
    from pathlib import Path

    try:
        Path("/tmp/worker_heartbeat").write_text(str(time.time()))  # noqa: S108
    except OSError:  # pragma: no cover - non-fatal
        pass


def main() -> None:  # pragma: no cover - entrypoint
    """Console entrypoint (``marine-worker``).

    When ``NATS_URL`` is set (or NATS is otherwise reachable), the worker
    connects a :class:`JetStreamQueue` and runs a durable pull-consumer loop as
    the production message backbone. Otherwise it falls back to the
    deterministic :class:`InMemoryQueue` and polls periodically. Live sources
    are disabled by default. SIGTERM/SIGINT trigger a clean shutdown, and a
    heartbeat file is refreshed every loop iteration for the HEALTHCHECK.
    """
    import asyncio
    import os
    import signal
    import time

    from ..config import get_settings
    from ..logging_config import configure_logging
    from ..messaging.queue import InMemoryQueue, JetStreamQueue

    s = get_settings()
    configure_logging(s.service.log_level, s.service.log_json)

    handlers = default_handlers()

    # C2 fix: filter handlers by WORKER_ROLE when set.
    worker_role = os.environ.get("WORKER_ROLE", "").strip().lower()
    if worker_role:
        role_handler_map = {
            "alerts": {"alert.created", "alert.updated", "alert.expired"},
            "ingest": {"dataset.updated", "processing.started", "processing.completed", "processing.failed"},
            "process": {"pfz.updated", "dataset.updated", "processing.started", "processing.completed", "processing.failed"},
        }
        allowed = role_handler_map.get(worker_role)
        if allowed is not None:
            handlers = {k: v for k, v in handlers.items() if k in allowed}
            log.info("worker_role_filter", role=worker_role, handler_count=len(handlers))

    # H7 fix: start Prometheus metrics HTTP server.
    try:
        from prometheus_client import start_http_server
        from ..metrics import REGISTRY
        start_http_server(9100, registry=REGISTRY)
        log.info("metrics_server_started", port=9100)
    except Exception as exc:  # noqa: BLE001
        log.warning("metrics_server_failed", error=str(exc))

    nats_url = os.environ.get("NATS_URL") or s.messaging.servers

    backend = "in_memory"
    jetstream: JetStreamQueue | None = None
    # H18 fix: use nats_url (from env or config) not just os.environ.
    if nats_url:
        jetstream = JetStreamQueue(
            servers=nats_url,
            stream_prefix=s.messaging.stream_prefix,
            max_deliver=s.messaging.max_deliver,
        )
        try:
            asyncio.run(jetstream.connect())
            backend = "jetstream"
        except Exception as exc:  # noqa: BLE001
            log.warning("jetstream_connect_failed", error=str(exc))
            jetstream = None

    log.info(
        "worker_ready",
        environment=s.service.environment,
        live_sources_enabled=s.service.enable_live_sources,
        backend=backend,
        handler_count=len(handlers),
    )

    _write_heartbeat()

    if jetstream is not None:

        async def _run() -> None:
            loop = asyncio.get_running_loop()

            def _shutdown() -> None:
                log.info("worker_shutdown_signal")
                jetstream.stop()

            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.add_signal_handler(sig, _shutdown)
                except (NotImplementedError, ValueError):
                    pass
            try:
                await jetstream.consume_loop(handlers)
            finally:
                await jetstream.close()

        asyncio.run(_run())
    else:
        mem_queue = InMemoryQueue(
            backoff_base=s.messaging.backoff_base_seconds,
            backoff_max=s.messaging.backoff_max_seconds,
        )
        worker = Worker(mem_queue, handlers)
        stopping = {"flag": False}

        def _handle_signal(_signum, _frame) -> None:
            log.info("worker_shutdown_signal")
            stopping["flag"] = True

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, _handle_signal)
            except (ValueError, OSError):  # pragma: no cover
                pass

        while not stopping["flag"]:
            _write_heartbeat()
            if not worker.run_once():
                time.sleep(0.5)
