"""IMD marine bulletin adapter (coastal and sea-area weather bulletins).

Why this source exists
----------------------
IMD's *numeric* marine NWP contract is unavailable: the documented API returns
HTTP 401 and no endpoint/schema/auth scheme is published (see
:mod:`.imd_nwp`, which deliberately performs no request). However IMD publishes
its operational **Coastal Weather Bulletin** and **Sea Area Bulletin** as open,
unauthenticated HTML from the Area/Cyclone Warning Centres. Those bulletins
carry, per named area:

* ``Wind`` — an explicit numeric range with gusts, in knots.
* ``Sea Condition`` — an authoritative WMO 3700 / Douglas **category**.
* ``Weather``, ``Visibility`` — descriptive text.
* ``Port Signal``, ``Storm Surge/Tidal Warning`` — operational warnings.

plus an explicit UTC validity window and an issue time.

What this adapter will and will not do
--------------------------------------
* Wind is parsed to a numeric range and converted knots -> m/s by the exact
  factor ``1852/3600``. The **upper** bound is emitted as the value so a range
  can only make downstream risk more pessimistic; both bounds are retained in
  metadata.
* Sea condition is emitted as a **categorical** record with ``value=None``.
  This adapter never converts a category into a wave height — that mapping is
  the safety gate's job, via the published table in :mod:`..domain.sea_state`,
  and it is always tagged as derived rather than measured.
* Bulletins are **area-scoped**, not point forecasts. Latitude/longitude are
  left ``None`` and the verbatim area name is retained. Nothing here implies a
  value at a specific coordinate.
* Unverified area names, field labels, or wind units raise
  :class:`SourceContractError`. Nothing is guessed, and a parse failure is
  never silently reported as "no data".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser

from ..domain.sea_state import parse_sea_state_category
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedAlert,
    ParsedForecast,
    RawPayload,
    SourceContractError,
    SourceUnavailableError,
)

PROVIDER = "IMD"
DATASET = "imd_marine_bulletin"

BASE_URL = "https://mausam.imd.gov.in/Forecast"
COASTAL_PATH = "coastal_bulletin_new.php"
SEA_AREA_PATH = "seaarea_bulletin_new.php"

KIND_COASTAL = "coastal"
KIND_SEA_AREA = "sea_area"

#: Exact knots -> m/s conversion (1 nautical mile = 1852 m).
_KNOTS_TO_MS = 1852.0 / 3600.0

_HTTP_TIMEOUT_S = 30.0

#: Verified issuing centres by bulletin id, confirmed against the live pages.
CENTRES: dict[int, str] = {
    1: "ACWC KOLKATA",
    2: "CWC THIRUVANANTHAPURAM",
    3: "CWC AHMEDABAD",
    4: "ACWC MUMBAI",
    5: "CWC BHUBANESWAR",
    6: "ACWC CHENNAI",
    7: "CWC VISAKHAPATANAM PORT",
}

#: Field labels published inside a bulletin block. Any other label encountered
#: in a label position is a contract change and raises rather than being dropped.
_FIELD_LABELS: dict[str, str] = {
    "wind": "wind",
    "weather": "weather",
    "visibility": "visibility",
    "sea condition": "sea_condition",
    "port signal": "port_signal",
    "storm surge/tidal warning": "storm_surge_tidal_warning",
    "storm surge / tidal warning": "storm_surge_tidal_warning",
    "synoptic situation": "synoptic_situation",
    "ttt warning": "ttt_warning",
    "time of issue": "time_of_issue",
    "part 4": "part_4",
    "part 5": "part_5",
    "part 6": "part_6",
}

#: Verified area vocabulary per (kind, centre id). Areas are matched exactly
#: (case-insensitively) so a renamed or newly added IMD area fails loudly
#: instead of being silently mis-scoped.
AREA_VOCABULARY: dict[tuple[str, int], tuple[str, ...]] = {
    (KIND_COASTAL, 4): (
        "North Maharashtra coast",
        "South Maharashtra and Goa coast",
    ),
    (KIND_SEA_AREA, 4): (
        "North East Arabian Sea",
        "North West Arabian Sea",
        "West Central Arabian Sea",
        "East Central Arabian Sea",
        "South West Arabian Sea",
        "South East Arabian Sea",
        "Lakshadweep Area",
        "Maldives Area",
    ),
}

#: Values that mean "no warning in force" for the operational warning rows.
_NIL_TOKENS = ("nil", "nil at all ports", "no warning", "none", "-", "--")

_VALIDITY_RE = re.compile(
    r"valid\s+for\s+(?P<hours>\d+)\s*hrs?\s+from\s+"
    r"(?P<from_hour>\d{1,2})\s*UTC\s+of\s+(?P<from_date>\d{4}-\d{2}-\d{2})"
    r"(?:\s+to\s+(?P<to_hour>\d{1,2})\s*UTC\s+of\s+(?P<to_date>\d{4}-\d{2}-\d{2}))?",
    re.IGNORECASE,
)
_ISSUE_RE = re.compile(
    r"(?P<hh>\d{1,2}):(?P<mm>\d{2})\s*IST\s+of\s+(?P<date>\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
# "10 TO 15 GUSTING TO 20 KNOTS", "15 - 20 KTS", "15 to 20 Gusting to 25 Knots"
_WIND_RE = re.compile(
    r"(?P<low>\d{1,3})\s*(?:to|-|–)\s*(?P<high>\d{1,3})"
    r"(?:\s*gusting\s*(?:to)?\s*(?P<gust>\d{1,3}))?"
    r"\s*(?P<unit>knots|knot|kts|kt|kmph|km/h)",
    re.IGNORECASE,
)
_IST_OFFSET = timedelta(hours=5, minutes=30)

_KNOT_UNITS = {"knots", "knot", "kts", "kt"}
_KMPH_UNITS = {"kmph", "km/h"}


class _TextNodeParser(HTMLParser):
    """Collect visible text nodes in document order, skipping script/style."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = " ".join(data.split())
        if text:
            self.nodes.append(text)


@dataclass
class WindRange:
    """A parsed numeric wind range, normalised to m/s."""

    low_ms: float
    high_ms: float
    gust_ms: float | None
    source_unit: str
    source_text: str
    direction_text: str

    @property
    def conservative_ms(self) -> float:
        """Upper bound of the sustained range."""
        return self.high_ms


@dataclass
class BulletinArea:
    """One named area block within a bulletin."""

    area_name: str
    fields: dict[str, str]


@dataclass
class ParsedBulletin:
    """A fully parsed bulletin document."""

    kind: str
    centre_id: int
    centre: str
    source_url: str
    valid_from: datetime | None
    valid_until: datetime | None
    issued_at: datetime | None
    synoptic_situation: str | None
    areas: list[BulletinArea]


def _to_ms(value: float, unit: str) -> float:
    """Convert a wind speed to m/s using exact factors."""
    normalised = unit.strip().lower()
    if normalised in _KNOT_UNITS:
        return round(value * _KNOTS_TO_MS, 4)
    if normalised in _KMPH_UNITS:
        return round(value * 1000.0 / 3600.0, 4)
    raise SourceContractError(
        f"unverified IMD bulletin wind unit {unit!r}; "
        f"verified units are {sorted(_KNOT_UNITS | _KMPH_UNITS)}"
    )


def parse_wind_text(text: str) -> WindRange | None:
    """Parse an IMD wind statement into a normalised numeric range.

    Returns ``None`` when the statement carries no numeric range at all (for
    example a purely qualitative remark), so the caller can record the field as
    non-numeric rather than fabricate a value. A numeric range with an
    *unverified unit* raises instead of being silently accepted.
    """
    if not text or not text.strip():
        return None
    match = _WIND_RE.search(text)
    if match is None:
        return None
    low = float(match.group("low"))
    high = float(match.group("high"))
    if high < low:
        low, high = high, low
    gust_raw = match.group("gust")
    unit = match.group("unit")
    gust = _to_ms(float(gust_raw), unit) if gust_raw is not None else None
    direction = text[: match.start()].strip(" ,:-")
    return WindRange(
        low_ms=_to_ms(low, unit),
        high_ms=_to_ms(high, unit),
        gust_ms=gust,
        source_unit=unit.lower(),
        source_text=" ".join(text.split()),
        direction_text=" ".join(direction.split()),
    )


def _parse_validity(flat: str) -> tuple[datetime | None, datetime | None]:
    match = _VALIDITY_RE.search(flat)
    if match is None:
        return None, None
    start = datetime.strptime(match.group("from_date"), "%Y-%m-%d").replace(
        hour=int(match.group("from_hour")), tzinfo=UTC
    )
    if match.group("to_date"):
        end = datetime.strptime(match.group("to_date"), "%Y-%m-%d").replace(
            hour=int(match.group("to_hour")), tzinfo=UTC
        )
    else:
        end = start + timedelta(hours=int(match.group("hours")))
    return start, end


def _parse_issue_time(flat: str) -> datetime | None:
    match = _ISSUE_RE.search(flat)
    if match is None:
        return None
    naive = datetime.strptime(match.group("date"), "%Y-%m-%d").replace(
        hour=int(match.group("hh")), minute=int(match.group("mm"))
    )
    return (naive - _IST_OFFSET).replace(tzinfo=UTC)


def parse_bulletin(
    document: str,
    *,
    kind: str,
    centre_id: int,
    source_url: str,
) -> ParsedBulletin:
    """Parse an IMD bulletin HTML document into structured areas.

    Raises :class:`SourceContractError` when the issuing centre, area
    vocabulary, or field labels do not match the verified contract.
    """
    if kind not in (KIND_COASTAL, KIND_SEA_AREA):
        raise SourceContractError(f"unknown IMD bulletin kind {kind!r}")
    expected_centre = CENTRES.get(centre_id)
    if expected_centre is None:
        raise SourceContractError(f"unverified IMD bulletin centre id {centre_id!r}")

    parser = _TextNodeParser()
    parser.feed(document)
    nodes = parser.nodes
    if not nodes:
        raise SourceContractError("IMD bulletin document contained no text nodes")

    flat = " ".join(nodes)
    if expected_centre.lower() not in flat.lower():
        raise SourceContractError(
            f"IMD bulletin id={centre_id} did not identify expected centre "
            f"{expected_centre!r}; contract may have changed"
        )

    vocabulary = AREA_VOCABULARY.get((kind, centre_id))
    if vocabulary is None:
        raise SourceContractError(
            f"no verified area vocabulary for kind={kind!r} centre id={centre_id!r}; "
            "an operator must verify the area names before ingestion"
        )
    lookup = {name.strip().lower(): name for name in vocabulary}

    valid_from, valid_until = _parse_validity(flat)
    issued_at = _parse_issue_time(flat)

    areas: list[BulletinArea] = []
    synoptic: str | None = None
    current: BulletinArea | None = None
    pending_label: str | None = None

    for node in nodes:
        key = node.strip().lower().rstrip(":").strip()

        # A verified area name opens a new block.
        if key in lookup:
            current = BulletinArea(area_name=lookup[key], fields={})
            areas.append(current)
            pending_label = None
            continue

        # A verified field label arms the next text node as its value.
        if key in _FIELD_LABELS:
            pending_label = _FIELD_LABELS[key]
            continue

        if pending_label is not None:
            value = " ".join(node.split())
            if pending_label == "synoptic_situation":
                synoptic = synoptic or value
            elif current is not None:
                current.fields.setdefault(pending_label, value)
            pending_label = None

    if not areas:
        raise SourceContractError(
            f"IMD bulletin id={centre_id} kind={kind} yielded no verified area blocks; "
            f"expected any of {vocabulary}"
        )

    return ParsedBulletin(
        kind=kind,
        centre_id=centre_id,
        centre=expected_centre,
        source_url=source_url,
        valid_from=valid_from,
        valid_until=valid_until,
        issued_at=issued_at,
        synoptic_situation=synoptic,
        areas=areas,
    )


def _base_metadata(bulletin: ParsedBulletin, area: BulletinArea) -> dict:
    return {
        "bulletin_kind": bulletin.kind,
        "issuing_centre": bulletin.centre,
        "centre_id": bulletin.centre_id,
        "area_description": area.area_name,
        "area_scoped": True,
        "point_forecast": False,
        "scope_note": (
            "Bulletin values apply to the named IMD area as a whole. They are "
            "not a forecast for a specific coordinate."
        ),
        "synoptic_situation": bulletin.synoptic_situation,
        "weather_text": area.fields.get("weather"),
        "visibility_text": area.fields.get("visibility"),
        "issued_at": bulletin.issued_at.isoformat() if bulletin.issued_at else None,
        "validity_timezone": "UTC",
    }


def build_records(
    bulletin: ParsedBulletin,
) -> tuple[list[ParsedForecast], list[ParsedAlert], list[str]]:
    """Convert a parsed bulletin into canonical forecast and alert records."""
    forecasts: list[ParsedForecast] = []
    alerts: list[ParsedAlert] = []
    diagnostics: list[str] = []

    for area in bulletin.areas:
        meta = _base_metadata(bulletin, area)

        # ── Wind: genuinely numeric ────────────────────────────────────────
        wind_text = area.fields.get("wind")
        wind = parse_wind_text(wind_text) if wind_text else None
        if wind_text and wind is None:
            diagnostics.append(
                f"{area.area_name}: wind statement carried no numeric range: {wind_text!r}"
            )
        if wind is not None:
            wind_meta = {
                **meta,
                "source_text": wind.source_text,
                "source_unit": wind.source_unit,
                "wind_direction_text": wind.direction_text,
                "wind_speed_range_ms": [wind.low_ms, wind.high_ms],
                "value_selection": "range_upper_bound_conservative",
            }
            forecasts.append(
                ParsedForecast(
                    parameter="wind_speed",
                    value=wind.conservative_ms,
                    unit="m/s",
                    latitude=None,
                    longitude=None,
                    valid_from=bulletin.valid_from,
                    forecast_time=bulletin.issued_at,
                    model_name="IMD marine bulletin",
                    provider=PROVIDER,
                    source_dataset=DATASET,
                    source_url=bulletin.source_url,
                    source_metadata=wind_meta,
                )
            )
            if wind.gust_ms is not None:
                forecasts.append(
                    ParsedForecast(
                        parameter="wind_gust",
                        value=wind.gust_ms,
                        unit="m/s",
                        latitude=None,
                        longitude=None,
                        valid_from=bulletin.valid_from,
                        forecast_time=bulletin.issued_at,
                        model_name="IMD marine bulletin",
                        provider=PROVIDER,
                        source_dataset=DATASET,
                        source_url=bulletin.source_url,
                        source_metadata={**wind_meta, "value_selection": "reported_gust"},
                    )
                )

        # ── Sea condition: categorical only, never a height ────────────────
        sea_text = area.fields.get("sea_condition")
        if sea_text:
            band = parse_sea_state_category(sea_text)
            if band is None:
                diagnostics.append(
                    f"{area.area_name}: unverified sea-state term {sea_text!r}; "
                    "emitted as category without a derived band"
                )
                sea_meta = {
                    **meta,
                    "sea_state_category": " ".join(sea_text.split()),
                    "derivation_basis": None,
                    "is_measurement": False,
                    "vocabulary_verified": False,
                }
            else:
                sea_meta = {**meta, **band.as_dict(), "vocabulary_verified": True}
            forecasts.append(
                ParsedForecast(
                    parameter="sea_state_category",
                    # Deliberately None: a category is not a numeric height.
                    value=None,
                    unit=None,
                    latitude=None,
                    longitude=None,
                    valid_from=bulletin.valid_from,
                    forecast_time=bulletin.issued_at,
                    model_name="IMD marine bulletin",
                    provider=PROVIDER,
                    source_dataset=DATASET,
                    source_url=bulletin.source_url,
                    source_metadata=sea_meta,
                )
            )

        # ── Operational warnings ───────────────────────────────────────────
        for field_key, event_type, headline in (
            ("port_signal", "port_signal", "PORT SIGNAL"),
            ("storm_surge_tidal_warning", "storm_surge", "STORM SURGE/TIDAL WARNING"),
        ):
            raw = area.fields.get(field_key)
            if not raw:
                continue
            if raw.strip().lower().rstrip(".") in _NIL_TOKENS:
                continue
            alerts.append(
                ParsedAlert(
                    alert_uid=(
                        f"imd-bulletin:{bulletin.kind}:{bulletin.centre_id}:"
                        f"{field_key}:{area.area_name.lower().replace(' ', '-')}:"
                        f"{(bulletin.issued_at or datetime.now(UTC)).strftime('%Y%m%dT%H%M')}"
                    ),
                    event_type=event_type,
                    # IMD bulletins do not publish CAP severity/certainty/urgency.
                    # They are recorded as explicitly unknown rather than inferred.
                    severity="unknown",
                    certainty="unknown",
                    urgency="unknown",
                    headline=headline,
                    description=" ".join(raw.split()),
                    area_description=area.area_name,
                    geometry=None,
                    issued_at=bulletin.issued_at,
                    effective_from=bulletin.valid_from,
                    valid_until=bulletin.valid_until,
                    source_url=bulletin.source_url,
                    provider=PROVIDER,
                    source_dataset=DATASET,
                    source_metadata=meta,
                )
            )

    return forecasts, alerts, diagnostics


class IMDMarineBulletinLiveAdapter:
    """Live adapter for IMD coastal and sea-area marine bulletins."""

    provider = PROVIDER
    dataset = DATASET

    def __init__(
        self,
        *,
        centre_ids: list[int] | tuple[int, ...] | None = None,
        kinds: list[str] | tuple[str, ...] | None = None,
        base_url: str = BASE_URL,
        live_enabled: bool | None = None,
        user_agent: str | None = None,
        cache=None,  # noqa: ANN001 - optional BulletinCache, injected in tests
    ) -> None:
        from ..config import get_settings

        settings = get_settings()
        self.live_enabled = (
            settings.service.enable_live_sources if live_enabled is None else live_enabled
        )
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent or getattr(
            settings.service, "imd_bulletin_user_agent", None
        ) or "MarineDataEngine/0.1 (+marine-data-engine)"
        # Only areas with a verified vocabulary are pollable.
        verified = sorted({cid for (_kind, cid) in AREA_VOCABULARY})
        self.centre_ids = tuple(centre_ids) if centre_ids else tuple(verified)
        self.kinds = tuple(kinds) if kinds else (KIND_COASTAL, KIND_SEA_AREA)
        self.cache = cache

    def _url(self, kind: str, centre_id: int) -> str:
        path = COASTAL_PATH if kind == KIND_COASTAL else SEA_AREA_PATH
        return f"{self.base_url}/{path}?id={centre_id}"

    def _http_get(self, url: str) -> str:
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) as response:  # noqa: S310
                status = getattr(response, "status", response.getcode())
                if status != 200:
                    raise SourceUnavailableError(f"IMD bulletin HTTP {status} for {url}")
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:  # pragma: no cover - network dependent
            raise SourceUnavailableError(f"IMD bulletin HTTP {exc.code} for {url}") from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network dependent
            raise SourceUnavailableError(f"IMD bulletin unreachable: {url}") from exc

    def _load(self, kind: str, centre_id: int) -> str:
        """Fetch a bulletin, using the injected cache when one is configured."""
        url = self._url(kind, centre_id)
        if self.cache is None:
            return self._http_get(url)
        return self.cache.get_or_fetch(
            key=f"{DATASET}:{kind}:{centre_id}",
            loader=lambda: self._http_get(url),
        )

    def fetch(self) -> FetchResult:
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "IMD marine bulletin connector is disabled by MDE_ENABLE_LIVE_SOURCES"
            )

        forecasts: list[ParsedForecast] = []
        alerts: list[ParsedAlert] = []
        diagnostics: list[str] = []
        documents: list[str] = []
        attempted = 0
        succeeded = 0

        for kind in self.kinds:
            for centre_id in self.centre_ids:
                if (kind, centre_id) not in AREA_VOCABULARY:
                    continue
                attempted += 1
                url = self._url(kind, centre_id)
                try:
                    document = self._load(kind, centre_id)
                    bulletin = parse_bulletin(
                        document, kind=kind, centre_id=centre_id, source_url=url
                    )
                    f, a, d = build_records(bulletin)
                except (SourceContractError, SourceUnavailableError) as exc:
                    diagnostics.append(f"{kind}/id={centre_id}: {type(exc).__name__}: {exc}")
                    continue
                documents.append(document)
                forecasts.extend(f)
                alerts.extend(a)
                diagnostics.extend(d)
                succeeded += 1

        if attempted and succeeded == 0:
            # Every verified bulletin failed to parse or fetch: surface it as a
            # contract error rather than an innocuous empty poll.
            raise SourceContractError(
                "no IMD marine bulletin could be fetched or parsed: " + "; ".join(diagnostics)
            )

        if succeeded < attempted:
            result_state = "degraded"
        elif not forecasts and not alerts:
            result_state = "empty"
        else:
            result_state = "success"

        raw = RawPayload(
            provider=PROVIDER,
            dataset=DATASET,
            data="\n<!-- bulletin boundary -->\n".join(documents).encode("utf-8"),
            ext="html",
            media_type="text/html",
            source_url=f"{self.base_url}/{COASTAL_PATH}",
            retrieved_at=datetime.now(UTC),
        )
        return FetchResult(
            raw=raw,
            forecasts=forecasts,
            alerts=alerts,
            result_state=result_state,
            status_detail=None,
            diagnostics=diagnostics,
        )
