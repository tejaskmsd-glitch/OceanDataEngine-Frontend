"""Shared helpers for Marine Data Layer orchestration DAGs.

These DAGs are deliberately thin: they emit *ingest trigger* events onto the
NATS work queue (or call the API's internal trigger endpoint) so the dedicated
Python workers perform the actual fetch/decode/normalize/QC. This preserves the
architectural rule that heavy processing never runs inside the orchestrator or
inside synchronous API requests (prompt §4).
"""
from __future__ import annotations

import json
import os
from typing import Any


def publish_ingest_trigger(subject: str, payload: dict[str, Any]) -> None:
    """Publish an ingest trigger to NATS JetStream.

    Falls back to logging when nats-py is unavailable so DAG parsing never
    breaks the scheduler. Real delivery happens when the worker/NATS stack is up.
    """
    nats_url = os.environ.get("MARINE_NATS_URL") or os.environ.get("NATS_URL", "nats://nats:4222")
    body = json.dumps(payload).encode("utf-8")

    try:
        import asyncio

        import nats  # type: ignore
        import nats.errors # type: ignore

        async def _send() -> None:
            nc = await nats.connect(nats_url, connect_timeout=5)
            try:
                js = nc.jetstream()
                for attempt in range(3):
                    try:
                        await js.publish(subject, body, timeout=5)
                        break
                    except nats.errors.TimeoutError:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(2 ** attempt)
            finally:
                await nc.drain()

        asyncio.run(_send())
    except Exception as exc:  # pragma: no cover
        # H9 fix: log properly and re-raise so Airflow marks the task as failed.
        import logging
        logging.getLogger("airflow.task").error(
            "NATS publish failed for subject=%s: %s payload=%s", subject, exc, payload
        )
        raise RuntimeError(
            f"Failed to publish ingest trigger to NATS ({subject}): {exc}"
        ) from exc
