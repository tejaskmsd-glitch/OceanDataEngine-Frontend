"""INCOIS tide gauge observation adapter.

INCOIS operates a coastal tide-gauge network; the water-level observations map
to the canonical ``observation`` table with ``parameter='water_level'``. The
model and API contract are ready, but the machine XHR endpoint is an
entry-page-only source pending capture (HAR-D), so the live connector is
DISABLED and refuses to run. Tests use the fixture adapter.

Each tide reading becomes a :class:`ParsedObservation` with
``station_type='tide_gauge'`` and ``unit='m'``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from dateutil import parser as dtparser

from ..config import get_settings
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedObservation,
    RawPayload,
)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = dtparser.parse(value)
    except (ValueError, OverflowError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_tide_observations(data: bytes) -> list[ParsedObservation]:
    """Parse a tide-gauge document into ``water_level`` observations."""
    doc = json.loads(data)
    if isinstance(doc, list):
        entries = doc
    elif isinstance(doc, dict):
        entries = doc.get("observations") or doc.get("stations") or doc.get("data") or []
    else:
        entries = []

    parsed: list[ParsedObservation] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        station_id = entry.get("station_id") or entry.get("id") or entry.get("station")
        if not station_id:
            continue
        level = entry.get("water_level_m", entry.get("water_level"))
        lat = entry.get("latitude", entry.get("lat"))
        lon = entry.get("longitude", entry.get("lon"))
        obs_time = _parse_dt(entry.get("observation_time") or entry.get("time"))
        parsed.append(
            ParsedObservation(
                station_id=str(station_id),
                station_type="tide_gauge",
                latitude=float(lat) if lat is not None else None,
                longitude=float(lon) if lon is not None else None,
                parameter="water_level",
                value=float(level) if level is not None else None,
                unit="m",
                observed_at=obs_time,
                provider="INCOIS",
                source_dataset="incois_tide",
            )
        )
    return parsed


class INCOISTideFixtureAdapter:
    """Deterministic offline INCOIS tide adapter reading a fixture document."""

    provider = "INCOIS"
    dataset = "incois_tide"
    live_enabled = False

    def __init__(self, data: bytes, *, source_url: str | None = None) -> None:
        self._data = data
        self._source_url = source_url or "fixture://incois/tide"

    def fetch(self) -> FetchResult:
        observations = parse_tide_observations(self._data)
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=self._data,
            ext="json",
            media_type="application/json",
            source_url=self._source_url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw, observations=observations)


class INCOISTideLiveAdapter:
    """Live INCOIS tide connector — DISABLED (endpoint UNVERIFIED, HAR-D)."""

    provider = "INCOIS"
    dataset = "incois_tide"

    def __init__(self) -> None:
        self.live_enabled = get_settings().service.enable_live_sources

    def fetch(self) -> FetchResult:
        raise LiveSourceDisabledError(
            "INCOIS tide live connector is disabled: the tide-gauge XHR endpoint "
            "is entry-page-only and UNVERIFIED (HAR-D). Use the fixture adapter "
            "until the endpoint is confirmed."
        )
