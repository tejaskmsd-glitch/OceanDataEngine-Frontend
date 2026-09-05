"""Buoy observation adapters.

Production uses the verified INCOIS Ocean Observation Network (OON): a dynamic
station catalog, a bounded current-station status query, and server-rendered
Highcharts pages whose x-axis explicitly states UTC. Only the final valid chart
pair is parsed, under strict parameter/label/unit and freshness checks.

The legacy IMD table parser remains solely for deterministic tests and is never
selected by the production worker.
"""

from __future__ import annotations

import io
import json
import math
import re
import tarfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser

from dateutil import parser as dtparser

from ..config import get_settings
from ..domain.normalize import normalize_pressure, normalize_sst, normalize_wind
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedObservation,
    ParsedStation,
    RawPayload,
    SourceContractError,
    SourceUnavailableError,
)

_HTTP_TIMEOUT_S = 30
_USER_AGENT = "marine-data-engine/0.1 (+incois-oon-buoy)"

OON_CATALOG_URL = "https://incois.gov.in/OON/fetchMooredBuoyData.jsp"
OON_BACKEND_URL = "https://incois.gov.in/OON/backend_process.jsp"
OON_OMNI_URL = (
    "https://incois.gov.in/site/datainfo/moored_omnidata_stock.jsp"
    "?buoy={station_id}&parameter={parameter}"
)
OON_MOORED_URL = (
    "https://incois.gov.in/site/datainfo/moored_data_stock.jsp"
    "?buoy={station_id}&parameter={parameter}"
)

# Canonical parameter names (align with domain.qc.PHYSICAL_RANGES).
_PARAM_WIND_SPEED = "wind_speed"
_PARAM_WIND_DIR = "wind_direction"
_PARAM_PRESSURE = "sea_level_pressure"
_PARAM_TEMPERATURE = "sea_surface_temperature"
_PARAM_WAVE_HEIGHT = "significant_wave_height"

# Map a normalized header token -> logical column key. The header text is
# lower-cased and stripped of units/punctuation before matching.
_HEADER_ALIASES: dict[str, str] = {
    "station id": "station_id",
    "station": "station_id",
    "buoy": "station_id",
    "latitude": "latitude",
    "lat": "latitude",
    "longitude": "longitude",
    "lon": "longitude",
    "long": "longitude",
    "observation time": "observed_at",
    "obs time": "observed_at",
    "time": "observed_at",
    "date time": "observed_at",
    "wind speed": _PARAM_WIND_SPEED,
    "wind direction": _PARAM_WIND_DIR,
    "pressure": _PARAM_PRESSURE,
    "air pressure": _PARAM_PRESSURE,
    "atmospheric pressure": _PARAM_PRESSURE,
    "air temperature": _PARAM_TEMPERATURE,
    "temperature": _PARAM_TEMPERATURE,
    "sea surface temperature": _PARAM_TEMPERATURE,
    "sst": _PARAM_TEMPERATURE,
    "wave height": _PARAM_WAVE_HEIGHT,
    "significant wave height": _PARAM_WAVE_HEIGHT,
}

# Parameter columns that must map to canonical values, with unit hints derived
# from the header text (e.g. "Wind Speed (knots)").
_PARAM_COLUMNS = {
    _PARAM_WIND_SPEED,
    _PARAM_WIND_DIR,
    _PARAM_PRESSURE,
    _PARAM_TEMPERATURE,
    _PARAM_WAVE_HEIGHT,
}

# Minimum recognizable columns for the page to be considered the buoy table.
_REQUIRED_KEYS = {"station_id"}


class BuoyStructureError(RuntimeError):
    """Raised when the IMD buoy HTML structure is not recognizable.

    Signals a likely upstream layout change (canary), so callers fail loudly
    rather than emitting mis-parsed observations.
    """


def _clean_header(text: str) -> str:
    """Normalize a header cell: lower-case, drop units in ()/[], collapse ws."""
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _unit_from_header(raw_header: str) -> str | None:
    """Extract a unit hint from a header like ``Wind Speed (knots)``."""
    m = re.search(r"[\(\[]([^)\]]+)[\)\]]", raw_header)
    return m.group(1).strip() if m else None


def _to_float(text: str | None) -> float | None:
    if text is None:
        return None
    t = text.strip()
    if t == "" or t.upper() in {"NA", "N/A", "-", "--", "NULL", "NAN"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _parse_dt(text: str | None) -> datetime | None:
    if not text or not text.strip():
        return None
    try:
        dt = dtparser.parse(text.strip())
    except (ValueError, OverflowError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class _BuoyTableParser(HTMLParser):
    """Collect the first ``<table>``'s header labels and data rows."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_table = False
        self._in_cell = False
        self._is_header_cell = False
        self._cell_buf: list[str] = []
        self._current_row: list[str] = []
        self._current_row_is_header = False
        self.headers: list[str] = []
        self.rows: list[list[str]] = []
        self._table_done = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if self._table_done:
            return
        if tag == "table" and not self._in_table:
            self._in_table = True
        elif self._in_table and tag == "tr":
            self._current_row = []
            self._current_row_is_header = False
        elif self._in_table and tag in ("td", "th"):
            self._in_cell = True
            self._is_header_cell = tag == "th"
            self._cell_buf = []

    def handle_endtag(self, tag: str) -> None:
        if self._table_done or not self._in_table:
            return
        if tag in ("td", "th") and self._in_cell:
            text = "".join(self._cell_buf).strip()
            self._current_row.append(text)
            if self._is_header_cell:
                self._current_row_is_header = True
            self._in_cell = False
        elif tag == "tr":
            if self._current_row:
                if self._current_row_is_header and not self.headers:
                    self.headers = self._current_row
                elif not self._current_row_is_header:
                    self.rows.append(self._current_row)
        elif tag == "table":
            self._in_table = False
            self._table_done = True

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_buf.append(data)


def _build_column_map(headers: list[str]) -> dict[int, tuple[str, str | None]]:
    """Map column index -> (logical key, unit hint) from header labels.

    Raises :class:`BuoyStructureError` when no recognizable columns are found
    or the required ``station_id`` column is missing (canary).
    """
    column_map: dict[int, tuple[str, str | None]] = {}
    for idx, raw in enumerate(headers):
        key = _HEADER_ALIASES.get(_clean_header(raw))
        if key is not None:
            column_map[idx] = (key, _unit_from_header(raw))

    found_keys = {key for key, _ in column_map.values()}
    if not found_keys:
        raise BuoyStructureError(
            "IMD buoy HTML has no recognizable columns "
            f"(headers={headers!r}). Upstream layout may have changed."
        )
    missing = _REQUIRED_KEYS - found_keys
    if missing:
        raise BuoyStructureError(
            f"IMD buoy HTML missing required column(s) {sorted(missing)} "
            f"(headers={headers!r}). Upstream layout may have changed."
        )
    return column_map


def _normalize_param(param: str, value: float, unit_hint: str | None) -> tuple[float, str]:
    """Normalize a raw parameter value+unit to canonical (value, unit)."""
    if param == _PARAM_WIND_SPEED:
        return normalize_wind(value, unit_hint or "m/s")
    if param == _PARAM_PRESSURE:
        return normalize_pressure(value, unit_hint or "hPa")
    if param == _PARAM_TEMPERATURE:
        return normalize_sst(value, unit_hint or "degC")
    if param == _PARAM_WIND_DIR:
        return (value % 360.0, "deg")
    if param == _PARAM_WAVE_HEIGHT:
        return (value, "m")
    return (value, unit_hint or "")


def parse_buoy_html(
    html_bytes: bytes, *, station_id: str | None = None, source_url: str | None = None
) -> list[ParsedObservation]:
    """Parse an IMD buoy observations HTML page into observations.

    ``station_id`` (from the request) is used as a fallback when a row omits
    an explicit station column. Raises :class:`BuoyStructureError` when the
    table structure is unrecognizable.
    """
    parser = _BuoyTableParser()
    parser.feed(html_bytes.decode("utf-8", errors="replace"))

    if not parser.headers:
        raise BuoyStructureError(
            "IMD buoy HTML contained no table header row. "
            "Upstream layout may have changed."
        )

    column_map = _build_column_map(parser.headers)
    param_indices = {
        idx: (key, unit) for idx, (key, unit) in column_map.items() if key in _PARAM_COLUMNS
    }

    observations: list[ParsedObservation] = []
    for row in parser.rows:
        row_station = station_id
        latitude = longitude = None
        observed_at = None

        for idx, (key, _unit) in column_map.items():
            if idx >= len(row):
                continue
            cell = row[idx]
            if key == "station_id" and cell:
                row_station = cell
            elif key == "latitude":
                latitude = _to_float(cell)
            elif key == "longitude":
                longitude = _to_float(cell)
            elif key == "observed_at":
                observed_at = _parse_dt(cell)

        if not row_station:
            # Skip filler/blank rows that carry no station identity.
            continue

        for idx, (param, unit_hint) in param_indices.items():
            if idx >= len(row):
                continue
            raw_val = _to_float(row[idx])
            if raw_val is None:
                continue
            value, unit = _normalize_param(param, raw_val, unit_hint)
            observations.append(
                ParsedObservation(
                    station_id=row_station,
                    station_type="buoy",
                    latitude=latitude,
                    longitude=longitude,
                    parameter=param,
                    value=value,
                    unit=unit,
                    observed_at=observed_at,
                    source_url=source_url,
                    source_metadata={"fixture_contract": True},
                )
            )
    return observations


class IMDBuoyFixtureAdapter:
    """Deterministic offline IMD buoy adapter reading a fixture HTML page."""

    provider = "IMD"
    dataset = "imd_buoy"
    live_enabled = False

    def __init__(
        self, html_bytes: bytes, *, station_id: str | None = None, source_url: str | None = None
    ) -> None:
        self._html = html_bytes
        self._station_id = station_id
        self._source_url = source_url or "fixture://imd/buoy"

    def fetch(self) -> FetchResult:
        observations = parse_buoy_html(
            self._html, station_id=self._station_id, source_url=self._source_url
        )
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=self._html,
            ext="html",
            media_type="text/html",
            source_url=self._source_url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw, observations=observations)


class _OptionParser(HTMLParser):
    """Collect server-rendered ``<option>`` values, labels, and selection."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.options: list[tuple[str, str, bool]] = []
        self._value: str | None = None
        self._selected = False
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "option":
            return
        attributes = {str(key).lower(): value for key, value in attrs}
        self._value = attributes.get("value")
        self._selected = "selected" in attributes
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._value is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self._value is not None:
            label = " ".join("".join(self._text).split())
            self.options.append((self._value, label, self._selected))
            self._value = None
            self._selected = False
            self._text = []


_OON_PARAMETER_SPECS: dict[str, tuple[str, set[str], set[str]]] = {
    "wind_speed": ("wind_speed", {"Wind Speed"}, {"m/s"}),
    "hm0": (
        "significant_wave_height",
        {"Significant Wave Height", "Wave Height"},
        {"m"},
    ),
}
_DATA_START_RE = re.compile(r"\bdata\s*:\s*\[")
_DATA_END_RE = re.compile(r"\]\s*,\s*tooltip\s*:")
_DATA_PAIR_RE = re.compile(
    r"\[\s*(?P<epoch>-?\d{10,16})\s*,\s*"
    r"(?P<value>-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*\]"
)


def _parse_utc_marker_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_oon_station_catalog(
    data: bytes, *, source_url: str = OON_CATALOG_URL
) -> list[ParsedStation]:
    """Parse the official dynamic OON moored-buoy station catalog."""
    try:
        entries = json.loads(data)
    except json.JSONDecodeError as exc:
        raise SourceContractError("OON station catalog is not valid JSON") from exc
    if not isinstance(entries, list):
        raise SourceContractError("OON station catalog must be an array")

    stations: list[ParsedStation] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise SourceContractError("OON station catalog contains a non-object item")
        station_id = str(entry.get("buoyId") or "").strip().upper()
        station_type = str(entry.get("type") or "").strip().upper()
        status = str(entry.get("status") or "").strip().lower()
        if not station_id or station_type not in {"OMNI", "MORED"}:
            raise SourceContractError(f"invalid OON station identity/type: {entry!r}")
        if station_id in seen:
            raise SourceContractError(f"duplicate OON station id {station_id}")
        seen.add(station_id)
        latitude = _to_float(str(entry.get("latitude", "")))
        longitude = _to_float(str(entry.get("longitude", "")))
        if latitude is None or longitude is None or not (
            -90 <= latitude <= 90 and -180 <= longitude <= 180
        ):
            raise SourceContractError(f"invalid OON coordinates for {station_id}")
        stations.append(
            ParsedStation(
                station_uid=station_id,
                name=station_id,
                station_type=f"buoy_{station_type.lower()}",
                latitude=latitude,
                longitude=longitude,
                status=status,
                provider="INCOIS",
                source_dataset="incois_buoy",
                source_url=source_url,
                source_metadata={
                    "oon_type": station_type,
                    "oon_status": status,
                    "status_semantics": {"new": "active", "old": "inactive"},
                },
            )
        )
    return stations


def parse_oon_backend_status(data: bytes) -> dict[str, dict]:
    """Parse OON's bounded current-station marker response."""
    try:
        entries = json.loads(data)
    except json.JSONDecodeError as exc:
        raise SourceContractError("OON backend status is not valid JSON") from exc
    if not isinstance(entries, list):
        raise SourceContractError("OON backend status must be an array")
    result: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        station_id = str(entry.get("buoy_id") or "").strip().upper()
        reported_at = _parse_utc_marker_time(entry.get("time"))
        if not station_id or reported_at is None:
            continue
        previous = result.get(station_id)
        if previous is None or reported_at > previous["reported_at"]:
            result[station_id] = {**entry, "reported_at": reported_at}
    return result


def parse_oon_chart(
    html_bytes: bytes,
    *,
    station: ParsedStation,
    parameter_token: str,
    source_url: str,
    retrieved_at: datetime,
    max_age: timedelta = timedelta(hours=24),
) -> ParsedObservation | None:
    """Extract the final valid OON chart pair without materializing history."""
    spec = _OON_PARAMETER_SPECS.get(parameter_token)
    if spec is None:
        raise SourceContractError(f"unverified OON parameter token {parameter_token!r}")
    canonical_parameter, expected_labels, expected_units = spec
    html = html_bytes.decode("utf-8", errors="replace")

    option_parser = _OptionParser()
    option_parser.feed(html)
    selected = [
        (value, label)
        for value, label, is_selected in option_parser.options
        if is_selected
    ]
    if not (len(selected) == 1 and selected[0][0] == parameter_token):
        raise BuoyStructureError(
            f"OON chart did not select requested parameter {parameter_token!r}: {selected!r}"
        )
    selected_label = selected[0][1]
    if selected_label not in expected_labels:
        raise BuoyStructureError(
            f"OON parameter/label mismatch: {parameter_token!r} -> {selected_label!r}"
        )
    if not re.search(r"useUTC\s*:\s*true", html) or "Time (UTC)" not in html:
        raise BuoyStructureError("OON chart no longer declares UTC timestamps")

    unit_match = re.search(
        r"yAxis\s*:\s*\[[\s\S]{0,3000}?title\s*:\s*\{[\s\S]{0,500}?"
        r"text\s*:\s*\[\s*[\"'](?P<unit>[^\"']+)[\"']\s*\]",
        html,
    )
    if unit_match is None:
        raise BuoyStructureError("OON chart unit was not found")
    source_unit = unit_match.group("unit").strip()
    if source_unit not in expected_units:
        raise BuoyStructureError(
            f"OON parameter/unit mismatch: {parameter_token!r} -> {source_unit!r}"
        )

    data_start = _DATA_START_RE.search(html)
    if data_start is None:
        raise BuoyStructureError("OON chart data array was not found")
    data_end = _DATA_END_RE.search(html, data_start.end())
    if data_end is None:
        raise BuoyStructureError("OON chart data-array boundary was not found")
    last_pair = None
    for pair in _DATA_PAIR_RE.finditer(html, data_start.end(), data_end.start()):
        last_pair = pair
    if last_pair is None:
        # A valid selected chart with an empty array is healthy-empty.
        return None

    epoch_ms = int(last_pair.group("epoch"))
    value = float(last_pair.group("value"))
    if not math.isfinite(value):
        raise BuoyStructureError("OON chart latest value is non-finite")
    try:
        observed_at = datetime.fromtimestamp(epoch_ms / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise BuoyStructureError("OON chart latest epoch is invalid") from exc
    if observed_at > retrieved_at + timedelta(minutes=15) or retrieved_at - observed_at > max_age:
        raise BuoyStructureError(
            f"OON chart latest value is outside freshness policy: {observed_at.isoformat()}"
        )

    return ParsedObservation(
        station_id=station.station_uid,
        station_type=station.station_type or "buoy",
        latitude=station.latitude,
        longitude=station.longitude,
        parameter=canonical_parameter,
        value=value,
        unit=source_unit,
        observed_at=observed_at,
        provider="INCOIS",
        source_dataset="incois_buoy",
        source_url=source_url,
        sensor_id=parameter_token,
        source_metadata={
            **station.source_metadata,
            "station_status": station.status,
            "parameter_token": parameter_token,
            "selected_parameter_label": selected_label,
            "chart_unit": source_unit,
            "chart_time_axis": "UTC",
            "history_policy": "only final valid pair parsed",
        },
    )


def _oon_archive(catalog: bytes, backend: bytes, pages: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        members = {"fetchMooredBuoyData.json": catalog, "backend_process.json": backend, **pages}
        for name, body in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    return output.getvalue()


class INCOISBuoyLiveAdapter:
    """Verified dynamic OON moored-buoy connector with bounded concurrency."""

    provider = "INCOIS"
    dataset = "incois_buoy"

    def __init__(
        self,
        station_id: str | None = None,
        *,
        station_ids: list[str] | tuple[str, ...] | None = None,
        parameter_tokens: list[str] | tuple[str, ...] = ("hm0", "wind_speed"),
        catalog_url: str = OON_CATALOG_URL,
        backend_url: str = OON_BACKEND_URL,
        live_enabled: bool | None = None,
        max_workers: int = 3,
        max_age_hours: float = 24.0,
    ) -> None:
        self.live_enabled = (
            get_settings().service.enable_live_sources if live_enabled is None else live_enabled
        )
        selected_ids = list(station_ids or ())
        if station_id:
            selected_ids.append(station_id)
        self.station_ids = {item.strip().upper() for item in selected_ids if item.strip()}
        self.parameter_tokens = tuple(dict.fromkeys(parameter_tokens))
        unknown = set(self.parameter_tokens) - set(_OON_PARAMETER_SPECS)
        if unknown:
            raise SourceContractError(f"unverified OON parameter token(s): {sorted(unknown)}")
        self.catalog_url = catalog_url
        self.backend_url = backend_url
        self.max_workers = max(1, min(max_workers, 6))
        self.max_age = timedelta(hours=max_age_hours)

    @staticmethod
    def _http_get(url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json,text/html"},
        )
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) as response:  # noqa: S310
            if getattr(response, "status", response.getcode()) != 200:
                raise SourceUnavailableError(f"OON GET failed for {url}")
            return response.read()

    @staticmethod
    def _http_post_json(url: str, payload: dict) -> bytes:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) as response:  # noqa: S310
            if getattr(response, "status", response.getcode()) != 200:
                raise SourceUnavailableError(f"OON POST failed for {url}")
            return response.read()

    @staticmethod
    def _detail_url(station: ParsedStation, token: str) -> str:
        template = (
            OON_OMNI_URL
            if station.source_metadata.get("oon_type") == "OMNI"
            else OON_MOORED_URL
        )
        return template.format(station_id=station.station_uid, parameter=token)

    def fetch(self) -> FetchResult:
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "INCOIS buoy live connector is disabled by MDE_ENABLE_LIVE_SOURCES"
            )
        retrieved_at = datetime.now(tz=UTC)
        marker_payload = {
            "startDate": (retrieved_at - timedelta(days=1)).date().isoformat(),
            "endDate": retrieved_at.date().isoformat(),
            "moored": True,
            "aws": False,
            "drifting": False,
        }
        try:
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="oon-catalog") as pool:
                catalog_future = pool.submit(self._http_get, self.catalog_url)
                backend_future = pool.submit(
                    self._http_post_json, self.backend_url, marker_payload
                )
                catalog_body = catalog_future.result()
                backend_body = backend_future.result()
        except SourceUnavailableError:
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise SourceUnavailableError(f"OON catalog/status fetch failed: {exc}") from exc

        stations = parse_oon_station_catalog(catalog_body, source_url=self.catalog_url)
        backend = parse_oon_backend_status(backend_body)
        diagnostics: list[str] = []
        eligible: list[ParsedStation] = []
        for station in stations:
            marker = backend.get(station.station_uid)
            if marker:
                station.last_reported_at = marker["reported_at"]
                station.source_metadata = {
                    **station.source_metadata,
                    "backend_category": marker.get("category"),
                    "backend_reported_at": marker["reported_at"].isoformat(),
                    "backend_coordinates": {
                        "latitude": marker.get("lat"),
                        "longitude": marker.get("lon"),
                    },
                    "coordinate_policy": "catalog coordinates retained",
                }
            if station.status != "new" or marker is None:
                continue
            if retrieved_at - marker["reported_at"] > self.max_age:
                continue
            if self.station_ids and station.station_uid not in self.station_ids:
                continue
            eligible.append(station)

        observations: list[ParsedObservation] = []
        pages: dict[str, bytes] = {}
        with ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="oon-chart",
        ) as pool:
            futures = {}
            for station in eligible:
                for token in self.parameter_tokens:
                    url = self._detail_url(station, token)
                    futures[pool.submit(self._http_get, url)] = (station, token, url)
            for future in as_completed(futures):
                station, token, url = futures[future]
                try:
                    body = future.result()
                    pages[f"charts/{station.station_uid}_{token}.html"] = body
                    observation = parse_oon_chart(
                        body,
                        station=station,
                        parameter_token=token,
                        source_url=url,
                        retrieved_at=retrieved_at,
                        max_age=self.max_age,
                    )
                    if observation is not None:
                        observations.append(observation)
                except Exception as exc:
                    diagnostics.append(
                        f"{station.station_uid}/{token}: {type(exc).__name__}: {exc}"
                    )

        state = "degraded" if diagnostics else ("empty" if not observations else "success")
        return FetchResult(
            raw=RawPayload(
                provider=self.provider,
                dataset=self.dataset,
                data=_oon_archive(catalog_body, backend_body, pages),
                ext="tar.gz",
                media_type="application/gzip",
                source_url=self.catalog_url,
                retrieved_at=retrieved_at,
            ),
            observations=observations,
            stations=stations,
            result_state=state,
            status_detail=(
                "source healthy but no current verified buoy parameter values"
                if state == "empty"
                else None
            ),
            diagnostics=list(dict.fromkeys(diagnostics)),
        )


class IMDBuoyLiveAdapter(INCOISBuoyLiveAdapter):
    """Backward-compatible name; production data is INCOIS OON, not IMD."""
