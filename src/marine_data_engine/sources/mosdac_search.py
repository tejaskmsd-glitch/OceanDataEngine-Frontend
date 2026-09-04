"""MOSDAC search source adapter.

MOSDAC (ISRO/SAC) exposes a dataset search endpoint (source_mapping §4,
SEARCH VERIFIED). We use it for *discovery only* — populating the dataset
registry with product metadata. Authenticated bulk downloads are a separate,
blocked capability (AUTH-A) and are never attempted here.

Endpoint::

    GET https://mosdac.gov.in/apios/datasets.json?datasetId=...&count=...&startIndex=...

Response envelope (defensive: several MOSDAC deployments differ slightly)::

    {"totalResults": N, "startIndex": I, "itemsPerPage": C, "datasets": [ {...}, ... ]}

Pagination uses ``startIndex`` + ``count``. HTTP 429 responses are honored as a
rate-limit signal (minute / daily budgets). Like every source here, the live
connector is DISABLED by default and only performs network I/O when
``enable_live_sources`` is true; tests use the fixture adapter.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..config import get_settings
from .base import FetchResult, LiveSourceDisabledError, RawPayload

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT_S = 15
_USER_AGENT = "marine-data-engine/0.1 (+discovery)"

DEFAULT_BASE_URL = "https://mosdac.gov.in"
SEARCH_PATH = "/apios/datasets.json"


class MOSDACRateLimitError(RuntimeError):
    """Raised when MOSDAC returns HTTP 429 (rate limit exceeded)."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class MosdacDataset:
    """A normalized MOSDAC dataset metadata entry."""

    dataset_id: str
    title: str | None = None
    description: str | None = None
    product: str | None = None
    parameters: list[str] = field(default_factory=list)
    source_url: str | None = None


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        # Comma/semicolon separated parameter strings are common.
        return [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
    return [str(value)]


def parse_search_response(body: bytes) -> list[MosdacDataset]:
    """Parse a MOSDAC ``datasets.json`` search response into entries.

    Tolerant of key-name variants (``datasets``/``results``/``items`` and
    ``datasetId``/``id`` etc.).
    """
    doc = json.loads(body)
    if isinstance(doc, list):
        entries = doc
    elif isinstance(doc, dict):
        entries = (
            doc.get("datasets")
            or doc.get("results")
            or doc.get("items")
            or doc.get("data")
            or []
        )
    else:
        entries = []

    parsed: list[MosdacDataset] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ds_id = (
            entry.get("datasetId")
            or entry.get("dataset_id")
            or entry.get("id")
            or entry.get("identifier")
        )
        if not ds_id:
            continue
        parsed.append(
            MosdacDataset(
                dataset_id=str(ds_id),
                title=entry.get("title") or entry.get("name"),
                description=entry.get("description") or entry.get("abstract"),
                product=entry.get("product") or entry.get("productType"),
                parameters=_as_list(entry.get("parameters") or entry.get("variables")),
                source_url=entry.get("url") or entry.get("link"),
            )
        )
    return parsed


def _total_results(body: bytes) -> int | None:
    """Best-effort extraction of a total-result count for pagination."""
    try:
        doc = json.loads(body)
    except (ValueError, TypeError):
        return None
    if isinstance(doc, dict):
        for key in ("totalResults", "total", "count"):
            val = doc.get(key)
            if isinstance(val, int):
                return val
    return None


class MOSDACSearchFixtureAdapter:
    """Fixture-backed MOSDAC search adapter (deterministic, offline)."""

    provider = "MOSDAC"
    dataset = "mosdac_search"
    live_enabled = False

    def __init__(self, response_bytes: bytes, *, source_url: str | None = None) -> None:
        self._data = response_bytes
        self._source_url = source_url or "fixture://mosdac/search"

    def search(self, dataset_id: str | None = None, *, count: int = 50, start_index: int = 0):
        """Return parsed dataset entries from the fixture (ignores paging)."""
        return parse_search_response(self._data)

    def fetch(self) -> FetchResult:
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=self._data,
            ext="json",
            media_type="application/json",
            source_url=self._source_url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw)


class MOSDACSearchAdapter:
    """Live MOSDAC search connector — DISABLED unless explicitly enabled.

    Performs discovery-only searches with pagination and rate-limit handling.
    Network I/O only runs when ``enable_live_sources`` is true.
    """

    provider = "MOSDAC"
    dataset = "mosdac_search"

    def __init__(
        self,
        base_url: str | None = None,
        *,
        minute_limit: int = 30,
        daily_limit: int = 1000,
    ) -> None:
        self.live_enabled = get_settings().service.enable_live_sources
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.minute_limit = minute_limit
        self.daily_limit = daily_limit

    def _require_enabled(self) -> None:
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "MOSDAC search live connector is disabled. Set "
                "MDE_ENABLE_LIVE_SOURCES=true to enable, or use the fixture adapter."
            )

    def _build_url(self, dataset_id: str | None, count: int, start_index: int) -> str:
        params: dict[str, str] = {"count": str(count), "startIndex": str(start_index)}
        if dataset_id:
            params["datasetId"] = dataset_id
        return f"{self.base_url}{SEARCH_PATH}?{urllib.parse.urlencode(params)}"

    def _http_get(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:  # noqa: S310
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = None
                raw_retry = exc.headers.get("Retry-After") if exc.headers else None
                if raw_retry:
                    try:
                        retry_after = float(raw_retry)
                    except ValueError:
                        retry_after = None
                raise MOSDACRateLimitError(
                    "MOSDAC search rate limit exceeded (HTTP 429). "
                    f"minute_limit={self.minute_limit} daily_limit={self.daily_limit}.",
                    retry_after=retry_after,
                ) from exc
            raise RuntimeError(f"MOSDAC search HTTP {exc.code}: {exc.reason}") from exc

    def search(
        self,
        dataset_id: str | None = None,
        *,
        count: int = 50,
        start_index: int = 0,
    ) -> list[MosdacDataset]:
        """Search a single page and return parsed dataset entries."""
        self._require_enabled()
        url = self._build_url(dataset_id, count, start_index)
        try:
            body = self._http_get(url)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise RuntimeError(f"MOSDAC search fetch failed: {exc}") from exc
        return parse_search_response(body)

    def search_all(
        self,
        dataset_id: str | None = None,
        *,
        count: int = 50,
        max_pages: int = 20,
    ) -> list[MosdacDataset]:
        """Search across pages using startIndex + count until exhausted."""
        self._require_enabled()
        results: list[MosdacDataset] = []
        start_index = 0
        total: int | None = None
        for _ in range(max_pages):
            url = self._build_url(dataset_id, count, start_index)
            try:
                body = self._http_get(url)
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                raise RuntimeError(f"MOSDAC search fetch failed: {exc}") from exc
            page = parse_search_response(body)
            if not page:
                break
            results.extend(page)
            if total is None:
                total = _total_results(body)
            start_index += count
            if total is not None and start_index >= total:
                break
            if len(page) < count:
                break
        return results

    def fetch(self, dataset_id: str | None = None, *, count: int = 50) -> FetchResult:
        self._require_enabled()
        url = self._build_url(dataset_id, count, 0)
        try:
            body = self._http_get(url)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise RuntimeError(f"MOSDAC search fetch failed: {exc}") from exc
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=body,
            ext="json",
            media_type="application/json",
            source_url=url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw)
