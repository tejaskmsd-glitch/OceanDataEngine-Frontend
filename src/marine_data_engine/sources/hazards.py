"""Cyclone / Tsunami / Storm-surge hazard bulletin parsers.

The live hazard endpoints (IMD RSMC cyclone bulletins, INCOIS TEWS tsunami
bulletins, storm-surge advisories) are UNVERIFIED (REG-A / HAR-C). Rather than
fabricate an endpoint, the adapters here parse deterministic fixture payloads
that mirror the documented bulletin contracts, and the live connectors are
DISABLED and refuse to run.

Cyclone fields map to the ``cyclone`` migration table; tsunami fields map to
the ``tsunami_event`` migration table. Storm surge is parsed into a portable
dict advisory (the surge table shape is documented but not yet an ORM entity).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from dateutil import parser as dtparser

from ..config import get_settings
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedCyclone,
    ParsedTsunami,
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


def _track_to_geojson(track) -> dict | None:
    """Convert a list of ``[lon, lat]`` pairs to a GeoJSON LineString."""
    if not track or not isinstance(track, list):
        return None
    coords: list[list[float]] = []
    for pt in track:
        if isinstance(pt, list | tuple) and len(pt) >= 2:
            try:
                coords.append([float(pt[0]), float(pt[1])])
            except (TypeError, ValueError):
                continue
    if len(coords) < 2:
        return None
    return {"type": "LineString", "coordinates": coords}


def parse_cyclone_bulletin(data: bytes) -> ParsedCyclone:
    """Parse a structured cyclone bulletin (JSON) into a :class:`ParsedCyclone`.

    Accepts nested ``center``/``movement`` objects (as in the fixture) or flat
    top-level keys, so it tolerates minor upstream shape variation.
    """
    doc = json.loads(data)
    if not isinstance(doc, dict):
        raise ValueError("cyclone bulletin must be a JSON object")

    center = doc.get("center") or {}
    movement = doc.get("movement") or {}

    center_lat = center.get("latitude", doc.get("center_lat"))
    center_lon = center.get("longitude", doc.get("center_lon"))
    if center_lat is None or center_lon is None:
        raise ValueError("cyclone bulletin missing center coordinates")

    return ParsedCyclone(
        cyclone_id=str(doc.get("cyclone_id") or doc.get("id") or ""),
        name=doc.get("name"),
        center_lat=float(center_lat),
        center_lon=float(center_lon),
        issue_time=_parse_dt(doc.get("issue_time")),
        movement_direction=movement.get("direction_deg", doc.get("movement_direction")),
        movement_speed=movement.get("speed_kmph", doc.get("movement_speed")),
        central_pressure=doc.get("central_pressure_hpa", doc.get("central_pressure")),
        max_sustained_wind=doc.get("max_sustained_wind_kmph", doc.get("max_sustained_wind")),
        intensity_category=doc.get("intensity_category"),
        track_geometry=_track_to_geojson(doc.get("track")),
    )


def parse_tsunami_bulletin(data: bytes) -> ParsedTsunami:
    """Parse a TEWS-like tsunami bulletin (JSON) into a :class:`ParsedTsunami`."""
    doc = json.loads(data)
    if not isinstance(doc, dict):
        raise ValueError("tsunami bulletin must be a JSON object")

    eq = doc.get("earthquake") or {}
    regions = doc.get("affected_regions")
    if regions is not None and not isinstance(regions, list):
        regions = [str(regions)]

    return ParsedTsunami(
        event_id=str(doc.get("event_id") or doc.get("id") or ""),
        earthquake_time=_parse_dt(doc.get("earthquake_time") or eq.get("time")),
        eq_lat=eq.get("latitude", doc.get("eq_lat")),
        eq_lon=eq.get("longitude", doc.get("eq_lon")),
        magnitude=eq.get("magnitude", doc.get("magnitude")),
        depth=eq.get("depth_km", eq.get("depth", doc.get("depth"))),
        tsunami_status=doc.get("tsunami_status"),
        alert_level=doc.get("alert_level"),
        affected_regions=regions,
    )


def parse_storm_surge_advisory(data: bytes) -> dict:
    """Parse a storm-surge advisory (JSON) into a normalized dict.

    The surge advisory contract is documented but not yet an ORM entity, so
    this returns a portable dict with canonical keys.
    """
    doc = json.loads(data)
    if not isinstance(doc, dict):
        raise ValueError("storm surge advisory must be a JSON object")
    return {
        "surge_id": str(doc.get("surge_id") or doc.get("id") or ""),
        "region": doc.get("region"),
        "issue_time": _parse_dt(doc.get("issue_time")),
        "peak_surge_m": doc.get("peak_surge_m"),
        "expected_landfall": _parse_dt(doc.get("expected_landfall")),
        "affected_coast": doc.get("affected_coast"),
        "advisory_text": doc.get("advisory_text"),
        "provider": doc.get("provider", "IMD"),
        "source_dataset": doc.get("source_dataset", "imd_storm_surge"),
    }


class CycloneFixtureAdapter:
    """Deterministic offline cyclone adapter reading a fixture bulletin."""

    provider = "IMD"
    dataset = "imd_rsmc"
    live_enabled = False

    def __init__(self, data: bytes, *, source_url: str | None = None) -> None:
        self._data = data
        self._source_url = source_url or "fixture://imd/rsmc"

    def fetch(self) -> FetchResult:
        cyclone = parse_cyclone_bulletin(self._data)
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=self._data,
            ext="json",
            media_type="application/json",
            source_url=self._source_url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw, cyclones=[cyclone])


class TsunamiFixtureAdapter:
    """Deterministic offline tsunami adapter reading a fixture bulletin."""

    provider = "INCOIS"
    dataset = "incois_tews"
    live_enabled = False

    def __init__(self, data: bytes, *, source_url: str | None = None) -> None:
        self._data = data
        self._source_url = source_url or "fixture://incois/tews"

    def fetch(self) -> FetchResult:
        tsunami = parse_tsunami_bulletin(self._data)
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=self._data,
            ext="json",
            media_type="application/json",
            source_url=self._source_url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw, tsunamis=[tsunami])


class CycloneLiveAdapter:
    """Live IMD RSMC cyclone connector — DISABLED (endpoint UNVERIFIED)."""

    provider = "IMD"
    dataset = "imd_rsmc"

    def __init__(self) -> None:
        self.live_enabled = get_settings().service.enable_live_sources

    def fetch(self) -> FetchResult:
        raise LiveSourceDisabledError(
            "IMD RSMC cyclone live connector is disabled: the machine bulletin "
            "endpoint is UNVERIFIED (REG-A/HAR-C). Use the fixture adapter until "
            "the endpoint is confirmed."
        )


class TsunamiLiveAdapter:
    """Live INCOIS TEWS tsunami connector — DISABLED (endpoint UNVERIFIED)."""

    provider = "INCOIS"
    dataset = "incois_tews"

    def __init__(self) -> None:
        self.live_enabled = get_settings().service.enable_live_sources

    def fetch(self) -> FetchResult:
        raise LiveSourceDisabledError(
            "INCOIS TEWS tsunami live connector is disabled: the machine bulletin "
            "endpoint is UNVERIFIED (REG-A/HAR-C). Use the fixture adapter until "
            "the endpoint is confirmed."
        )
