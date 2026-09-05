"""INCOIS High Wave Alert and Swell Surge live adapter.

Verified machine contracts:
- alerts: ``/incoismobileappdata/rest/incois/hwassalatestdata``
- district geometry: ``/incoismobileappdata/rest/incois/districtpolygons``

The alert arrays are JSON strings nested inside a JSON object and therefore
require a second decode. Geometry is joined by normalized ``STATE+District``;
object IDs and district names alone are not globally reliable.
"""

from __future__ import annotations

import gzip
import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from dateutil import parser as dtparser

from ..config import get_settings
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedAlert,
    RawPayload,
    SourceContractError,
    SourceUnavailableError,
)

ALERT_URL = (
    "https://sarat.incois.gov.in/incoismobileappdata/rest/incois/"
    "hwassalatestdata"
)
GEOMETRY_URL = (
    "https://samudra.incois.gov.in/incoismobileappdata/rest/incois/"
    "districtpolygons"
)
_HTTP_TIMEOUT_S = 20
_USER_AGENT = "marine-data-engine/0.1 (+incois-hwa)"
_IST = ZoneInfo("Asia/Kolkata")
_VALIDITY_RE = re.compile(
    r"\bduring\s+(?P<start_time>\d{2}:\d{2})\s+hours\s+on\s+"
    r"(?P<start_date>\d{2}-\d{2}-\d{4})\s+to\s+"
    r"(?P<end_time>\d{2}:\d{2})\s+hours\s+on\s+"
    r"(?P<end_date>\d{2}-\d{2}-\d{4})\b",
    re.IGNORECASE,
)

# Explicit, tested mapping. Unknown upstream colours remain ``unknown``.
_COLOR_SEVERITY = {
    "GREEN": "minor",
    "YELLOW": "moderate",
    "ORANGE": "severe",
    "RED": "extreme",
}
_ALERT_EVENT_TYPE = {
    "HIGH WAVE WATCH": "high_wave",
    "HIGH WAVE WARNING": "high_wave",
    "SWELL SURGE WATCH": "swell_surge",
    "SWELL SURGE WARNING": "swell_surge",
}


def _parse_dt(value: str | None) -> datetime | None:
    """Backward-compatible parser used by deterministic legacy fixtures."""
    if not value:
        return None
    try:
        dt = dtparser.parse(value)
    except (ValueError, OverflowError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _norm_join_value(value: object) -> str:
    return " ".join(str(value or "").strip().upper().split())


def parse_alert_validity(message: str | None) -> tuple[datetime | None, datetime | None]:
    """Parse the verified English validity phrase as India Standard Time.

    No fallback date inference is attempted. A non-matching message returns
    ``(None, None)`` so callers can mark the response degraded rather than
    silently assuming UTC or manufacturing a validity window.
    """
    if not message:
        return (None, None)
    match = _VALIDITY_RE.search(message)
    if match is None:
        return (None, None)
    try:
        start = datetime.strptime(
            f"{match.group('start_date')} {match.group('start_time')}",
            "%d-%m-%Y %H:%M",
        ).replace(tzinfo=_IST)
        end = datetime.strptime(
            f"{match.group('end_date')} {match.group('end_time')}",
            "%d-%m-%Y %H:%M",
        ).replace(tzinfo=_IST)
    except ValueError:
        return (None, None)
    if end < start:
        return (None, None)
    return (start, end)


def _decode_embedded_list(value: object, field_name: str) -> list[dict]:
    if value is None or (isinstance(value, str) and value.strip().lower() in {"", "none", "null"}):
        return []
    decoded = value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SourceContractError(f"INCOIS {field_name} is not valid embedded JSON") from exc
    if not isinstance(decoded, list):
        raise SourceContractError(f"INCOIS {field_name} must decode to an array")
    if not all(isinstance(item, dict) for item in decoded):
        raise SourceContractError(f"INCOIS {field_name} contains a non-object item")
    return decoded


def parse_high_wave_alerts(
    data: bytes, *, source_url: str | None = None
) -> list[ParsedAlert]:
    """Parse the deterministic legacy fixture contract used by unit tests."""
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
        props = entry.get("properties") if "properties" in entry else entry
        if not isinstance(props, dict):
            continue
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
                source_url=source_url or props.get("source_url"),
                provider="INCOIS",
                source_dataset="incois_hwa",
                source_metadata={"fixture_contract": True},
            )
        )
    return parsed


def parse_live_high_wave_alerts(
    alert_data: bytes,
    geometry_data: bytes,
    *,
    alert_url: str = ALERT_URL,
    geometry_url: str = GEOMETRY_URL,
) -> tuple[list[ParsedAlert], list[str]]:
    """Parse verified live HWA/SSA and district-geometry responses."""
    try:
        alert_doc = json.loads(alert_data)
        geometry_doc = json.loads(geometry_data)
    except json.JSONDecodeError as exc:
        raise SourceContractError("INCOIS HWA response is not valid JSON") from exc
    if not isinstance(alert_doc, dict):
        raise SourceContractError("INCOIS HWA top-level response must be an object")
    if not isinstance(geometry_doc, dict) or geometry_doc.get("type") != "FeatureCollection":
        raise SourceContractError("INCOIS HWA geometry must be a GeoJSON FeatureCollection")

    geometry_index: dict[tuple[str, str], dict | None] = {}
    diagnostics: list[str] = []
    for feature in geometry_doc.get("features") or []:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") or {}
        geometry = feature.get("geometry")
        if not isinstance(props, dict) or not isinstance(geometry, dict):
            continue
        if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            continue
        key = (_norm_join_value(props.get("STATE")), _norm_join_value(props.get("District")))
        if not all(key):
            continue
        if key in geometry_index:
            geometry_index[key] = None
            diagnostics.append(f"ambiguous district geometry for {key[0]}/{key[1]}")
        else:
            geometry_index[key] = geometry

    feeds = (
        ("HWAJson", "LatestHWADate"),
        ("SSAJson", "LatestSSADate"),
    )
    parsed: list[ParsedAlert] = []
    for array_field, date_field in feeds:
        latest_date = alert_doc.get(date_field)
        entries = _decode_embedded_list(alert_doc.get(array_field), array_field)
        for entry in entries:
            state = _norm_join_value(entry.get("STATE"))
            district = _norm_join_value(entry.get("District"))
            alert_name = _norm_join_value(entry.get("Alert"))
            color = _norm_join_value(entry.get("Color"))
            message = str(entry.get("Message") or "").strip() or None
            object_id = entry.get("OBJECTID")
            key = (state, district)
            geometry = geometry_index.get(key)
            if geometry is None:
                diagnostics.append(f"missing unambiguous geometry for {state}/{district}")

            valid_from, valid_until = parse_alert_validity(message)
            if valid_from is None or valid_until is None:
                diagnostics.append(f"unparsed validity for {alert_name} {state}/{district}")

            severity = _COLOR_SEVERITY.get(color, "unknown")
            if severity == "unknown":
                diagnostics.append(f"unknown HWA colour {color!r} for {state}/{district}")
            event_type = _ALERT_EVENT_TYPE.get(alert_name, "marine_hazard")
            if event_type == "marine_hazard":
                diagnostics.append(f"unknown HWA alert type {alert_name!r}")

            uid_parts = (
                "incois",
                event_type,
                str(latest_date or "undated"),
                state.replace(" ", "-"),
                district.replace(" ", "-"),
                str(object_id if object_id is not None else "no-object-id"),
            )
            parsed.append(
                ParsedAlert(
                    alert_uid=":".join(uid_parts).lower(),
                    event_type=event_type,
                    severity=severity,
                    certainty="likely",
                    urgency="expected",
                    headline=alert_name or None,
                    description=message,
                    area_description=", ".join(part for part in (district, state) if part),
                    geometry=geometry,
                    # The source exposes only an issue *date*. Do not invent a time.
                    issued_at=None,
                    effective_from=valid_from,
                    valid_until=valid_until,
                    source_url=alert_url,
                    provider="INCOIS",
                    source_dataset="incois_hwa",
                    source_metadata={
                        "object_id": object_id,
                        "district": entry.get("District"),
                        "state": entry.get("STATE"),
                        "alert": entry.get("Alert"),
                        "color": entry.get("Color"),
                        "issue_date": entry.get("Issue Date"),
                        "latest_feed_date": latest_date,
                        "validity_timezone": "Asia/Kolkata",
                        "geometry_source_url": geometry_url,
                        "geometry_join": "normalized STATE + District",
                    },
                )
            )
    return parsed, list(dict.fromkeys(diagnostics))


class INCOISHighWaveFixtureAdapter:
    """Explicit deterministic fixture adapter; never selected in production."""

    provider = "INCOIS"
    dataset = "incois_hwa"
    live_enabled = False

    def __init__(self, data: bytes, *, source_url: str | None = None) -> None:
        self._data = data
        self._source_url = source_url or "fixture://incois/hwa"

    def fetch(self) -> FetchResult:
        alerts = parse_high_wave_alerts(self._data, source_url=self._source_url)
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
            alerts=alerts,
            result_state="empty" if not alerts else "success",
        )


class INCOISHighWaveLiveAdapter:
    """Verified live INCOIS HWA/SSA connector."""

    provider = "INCOIS"
    dataset = "incois_hwa"

    def __init__(
        self,
        *,
        alert_url: str = ALERT_URL,
        geometry_url: str = GEOMETRY_URL,
        live_enabled: bool | None = None,
    ) -> None:
        self.live_enabled = (
            get_settings().service.enable_live_sources if live_enabled is None else live_enabled
        )
        self.alert_url = alert_url
        self.geometry_url = geometry_url

    @staticmethod
    def _http_get(url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) as response:  # noqa: S310
            status = getattr(response, "status", response.getcode())
            if status not in {200, 202}:
                raise SourceUnavailableError(f"INCOIS HWA HTTP {status} for {url}")
            body = response.read()
            content_encoding = response.headers.get("Content-Encoding", "").lower()
            if body.startswith(b"\x1f\x8b"):
                try:
                    return gzip.decompress(body)
                except OSError as exc:
                    raise SourceContractError(
                        f"INCOIS HWA returned malformed gzip content for {url}"
                    ) from exc
            if "gzip" in content_encoding and body:
                raise SourceContractError(
                    f"INCOIS HWA declared gzip content without a gzip body for {url}"
                )
            return body

    def fetch(self) -> FetchResult:
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "INCOIS HWA live connector is disabled by MDE_ENABLE_LIVE_SOURCES"
            )
        try:
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="incois-hwa") as pool:
                alert_future = pool.submit(self._http_get, self.alert_url)
                geometry_future = pool.submit(self._http_get, self.geometry_url)
                alert_data = alert_future.result()
                geometry_data = geometry_future.result()
        except SourceUnavailableError:
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise SourceUnavailableError(f"INCOIS HWA fetch failed: {exc}") from exc

        alerts, diagnostics = parse_live_high_wave_alerts(
            alert_data,
            geometry_data,
            alert_url=self.alert_url,
            geometry_url=self.geometry_url,
        )
        retrieved_at = datetime.now(tz=UTC)
        raw_envelope = json.dumps(
            {
                "retrieved_at": retrieved_at.isoformat(),
                "responses": {
                    self.alert_url: json.loads(alert_data),
                    self.geometry_url: json.loads(geometry_data),
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        result_state = "degraded" if diagnostics else ("empty" if not alerts else "success")
        return FetchResult(
            raw=RawPayload(
                provider=self.provider,
                dataset=self.dataset,
                data=raw_envelope,
                ext="json",
                media_type="application/json",
                source_url=self.alert_url,
                retrieved_at=retrieved_at,
            ),
            alerts=alerts,
            result_state=result_state,
            status_detail=(
                "source healthy but no active HWA/SSA records" if result_state == "empty" else None
            ),
            diagnostics=diagnostics,
        )
