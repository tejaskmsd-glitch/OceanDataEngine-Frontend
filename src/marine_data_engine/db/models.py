"""Canonical marine data model (SQLAlchemy ORM).

Every environmental record preserves distinct timestamps (never conflated):
``observed_at``, ``issued_at``, ``valid_from``, ``valid_until``,
``forecast_time``, ``retrieved_at``, ``processed_at``; plus provenance
(``source``, ``provider``, ``dataset_id``, ``source_url``), versioning
(``processing_version``), and QC fields (``quality_status``,
``quality_score``, ``missing_flag``, ``outlier_flag``, ``interpolated_flag``).

An ``idempotency_key`` uniquely identifies the logical record so that repeated
ingestion of the same upstream item does not create duplicates.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, GeometryJSON, ts_column, utcnow
from .enums import (
    Certainty,
    DatasetStatus,
    JobStatus,
    QCStatus,
    QueuePriority,
    Severity,
    Urgency,
)


# --------------------------------------------------------------------------- #
# Provenance / registry
# --------------------------------------------------------------------------- #
class Source(Base):
    """An authoritative upstream provider (IMD, INCOIS, MOSDAC, ...)."""

    __tablename__ = "source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Live connector enabled? Fixtures are used when disabled.
    live_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    licensing_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = ts_column(default=utcnow)

    datasets: Mapped[list[Dataset]] = relationship(back_populates="source")


class DatasetCollection(Base):
    """A logical grouping of related datasets (e.g. a provider product family)."""

    __tablename__ = "dataset_collection"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = ts_column(default=utcnow)

    datasets: Mapped[list[Dataset]] = relationship(back_populates="collection")


class Dataset(Base):
    """Dataset registry entry with freshness/health metadata."""

    __tablename__ = "dataset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"), index=True)
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_collection.id"), nullable=True, index=True
    )
    product: Mapped[str] = mapped_column(String(255))
    parameters: Mapped[list] = mapped_column(default=list)
    spatial_coverage: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spatial_resolution: Mapped[str | None] = mapped_column(String(128), nullable=True)
    temporal_resolution: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fmt: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_method: Mapped[str | None] = mapped_column(String(128), nullable=True)
    auth_required: Mapped[bool] = mapped_column(Boolean, default=False)
    # Expected update cadence in seconds; used for staleness detection.
    expected_update_interval_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stale_multiplier: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority: Mapped[str] = mapped_column(String(32), default=QueuePriority.NORMAL_INGESTION.value)
    retention_policy: Mapped[str | None] = mapped_column(String(255), nullable=True)
    licensing_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=DatasetStatus.DISABLED.value)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_success_at: Mapped[datetime | None] = ts_column(nullable=True)
    last_failure_at: Mapped[datetime | None] = ts_column(nullable=True)
    last_processed_at: Mapped[datetime | None] = ts_column(nullable=True)
    created_at: Mapped[datetime] = ts_column(default=utcnow)
    updated_at: Mapped[datetime] = ts_column(default=utcnow, onupdate=utcnow)

    source: Mapped[Source] = relationship(back_populates="datasets")
    collection: Mapped[DatasetCollection | None] = relationship(back_populates="datasets")
    assets: Mapped[list[DatasetAsset]] = relationship(back_populates="dataset")


class DatasetAsset(Base):
    """A concrete stored artifact belonging to a dataset (raw or processed)."""

    __tablename__ = "dataset_asset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("dataset.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="raw")  # raw | processed | derived
    storage_uri: Mapped[str] = mapped_column(String(1024))
    media_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ingestion_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingestion_job.id"), nullable=True, index=True
    )
    retrieved_at: Mapped[datetime | None] = ts_column(nullable=True)
    created_at: Mapped[datetime] = ts_column(default=utcnow)

    dataset: Mapped[Dataset] = relationship(back_populates="assets")


# --------------------------------------------------------------------------- #
# Provenance mixin shared by environmental records
# --------------------------------------------------------------------------- #
class _ProvenanceMixin:
    """Distinct timestamps, provenance, version, and QC fields."""

    provider: Mapped[str] = mapped_column(String(64), index=True)
    source_dataset: Mapped[str] = mapped_column(String(128), index=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    processing_version: Mapped[str] = mapped_column(String(32), default="1.0.0")

    # Distinct timestamps — never conflated.
    observed_at = ts_column(nullable=True)
    issued_at = ts_column(nullable=True)
    valid_from = ts_column(nullable=True)
    valid_until = ts_column(nullable=True)
    forecast_time = ts_column(nullable=True)
    retrieved_at = ts_column(nullable=True)
    processed_at = ts_column(default=utcnow)

    # Quality-control fields.
    quality_status: Mapped[str] = mapped_column(String(16), default=QCStatus.UNKNOWN.value)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    missing_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    outlier_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    interpolated_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    # Idempotency: unique logical identity of the upstream record.
    idempotency_key: Mapped[str] = mapped_column(String(255), index=True)


# --------------------------------------------------------------------------- #
# Environmental records
# --------------------------------------------------------------------------- #
class Observation(Base, _ProvenanceMixin):
    """A single in-situ or gridded observation value."""

    __tablename__ = "observation"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_observation_idem"),
        Index("ix_observation_param_time", "parameter", "observed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    station_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    parameter: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Forecast(Base, _ProvenanceMixin):
    """A forecast value with full model/cycle/horizon semantics."""

    __tablename__ = "forecast"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_forecast_idem"),
        Index("ix_forecast_param_valid", "parameter", "valid_from"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_cycle: Mapped[str | None] = mapped_column(String(32), nullable=True)
    forecast_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    parameter: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Alert(Base, _ProvenanceMixin):
    """A normalized warning/alert (CAP-aligned)."""

    __tablename__ = "alert"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_alert_idem"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_uid: Mapped[str] = mapped_column(String(255), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default=Severity.UNKNOWN.value)
    certainty: Mapped[str] = mapped_column(String(16), default=Certainty.UNKNOWN.value)
    urgency: Mapped[str] = mapped_column(String(16), default=Urgency.UNKNOWN.value)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    area_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    geometry = mapped_column(GeometryJSON, nullable=True)
    bbox_minx: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_miny: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_maxx: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_maxy: Mapped[float | None] = mapped_column(Float, nullable=True)


class Advisory(Base, _ProvenanceMixin):
    """A fisheries/ecosystem advisory (Tuna/Hilsa/HAB/coral/jellyfish/...)."""

    __tablename__ = "advisory"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_advisory_idem"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    advisory_uid: Mapped[str] = mapped_column(String(255), index=True)
    advisory_type: Mapped[str] = mapped_column(String(64), index=True)
    species_or_ecosystem: Mapped[str | None] = mapped_column(String(128), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    geometry = mapped_column(GeometryJSON, nullable=True)


class PFZ(Base, _ProvenanceMixin):
    """A Potential Fishing Zone advisory polygon."""

    __tablename__ = "pfz"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_pfz_idem"),
        Index("ix_pfz_validity", "valid_from", "valid_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pfz_uid: Mapped[str] = mapped_column(String(255), index=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    advisory_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    advisory_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sst_context: Mapped[float | None] = mapped_column(Float, nullable=True)
    chlorophyll_context: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    geometry = mapped_column(GeometryJSON, nullable=True)
    # Representative point for coarse distance queries (portable stand-in for
    # PostGIS ST_Distance on the polygon).
    centroid_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_lon: Mapped[float | None] = mapped_column(Float, nullable=True)


# --------------------------------------------------------------------------- #
# Reference / geospatial entities
# --------------------------------------------------------------------------- #
class Station(Base):
    """An observing station (buoy, tide gauge, coastal, ship)."""

    __tablename__ = "station"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    station_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = ts_column(default=utcnow)


class Port(Base):
    """A port / harbour reference feature."""

    __tablename__ = "port"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    port_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = ts_column(default=utcnow)


class MarineZone(Base):
    """A maritime zone (EEZ, restricted, MPA, ecological, operational).

    Not covered by IMD/INCOIS/MOSDAC; populated only from operator-configured
    authoritative GIS sources. Legal boundaries are never inferred.
    """

    __tablename__ = "marine_zone"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zone_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    zone_type: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    restriction: Mapped[str | None] = mapped_column(Text, nullable=True)
    authority: Mapped[str | None] = mapped_column(String(255), nullable=True)
    geometry = mapped_column(GeometryJSON, nullable=True)
    effective_from: Mapped[datetime | None] = ts_column(nullable=True)
    effective_until: Mapped[datetime | None] = ts_column(nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = ts_column(default=utcnow)


# --------------------------------------------------------------------------- #
# Processing / lineage entities
# --------------------------------------------------------------------------- #
class IngestionJob(Base):
    """A unit of work that fetches raw data from a source into raw storage."""

    __tablename__ = "ingestion_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    dataset_key: Mapped[str] = mapped_column(String(128), index=True)
    priority: Mapped[str] = mapped_column(String(32), default=QueuePriority.NORMAL_INGESTION.value)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED.value, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    idempotency_key: Mapped[str] = mapped_column(String(255), index=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    bytes_fetched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queued_at: Mapped[datetime] = ts_column(default=utcnow)
    started_at: Mapped[datetime | None] = ts_column(nullable=True)
    finished_at: Mapped[datetime | None] = ts_column(nullable=True)


class ProcessingJob(Base):
    """A unit of work that decodes/normalizes/QCs raw data into canonical rows."""

    __tablename__ = "processing_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    dataset_key: Mapped[str] = mapped_column(String(128), index=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    priority: Mapped[str] = mapped_column(String(32), default=QueuePriority.NORMAL_INGESTION.value)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED.value, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    idempotency_key: Mapped[str] = mapped_column(String(255), index=True)
    ingestion_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingestion_job.id"), nullable=True, index=True
    )
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime] = ts_column(default=utcnow)
    started_at: Mapped[datetime | None] = ts_column(nullable=True)
    finished_at: Mapped[datetime | None] = ts_column(nullable=True)


class ProcessingRun(Base):
    """A concrete execution of a processing job (retries create new runs)."""

    __tablename__ = "processing_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    processing_job_id: Mapped[int] = mapped_column(
        ForeignKey("processing_job.id"), index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.RUNNING.value)
    worker: Mapped[str | None] = mapped_column(String(128), nullable=True)
    records_in: Mapped[int] = mapped_column(Integer, default=0)
    records_accepted: Mapped[int] = mapped_column(Integer, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0)
    records_quarantined: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = ts_column(default=utcnow)
    finished_at: Mapped[datetime | None] = ts_column(nullable=True)


class Evidence(Base):
    """Provenance/evidence package attached to an API response by request_id."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    endpoint: Mapped[str] = mapped_column(String(255))
    query_params: Mapped[dict] = mapped_column(default=dict)
    sources: Mapped[list] = mapped_column(default=list)
    record_refs: Mapped[list] = mapped_column(default=list)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    freshness: Mapped[dict] = mapped_column(default=dict)
    quality: Mapped[dict] = mapped_column(default=dict)
    warnings: Mapped[list] = mapped_column(default=list)
    generated_at: Mapped[datetime] = ts_column(default=utcnow)


class DataQualityRecord(Base):
    """QC audit record for a processed entity (never silently discarded)."""

    __tablename__ = "data_quality_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_idempotency_key: Mapped[str] = mapped_column(String(255), index=True)
    dataset_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    quality_status: Mapped[str] = mapped_column(String(16), default=QCStatus.UNKNOWN.value)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    checks: Mapped[list] = mapped_column(default=list)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    processing_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("processing_run.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = ts_column(default=utcnow)


# Convenience export of all model classes (used by metadata create/registry).
ALL_MODELS = [
    Source,
    DatasetCollection,
    Dataset,
    DatasetAsset,
    Observation,
    Forecast,
    Alert,
    Advisory,
    PFZ,
    Station,
    Port,
    MarineZone,
    IngestionJob,
    ProcessingJob,
    ProcessingRun,
    Evidence,
    DataQualityRecord,
]
