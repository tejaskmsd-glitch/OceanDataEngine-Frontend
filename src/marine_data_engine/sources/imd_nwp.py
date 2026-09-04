"""IMD NWP (Numerical Weather Prediction) marine forecast adapter.

Per source_mapping.md §4, IMD publishes NWP marine forecast products (wind,
mean-sea-level pressure, rainfall, significant wave height) via an authenticated
API. The exact endpoint list is UNVERIFIED until registration/token access is
obtained (REG-A); the base host is ``https://api.imd.gov.in``.

This module ships:

- :func:`parse_nwp_forecast` — pure parser mapping the documented NWP grid-point
  contract into :class:`ParsedForecast` records (one per parameter per point);
- :class:`IMDNwpFixtureAdapter` — deterministic offline adapter reading a
  fixture file; and
- :class:`IMDNwpAdapter` — the live connector, gated on both
  ``enable_live_sources`` and a non-empty ``IMD_API_TOKEN``. When the token is
  blank it raises :class:`AuthenticationRequiredError`.

All HTTP calls use :mod:`urllib.request` (no external dependencies).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import UTC, datetime

from dateutil import parser as dtparser

from ..config import get_settings
from .base import (
    AuthenticationRequiredError,
    FetchResult,
    LiveSourceDisabledError,
    ParsedForecast,
    RawPayload,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.imd.gov.in"
_HTTP_TIMEOUT_S = 20
_USER_AGENT = "marine-data-engine/0.1 (+nwp)"

# Map fixture/API point keys to (canonical parameter, unit).
_PARAMETER_MAP: dict[str, tuple[str, str]] = {
    "wind_speed_mps": ("wind_speed", "m/s"),
    "wind_direction_deg": ("wind_direction", "deg"),
    "mean_sea_level_pressure_hpa": ("mslp", "hPa"),
    "rainfall_mm": ("rainfall", "mm"),
    "significant_wave_height_m": ("significant_wave_height", "m"),
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = dtparser.parse(value)
    except (ValueError, OverflowError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_nwp_forecast(data: bytes) -> list[ParsedForecast]:
    """Parse an IMD NWP marine forecast document into forecast records.

    The document is a JSON object with model metadata and a ``points`` list;
    each point contributes one :class:`ParsedForecast` per known parameter.
    """
    doc = json.loads(data)
    if not isinstance(doc, dict):
        raise ValueError("IMD NWP forecast must be a JSON object")

    model_name = doc.get("model") or doc.get("model_name")
    model_cycle = doc.get("model_cycle")
    resolution = doc.get("resolution")
    forecast_time = _parse_dt(doc.get("issued_at") or model_cycle)
    points = doc.get("points") or doc.get("forecasts") or []

    parsed: list[ParsedForecast] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        lat = point.get("latitude", point.get("lat"))
        lon = point.get("longitude", point.get("lon"))
        valid_from = _parse_dt(point.get("valid_from") or point.get("valid_time"))
        fhour = point.get("forecast_hour")
        for key, (parameter, unit) in _PARAMETER_MAP.items():
            if key not in point or point[key] is None:
                continue
            try:
                value = float(point[key])
            except (TypeError, ValueError):
                continue
            parsed.append(
                ParsedForecast(
                    parameter=parameter,
                    value=value,
                    unit=unit,
                    latitude=float(lat) if lat is not None else None,
                    longitude=float(lon) if lon is not None else None,
                    valid_from=valid_from,
                    forecast_time=forecast_time,
                    model_name=model_name,
                    model_cycle=model_cycle,
                    forecast_hour=int(fhour) if fhour is not None else None,
                    resolution=resolution,
                )
            )
    return parsed


class IMDNwpFixtureAdapter:
    """Deterministic offline IMD NWP adapter reading a fixture forecast."""

    provider = "IMD"
    dataset = "imd_nwp"
    live_enabled = False

    def __init__(self, data: bytes, *, source_url: str | None = None) -> None:
        self._data = data
        self._source_url = source_url or "fixture://imd/nwp"

    def fetch_marine_forecast(self) -> list[ParsedForecast]:
        return parse_nwp_forecast(self._data)

    def fetch(self) -> FetchResult:
        forecasts = parse_nwp_forecast(self._data)
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=self._data,
            ext="json",
            media_type="application/json",
            source_url=self._source_url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw, forecasts=forecasts)


class IMDNwpAdapter:
    """Live IMD NWP connector — flag- and token-gated.

    Network I/O only runs when ``enable_live_sources`` is true and
    ``IMD_API_TOKEN`` is non-empty. The concrete endpoint path is UNVERIFIED
    (REG-A); a configurable ``forecast_path`` documents the expected shape.
    """

    provider = "IMD"
    dataset = "imd_nwp"

    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str | None = None,
        forecast_path: str = "/nwp/marine/forecast",
    ) -> None:
        settings = get_settings()
        self.live_enabled = settings.service.enable_live_sources
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._token = token if token is not None else settings.credentials.imd_api_token
        self.forecast_path = forecast_path

    def _require_enabled(self) -> None:
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "IMD NWP live connector is disabled. Set MDE_ENABLE_LIVE_SOURCES=true "
                "to enable, or use IMDNwpFixtureAdapter."
            )

    def _require_token(self) -> None:
        if not self._token:
            raise AuthenticationRequiredError(
                "IMD NWP requires a bearer token, but IMD_API_TOKEN is blank. "
                "Configure it in the environment (REG-A) or use IMDNwpFixtureAdapter."
            )

    def _http_get(self, url: str) -> bytes:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _USER_AGENT,
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:  # noqa: S310
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise AuthenticationRequiredError(
                    "IMD NWP rejected the bearer token (HTTP 401)."
                ) from exc
            raise RuntimeError(f"IMD NWP HTTP {exc.code}: {exc.reason}") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise RuntimeError(f"IMD NWP fetch failed: {exc}") from exc

    def fetch_marine_forecast(self) -> list[ParsedForecast]:
        """Fetch and parse the live marine forecast into forecast records."""
        self._require_enabled()
        self._require_token()
        url = f"{self.base_url}{self.forecast_path}"
        body = self._http_get(url)
        return parse_nwp_forecast(body)

    def fetch(self) -> FetchResult:
        self._require_enabled()
        self._require_token()
        url = f"{self.base_url}{self.forecast_path}"
        body = self._http_get(url)
        forecasts = parse_nwp_forecast(body)
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=body,
            ext="json",
            media_type="application/json",
            source_url=url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw, forecasts=forecasts)
