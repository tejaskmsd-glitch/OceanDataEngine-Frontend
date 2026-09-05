"""IMD numeric marine NWP contract status and explicit test-fixture parser.

The official IMD API reference documents textual marine bulletin endpoints,
but live calls are HTTP 401 and the credential/header contract is not public.
No official ``/nwp/marine/forecast`` endpoint or numeric grid-point schema has
been verified. Production therefore fails closed with
:class:`SourceContractUnavailableError`; it never sends a guessed bearer token
or converts bulletin prose into fabricated numeric forecasts.

``parse_nwp_forecast`` exists only for the repository's explicitly synthetic
offline fixture and must not be treated as an upstream IMD response contract.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from dateutil import parser as dtparser

from ..config import get_settings
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedForecast,
    RawPayload,
    SourceContractUnavailableError,
)

OFFICIAL_API_REFERENCE = "https://api.imd.gov.in/public/api_reference.html"
VERIFIED_MARINE_ENDPOINTS = (
    "https://api.imd.gov.in/api/v1/seabulletin",
    "https://api.imd.gov.in/api/v1/coastalbulletin",
    "https://api.imd.gov.in/api/v1/portwarning",
)

# Synthetic fixture keys only; this is not asserted to be a live IMD schema.
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


def parse_nwp_forecast(
    data: bytes, *, source_url: str | None = None
) -> list[ParsedForecast]:
    """Parse the explicitly synthetic numeric NWP test fixture."""
    doc = json.loads(data)
    if not isinstance(doc, dict):
        raise ValueError("synthetic IMD NWP fixture must be a JSON object")

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
        forecast_hour = point.get("forecast_hour")
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
                    forecast_hour=int(forecast_hour) if forecast_hour is not None else None,
                    resolution=resolution,
                    provider="IMD",
                    source_dataset="imd_nwp",
                    source_url=source_url,
                    source_metadata={
                        "synthetic_fixture_contract": True,
                        "not_verified_as_live_imd_schema": True,
                    },
                )
            )
    return parsed


class IMDNwpFixtureAdapter:
    """Explicit deterministic synthetic fixture adapter."""

    provider = "IMD"
    dataset = "imd_nwp"
    live_enabled = False

    def __init__(self, data: bytes, *, source_url: str | None = None) -> None:
        self._data = data
        self._source_url = source_url or "fixture://imd/nwp"

    def fetch_marine_forecast(self) -> list[ParsedForecast]:
        return parse_nwp_forecast(self._data, source_url=self._source_url)

    def fetch(self) -> FetchResult:
        forecasts = self.fetch_marine_forecast()
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=self._data,
            ext="json",
            media_type="application/json",
            source_url=self._source_url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(
            raw=raw,
            forecasts=forecasts,
            result_state="empty" if not forecasts else "success",
            status_detail="explicit synthetic test fixture; not production data",
        )


class IMDNwpAdapter:
    """Fail-closed production status adapter for unavailable numeric IMD NWP."""

    provider = "IMD"
    dataset = "imd_nwp"

    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str | None = None,
        forecast_path: str | None = None,
        live_enabled: bool | None = None,
    ) -> None:
        # Legacy arguments are accepted only to avoid breaking callers. They are
        # deliberately never used for an outbound request or auth header.
        self.live_enabled = (
            get_settings().service.enable_live_sources if live_enabled is None else live_enabled
        )
        self.base_url = base_url
        self._legacy_token_supplied = bool(token)
        self._legacy_path_supplied = forecast_path is not None

    def _raise_status(self) -> None:
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "IMD numeric NWP connector is disabled by MDE_ENABLE_LIVE_SOURCES"
            )
        raise SourceContractUnavailableError(
            "IMD numeric marine NWP is auth/contract unavailable: official marine "
            "bulletin endpoints return HTTP 401, the credential/header scheme is "
            "undocumented, and no verified numeric forecast endpoint/schema exists. "
            f"Reference: {OFFICIAL_API_REFERENCE}"
        )

    def fetch_marine_forecast(self) -> list[ParsedForecast]:
        self._raise_status()
        raise AssertionError("unreachable")

    def fetch(self) -> FetchResult:
        self._raise_status()
        raise AssertionError("unreachable")
