"""INCOIS WaveWatch III adapter via the public THREDDS NetCDF Subset Service.

Why this source exists
----------------------
The engine had no numeric wave height anywhere in Indian waters. IMD's numeric
marine NWP is ``contract_unavailable`` (HTTP 401, no published schema), and the
IMD bulletin source recovers only a categorical sea state, which the safety gate
must cap at ``CLEARED_WITH_CAUTION`` because a word is not a measurement.

INCOIS runs an operational WaveWatch III and serves it from a **real machine
contract** -- a THREDDS Data Server exposing OPeNDAP, DAP4, WCS, WMS and the
NetCDF Subset Service (NCSS) -- openly and unauthenticated. NCSS point requests
return CSV, so a coordinate/time query needs no HTML scraping and no NetCDF
decoder.

Discovered from the Local Sea Forecast viewer's own catalogue reference:
``https://incois.gov.in/thredds/catalog/osf/ww3/catalog.xml``

Verified contract (``rsmc_coast_ww3_<init>.nc``)
-----------------------------------------------
* Domain 4.95-25.05 degN, 64.95-95.05 degE on a regular 0.1 deg grid
  (201 x 301 nodes).
* 56 time steps at 3 h spacing, spanning ~7 days from 00 UTC of the day after
  the init date.
* Variables used here: ``HS`` (wave height), ``T01``/``T02`` (mean periods),
  ``PHS00``/``PHS01`` (partitioned/swell heights), ``MWD`` (mean direction),
  ``UWND``/``VWND`` (wind components).

Two traps this adapter is built to survive
------------------------------------------
**1. The declared unit is empty.** Every variable ships ``units=""``. The unit
exists only inside the human-readable ``long_name`` -- ``"Wave height (m)"``,
``"Wind U (m/s)"``. A naive reader that trusted ``units`` would treat metres as
dimensionless; a strict reader that required a populated ``units`` would reject
the entire dataset. This adapter resolves the unit from the documented trailing
``(unit)`` group of ``long_name`` and then asserts it equals the unit the
parameter requires, via :mod:`..domain.units`. If ``long_name`` carries no unit
group, the variable is **refused, not assumed** -- which is why ``PWP``
("Peak Wave Period", no unit stated) is deliberately excluded even though it
would be useful.

**2. Land is NaN, and NaN is not zero.** Panaji's own grid node (15.5N, 73.8E)
is land-masked and returns ``NaN``. Read as a number that is a flat calm on a
monsoon coast. This adapter treats ``NaN`` as *absence of a value*, then
resolves the nearest **wet** node by expanding-ring search, and reports the
resulting displacement in ``grid_distance_km`` together with
``requested_point_land_masked``. A caller can therefore see that the value
belongs to a node some distance away, rather than believing it is a forecast at
the requested coordinate.

Sea-state selection is conservative by construction: where several wet nodes
fall inside the search radius, the **largest** significant wave height is
emitted and the contributing node recorded, so a sheltered estuary node can
never make an exposed passage look calmer than it is.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..domain.unit_labels import (
    UnknownUnitError,
    extract_unit_from_long_name,
    require_unit,
)
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedForecast,
    RawPayload,
    SourceContractError,
    SourceUnavailableError,
)

__all__ = [
    "WW3_VARIABLES",
    "init_datetime",
    "GridSample",
    "parse_catalog_latest_coast_file",
    "parse_dataset_units",
    "parse_ncss_point_csv",
    "records_from_samples",
    "resolve_wind",
]

PROVIDER = "INCOIS"
DATASET = "incois_ww3"
MODEL_NAME = "INCOIS WaveWatch III (RSMC coastal)"
RESOLUTION = "0.1deg"

_THREDDS = "https://incois.gov.in/thredds"
CATALOG_URL = f"{_THREDDS}/catalog/osf/ww3/catalog.xml"

# Only the coastal RSMC product is consumed. The other prefixes present in the
# catalogue (io_ww3, nio_ww3, pacific_ww3) are either stale by months or cover a
# domain irrelevant to Indian coastal safety, so they are not silently accepted.
_COAST_FILE = re.compile(r"^rsmc_coast_ww3_(\d{8})\.nc$")

_URLPATH = re.compile(r'urlPath="osf/ww3/([A-Za-z0-9_]+\.nc)"')
_GRID = re.compile(r'<grid name="([^"]+)"[^>]*>(.*?)</grid>', re.S)
_LONG_NAME_ATTR = re.compile(r'name="long_name" value="([^"]*)"')

# Source variable -> (canonical parameter name, required canonical unit).
#
# ``PWP`` is intentionally absent: its long_name is "Peak Wave Period" with no
# unit group, so its unit is unverifiable and it must not be ingested.
WW3_VARIABLES: dict[str, tuple[str, str]] = {
    "HS": ("significant_wave_height", "m"),
    "T01": ("mean_wave_period", "s"),
    "T02": ("zero_crossing_wave_period", "s"),
    "PHS00": ("swell_height_partition_0", "m"),
    "PHS01": ("swell_height_partition_1", "m"),
    "MWD": ("mean_wave_direction", "deg"),
    "UWND": ("eastward_wind", "m/s"),
    "VWND": ("northward_wind", "m/s"),
}

# Default poll points: major fishing harbours / landing centres on both coasts.
# Every one is a *requested* coordinate; the adapter resolves each to the wet
# grid nodes that actually carry a forecast and records the displacement.
DEFAULT_POINTS: tuple[tuple[float, float], ...] = (
    (15.4909, 73.8278),   # Panaji / Mormugao, Goa
    (19.0760, 72.8777),   # Mumbai, Maharashtra
    (8.4004, 76.9787),    # Vizhinjam, Kerala
    (9.9312, 76.2673),    # Kochi, Kerala
    (13.0827, 80.2707),   # Chennai, Tamil Nadu
    (17.6868, 83.2185),   # Visakhapatnam, Andhra Pradesh
    (21.6417, 69.6293),   # Porbandar, Gujarat
    (22.5726, 88.3639),   # Kolkata approaches, West Bengal
)

_EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = rlat2 - rlat1
    dlon = math.radians(lon2 - lon1)
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(h))


@dataclass(frozen=True)
class GridSample:
    """One WW3 grid node at one time step.

    ``values`` maps the *source* variable name to a float, and contains only
    variables that were actually present and finite. A land-masked (``NaN``)
    variable is omitted rather than stored as zero, so ``is_wet`` is a
    statement about evidence rather than about magnitude.
    """

    valid_from: datetime
    latitude: float
    longitude: float
    values: dict[str, float]

    @property
    def is_wet(self) -> bool:
        """True when the node reported a finite significant wave height."""
        return "HS" in self.values


def parse_catalog_latest_coast_file(xml: str) -> tuple[str, str]:
    """Return ``(filename, init_yyyymmdd)`` for the newest coastal WW3 file.

    Raises :class:`SourceContractError` when the catalogue contains no file
    matching the verified ``rsmc_coast_ww3_<yyyymmdd>.nc`` naming. An empty or
    restructured catalogue is an upstream contract change, not "no data".
    """
    matches: list[tuple[str, str]] = []
    for name in _URLPATH.findall(xml):
        m = _COAST_FILE.match(name)
        if m:
            matches.append((name, m.group(1)))
    if not matches:
        raise SourceContractError(
            "INCOIS WW3 catalogue contains no rsmc_coast_ww3_<yyyymmdd>.nc "
            "dataset; the catalogue layout or product naming has changed"
        )
    matches.sort(key=lambda item: item[1])
    return matches[-1]


def parse_dataset_units(xml: str) -> dict[str, str]:
    """Verify every required variable and resolve its unit from ``long_name``.

    Returns a mapping of source variable name to canonical unit. Raises
    :class:`SourceContractError` if a required variable is missing, states no
    unit, or states a unit other than the one the parameter requires.
    """
    long_names: dict[str, str] = {}
    for match in _GRID.finditer(xml):
        name, body = match.group(1), match.group(2)
        attr = _LONG_NAME_ATTR.search(body)
        long_names[name] = attr.group(1) if attr else ""

    if not long_names:
        raise SourceContractError(
            "INCOIS WW3 dataset description exposed no <grid> variables; "
            "the NCSS description layout has changed"
        )

    resolved: dict[str, str] = {}
    for var, (parameter, expected) in WW3_VARIABLES.items():
        if var not in long_names:
            raise SourceContractError(
                f"INCOIS WW3 dataset is missing required variable {var!r} "
                f"(needed for {parameter})"
            )
        try:
            declared = extract_unit_from_long_name(long_names[var])
        except UnknownUnitError as exc:
            raise SourceContractError(
                f"INCOIS WW3 variable {var!r} states no verifiable unit "
                f"(long_name={long_names[var]!r}): {exc}"
            ) from exc
        try:
            resolved[var] = require_unit(
                declared, expected, context=f"{DATASET}.{var}"
            )
        except ValueError as exc:
            raise SourceContractError(
                f"INCOIS WW3 variable {var!r} unit contract violation: {exc}"
            ) from exc
    return resolved


def _parse_float(raw: str) -> float | None:
    """Parse a CSV cell, mapping NaN/blank to ``None`` (land mask / no value)."""
    text = raw.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def parse_ncss_point_csv(text: str) -> list[GridSample]:
    """Parse an NCSS point-request CSV response into :class:`GridSample` rows.

    NCSS emits headers of the form ``HS[unit=""]`` and
    ``latitude[unit="degrees_north"]``; the bracketed suffix is stripped to
    recover the variable name. The empty unit is *not* read from here -- units
    come from the dataset description via :func:`parse_dataset_units`.
    """
    stripped = text.strip()
    if not stripped:
        raise SourceContractError("INCOIS WW3 NCSS returned an empty response")
    if stripped.lstrip().startswith("<"):
        raise SourceContractError(
            "INCOIS WW3 NCSS returned markup instead of CSV; the request was "
            "rejected or the service changed"
        )

    reader = csv.reader(io.StringIO(stripped))
    try:
        header = next(reader)
    except StopIteration:
        raise SourceContractError(
            "INCOIS WW3 NCSS response had no header row"
        ) from None

    cols = [re.sub(r"\[.*?\]$", "", h.strip()) for h in header]
    try:
        i_time = cols.index("time")
        i_lat = cols.index("latitude")
        i_lon = cols.index("longitude")
    except ValueError as exc:
        raise SourceContractError(
            f"INCOIS WW3 NCSS CSV missing a required column "
            f"(time/latitude/longitude); got {cols}"
        ) from exc

    samples: list[GridSample] = []
    for row in reader:
        if len(row) != len(cols):
            continue
        try:
            when = datetime.fromisoformat(
                row[i_time].strip().replace("Z", "+00:00")
            ).astimezone(UTC)
        except ValueError as exc:
            raise SourceContractError(
                f"INCOIS WW3 NCSS emitted an unparseable time "
                f"{row[i_time]!r}"
            ) from exc
        lat, lon = _parse_float(row[i_lat]), _parse_float(row[i_lon])
        if lat is None or lon is None:
            raise SourceContractError(
                "INCOIS WW3 NCSS row carried no usable grid coordinate"
            )
        values: dict[str, float] = {}
        for idx, col in enumerate(cols):
            if col in WW3_VARIABLES:
                parsed = _parse_float(row[idx])
                if parsed is not None:
                    values[col] = parsed
        samples.append(
            GridSample(
                valid_from=when, latitude=lat, longitude=lon, values=values
            )
        )
    return samples


def resolve_wind(u: float, v: float) -> tuple[float, float]:
    """Return ``(speed_ms, direction_deg_from)`` for wind components.

    Direction follows the meteorological convention -- the compass bearing the
    wind blows *from* -- computed as ``(270 - atan2(v, u))`` reduced modulo 360.
    """
    speed = math.hypot(u, v)
    bearing = (270.0 - math.degrees(math.atan2(v, u))) % 360.0
    return speed, bearing


def init_datetime(init_date: str) -> datetime:
    """Model production instant for an ``init_date`` of the form YYYYMMDD.

    This is what belongs in ``forecast_time``: the moment the forecast was
    *produced*. ``valid_from`` carries the future instant the value applies to.
    Conflating the two makes every genuine forecast look like an observation
    timestamped in the future, which QC correctly hard-rejects.
    """
    return datetime.strptime(init_date, "%Y%m%d").replace(tzinfo=UTC)


def _record(
    parameter: str,
    value: float,
    unit: str,
    node: GridSample,
    when: datetime,
    source_url: str,
    base_meta: dict,
    *,
    produced_at: datetime,
    **extra: object,
) -> ParsedForecast:
    """Build one :class:`ParsedForecast` for *node* at *when*.

    Kept at module level (rather than as a closure inside the per-time-step
    loop) so no record can accidentally capture a later iteration's node.
    """
    return ParsedForecast(
        parameter=parameter,
        value=value,
        unit=unit,
        latitude=node.latitude,
        longitude=node.longitude,
        valid_from=when,
        forecast_time=produced_at,
        forecast_hour=max(
            0, int(round((when - produced_at).total_seconds() / 3600))
        ),
        model_cycle=produced_at.strftime("%Y%m%dT%H"),
        model_name=MODEL_NAME,
        resolution=RESOLUTION,
        provider=PROVIDER,
        source_dataset=DATASET,
        source_url=source_url,
        source_metadata={**base_meta, **extra},
    )


def records_from_samples(
    samples: list[GridSample],
    *,
    request_lat: float,
    request_lon: float,
    source_url: str,
    init_date: str,
    requested_point_land_masked: bool,
    retrieved_at: datetime | None = None,
    search_radius_km: float | None = None,
) -> list[ParsedForecast]:
    """Convert wet grid samples into :class:`ParsedForecast` records.

    For each time step **two** nodes are reported, because collapsing them
    would destroy information a caller needs:

    * ``nearest_wet_node`` -- the closest node that carries a forecast, which is
      the most locally representative answer to "what is it like here".
    * ``max_within_radius`` -- the roughest node inside the search radius, which
      is what a departure decision must be judged against, since a vessel does
      not stay on the single node nearest the harbour.

    When both resolve to the same node a single set of records is emitted, tagged
    ``nearest_wet_node+max_within_radius``, so no duplicate rows are produced.

    Every verified variable at the chosen node is emitted, plus derived
    ``wind_speed``/``wind_direction`` from the components and ``swell_height``
    as the larger partitioned height.

    Every record carries ``grid_latitude``/``grid_longitude``,
    ``grid_distance_km`` and ``requested_point_land_masked`` so the spatial
    displacement between the request and the node that answered it is always
    visible downstream.
    """
    by_time: dict[datetime, list[GridSample]] = {}
    for sample in samples:
        if sample.is_wet:
            by_time.setdefault(sample.valid_from, []).append(sample)

    records: list[ParsedForecast] = []
    for when in sorted(by_time):
        candidates = by_time[when]
        nearest = min(
            candidates,
            key=lambda s: haversine_km(
                request_lat, request_lon, s.latitude, s.longitude
            ),
        )
        roughest = max(candidates, key=lambda s: s.values["HS"])
        if (nearest.latitude, nearest.longitude) == (
            roughest.latitude,
            roughest.longitude,
        ):
            selections = [(nearest, "nearest_wet_node+max_within_radius")]
        else:
            selections = [
                (nearest, "nearest_wet_node"),
                (roughest, "max_within_radius"),
            ]
        for node, selection in selections:
            records.extend(
                _records_for_node(
                    node,
                    when,
                    selection,
                    request_lat=request_lat,
                    request_lon=request_lon,
                    source_url=source_url,
                    init_date=init_date,
                    requested_point_land_masked=requested_point_land_masked,
                    retrieved_at=retrieved_at,
                    search_radius_km=search_radius_km,
                )
            )
    return records


def _records_for_node(
    node: GridSample,
    when: datetime,
    selection: str,
    *,
    request_lat: float,
    request_lon: float,
    source_url: str,
    init_date: str,
    requested_point_land_masked: bool,
    retrieved_at: datetime | None,
    search_radius_km: float | None,
) -> list[ParsedForecast]:
    """Emit every verified and derived record for one node at one time step."""
    records: list[ParsedForecast] = []
    produced_at = init_datetime(init_date)
    distance = haversine_km(
        request_lat, request_lon, node.latitude, node.longitude
    )
    base_meta = {
        "model": MODEL_NAME,
        "init_date": init_date,
        "model_produced_at": init_datetime(init_date).isoformat(),
        "grid_latitude": node.latitude,
        "grid_longitude": node.longitude,
        "grid_distance_km": round(distance, 3),
        "grid_resolution_deg": 0.1,
        "requested_latitude": request_lat,
        "requested_longitude": request_lon,
        "requested_point_land_masked": requested_point_land_masked,
        "node_selection": selection,
        "is_measurement": False,
        "provenance": "numerical_wave_model",
        "unit_source": "long_name_parenthetical",
        "land_mask_convention": "NaN indicates land; never read as zero",
    }
    if search_radius_km is not None:
        base_meta["search_radius_km"] = search_radius_km
    if retrieved_at is not None:
        base_meta["retrieved_at"] = retrieved_at.isoformat()

    for var, (parameter, unit) in WW3_VARIABLES.items():
        if var in node.values:
            records.append(
                _record(
                    parameter,
                    node.values[var],
                    unit,
                    node,
                    when,
                    source_url,
                    base_meta,
                    produced_at=produced_at,
                    source_variable=var,
                )
            )

    u, v = node.values.get("UWND"), node.values.get("VWND")
    if u is not None and v is not None:
        speed, bearing = resolve_wind(u, v)
        records.append(
            _record(
                "wind_speed",
                speed,
                "m/s",
                node,
                when,
                source_url,
                base_meta,
                produced_at=produced_at,
                source_variable="UWND,VWND",
                derivation="hypot(UWND, VWND)",
            )
        )
        records.append(
            _record(
                "wind_direction",
                bearing,
                "deg",
                node,
                when,
                source_url,
                base_meta,
                produced_at=produced_at,
                source_variable="UWND,VWND",
                derivation=(
                    "(270 - atan2(VWND, UWND)) mod 360, direction from"
                ),
            )
        )

    partitions = [
        node.values[k] for k in ("PHS00", "PHS01") if k in node.values
    ]
    if partitions:
        records.append(
            _record(
                "swell_height",
                max(partitions),
                "m",
                node,
                when,
                source_url,
                base_meta,
                produced_at=produced_at,
                source_variable="max(PHS00, PHS01)",
                derivation=(
                    "largest partitioned wave height, conservative"
                ),
            )
        )

    return records


# ---------------------------------------------------------------------------
# Live adapter
# ---------------------------------------------------------------------------

_HTTP_TIMEOUT_S = 60
NCSS_BASE = f"{_THREDDS}/ncss/grid/osf/ww3"

# Default probe geometry. The search is deliberately bounded: an unbounded
# nearest-wet-node search could answer a coastal query with an open-ocean node
# hundreds of kilometres away and still look plausible.
DEFAULT_SEARCH_RADIUS_KM = 30.0
_GRID_STEP_DEG = 0.1


def _probe_offsets(max_rings: int) -> list[tuple[int, int]]:
    """Grid-node offsets ordered by ring, nearest ring first."""
    offsets: list[tuple[int, int]] = []
    for ring in range(max_rings + 1):
        ring_offsets = {
            (dlat, dlon)
            for dlat in range(-ring, ring + 1)
            for dlon in range(-ring, ring + 1)
            if max(abs(dlat), abs(dlon)) == ring
        }
        offsets.extend(sorted(ring_offsets))
    return offsets


class IncoisWW3LiveAdapter:
    """Live adapter for INCOIS WaveWatch III via the THREDDS NCSS service.

    The catalogue and the dataset description are *contract* documents that
    change at most daily, so both are read through the injected cache; only the
    per-coordinate point queries go upstream on every poll. The cache is
    fail-open by construction (see :mod:`..cache`), so a Redis outage degrades
    to direct fetches rather than taking a safety source offline.
    """

    provider = PROVIDER
    dataset = DATASET

    def __init__(
        self,
        *,
        points: list[tuple[float, float]] | None = None,
        search_radius_km: float | None = None,
        horizon_hours: int = 48,
        live_enabled: bool | None = None,
        user_agent: str | None = None,
        cache=None,  # noqa: ANN001 - optional BulletinCache, injected in tests
    ) -> None:
        from ..config import get_settings

        settings = get_settings()
        self.live_enabled = (
            settings.service.enable_live_sources
            if live_enabled is None
            else live_enabled
        )
        self.user_agent = (
            user_agent
            or getattr(settings.service, "imd_bulletin_user_agent", None)
            or "MarineDataEngine/0.1 (+marine-data-engine)"
        )
        self.search_radius_km = float(
            search_radius_km
            if search_radius_km is not None
            else getattr(
                settings.service, "ww3_search_radius_km", DEFAULT_SEARCH_RADIUS_KM
            )
        )
        self.horizon_hours = int(horizon_hours)
        self.points = list(points) if points else list(DEFAULT_POINTS)
        self.cache = cache

    # -- I/O ---------------------------------------------------------------

    def _http_get(self, url: str) -> str:
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            url, headers={"User-Agent": self.user_agent, "Accept": "*/*"}
        )
        try:
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=_HTTP_TIMEOUT_S
            ) as response:
                status = getattr(response, "status", response.getcode())
                if status != 200:
                    raise SourceUnavailableError(
                        f"INCOIS WW3 HTTP {status} for {url}"
                    )
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:  # pragma: no cover - network
            raise SourceUnavailableError(
                f"INCOIS WW3 HTTP {exc.code} for {url}"
            ) from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network
            raise SourceUnavailableError(
                f"INCOIS WW3 unreachable: {url}"
            ) from exc

    def _cached(self, key: str, url: str) -> str:
        if self.cache is None:
            return self._http_get(url)
        return self.cache.get_or_fetch(
            key=f"{DATASET}:{key}", loader=lambda: self._http_get(url)
        )

    # -- contract discovery -------------------------------------------------

    def discover(self) -> tuple[str, str, dict[str, str]]:
        """Return ``(filename, init_date, verified_units)``, both cached."""
        catalog = self._cached("catalog", CATALOG_URL)
        filename, init_date = parse_catalog_latest_coast_file(catalog)
        desc = self._cached(
            f"dataset:{filename}", f"{NCSS_BASE}/{filename}/dataset.xml"
        )
        return filename, init_date, parse_dataset_units(desc)

    def _point_url(
        self,
        filename: str,
        variables: list[str],
        lat: float,
        lon: float,
        at: datetime | None,
    ) -> str:
        import urllib.parse

        params: dict[str, object] = {
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "accept": "csv",
        }
        if at is None:
            # This THREDDS build rejects ``time=present`` with HTTP 400, so an
            # explicit bounded window is requested instead. The window is
            # forward-looking and capped by ``horizon_hours`` so a poll cannot
            # silently pull the entire 7 day series for every point.
            start = datetime.now(UTC)
            end = start + timedelta(hours=self.horizon_hours)
            params["time_start"] = start.strftime("%Y-%m-%dT%H:%M:%SZ")
            params["time_end"] = end.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            params["time"] = at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        query = "&".join(f"var={v}" for v in variables)
        return (
            f"{NCSS_BASE}/{filename}?{query}&{urllib.parse.urlencode(params)}"
        )

    def fetch(self, at: datetime | None = None) -> FetchResult:
        """Poll every configured point and return numeric wave forecasts."""
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "INCOIS WW3 connector is disabled by MDE_ENABLE_LIVE_SOURCES"
            )

        retrieved_at = datetime.now(UTC)
        filename, init_date, units = self.discover()
        variables = list(units)
        max_rings = max(
            1,
            int(
                math.ceil(
                    self.search_radius_km / (_GRID_STEP_DEG * 111.0)
                )
            ),
        )
        offsets = _probe_offsets(max_rings)

        forecasts: list[ParsedForecast] = []
        # Upstream failures and legitimate findings are tracked separately.
        # "the service would not answer" and "the service answered, and there is
        # no wet node here" are different claims: only the first is a fault.
        errors: list[str] = []
        notes: list[str] = []
        payload_parts: list[str] = []

        for lat, lon in self.points:
            samples: list[GridSample] = []
            request_masked: bool | None = None
            for dlat, dlon in offsets:
                plat = round(lat + dlat * _GRID_STEP_DEG, 4)
                plon = round(lon + dlon * _GRID_STEP_DEG, 4)
                if haversine_km(lat, lon, plat, plon) > self.search_radius_km:
                    continue
                url = self._point_url(filename, variables, plat, plon, at)
                try:
                    body = self._http_get(url)
                except SourceUnavailableError as exc:
                    errors.append(str(exc))
                    continue
                payload_parts.append(f"# {url}\n{body}")
                probe = parse_ncss_point_csv(body)
                if request_masked is None and (dlat, dlon) == (0, 0):
                    request_masked = not any(s.is_wet for s in probe)
                samples.extend(
                    s
                    for s in probe
                    if s.is_wet
                    and haversine_km(lat, lon, s.latitude, s.longitude)
                    <= self.search_radius_km
                )

            if not samples:
                notes.append(
                    f"no wet WW3 node within {self.search_radius_km:g} km of "
                    f"({lat}, {lon}); land-masked or outside the model domain"
                )
                continue

            forecasts.extend(
                records_from_samples(
                    samples,
                    request_lat=lat,
                    request_lon=lon,
                    source_url=f"{NCSS_BASE}/{filename}",
                    init_date=init_date,
                    requested_point_land_masked=bool(request_masked),
                    retrieved_at=retrieved_at,
                    search_radius_km=self.search_radius_km,
                )
            )

        raw = RawPayload(
            provider=PROVIDER,
            dataset=DATASET,
            data="\n".join(payload_parts).encode("utf-8"),
            ext="csv",
            media_type="text/csv",
            source_url=f"{NCSS_BASE}/{filename}",
            retrieved_at=retrieved_at,
        )
        # An upstream failure must not be reported as a healthy empty poll:
        # "empty" means the source genuinely had nothing, whereas diagnostics
        # mean we failed to find out. Those are different claims and only the
        # first one is safe to treat as reassuring.
        if forecasts:
            state = "degraded" if errors else "success"
            detail = (
                f"{len(errors)} point probe(s) failed; forecasts returned "
                f"from the remainder"
                if errors
                else None
            )
        elif errors:
            state = "degraded"
            detail = f"no forecasts retrieved; first error: {errors[0]}"
        else:
            state = "empty"
            detail = "no wet WW3 nodes resolved for any configured point"
        return FetchResult(
            raw=raw,
            forecasts=forecasts,
            result_state=state,
            status_detail=detail,
            diagnostics=errors + notes,
        )
