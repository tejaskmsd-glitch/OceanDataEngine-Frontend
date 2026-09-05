"""Explicit Pydantic v2 API schemas.

The ORM is never exposed. Every endpoint returns one of these explicit models,
wrapped in the canonical response envelope (requirements §20).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FreshnessModel(BaseModel):
    reference_at: datetime | None = None
    age_seconds: float | None = None
    age_minutes: float | None = None
    is_stale: bool = False
    freshness_score: float = 0.0
    expected_update_interval_s: int | None = None
    stale_threshold_s: float | None = None


class SourceRef(BaseModel):
    provider: str
    dataset: str
    source_url: str | None = None
    issued_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    retrieved_at: datetime | None = None
    processing_version: str | None = None


class QualityModel(BaseModel):
    quality_status: str | None = None
    quality_score: float | None = None


class Meta(BaseModel):
    generated_at: datetime
    request_id: str
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    freshness: FreshnessModel | None = None
    confidence: float | None = None


class Envelope[T](BaseModel):
    """Canonical response envelope."""

    data: T
    meta: Meta
    sources: list[SourceRef] = Field(default_factory=list)
    quality: QualityModel | None = None
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Health / datasets
# --------------------------------------------------------------------------- #
class HealthData(BaseModel):
    status: str
    version: str
    environment: str
    live_sources_enabled: bool
    time: datetime


class DatasetModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    dataset_id: str | None = None  # dashboard alias
    provider: str
    product: str
    parameters: list[str] = Field(default_factory=list)
    status: str
    fmt: str | None = None
    format: str | None = None  # dashboard alias
    spatial_coverage: str | None = None
    spatial_resolution: str | None = None
    temporal_resolution: str | None = None
    expected_update_interval_s: int | None = None
    last_success_at: datetime | None = None
    last_success: str | None = None  # dashboard alias
    last_processed_at: datetime | None = None
    last_updated: str | None = None  # dashboard alias
    last_checked_at: datetime | None = None
    last_result_count: int | None = None
    last_result_state: str = "not_run"
    status_detail: str | None = None
    consecutive_failures: int = 0


class DataHealthModel(BaseModel):
    dataset: str
    dataset_id: str | None = None  # dashboard alias
    provider: str
    status: str
    consecutive_failures: int = 0
    last_success_at: datetime | None = None
    last_success: str | None = None  # dashboard alias
    last_checked_at: datetime | None = None
    last_result_count: int | None = None
    last_result_state: str = "not_run"
    status_detail: str | None = None
    freshness: FreshnessModel


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
class JobModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    job_id: str
    source: str | None = None
    dataset: str | None = None
    job_type: str | None = None
    status: str | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    worker: str | None = None
    error: str | None = None
    retry_count: int | None = None


# --------------------------------------------------------------------------- #
# Dataset status (single dataset with freshness)
# --------------------------------------------------------------------------- #
class DatasetStatusModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dataset_id: str
    key: str
    provider: str
    product: str
    parameters: list[str] = Field(default_factory=list)
    status: str
    fmt: str | None = None
    spatial_coverage: str | None = None
    temporal_resolution: str | None = None
    expected_update_interval_s: int | None = None
    last_success_at: datetime | None = None
    last_processed_at: datetime | None = None
    last_checked_at: datetime | None = None
    last_result_count: int | None = None
    last_result_state: str = "not_run"
    status_detail: str | None = None
    consecutive_failures: int = 0
    freshness: FreshnessModel


# --------------------------------------------------------------------------- #
# PFZ
# --------------------------------------------------------------------------- #
class PFZModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pfz_uid: str
    pfz_id: str | None = None  # dashboard alias
    region: str | None = None
    advisory_text: str | None = None
    advisory_type: str | None = None
    geometry: dict[str, Any] | None = None
    distance_km: float
    inside: bool
    valid: bool | None = None
    issued_at: datetime | None = None
    issue_time: datetime | None = None  # dashboard alias
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    confidence: float | None = None
    quality_status: str
    provider: str
    source: str | None = None  # dashboard alias
    source_dataset: str
    source_url: str | None = None


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #
class AlertModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    alert_uid: str
    warning_id: str | None = None  # dashboard alias (set from alert_uid)
    event_type: str
    severity: str
    certainty: str
    urgency: str
    headline: str | None = None
    description: str | None = None
    area_description: str | None = None
    geometry: dict[str, Any] | None = None
    distance_km: float | None = None
    issued_at: datetime | None = None
    valid_from: datetime | None = None
    effective_from: datetime | None = None  # dashboard alias
    valid_until: datetime | None = None
    expires_at: datetime | None = None  # dashboard alias
    quality_status: str
    provider: str
    source_dataset: str
    source: str | None = None  # dashboard alias
    source_url: str | None = None


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #
class EvidenceModel(BaseModel):
    request_id: str
    endpoint: str
    query_params: dict[str, Any] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    record_refs: list[Any] = Field(default_factory=list)
    confidence: float | None = None
    freshness: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    capability_status: str | None = None
    data_versions: dict[str, Any] = Field(default_factory=dict)
    data_lineage: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime


# --------------------------------------------------------------------------- #
# Observations (ocean + weather conditions)
# --------------------------------------------------------------------------- #
class ObservationModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    observation_uid: str
    parameter: str
    value: float | None = None
    unit: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    station_id: str | None = None
    station_type: str | None = None
    distance_km: float | None = None
    observed_at: datetime | None = None
    issued_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    retrieved_at: datetime | None = None
    quality_status: str
    quality_score: float | None = None
    provider: str
    source_dataset: str
    source_url: str | None = None


# --------------------------------------------------------------------------- #
# Forecasts (ocean + weather)
# --------------------------------------------------------------------------- #
class ForecastModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    forecast_uid: str
    parameter: str
    value: float | None = None
    unit: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    model_name: str | None = None
    model_cycle: str | None = None
    forecast_hour: int | None = None
    resolution: str | None = None
    distance_km: float | None = None
    forecast_time: datetime | None = None
    issued_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    retrieved_at: datetime | None = None
    quality_status: str
    quality_score: float | None = None
    provider: str
    source_dataset: str
    source_url: str | None = None


# --------------------------------------------------------------------------- #
# Fishing advisories
# --------------------------------------------------------------------------- #
class AdvisoryModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    advisory_uid: str
    advisory_type: str
    species_or_ecosystem: str | None = None
    region: str | None = None
    recommendation: str | None = None
    geometry: dict[str, Any] | None = None
    distance_km: float | None = None
    issued_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    retrieved_at: datetime | None = None
    quality_status: str
    provider: str
    source_dataset: str
    source_url: str | None = None


# --------------------------------------------------------------------------- #
# Geofence / marine zones
# --------------------------------------------------------------------------- #
class ZoneModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    zone_uid: str
    zone_type: str
    name: str
    status: str | None = None
    restriction: str | None = None
    authority: str | None = None
    geometry: dict[str, Any] | None = None
    distance_km: float | None = None
    inside: bool | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    source: str | None = None
    source_url: str | None = None


# --------------------------------------------------------------------------- #
# Capability status (for not-yet-implemented / blocked capabilities)
# --------------------------------------------------------------------------- #
class CapabilityStatus(BaseModel):
    """Honest capability status returned by endpoints without data/impl yet.

    ``status`` is one of ``NOT_STARTED``, ``SOURCE_GAP``, ``BLOCKED``.
    """

    capability: str
    status: str
    explanation: str
    blocker: str | None = None
    required_inputs: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Safe routing request body
# --------------------------------------------------------------------------- #
class GeoPoint(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class SafeRouteRequest(BaseModel):
    start: GeoPoint
    end: GeoPoint
    departure_time: datetime | None = None
    vessel_type: str | None = None


class IntersectionRequest(BaseModel):
    """GeoJSON geometry to intersect against marine zones."""

    geometry: dict[str, Any]


# --------------------------------------------------------------------------- #
# Derived-capability result models (risk / suitability / routing)
# --------------------------------------------------------------------------- #
class RiskFactorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    value: float | None = None
    threshold_low: float
    threshold_high: float
    weight: float
    contribution: float


class MarineRiskModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    risk_score: float
    risk_level: str
    factors: list[RiskFactorModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)


class FishingSuitabilityModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score: float
    classification: str
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    confidence: float | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)


class RouteSegmentModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start: list[float]
    end: list[float]
    distance_km: float
    travel_time_hours: float | None = None
    risk_score: float
    penalties: dict[str, Any] = Field(default_factory=dict)


class SafeRouteModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    geometry: dict[str, Any]
    total_distance_km: float
    estimated_duration_hours: float | None = None
    route_risk_score: float
    segments: list[RouteSegmentModel] = Field(default_factory=list)
    avoided_zones: list[str] = Field(default_factory=list)
    major_risk_drivers: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    status: str
    warnings: list[str] = Field(default_factory=list)
