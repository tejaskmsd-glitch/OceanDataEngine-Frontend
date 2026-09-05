"""Production worker runtime and event dispatch.

Fixtures are never selected implicitly. Ingest handlers always instantiate the
live connector; disabled, auth-blocked, contract-unavailable, license-gated,
and transport failures are recorded as distinct dataset outcomes.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ..db.enums import JobStatus, QueuePriority
from ..logging_config import get_logger
from ..messaging.queue import InMemoryQueue, Message
from ..messaging.subjects import WORK_PRIORITIES
from ..metrics import DLQ_DEPTH, JOB_TOTAL, QUEUE_DEPTH
from ..sources.base import SourceAdapterError

if TYPE_CHECKING:
    from ..messaging.queue import JetStreamQueue

log = get_logger("worker")
Handler = Callable[[dict], None]
AdapterFactory = Callable[[object, dict], object]
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


def _log_event(kind: str) -> Handler:
    def _handler(payload: dict) -> None:
        log.info(
            "event_received",
            event_type=kind,
            **{key: value for key, value in payload.items() if key != "type"},
        )

    return _handler


def _safe_optional_id(value: object, field: str) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not _SAFE_ID_RE.fullmatch(text):
        raise ValueError(f"invalid {field}: {text!r}")
    return text


def _safe_id_list(value: object, field: str) -> list[str]:
    if value in (None, ""):
        return []
    raw_items = value if isinstance(value, list | tuple) else [value]
    return [
        item
        for raw in raw_items
        if (item := _safe_optional_id(raw, field)) is not None
    ]


def _build_ingest_handler(
    adapter_factory: AdapterFactory,
    *,
    provider: str,
    dataset_key: str,
) -> Handler:
    """Build a live-only source fetch/persist handler."""

    def _handler(payload: dict) -> None:
        from ..config import get_settings
        from ..db.session import session_scope
        from ..services.ingestion import IngestionService
        from ..storage.raw_store import build_raw_store

        settings = get_settings()
        log.info(
            "ingest_handler_start",
            dataset=dataset_key,
            payload_keys=list(payload.keys()),
        )
        try:
            adapter = adapter_factory(settings, payload)
            result = adapter.fetch()
        except Exception as exc:  # noqa: BLE001
            log.error(
                "ingest_fetch_failed",
                dataset=dataset_key,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            # Persist the source outcome even though there is correctly no raw
            # artifact for a request that never produced trusted bytes.
            with session_scope() as session:
                service = IngestionService(session, build_raw_store())
                service.record_source_error(provider, dataset_key, exc)
            if isinstance(exc, SourceAdapterError) and not exc.retryable:
                # Known operator action/state; acknowledge instead of retrying
                # five times into a dead-letter queue.
                return
            raise

        try:
            with session_scope() as session:
                service = IngestionService(session, build_raw_store())
                summary = service.ingest(result)
            log.info(
                "ingest_handler_complete",
                dataset=dataset_key,
                source_state=result.result_state,
                accepted=summary.accepted,
                rejected=summary.rejected,
                quarantined=summary.quarantined,
                skipped=summary.skipped_duplicates,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("ingest_persist_failed", dataset=dataset_key, error=str(exc))
            raise

    return _handler


def _imd_cap_adapter_factory(_settings, _payload):
    from ..sources.imd_cap import IMDCapLiveAdapter

    return IMDCapLiveAdapter()


def _incois_pfz_adapter_factory(_settings, _payload):
    from ..sources.incois_pfz import INCOISPfzLiveAdapter

    return INCOISPfzLiveAdapter()


def _incois_hwa_adapter_factory(_settings, _payload):
    from ..sources.incois_hwa import INCOISHighWaveLiveAdapter

    return INCOISHighWaveLiveAdapter()


def _incois_buoy_adapter_factory(_settings, payload):
    from ..sources.imd_buoy import INCOISBuoyLiveAdapter

    station_ids = _safe_id_list(
        payload.get("station_ids") or payload.get("station_id"), "station_id"
    )
    raw_parameters = payload.get("parameter_tokens")
    parameter_tokens = (
        _safe_id_list(raw_parameters, "parameter_token")
        if raw_parameters
        else ["hm0", "wind_speed"]
    )
    return INCOISBuoyLiveAdapter(
        station_ids=station_ids,
        parameter_tokens=parameter_tokens,
    )


def _imd_nwp_adapter_factory(_settings, _payload):
    from ..sources.imd_nwp import IMDNwpAdapter

    # No token/path is passed: the production adapter records the verified
    # auth/contract-unavailable state and never sends a guessed request.
    return IMDNwpAdapter()


def _incois_tide_adapter_factory(_settings, _payload):
    from ..sources.incois_tide import INCOISTideLiveAdapter

    return INCOISTideLiveAdapter()


def _incois_erddap_adapter_factory(_settings, payload):
    from ..sources.incois_erddap import INCOISErddapLiveAdapter

    dataset_id = _safe_optional_id(payload.get("dataset_id"), "dataset_id")
    return INCOISErddapLiveAdapter(dataset_id=dataset_id)


def _mosdac_search_adapter_factory(_settings, payload):
    from ..sources.mosdac_search import MOSDACSearchAdapter

    dataset_id = _safe_optional_id(payload.get("dataset_id"), "dataset_id")
    return MOSDACSearchAdapter(dataset_id=dataset_id)


def _marine_regions_adapter_factory(_settings, _payload):
    from ..sources.marine_regions import MarineRegionsEEZLiveAdapter

    return MarineRegionsEEZLiveAdapter()


def _freshness_handler(_payload: dict) -> None:
    from ..config import get_settings
    from ..db.session import session_scope
    from ..services.freshness import evaluate_dataset_freshness

    with session_scope() as session:
        results = evaluate_dataset_freshness(
            session,
            default_stale_multiplier=get_settings().service.default_stale_multiplier,
        )
    log.info("freshness_evaluation_complete", dataset_count=len(results))


def default_handlers() -> dict[str, Handler]:
    """Return the complete handler registry keyed by payload ``type``."""
    handlers: dict[str, Handler] = {
        "alert.created": _log_event("alert.created"),
        "alert.updated": _log_event("alert.updated"),
        "alert.expired": _log_event("alert.expired"),
        "observation.ingested": _log_event("observation.ingested"),
        "pfz.updated": _log_event("pfz.updated"),
        "dataset.updated": _log_event("dataset.updated"),
        "processing.started": _log_event("processing.started"),
        "processing.completed": _log_event("processing.completed"),
        "processing.failed": _log_event("processing.failed"),
        "ingest.imd_cap": _build_ingest_handler(
            _imd_cap_adapter_factory, provider="IMD", dataset_key="imd_cap"
        ),
        "ingest.incois_pfz": _build_ingest_handler(
            _incois_pfz_adapter_factory,
            provider="INCOIS",
            dataset_key="incois_pfz",
        ),
        "ingest.incois_hwa": _build_ingest_handler(
            _incois_hwa_adapter_factory,
            provider="INCOIS",
            dataset_key="incois_hwa",
        ),
        "ingest.incois_buoy": _build_ingest_handler(
            _incois_buoy_adapter_factory,
            provider="INCOIS",
            dataset_key="incois_buoy",
        ),
        "ingest.imd_nwp": _build_ingest_handler(
            _imd_nwp_adapter_factory, provider="IMD", dataset_key="imd_nwp"
        ),
        "ingest.incois_tide": _build_ingest_handler(
            _incois_tide_adapter_factory,
            provider="INCOIS",
            dataset_key="incois_tide",
        ),
        "ingest.incois_erddap": _build_ingest_handler(
            _incois_erddap_adapter_factory,
            provider="INCOIS",
            dataset_key="incois_erddap",
        ),
        "ingest.mosdac_search": _build_ingest_handler(
            _mosdac_search_adapter_factory,
            provider="MOSDAC",
            dataset_key="mosdac_search",
        ),
        "ingest.marine_regions_eez": _build_ingest_handler(
            _marine_regions_adapter_factory,
            provider="Marine Regions",
            dataset_key="marine_regions_eez_india",
        ),
        "process.freshness_eval": _freshness_handler,
    }
    # Compatibility event name. It resolves to the same verified INCOIS OON
    # implementation and never to the old synthetic BD08 assumption.
    handlers["ingest.imd_buoy"] = handlers["ingest.incois_buoy"]
    return handlers


_ALERT_ROLE_TYPES = {
    "alert.created",
    "alert.updated",
    "alert.expired",
    "ingest.imd_cap",
    "ingest.incois_hwa",
}
_INGEST_ROLE_TYPES = {
    "observation.ingested",
    "pfz.updated",
    "dataset.updated",
    "processing.started",
    "processing.completed",
    "processing.failed",
    "ingest.incois_pfz",
    "ingest.incois_buoy",
    "ingest.imd_buoy",
    "ingest.imd_nwp",
    "ingest.incois_tide",
    "ingest.incois_erddap",
    "ingest.mosdac_search",
    "ingest.marine_regions_eez",
}
_PROCESS_ROLE_TYPES = {"process.freshness_eval"}


def handlers_for_role(role: str, handlers: dict[str, Handler] | None = None) -> dict[str, Handler]:
    """Return handlers owned by a deployment role."""
    registry = handlers or default_handlers()
    role = role.strip().lower()
    allowed = {
        "alerts": _ALERT_ROLE_TYPES,
        "ingest": _INGEST_ROLE_TYPES,
        "process": _PROCESS_ROLE_TYPES,
    }.get(role)
    if allowed is None:
        return registry
    return {name: handler for name, handler in registry.items() if name in allowed}


def priorities_for_role(role: str) -> tuple[QueuePriority, ...]:
    """Map roles to non-overlapping JetStream priority streams."""
    return {
        "alerts": (QueuePriority.CRITICAL_ALERTS,),
        "ingest": (
            QueuePriority.REALTIME_OBSERVATIONS,
            QueuePriority.SCIENTIFIC,
            QueuePriority.BACKFILL_ARCHIVE,
        ),
        "process": (QueuePriority.NORMAL_INGESTION,),
    }.get(role.strip().lower(), WORK_PRIORITIES)


class Worker:
    """Priority-draining worker for the deterministic in-memory queue."""

    def __init__(self, queue: InMemoryQueue, handlers: dict[str, Handler]) -> None:
        self.queue = queue
        self.handlers = handlers

    def _update_metrics(self) -> None:
        for priority in WORK_PRIORITIES:
            QUEUE_DEPTH.labels(priority.value).set(self.queue.depth(priority))
            DLQ_DEPTH.labels(priority.value).set(self.queue.dlq_depth(priority))

    def _dispatch(self, message: Message) -> None:
        handler = self.handlers.get(message.payload.get("type", ""))
        if handler is None:
            raise KeyError(f"no handler for event type {message.payload.get('type')!r}")
        handler(message.payload)

    def run_once(self, *, now: datetime | None = None) -> bool:
        """Process one ready message; return false when the queue is idle."""
        now = now or datetime.now(tz=UTC)
        message = self.queue.next_ready(now=now)
        if message is None:
            self._update_metrics()
            return False
        try:
            self._dispatch(message)
            self.queue.ack(message)
            JOB_TOTAL.labels(
                message.payload.get("type", "unknown"), JobStatus.SUCCEEDED.value
            ).inc()
        except Exception as exc:  # noqa: BLE001
            dead = self.queue.nack(message, error=str(exc), now=now)
            status = JobStatus.DEAD_LETTER.value if dead else JobStatus.RETRYING.value
            JOB_TOTAL.labels(message.payload.get("type", "unknown"), status).inc()
            log.warning(
                "job_failed",
                message_id=message.message_id,
                priority=message.priority.value,
                attempts=message.attempts,
                dead_lettered=dead,
                error_code=type(exc).__name__,
                error=str(exc),
            )
        finally:
            self._update_metrics()
        return True

    def drain(self, *, max_iterations: int = 10_000, now: datetime | None = None) -> int:
        """Process all currently ready messages and return the count."""
        processed = 0
        for _ in range(max_iterations):
            if not self.run_once(now=now):
                break
            processed += 1
        return processed


def _write_heartbeat() -> None:
    import time
    from pathlib import Path

    try:
        Path("/tmp/worker_heartbeat").write_text(str(time.time()))  # noqa: S108
    except OSError:  # pragma: no cover
        pass


async def _run_jetstream_session(
    jetstream: JetStreamQueue,
    handlers: dict[str, Handler],
    *,
    on_ready: Callable[[], None] | None = None,
) -> None:
    """Run the complete NATS lifecycle on the current event loop."""
    try:
        await jetstream.connect()
        if on_ready is not None:
            on_ready()
        await jetstream.consume_loop(handlers)
    finally:
        await jetstream.close()


def main() -> None:  # pragma: no cover - process entrypoint
    import asyncio
    import os
    import signal
    import time

    from ..config import get_settings
    from ..logging_config import configure_logging
    from ..messaging.queue import JetStreamQueue

    settings = get_settings()
    configure_logging(settings.service.log_level, settings.service.log_json)

    worker_role = os.environ.get("WORKER_ROLE", "").strip().lower()
    handlers = handlers_for_role(worker_role)
    priorities = priorities_for_role(worker_role)
    log.info(
        "worker_role_filter",
        role=worker_role or "all",
        handler_count=len(handlers),
        priorities=[priority.value for priority in priorities],
    )

    try:
        from prometheus_client import start_http_server

        from ..metrics import REGISTRY

        start_http_server(9100, registry=REGISTRY)
        log.info("metrics_server_started", port=9100)
    except Exception as exc:  # noqa: BLE001
        log.warning("metrics_server_failed", error=str(exc))

    nats_url = os.environ.get("NATS_URL") or settings.messaging.servers
    jetstream: JetStreamQueue | None = None
    if nats_url:
        jetstream = JetStreamQueue(
            servers=nats_url,
            stream_prefix=settings.messaging.stream_prefix,
            max_deliver=settings.messaging.max_deliver,
            consumer_name=worker_role or "all",
            priorities=priorities,
        )

    if jetstream is not None:

        async def _run() -> None:
            loop = asyncio.get_running_loop()

            def _shutdown() -> None:
                log.info("worker_shutdown_signal")
                jetstream.stop()

            def _ready() -> None:
                log.info(
                    "worker_ready",
                    environment=settings.service.environment,
                    live_sources_enabled=settings.service.enable_live_sources,
                    backend="jetstream",
                    handler_count=len(handlers),
                )
                _write_heartbeat()

            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.add_signal_handler(sig, _shutdown)
                except (NotImplementedError, ValueError):
                    pass
            await _run_jetstream_session(jetstream, handlers, on_ready=_ready)

        try:
            asyncio.run(_run())
        except Exception as exc:  # noqa: BLE001
            log.error(
                "jetstream_runtime_failed",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise
        return

    log.info(
        "worker_ready",
        environment=settings.service.environment,
        live_sources_enabled=settings.service.enable_live_sources,
        backend="in_memory",
        handler_count=len(handlers),
    )
    _write_heartbeat()

    memory_queue = InMemoryQueue(
        backoff_base=settings.messaging.backoff_base_seconds,
        backoff_max=settings.messaging.backoff_max_seconds,
    )
    worker = Worker(memory_queue, handlers)
    stopping = {"flag": False}

    def _handle_signal(_signum, _frame) -> None:
        log.info("worker_shutdown_signal")
        stopping["flag"] = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):
            pass
    while not stopping["flag"]:
        _write_heartbeat()
        if not worker.run_once():
            time.sleep(0.5)
