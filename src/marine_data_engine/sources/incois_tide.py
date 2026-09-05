"""INCOIS TEWS tide-gauge station and latest-observation adapter.

The official station catalog is XML. Per-station JSON contains historical chart
arrays whose x-values are malformed upstream; this adapter deliberately ignores
those arrays and emits only each sensor's explicit ``lastReportedDate`` and
``lastreportedvalue`` fields, documented by the official chart as UTC/metres.
"""

from __future__ import annotations

import io
import json
import math
import ssl
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from dateutil import parser as dtparser

from ..config import get_settings
from ..tls import build_incois_ssl_context
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedObservation,
    ParsedStation,
    RawPayload,
    SourceContractError,
    SourceUnavailableError,
)

STATION_URL = "https://tsunami.incois.gov.in/itews/homexmls/TideStations.xml"
OBSERVATION_URL_TEMPLATE = "https://tsunami.incois.gov.in/itews/JSONS/{station}_1.json"
_HTTP_TIMEOUT_S = 20
_USER_AGENT = "marine-data-engine/0.1 (+incois-tews-tide)"
_ACTUAL_SENSOR_NAMES = {"RAD", "PRS", "ENC"}
_NOT_REPORTING_DATE_MARKERS = {"not reporting", "notreporting"}


@dataclass(frozen=True)
class TEWSStation:
    parsed: ParsedStation
    code: str
    display_name: str


def _parse_dt(value: str | None) -> datetime | None:
    """Backward-compatible parser for the deterministic legacy fixture."""
    if not value:
        return None
    try:
        dt = dtparser.parse(value)
    except (ValueError, OverflowError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_tide_observations(
    data: bytes, *, source_url: str | None = None
) -> list[ParsedObservation]:
    """Parse the deterministic legacy tide fixture contract."""
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
        parsed.append(
            ParsedObservation(
                station_id=str(station_id),
                station_type="tide_gauge",
                latitude=float(lat) if lat is not None else None,
                longitude=float(lon) if lon is not None else None,
                parameter="water_level",
                value=float(level) if level is not None else None,
                unit="m",
                observed_at=_parse_dt(entry.get("observation_time") or entry.get("time")),
                provider="INCOIS",
                source_dataset="incois_tide",
                source_url=source_url,
                source_metadata={"fixture_contract": True},
            )
        )
    return parsed


def _strict_float(value: object, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise SourceContractError(f"invalid TEWS {field}: {value!r}") from exc
    if not math.isfinite(parsed):
        raise SourceContractError(f"non-finite TEWS {field}: {value!r}")
    return parsed


def _parse_station_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%b-%d %H:%M", "%Y-%b-%d %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_tews_station_xml(
    data: bytes, *, source_url: str = STATION_URL
) -> tuple[list[TEWSStation], list[str]]:
    """Parse the official ``TideStations.xml`` station catalog."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise SourceContractError("TEWS station catalog is not valid XML") from exc
    if root.tag != "stations":
        raise SourceContractError(f"unexpected TEWS station root {root.tag!r}")

    stations: list[TEWSStation] = []
    diagnostics: list[str] = []
    seen: set[str] = set()
    for node in root.findall("station"):

        def text(tag: str, bound_node: ET.Element = node) -> str | None:
            value = bound_node.findtext(tag)
            return value.strip() if value and value.strip() else None

        code = text("statname")
        display_name = text("statrealName")
        if not code or not display_name:
            diagnostics.append("TEWS station missing statname/statrealName")
            continue
        uid = f"TEWS:{code.lower()}"
        if uid in seen:
            diagnostics.append(f"duplicate TEWS station code {code}")
            continue
        seen.add(uid)
        try:
            latitude = _strict_float(text("latitude"), "station latitude")
            longitude = _strict_float(text("longitude"), "station longitude")
        except SourceContractError as exc:
            diagnostics.append(f"{code}: {exc}")
            continue
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            diagnostics.append(f"{code}: station coordinates out of range")
            continue
        status = node.attrib.get("status")
        station_date_raw = text("date")
        station_date = _parse_station_time(station_date_raw)
        normalized_station_date = " ".join((station_date_raw or "").lower().split())
        if (
            station_date_raw
            and station_date is None
            and normalized_station_date not in _NOT_REPORTING_DATE_MARKERS
        ):
            diagnostics.append(f"{code}: unparsed station date {station_date_raw!r}")
        parsed = ParsedStation(
            station_uid=uid,
            name=display_name,
            station_type="tide_gauge",
            latitude=latitude,
            longitude=longitude,
            status=status,
            provider="INCOIS",
            source_dataset="incois_tide",
            source_url=source_url,
            last_reported_at=station_date,
            source_metadata={
                "station_code": code,
                "display_name": display_name,
                "country": text("country"),
                "owner": text("owner"),
                "color_class": text("colorClass"),
                "catalog_date": station_date_raw,
                "catalog_date_timezone": "UTC",
            },
        )
        stations.append(TEWSStation(parsed=parsed, code=code, display_name=display_name))
    return stations, diagnostics


def _parse_explicit_observation_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_tews_observation_series(
    data: bytes,
    station: TEWSStation,
    *,
    source_url: str,
    retrieved_at: datetime,
    max_age: timedelta = timedelta(hours=24),
) -> tuple[list[ParsedObservation], list[str]]:
    """Parse only explicit latest sensor fields; never inspect chart x-values."""
    try:
        series_list = json.loads(data)
    except json.JSONDecodeError as exc:
        raise SourceContractError(f"TEWS {station.code} response is not valid JSON") from exc
    if not isinstance(series_list, list):
        raise SourceContractError(f"TEWS {station.code} response must be an array")
    if not series_list:
        return [], []

    observations: list[ParsedObservation] = []
    diagnostics: list[str] = []
    for series in series_list:
        if not isinstance(series, dict):
            diagnostics.append(f"{station.code}: non-object chart series")
            continue
        sensor = str(series.get("name") or "").strip().upper()
        # Predicted and Residual are not observations. Only the verified TEWS
        # physical sensor names are eligible.
        if sensor not in _ACTUAL_SENSOR_NAMES:
            continue
        observed_at = _parse_explicit_observation_time(series.get("lastReportedDate"))
        if observed_at is None:
            diagnostics.append(f"{station.code}/{sensor}: invalid lastReportedDate")
            continue
        raw_value = series.get("lastreportedvalue")
        try:
            value = _strict_float(raw_value, "lastreportedvalue")
        except SourceContractError as exc:
            diagnostics.append(f"{station.code}/{sensor}: {exc}")
            continue
        age = retrieved_at - observed_at
        if age > max_age or observed_at > retrieved_at + timedelta(minutes=15):
            diagnostics.append(
                f"{station.code}/{sensor}: explicit latest value outside freshness policy"
            )
            continue
        observations.append(
            ParsedObservation(
                station_id=station.parsed.station_uid,
                station_type="tide_gauge",
                latitude=station.parsed.latitude,
                longitude=station.parsed.longitude,
                parameter="water_level",
                value=value,
                unit="m",
                observed_at=observed_at,
                provider="INCOIS",
                source_dataset="incois_tide",
                source_url=source_url,
                sensor_id=sensor,
                source_metadata={
                    **station.parsed.source_metadata,
                    "station_status": station.parsed.status,
                    "sensor_name": sensor,
                    "last_reported_date_timezone": "UTC",
                    "historical_data_x_values_ignored": True,
                    "source_unit": "m",
                },
            )
        )
    return observations, diagnostics


def _raw_archive(station_xml: bytes, responses: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        members = {"TideStations.xml": station_xml, **responses}
        for name, body in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    return output.getvalue()


class INCOISTideFixtureAdapter:
    """Explicit deterministic fixture adapter; never selected in production."""

    provider = "INCOIS"
    dataset = "incois_tide"
    live_enabled = False

    def __init__(self, data: bytes, *, source_url: str | None = None) -> None:
        self._data = data
        self._source_url = source_url or "fixture://incois/tide"

    def fetch(self) -> FetchResult:
        observations = parse_tide_observations(self._data, source_url=self._source_url)
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
            observations=observations,
            result_state="empty" if not observations else "success",
        )


class INCOISTideLiveAdapter:
    """Verified TEWS station/latest-observation connector."""

    provider = "INCOIS"
    dataset = "incois_tide"

    def __init__(
        self,
        *,
        station_url: str = STATION_URL,
        observation_url_template: str = OBSERVATION_URL_TEMPLATE,
        live_enabled: bool | None = None,
        max_workers: int = 8,
        max_age_hours: float = 24.0,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.live_enabled = (
            get_settings().service.enable_live_sources if live_enabled is None else live_enabled
        )
        self.station_url = station_url
        self.observation_url_template = observation_url_template
        self.max_workers = max(1, min(max_workers, 12))
        self.max_age = timedelta(hours=max_age_hours)
        self._ssl_context = ssl_context or build_incois_ssl_context()

    def _http_get(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json,application/xml"},
        )
        with urllib.request.urlopen(  # noqa: S310
            request, timeout=_HTTP_TIMEOUT_S, context=self._ssl_context
        ) as response:
            status = getattr(response, "status", response.getcode())
            if status != 200:
                raise SourceUnavailableError(f"TEWS HTTP {status} for {url}")
            return response.read()

    def _observation_url(self, station: TEWSStation) -> str:
        filename = urllib.parse.quote(station.display_name.upper(), safe="")
        return self.observation_url_template.format(station=filename)

    def fetch(self) -> FetchResult:
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "INCOIS tide live connector is disabled by MDE_ENABLE_LIVE_SOURCES"
            )
        try:
            station_xml = self._http_get(self.station_url)
        except SourceUnavailableError:
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise SourceUnavailableError(f"TEWS station catalog fetch failed: {exc}") from exc

        stations, diagnostics = parse_tews_station_xml(
            station_xml, source_url=self.station_url
        )
        reporting = [
            station
            for station in stations
            if str(station.parsed.status or "").strip().lower() == "reporting"
        ]
        retrieved_at = datetime.now(tz=UTC)
        responses: dict[str, bytes] = {}
        observations: list[ParsedObservation] = []

        with ThreadPoolExecutor(
            max_workers=self.max_workers, thread_name_prefix="incois-tews"
        ) as pool:
            futures = {
                pool.submit(self._http_get, self._observation_url(station)): station
                for station in reporting
            }
            for future in as_completed(futures):
                station = futures[future]
                url = self._observation_url(station)
                try:
                    body = future.result()
                    response_name = f"observations/{station.display_name.upper()}_1.json"
                    responses[response_name] = body
                    parsed, series_diagnostics = parse_tews_observation_series(
                        body,
                        station,
                        source_url=url,
                        retrieved_at=retrieved_at,
                        max_age=self.max_age,
                    )
                    observations.extend(parsed)
                    diagnostics.extend(series_diagnostics)
                except Exception as exc:  # one station must not hide healthy peers
                    diagnostics.append(
                        f"{station.code}: observation fetch/parse failed: "
                        f"{type(exc).__name__}: {exc}"
                    )

        state = "degraded" if diagnostics else ("empty" if not observations else "success")
        return FetchResult(
            raw=RawPayload(
                provider=self.provider,
                dataset=self.dataset,
                data=_raw_archive(station_xml, responses),
                ext="tar.gz",
                media_type="application/gzip",
                source_url=self.station_url,
                retrieved_at=retrieved_at,
            ),
            observations=observations,
            stations=[station.parsed for station in stations],
            result_state=state,
            status_detail=(
                "source healthy but reporting stations returned no current observations"
                if state == "empty"
                else None
            ),
            diagnostics=list(dict.fromkeys(diagnostics)),
        )
