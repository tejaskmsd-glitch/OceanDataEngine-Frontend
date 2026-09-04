"""In-process alert broker for the WebSocket stream.

Decouples alert event producers from WebSocket subscribers. In production the
producer is a NATS JetStream consumer bridging ``events.alerts`` to connected
clients; here it is an asyncio pub/sub usable by both the app and tests.
"""

from __future__ import annotations

import asyncio
from collections import deque


class AlertBroker:
    """Fan-out broker with a small replay buffer for new subscribers."""

    def __init__(self, replay: int = 20) -> None:
        self._subscribers: set[asyncio.Queue[dict]] = set()
        self._recent: deque[dict] = deque(maxlen=replay)
        self._lock = asyncio.Lock()

    async def publish(self, event: dict) -> None:
        async with self._lock:
            self._recent.append(event)
            targets = list(self._subscribers)
        for q in targets:
            q.put_nowait(event)

    async def subscribe(self) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue()
        async with self._lock:
            for event in self._recent:
                q.put_nowait(event)
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue[dict]) -> None:
        async with self._lock:
            self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


_broker: AlertBroker | None = None


def get_broker() -> AlertBroker:
    global _broker
    if _broker is None:
        _broker = AlertBroker()
    return _broker
