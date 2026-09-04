"""Source adapter base interfaces and parsed canonical record types.

Parsers return light dataclasses (not ORM objects) so parsing is pure and
testable. The ingestion service maps these into ORM rows and runs QC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class RawPayload:
    """Raw bytes fetched from a source, with retrieval provenance."""

    provider: str
    dataset: str
    data: bytes
    ext: str
    media_type: str | None
    source_url: str | None
    retrieved_at: datetime


@dataclass
class ParsedAlert:
    """A normalized CAP alert prior to ORM mapping."""

    alert_uid: str
    event_type: str
    severity: str
    certainty: str
    urgency: str
    headline: str | None
    description: str | None
    area_description: str | None
    geometry: dict | None
    issued_at: datetime | None
    effective_from: datetime | None
    valid_until: datetime | None
    source_url: str | None
    provider: str = "IMD"
    source_dataset: str = "imd_cap"


@dataclass
class ParsedPFZ:
    """A normalized PFZ advisory prior to ORM mapping."""

    pfz_uid: str
    region: str | None
    advisory_text: str | None
    advisory_type: str | None
    geometry: dict | None
    issue_time: datetime | None
    valid_from: datetime | None
    valid_until: datetime | None
    sst_context: float | None = None
    chlorophyll_context: float | None = None
    confidence: float | None = None
    source_url: str | None = None
    provider: str = "INCOIS"
    source_dataset: str = "incois_pfz"


@dataclass
class ParsedObservation:
    """A normalized in-situ/station observation value prior to ORM mapping.

    One record represents a single (station, parameter) reading. A buoy report
    that carries several parameters (wind, pressure, temperature, wave height)
    fans out into several :class:`ParsedObservation` instances sharing the same
    ``station_id`` and ``observed_at``.
    """

    station_id: str
    station_type: str
    latitude: float | None
    longitude: float | None
    parameter: str
    value: float | None
    unit: str | None
    observed_at: datetime | None
    provider: str = "IMD"
    source_dataset: str = "imd_buoy"


@dataclass
class ParsedForecast:
    """A normalized forecast value prior to ORM mapping.

    Mirrors the ``forecast`` ORM table: one record is a single
    (parameter, valid_from) value at a location, tagged with the model that
    produced it. A multi-parameter NWP grid point fans out into several
    :class:`ParsedForecast` instances.
    """

    parameter: str
    value: float | None
    unit: str | None
    latitude: float | None
    longitude: float | None
    valid_from: datetime | None
    forecast_time: datetime | None = None
    model_name: str | None = None
    model_cycle: str | None = None
    forecast_hour: int | None = None
    resolution: str | None = None
    provider: str = "IMD"
    source_dataset: str = "imd_nwp"


@dataclass
class ParsedCyclone:
    """A normalized cyclone bulletin prior to ORM mapping."""

    cyclone_id: str
    name: str | None
    center_lat: float
    center_lon: float
    issue_time: datetime | None
    movement_direction: float | None
    movement_speed: float | None
    central_pressure: float | None
    max_sustained_wind: float | None
    intensity_category: str | None
    track_geometry: dict | None  # GeoJSON LineString
    provider: str = "IMD"
    source_dataset: str = "imd_rsmc"


@dataclass
class ParsedTsunami:
    """A normalized tsunami (TEWS) bulletin prior to ORM mapping."""

    event_id: str
    earthquake_time: datetime | None
    eq_lat: float | None
    eq_lon: float | None
    magnitude: float | None
    depth: float | None
    tsunami_status: str | None
    alert_level: str | None
    affected_regions: list[str] | None
    provider: str = "INCOIS"
    source_dataset: str = "incois_tews"


@dataclass
class FetchResult:
    """Result of a source fetch: raw payload plus parsed records."""

    raw: RawPayload
    alerts: list[ParsedAlert] = field(default_factory=list)
    pfz: list[ParsedPFZ] = field(default_factory=list)
    observations: list[ParsedObservation] = field(default_factory=list)
    cyclones: list[ParsedCyclone] = field(default_factory=list)
    tsunamis: list[ParsedTsunami] = field(default_factory=list)
    forecasts: list[ParsedForecast] = field(default_factory=list)


class SourceAdapter(Protocol):
    """Common adapter interface."""

    provider: str
    dataset: str
    live_enabled: bool

    def fetch(self) -> FetchResult: ...


class LiveSourceDisabledError(RuntimeError):
    """Raised when a live connector is invoked while disabled."""


class AuthenticationRequiredError(RuntimeError):
    """Raised when a connector requires credentials that are not configured.

    Distinct from :class:`LiveSourceDisabledError`: the connector may be enabled
    for live use, but cannot proceed because a username/password/token is blank.
    """
