"""INCOIS ERDDAP source adapter.

INCOIS publishes an ERDDAP server (source_mapping §3, CATALOG VERIFIED). The
catalog and per-dataset metadata are consumed as JSON:

- Catalog:      ``GET /erddap/info/index.json?page=1&itemsPerPage=1000``
- Per-dataset:  ``GET /erddap/info/{dataset_id}/index.json``

ERDDAP JSON responses use a tabular envelope::

    {"table": {"columnNames": [...], "columnTypes": [...], "rows": [[...], ...]}}

For the catalog, each row describes one dataset; the ``Dataset ID`` column is
the stable identifier and ``Title`` the human-readable name.

TLS note (source_mapping V3-TLS): the INCOIS endpoint has historically omitted
an intermediate certificate. We build an SSL context from the ``certifi`` CA
bundle (never disabling verification). If ``certifi`` is unavailable we fall
back to the system default context and log a warning — verification stays ON.

Like every source in this package, the live connector is DISABLED by default
and only performs network I/O when ``enable_live_sources`` is true. Tests use
the fixture adapter and never touch the network.
"""

from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime

from ..config import get_settings
from .base import FetchResult, LiveSourceDisabledError, RawPayload

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT_S = 15
_USER_AGENT = "marine-data-engine/0.1 (+ingest)"

CATALOG_PATH = "/erddap/info/index.json?page=1&itemsPerPage=1000"
DATASET_INFO_PATH = "/erddap/info/{dataset_id}/index.json"
DEFAULT_BASE_URL = "https://erddap.incois.gov.in"


@dataclass
class ErddapDataset:
    """A single ERDDAP catalog entry (dataset id + title + metadata)."""

    dataset_id: str
    title: str | None = None
    institution: str | None = None
    griddap: str | None = None
    tabledap: str | None = None


def _build_ssl_context() -> ssl.SSLContext:
    """Return a verifying SSL context, preferring the certifi CA bundle.

    Never disables verification. If certifi cannot be loaded we fall back to
    the platform default verifying context and emit a warning.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception as exc:  # pragma: no cover - defensive, certifi is pinned
        logger.warning(
            "certifi CA bundle unavailable (%s); using system default verifying "
            "SSL context. TLS verification remains ENABLED.",
            exc,
        )
        return ssl.create_default_context()


def parse_catalog(catalog_bytes: bytes) -> list[ErddapDataset]:
    """Parse an ERDDAP ``info/index.json`` catalog into dataset entries."""
    doc = json.loads(catalog_bytes)
    table = doc.get("table", {}) if isinstance(doc, dict) else {}
    columns: list[str] = table.get("columnNames", []) or []
    rows: list[list] = table.get("rows", []) or []

    # Locate columns case-insensitively; ERDDAP uses "Dataset ID"/"Title".
    def _col_index(*names: str) -> int | None:
        lowered = [c.lower() if isinstance(c, str) else "" for c in columns]
        for name in names:
            if name.lower() in lowered:
                return lowered.index(name.lower())
        return None

    idx_id = _col_index("Dataset ID", "datasetID", "dataset_id")
    idx_title = _col_index("Title")
    idx_inst = _col_index("Institution")
    idx_grid = _col_index("griddap")
    idx_table = _col_index("tabledap")

    def _cell(row: list, idx: int | None) -> str | None:
        if idx is None or idx >= len(row) or row[idx] in (None, ""):
            return None
        return str(row[idx])

    datasets: list[ErddapDataset] = []
    for row in rows:
        if idx_id is None or idx_id >= len(row):
            continue
        ds_id = row[idx_id]
        if not ds_id:
            continue
        datasets.append(
            ErddapDataset(
                dataset_id=str(ds_id),
                title=_cell(row, idx_title),
                institution=_cell(row, idx_inst),
                griddap=_cell(row, idx_grid),
                tabledap=_cell(row, idx_table),
            )
        )
    return datasets


class INCOISErddapCatalogAdapter:
    """Fixture-backed INCOIS ERDDAP catalog adapter (deterministic, offline)."""

    provider = "INCOIS"
    dataset = "incois_erddap"
    live_enabled = False

    def __init__(self, catalog_bytes: bytes, *, source_url: str | None = None) -> None:
        self._data = catalog_bytes
        self._source_url = source_url or "fixture://incois/erddap/catalog"

    def list_datasets(self) -> list[ErddapDataset]:
        """Return the parsed catalog dataset entries."""
        return parse_catalog(self._data)

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


# Backwards/clarity alias: the fixture adapter *is* the catalog adapter reading
# from a local JSON fixture.
INCOISErddapFixtureAdapter = INCOISErddapCatalogAdapter


class INCOISErddapLiveAdapter:
    """Live INCOIS ERDDAP connector — DISABLED unless explicitly enabled.

    Fetches the catalog (and optionally per-dataset info) over HTTPS using a
    verifying SSL context built from the certifi bundle. Network I/O only runs
    when ``enable_live_sources`` is true.
    """

    provider = "INCOIS"
    dataset = "incois_erddap"

    def __init__(self, base_url: str | None = None) -> None:
        self.live_enabled = get_settings().service.enable_live_sources
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._ssl_context = _build_ssl_context()

    def _http_get(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(  # noqa: S310
            req, timeout=_HTTP_TIMEOUT_S, context=self._ssl_context
        ) as resp:
            return resp.read()

    def _require_enabled(self) -> None:
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "INCOIS ERDDAP live connector is disabled. Set "
                "MDE_ENABLE_LIVE_SOURCES=true to enable, or use the fixture adapter."
            )

    def list_datasets(self) -> list[ErddapDataset]:
        """Fetch and parse the live ERDDAP catalog."""
        self._require_enabled()
        url = f"{self.base_url}{CATALOG_PATH}"
        try:
            body = self._http_get(url)
        except (urllib.error.URLError, ssl.SSLError, OSError, TimeoutError) as exc:
            raise RuntimeError(f"INCOIS ERDDAP catalog fetch failed: {exc}") from exc
        return parse_catalog(body)

    def dataset_info(self, dataset_id: str) -> dict:
        """Fetch per-dataset ERDDAP info as a parsed JSON dict."""
        self._require_enabled()
        url = f"{self.base_url}{DATASET_INFO_PATH.format(dataset_id=dataset_id)}"
        try:
            body = self._http_get(url)
        except (urllib.error.URLError, ssl.SSLError, OSError, TimeoutError) as exc:
            raise RuntimeError(
                f"INCOIS ERDDAP dataset info fetch failed ({dataset_id}): {exc}"
            ) from exc
        return json.loads(body)

    def fetch(self) -> FetchResult:
        self._require_enabled()
        url = f"{self.base_url}{CATALOG_PATH}"
        try:
            body = self._http_get(url)
        except (urllib.error.URLError, ssl.SSLError, OSError, TimeoutError) as exc:
            raise RuntimeError(f"INCOIS ERDDAP catalog fetch failed: {exc}") from exc
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
