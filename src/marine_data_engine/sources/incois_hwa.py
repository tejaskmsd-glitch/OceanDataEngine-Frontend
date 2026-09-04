"""INCOIS High Wave Alert (HWA) adapter.

INCOIS issues High Wave Alerts with severity, an affected-coast polygon, a
validity window, and advisory text. These map to the canonical ``alert`` table
(:class:`ParsedAlert`) with ``event_type='high_wave'``. The alert model is
ready, but the machine feed is UNVERIFIED (HAR-C), so the live connector is
DISABLED. Tests use the fixture adapter.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from dateutil import parser as dtparser

from ..config import get_settings
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedAlert,
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


def parse_high_wave_alerts(data: bytes) -> list[ParsedAlert]:
    """Parse an INCOIS High Wave Alert document into :class:`ParsedAlert`."""
    doc = json.loads(data)
    if isinstance(doc, list):
        entries = doc
    elif isinstance(doc, dict):
        entries = doc.get("alerts") or doc.get("features") or doc.get("data") or []
    else:
        entries = []

    parsed: list[ParsedAlert] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        # Support both flat objects and GeoJSON-style features.
        props = entry.get("properties") if "properties" in entry else entry
        geometry = entry.get("geometry") or props.get("geometry")
        alert_uid = props.get("alert_id") or props.get("id") or props.get("uid")
        if not alert_uid:
            continue
        parsed.append(
            ParsedAlert(
                alert_uid=str(alert_uid),
                event_type="high_wave",
                severity=str(props.get("severity") or "unknown").lower(),
                certainty=str(props.get("certainty") or "observed").lower(),
                urgency=str(props.get("urgency") or "expected").lower(),
                headline=props.get("headline"),
                description=props.get("advisory_text") or props.get("description"),
                area_description=props.get("area_description") or props.get("region"),
                geometry=geometry,
                issued_at=_parse_dt(props.get("issued_at")),
                effective_from=_parse_dt(props.get("valid_from")),
                valid_until=_parse_dt(props.get("valid_until")),
                source_url=props.get("source_url"),
                provider="INCOIS",
                source_dataset="incois_hwa",
            )
        )
    return parsed


class INCOISHighWaveFixtureAdapter:
    """Deterministic offline INCOIS HWA adapter reading a fixture document."""

    provider = "INCOIS"
    dataset = "incois_hwa"
    live_enabled = False

    def __init__(self, data: bytes, *, source_url: str | None = None) -> None:
        self._data = data
        self._source_url = source_url or "fixture://incois/hwa"

    def fetch(self) -> FetchResult:
        alerts = parse_high_wave_alerts(self._data)
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=self._data,
            ext="json",
            media_type="application/json",
            source_url=self._source_url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw, alerts=alerts)


class INCOISHighWaveLiveAdapter:
    """Live INCOIS HWA connector — DISABLED (feed UNVERIFIED, HAR-C)."""

    provider = "INCOIS"
    dataset = "incois_hwa"

    def __init__(self) -> None:
        self.live_enabled = get_settings().service.enable_live_sources

    def fetch(self) -> FetchResult:
        raise LiveSourceDisabledError(
            "INCOIS High Wave Alert live connector is disabled: the machine feed "
            "is UNVERIFIED (HAR-C). Use the fixture adapter until it is confirmed."
        )
