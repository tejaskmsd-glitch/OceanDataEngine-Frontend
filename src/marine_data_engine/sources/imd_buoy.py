"""IMD moored-buoy HTML observation adapter.

Pattern-verified entry URL (source_mapping):
``https://mausam.imd.gov.in/imd_latest/contents/buoy_obs.php?id=<stationId>``

The response is an HTML page containing a table of latest buoy observations.
There is no machine (JSON/CSV) endpoint, so this module parses the HTML table
with the stdlib :class:`html.parser.HTMLParser` (no third-party HTML deps).

Each table row carries several parameters (wind, pressure, temperature, wave
height); a row therefore fans out into one :class:`ParsedObservation` per
present parameter, all sharing the row's ``station_id`` and ``observed_at``.

Source values are normalized to canonical units on parse:
    wind speed   knots -> m/s      (domain.normalize.normalize_wind)
    pressure     hPa   -> hPa       (passthrough)
    temperature  degC  -> degC      (passthrough)

CANARY: the header row is validated against an expected set of column labels.
If the upstream HTML structure changes (columns renamed/removed/reordered
beyond recognition), :class:`BuoyStructureError` is raised instead of silently
emitting garbage.

The live connector is DISABLED by default and only performs an HTTP GET when
``enable_live_sources`` is true (tests never touch the network).
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser

from dateutil import parser as dtparser

from ..config import get_settings
from ..domain.normalize import normalize_pressure, normalize_sst, normalize_wind
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedObservation,
    RawPayload,
)

_HTTP_TIMEOUT_S = 10
_USER_AGENT = "marine-data-engine/0.1 (+ingest)"

BUOY_URL_TEMPLATE = "https://mausam.imd.gov.in/imd_latest/contents/buoy_obs.php?id={station_id}"

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


class IMDBuoyLiveAdapter:
    """Live IMD buoy connector — DISABLED unless explicitly enabled.

    Fetches ``buoy_obs.php?id=<stationId>`` and parses the HTML table. Network
    fetching is only attempted when ``enable_live_sources`` is true; otherwise
    it raises to prevent accidental live calls.
    """

    provider = "IMD"
    dataset = "imd_buoy"

    def __init__(self, station_id: str) -> None:
        self.station_id = station_id
        self.live_enabled = get_settings().service.enable_live_sources

    @staticmethod
    def _http_get(url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:  # noqa: S310
            return resp.read()

    def fetch(self) -> FetchResult:
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "IMD buoy live connector is disabled. Set MDE_ENABLE_LIVE_SOURCES=true "
                "to enable, or use the fixture adapter."
            )
        url = BUOY_URL_TEMPLATE.format(station_id=self.station_id)
        try:
            html_bytes = self._http_get(url)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise RuntimeError(f"IMD buoy fetch failed ({url}): {exc}") from exc

        observations = parse_buoy_html(html_bytes, station_id=self.station_id, source_url=url)
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=html_bytes,
            ext="html",
            media_type="text/html",
            source_url=url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw, observations=observations)
