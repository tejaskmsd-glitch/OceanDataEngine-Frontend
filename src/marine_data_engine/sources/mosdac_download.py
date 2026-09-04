"""MOSDAC authenticated download connector (source_mapping.md §6.2.1).

MOSDAC (ISRO/SAC) exposes a token-authenticated download API distinct from the
discovery search endpoint (:mod:`.mosdac_search`). Bulk downloads are a
credential-gated capability: this connector is fully implemented against the
documented ``download_api`` contract but performs live network I/O only when
BOTH ``enable_live_sources`` is true AND MOSDAC credentials are configured.

Documented endpoints (relative to ``https://mosdac.gov.in``)::

    POST /download_api/gettoken        {username, password} -> {access_token, refresh_token}
    GET  /download_api/check-internet  {datasetId}          -> release status
    GET  /download_api/download?id=..  (Bearer)             -> file bytes
    POST /download_api/refresh-token   {refresh_token}      -> {access_token}
    POST /download_api/logout          (Bearer)             -> {}

Rate limiting (HTTP 429): ``minute_limit`` -> sleep 20s and retry once;
``daily_limit`` -> stop (raise). Auth failures (HTTP 401
``NO_ACCESS_TOKEN``/``INVALID_TOKEN``) trigger a single re-authentication.
HTTP 404 ``NOT_RELEASED`` means the dataset is not yet published.

All HTTP calls use :mod:`urllib.request` (no external dependencies). When
credentials are blank, :meth:`fetch` raises :class:`AuthenticationRequiredError`
with a clear message instead of attempting a doomed live call.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from ..config import get_settings
from .base import (
    AuthenticationRequiredError,
    FetchResult,
    LiveSourceDisabledError,
    RawPayload,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://mosdac.gov.in"
_HTTP_TIMEOUT_S = 30
_USER_AGENT = "marine-data-engine/0.1 (+download)"
_MINUTE_LIMIT_SLEEP_S = 20.0


class MOSDACDailyLimitError(RuntimeError):
    """Raised when MOSDAC reports the daily download budget is exhausted."""


class MOSDACNotReleasedError(RuntimeError):
    """Raised when a requested dataset/record is not yet released (HTTP 404)."""


class MOSDACDownloadError(RuntimeError):
    """Generic MOSDAC download API error."""


def _extract_error_code(body: bytes | None) -> str | None:
    """Best-effort extraction of a MOSDAC error code from a JSON error body."""
    if not body:
        return None
    try:
        doc = json.loads(body)
    except (ValueError, TypeError):
        return None
    if isinstance(doc, dict):
        code = doc.get("error") or doc.get("code") or doc.get("status")
        return str(code) if code is not None else None
    return None


class MOSDACDownloadAdapter:
    """Live MOSDAC download connector — credential- and flag-gated.

    Network I/O only runs when ``enable_live_sources`` is true and non-empty
    MOSDAC credentials are configured. Otherwise :meth:`fetch` raises
    :class:`AuthenticationRequiredError` (blank creds) or
    :class:`LiveSourceDisabledError` (live sources off).
    """

    provider = "MOSDAC"
    dataset = "mosdac_download"

    def __init__(
        self,
        base_url: str | None = None,
        *,
        username: str | None = None,
        password: str | None = None,
        minute_limit: int = 30,
        daily_limit: int = 1000,
    ) -> None:
        settings = get_settings()
        self.live_enabled = settings.service.enable_live_sources
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._username = username if username is not None else settings.credentials.mosdac_username
        self._password = password if password is not None else settings.credentials.mosdac_password
        self.minute_limit = minute_limit
        self.daily_limit = daily_limit
        self.access_token: str | None = None
        self.refresh_token_value: str | None = None

    # -- guards ---------------------------------------------------------- #
    def _require_enabled(self) -> None:
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "MOSDAC download live connector is disabled. Set "
                "MDE_ENABLE_LIVE_SOURCES=true to enable, or use "
                "MOSDACDownloadFixtureAdapter."
            )

    def _require_credentials(self) -> None:
        if not (self._username and self._password):
            raise AuthenticationRequiredError(
                "MOSDAC download requires credentials, but MOSDAC_USERNAME and/or "
                "MOSDAC_PASSWORD are blank. Configure them in the environment "
                "(AUTH-A) or use MOSDACDownloadFixtureAdapter for offline runs."
            )

    # -- low-level HTTP -------------------------------------------------- #
    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        auth: bool = False,
    ) -> tuple[int, bytes, dict]:
        """Perform an HTTP request; return (status, body, headers).

        Raises the mapped domain error for 401/404/429; other non-2xx raise
        :class:`MOSDACDownloadError`.
        """
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        data = None
        headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:  # noqa: S310
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else None
            code = _extract_error_code(body)
            if exc.code == 429:
                if code and "daily" in code.lower():
                    raise MOSDACDailyLimitError(
                        "MOSDAC daily download limit reached; stopping."
                    ) from exc
                # minute_limit (or unspecified): signal a retryable rate limit.
                raise _MinuteRateLimit(code or "minute_limit") from exc
            if exc.code == 401:
                raise _AuthExpired(code or "INVALID_TOKEN") from exc
            if exc.code == 404:
                raise MOSDACNotReleasedError(
                    f"MOSDAC resource not released (HTTP 404, code={code})."
                ) from exc
            raise MOSDACDownloadError(
                f"MOSDAC download HTTP {exc.code}: {exc.reason}"
            ) from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise MOSDACDownloadError(f"MOSDAC download request failed: {exc}") from exc

    # -- session management --------------------------------------------- #
    def authenticate(self, username: str | None = None, password: str | None = None) -> str:
        """POST /download_api/gettoken and store access/refresh tokens."""
        self._require_enabled()
        user = username or self._username
        pwd = password or self._password
        if not (user and pwd):
            self._require_credentials()
        _status, body, _headers = self._request(
            "POST",
            "/download_api/gettoken",
            json_body={"username": user, "password": pwd},
        )
        doc = json.loads(body) if body else {}
        self.access_token = doc.get("access_token") or doc.get("accessToken")
        self.refresh_token_value = doc.get("refresh_token") or doc.get("refreshToken")
        if not self.access_token:
            raise MOSDACDownloadError("MOSDAC gettoken returned no access_token.")
        return self.access_token

    def refresh_token(self) -> str:
        """POST /download_api/refresh-token; refresh the access token."""
        self._require_enabled()
        if not self.refresh_token_value:
            return self.authenticate()
        _status, body, _headers = self._request(
            "POST",
            "/download_api/refresh-token",
            json_body={"refresh_token": self.refresh_token_value},
        )
        doc = json.loads(body) if body else {}
        self.access_token = doc.get("access_token") or doc.get("accessToken")
        if not self.access_token:
            raise MOSDACDownloadError("MOSDAC refresh-token returned no access_token.")
        return self.access_token

    def logout(self) -> None:
        """POST /download_api/logout and clear stored tokens."""
        self._require_enabled()
        if self.access_token:
            try:
                self._request("POST", "/download_api/logout", auth=True)
            except MOSDACDownloadError as exc:  # pragma: no cover - best-effort
                logger.warning("mosdac_logout_failed: %s", exc)
        self.access_token = None
        self.refresh_token_value = None

    # -- dataset operations --------------------------------------------- #
    def check_released(self, dataset_id: str) -> bool:
        """GET /download_api/check-internet {datasetId}; True if released."""
        self._require_enabled()
        self._require_credentials()
        if not self.access_token:
            self.authenticate()
        try:
            _status, body, _headers = self._request(
                "GET",
                "/download_api/check-internet",
                json_body={"datasetId": dataset_id},
                auth=True,
            )
        except MOSDACNotReleasedError:
            return False
        doc = json.loads(body) if body else {}
        released = doc.get("released", doc.get("status"))
        if isinstance(released, bool):
            return released
        return str(released).lower() in {"released", "true", "ok", "1"}

    def download(self, record_id: str) -> bytes:
        """GET /download_api/download?id=<record_id>; return file bytes.

        Handles a single re-authentication on 401 and one 20s retry on a
        minute-limit 429. A daily-limit 429 stops immediately.
        """
        self._require_enabled()
        self._require_credentials()
        if not self.access_token:
            self.authenticate()

        reauthed = False
        rate_retried = False
        while True:
            try:
                _status, body, _headers = self._request(
                    "GET",
                    "/download_api/download",
                    params={"id": record_id},
                    auth=True,
                )
                return body
            except _AuthExpired:
                if reauthed:
                    raise MOSDACDownloadError(
                        "MOSDAC download failed: token invalid after re-auth."
                    ) from None
                reauthed = True
                self.refresh_token()
            except _MinuteRateLimit:
                if rate_retried:
                    raise MOSDACDownloadError(
                        "MOSDAC download failed: rate limited after retry."
                    ) from None
                rate_retried = True
                time.sleep(_MINUTE_LIMIT_SLEEP_S)

    def fetch(self, record_id: str | None = None, *, dataset_id: str | None = None) -> FetchResult:
        """Download a record and wrap the bytes in a :class:`FetchResult`.

        Raises :class:`AuthenticationRequiredError` when credentials are blank
        and :class:`LiveSourceDisabledError` when live sources are disabled.
        """
        self._require_enabled()
        self._require_credentials()
        rid = record_id or dataset_id
        if not rid:
            raise MOSDACDownloadError("MOSDAC download requires a record_id or dataset_id.")
        if dataset_id and not self.check_released(dataset_id):
            raise MOSDACNotReleasedError(f"MOSDAC dataset {dataset_id!r} is not released.")
        data = self.download(rid)
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=data,
            ext="bin",
            media_type="application/octet-stream",
            source_url=f"{self.base_url}/download_api/download?id={rid}",
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw)


class _AuthExpired(RuntimeError):
    """Internal signal: HTTP 401 auth token expired/invalid."""


class _MinuteRateLimit(RuntimeError):
    """Internal signal: HTTP 429 minute-limit (retryable)."""


class MOSDACDownloadFixtureAdapter:
    """Deterministic offline MOSDAC download adapter.

    Simulates the token dance and returns fixture bytes so the download path is
    exercisable without credentials or network access.
    """

    provider = "MOSDAC"
    dataset = "mosdac_download"
    live_enabled = False

    def __init__(self, payload: bytes, *, source_url: str | None = None) -> None:
        self._payload = payload
        self._source_url = source_url or "fixture://mosdac/download"
        self.access_token: str | None = None
        self.refresh_token_value: str | None = None

    def authenticate(self, username: str = "fixture", password: str = "fixture") -> str:
        self.access_token = "fixture-access-token"
        self.refresh_token_value = "fixture-refresh-token"
        return self.access_token

    def refresh_token(self) -> str:
        self.access_token = "fixture-access-token-refreshed"
        return self.access_token

    def logout(self) -> None:
        self.access_token = None
        self.refresh_token_value = None

    def check_released(self, dataset_id: str) -> bool:  # noqa: ARG002
        return True

    def download(self, record_id: str) -> bytes:  # noqa: ARG002
        if not self.access_token:
            self.authenticate()
        return self._payload

    def fetch(self, record_id: str = "fixture-record", *, dataset_id: str | None = None):  # noqa: ARG002
        data = self.download(record_id)
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=data,
            ext="bin",
            media_type="application/octet-stream",
            source_url=self._source_url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw)
