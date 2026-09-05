"""Redis-backed lazy-refresh cache with single-flight fetch coordination.

Purpose
-------
Scraped bulletins are refreshed on a schedule, but several workers (and a
manually triggered DAG run) can want the same document at once. Without
coordination each one issues its own request to the upstream government host.
This module provides:

* **Lazy population** — a document is fetched on first miss and cached until
  its TTL expires, so repeat reads inside a bulletin's validity window cost
  nothing upstream.
* **Single-flight** — concurrent misses for the same key elect exactly one
  fetcher via ``SET NX``; the others wait briefly for that result.

Fail-open by design
-------------------
This cache sits in front of a **safety-relevant** data path, so it must never
become a new single point of failure. Every Redis error is swallowed and
degrades to a direct upstream fetch. The cache can make the system faster and
gentler on the upstream host; it can never make it unavailable.

Correctness note: the cache stores *raw upstream documents*, never parsed
safety values. A stale cache entry can therefore only ever delay a fresh
bulletin, and freshness remains visible because parsed records carry the
bulletin's own issue time and validity window.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import structlog

log = structlog.get_logger(__name__)

#: Default TTL. Bulletins are issued roughly twice daily with a 12 h validity,
#: so a short TTL keeps freshness while collapsing bursts of reads.
DEFAULT_TTL_S = 900

#: How long a waiter blocks for the elected fetcher before fetching itself.
DEFAULT_WAIT_TIMEOUT_S = 5.0
_WAIT_POLL_INTERVAL_S = 0.1

#: Lock lifetime. Must exceed a realistic upstream fetch so a crashed holder
#: cannot wedge other workers for long.
DEFAULT_LOCK_TTL_S = 45


class BulletinCache:
    """Lazy-population cache with single-flight coordination.

    ``client`` is any object implementing the small subset of the Redis API used
    here (``get``, ``set``, ``delete``). Passing ``None`` disables caching
    entirely and every call falls through to the loader.
    """

    def __init__(
        self,
        client=None,  # noqa: ANN001 - duck-typed redis client
        *,
        ttl_s: int = DEFAULT_TTL_S,
        lock_ttl_s: int = DEFAULT_LOCK_TTL_S,
        wait_timeout_s: float = DEFAULT_WAIT_TIMEOUT_S,
        namespace: str = "mde:cache",
    ) -> None:
        self.client = client
        self.ttl_s = int(ttl_s)
        self.lock_ttl_s = int(lock_ttl_s)
        self.wait_timeout_s = float(wait_timeout_s)
        self.namespace = namespace.rstrip(":")
        # Observability counters (also make behaviour assertable in tests).
        self.hits = 0
        self.misses = 0
        self.single_flight_waits = 0
        self.degraded_fetches = 0

    # ── key helpers ────────────────────────────────────────────────────────
    def _value_key(self, key: str) -> str:
        return f"{self.namespace}:v:{key}"

    def _lock_key(self, key: str) -> str:
        return f"{self.namespace}:lock:{key}"

    # ── low-level, always fail-open ────────────────────────────────────────
    def _get(self, key: str) -> str | None:
        if self.client is None:
            return None
        try:
            raw = self.client.get(self._value_key(key))
        except Exception as exc:  # noqa: BLE001 - cache must never break the path
            log.warning("cache_get_failed", key=key, error=str(exc))
            return None
        if raw is None:
            return None
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return str(raw)

    def _set(self, key: str, value: str, ttl_s: int | None = None) -> None:
        if self.client is None:
            return
        try:
            self.client.set(self._value_key(key), value, ex=int(ttl_s or self.ttl_s))
        except Exception as exc:  # noqa: BLE001
            log.warning("cache_set_failed", key=key, error=str(exc))

    def _acquire(self, key: str) -> bool:
        """Try to become the single elected fetcher for ``key``."""
        if self.client is None:
            return True
        try:
            acquired = self.client.set(self._lock_key(key), "1", nx=True, ex=self.lock_ttl_s)
        except Exception as exc:  # noqa: BLE001
            log.warning("cache_lock_failed", key=key, error=str(exc))
            # Cannot coordinate: let the caller fetch rather than stall.
            return True
        return bool(acquired)

    def _release(self, key: str) -> None:
        if self.client is None:
            return
        try:
            self.client.delete(self._lock_key(key))
        except Exception as exc:  # noqa: BLE001
            log.warning("cache_unlock_failed", key=key, error=str(exc))

    # ── public API ─────────────────────────────────────────────────────────
    def get_or_fetch(
        self,
        *,
        key: str,
        loader: Callable[[], str],
        ttl_s: int | None = None,
    ) -> str:
        """Return the cached document for ``key`` or populate it via ``loader``.

        At most one caller runs ``loader`` for a given key at a time. Waiters
        that time out fall back to calling ``loader`` themselves rather than
        failing, keeping the data path available.
        """
        cached = self._get(key)
        if cached is not None:
            self.hits += 1
            return cached

        self.misses += 1
        if self._acquire(key):
            try:
                value = loader()
                self._set(key, value, ttl_s)
                return value
            finally:
                self._release(key)

        # Another worker is fetching: wait briefly for its result.
        self.single_flight_waits += 1
        deadline = time.monotonic() + self.wait_timeout_s
        while time.monotonic() < deadline:
            time.sleep(_WAIT_POLL_INTERVAL_S)
            cached = self._get(key)
            if cached is not None:
                self.hits += 1
                return cached

        # Elected fetcher was too slow or died. Fetch directly.
        log.info("cache_single_flight_timeout", key=key)
        self.degraded_fetches += 1
        value = loader()
        self._set(key, value, ttl_s)
        return value

    def invalidate(self, key: str) -> None:
        """Drop a cached document, forcing the next read to refetch."""
        if self.client is None:
            return
        try:
            self.client.delete(self._value_key(key))
        except Exception as exc:  # noqa: BLE001
            log.warning("cache_invalidate_failed", key=key, error=str(exc))


def build_redis_client(url: str | None):  # noqa: ANN201 - duck-typed client
    """Best-effort Redis client. Returns ``None`` when unavailable.

    A missing package, unset URL, or unreachable server all yield ``None`` so
    callers transparently run uncached instead of failing.
    """
    if not url:
        return None
    try:
        import redis  # noqa: PLC0415 - optional dependency
    except ImportError:
        log.info("redis_package_absent", detail="cache disabled; running uncached")
        return None
    try:
        client = redis.Redis.from_url(url, socket_timeout=2.0, socket_connect_timeout=2.0)
        client.ping()
    except Exception as exc:  # noqa: BLE001
        log.warning("redis_unavailable", url=url, error=str(exc))
        return None
    log.info("redis_cache_enabled", url=url)
    return client


def build_bulletin_cache(url: str | None = None, *, ttl_s: int = DEFAULT_TTL_S) -> BulletinCache:
    """Construct a :class:`BulletinCache`, degrading to uncached when needed."""
    if url is None:
        from .config import get_settings

        url = getattr(get_settings().service, "redis_url", "") or None
    return BulletinCache(build_redis_client(url), ttl_s=ttl_s)
