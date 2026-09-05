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
    source_metadata: dict = field(default_factory=dict)


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
    source_metadata: dict = field(default_factory=dict)


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
    source_url: str | None = None
    sensor_id: str | None = None
    source_metadata: dict = field(default_factory=dict)


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
    source_url: str | None = None
    source_metadata: dict = field(default_factory=dict)


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
    source_url: str | None = None
    source_metadata: dict = field(default_factory=dict)


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
    source_url: str | None = None
    source_metadata: dict = field(default_factory=dict)


@dataclass
class ParsedStation:
    """Authoritative upstream station metadata prior to ORM upsert."""

    station_uid: str
    name: str | None
    station_type: str | None
    latitude: float | None
    longitude: float | None
    status: str | None
    provider: str
    source_dataset: str
    source_url: str | None = None
    last_reported_at: datetime | None = None
    source_metadata: dict = field(default_factory=dict)


@dataclass
class ParsedMarineZone:
    """Authoritative marine-zone geometry prior to ORM upsert."""

    zone_uid: str
    zone_type: str
    name: str
    geometry: dict
    status: str | None = None
    restriction: str | None = None
    authority: str | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    provider: str = "Marine Regions"
    source_dataset: str = "marine_regions_eez"
    source_url: str | None = None
    source_metadata: dict = field(default_factory=dict)


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
    stations: list[ParsedStation] = field(default_factory=list)
    marine_zones: list[ParsedMarineZone] = field(default_factory=list)
    # Source-level outcome is explicit so an empty but healthy response is not
    # confused with a source that has never run or failed before parsing.
    result_state: str = "success"  # success | empty | degraded
    status_detail: str | None = None
    diagnostics: list[str] = field(default_factory=list)

    @property
    def record_count(self) -> int:
        """Number of canonical records emitted by this fetch."""
        return sum(
            len(records)
            for records in (
                self.alerts,
                self.pfz,
                self.observations,
                self.cyclones,
                self.tsunamis,
                self.forecasts,
                self.stations,
                self.marine_zones,
            )
        )


class SourceAdapter(Protocol):
    """Common adapter interface."""

    provider: str
    dataset: str
    live_enabled: bool

    def fetch(self) -> FetchResult: ...


class SourceAdapterError(RuntimeError):
    """Base error carrying a machine-readable dataset result state."""

    result_state = "unavailable"
    retryable = True


class LiveSourceDisabledError(SourceAdapterError):
    """Raised when a live connector is invoked while disabled."""

    result_state = "disabled"
    retryable = False


class AuthenticationRequiredError(SourceAdapterError):
    """Raised when a verified connector requires unavailable credentials."""

    result_state = "auth_blocked"
    retryable = False


class SourceContractUnavailableError(SourceAdapterError):
    """Raised when no verified machine contract exists for the requested data."""

    result_state = "contract_unavailable"
    retryable = False


class SourceLicenseRequiredError(SourceAdapterError):
    """Raised when authoritative data reuse is blocked pending license approval."""

    result_state = "license_gated"
    retryable = False


class SourceContractError(SourceAdapterError):
    """Raised when a live response violates a verified upstream contract."""

    result_state = "contract_error"
    retryable = True


class SourceUnavailableError(SourceAdapterError):
    """Raised for transport/server failures after a live request was attempted."""

    result_state = "source_unavailable"
    retryable = True
