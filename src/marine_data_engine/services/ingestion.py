"""Ingestion service.

Turns adapter :class:`FetchResult` output into canonical ORM rows with:
- immutable raw storage of the source bytes,
- idempotent upserts (duplicate upstream items are skipped),
- QC evaluation and a :class:`DataQualityRecord` audit row per entity,
- distinct provenance/timestamps/version fields,
- ingestion + processing job/run lineage,
- alert lifecycle events published to the queue.

Rejected records are still stored as QC audit rows (never silently dropped);
their canonical row is written with the QC disposition so downstream queries
can filter by ``quality_status``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.enums import JobStatus, QCStatus, QueuePriority, Severity
from ..db.models import (
    PFZ,
    Alert,
    DataQualityRecord,
    Dataset,
    DatasetAsset,
    Evidence,  # noqa: F401  (referenced by evidence service; import cohesion)
    Forecast,
    IngestionJob,
    MarineZone,
    Observation,
    ProcessingJob,
    ProcessingRun,
    Station,
)
from ..domain.events import (
    alert_created,
    dataset_updated,
    observation_ingested,
    pfz_updated,
    processing_completed,
    processing_failed,
)
from ..domain.geo import geometry_bbox, geometry_centroid
from ..domain.idempotency import make_idempotency_key
from ..domain.qc import qc_geometry_record, qc_observation
from ..messaging.queue import InMemoryQueue
from ..metrics import RECORDS_PROCESSED_TOTAL, SOURCE_FETCH_TOTAL
from ..sources.base import (
    FetchResult,
    ParsedAlert,
    ParsedForecast,
    ParsedMarineZone,
    ParsedObservation,
    ParsedPFZ,
    ParsedStation,
)
from ..storage.raw_store import RawStore

PROCESSING_VERSION = "1.0.0"

# Event subjects (payload only; WS layer subscribes to alert events).
_CRITICAL_EVENTS = {"cyclone", "tsunami", "storm_surge"}


@dataclass
class IngestSummary:
    """Outcome of an ingestion run."""

    dataset_key: str
    raw_uri: str
    accepted: int = 0
    rejected: int = 0
    quarantined: int = 0
    skipped_duplicates: int = 0
    alert_events: list[dict] = None  # type: ignore[assignment]
    pfz_events: list[dict] = None  # type: ignore[assignment]
    observation_events: list[dict] = None  # type: ignore[assignment]
    processing_events: list[dict] = None  # type: ignore[assignment]
    dataset_events: list[dict] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.alert_events is None:
            self.alert_events = []
        if self.pfz_events is None:
            self.pfz_events = []
        if self.observation_events is None:
            self.observation_events = []
        if self.processing_events is None:
            self.processing_events = []
        if self.dataset_events is None:
            self.dataset_events = []


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _severity_priority(event_type: str, severity: str) -> QueuePriority:
    if event_type in _CRITICAL_EVENTS or severity in {
        Severity.SEVERE.value,
        Severity.EXTREME.value,
    }:
        return QueuePriority.CRITICAL_ALERTS
    return QueuePriority.NORMAL_INGESTION


class IngestionService:
    """Persist adapter output into the canonical model with QC + lineage."""

    def __init__(
        self,
        session: Session,
        raw_store: RawStore,
        queue: InMemoryQueue | None = None,
        alert_callback: Callable[[dict], None] | None = None,
    ) -> None:
        self.session = session
        self.raw_store = raw_store
        self.queue = queue
        # Optional sink invoked for each non-rejected alert event so producers
        # outside the request cycle (e.g. the WebSocket AlertBroker) can receive
        # live alerts. Kept sync so IngestionService itself stays sync.
        self.alert_callback = alert_callback

    # ------------------------------------------------------------------ #
    def ingest(self, result: FetchResult) -> IngestSummary:
        raw = result.raw
        stored = self.raw_store.put(
            provider=raw.provider,
            dataset=raw.dataset,
            data=raw.data,
            ext=raw.ext,
            media_type=raw.media_type,
            when=raw.retrieved_at,
        )
        SOURCE_FETCH_TOTAL.labels(raw.provider, raw.dataset, "success").inc()

        dataset = self._ensure_dataset(raw.provider, raw.dataset)

        # Idempotency: re-ingesting the same raw payload (same checksum) must not
        # create duplicate lineage rows or violate unique constraints. Reuse the
        # existing job/asset/run when the checksum has been seen before.
        ingestion_job = self.session.execute(
            select(IngestionJob).where(
                IngestionJob.idempotency_key == stored.checksum_sha256
            )
        ).scalar_one_or_none()
        if ingestion_job is None:
            ingestion_job = IngestionJob(
                job_uid=uuid.uuid4().hex,
                dataset_key=dataset.key,
                priority=QueuePriority.NORMAL_INGESTION.value,
                status=JobStatus.RUNNING.value,
                idempotency_key=stored.checksum_sha256,
                started_at=_now(),
                bytes_fetched=stored.size_bytes,
            )
            self.session.add(ingestion_job)
            self.session.flush()

        existing_asset = self.session.execute(
            select(DatasetAsset).where(
                DatasetAsset.dataset_id == dataset.id,
                DatasetAsset.storage_uri == stored.uri,
            )
        ).scalar_one_or_none()
        if existing_asset is None:
            self.session.add(
                DatasetAsset(
                    dataset_id=dataset.id,
                    role="raw",
                    storage_uri=stored.uri,
                    media_type=stored.media_type,
                    checksum_sha256=stored.checksum_sha256,
                    size_bytes=stored.size_bytes,
                    ingestion_job_id=ingestion_job.id,
                    retrieved_at=stored.retrieved_at,
                )
            )
            self.session.flush()

        proc_job = self.session.execute(
            select(ProcessingJob).where(
                ProcessingJob.idempotency_key == stored.checksum_sha256
            )
        ).scalar_one_or_none()
        if proc_job is None:
            proc_job = ProcessingJob(
                job_uid=uuid.uuid4().hex,
                dataset_key=dataset.key,
                job_type=f"normalize_{raw.dataset}",
                priority=QueuePriority.NORMAL_INGESTION.value,
                status=JobStatus.RUNNING.value,
                idempotency_key=stored.checksum_sha256,
                ingestion_job_id=ingestion_job.id,
                started_at=_now(),
            )
            self.session.add(proc_job)
            self.session.flush()

        run = self.session.execute(
            select(ProcessingRun).where(
                ProcessingRun.processing_job_id == proc_job.id
            )
        ).scalars().first()
        if run is None:
            run = ProcessingRun(
                run_uid=uuid.uuid4().hex,
                processing_job_id=proc_job.id,
                attempt=1,
                status=JobStatus.RUNNING.value,
                worker="ingestion-service",
                started_at=_now(),
            )
            self.session.add(run)
            self.session.flush()

        summary = IngestSummary(dataset_key=dataset.key, raw_uri=stored.uri)

        try:
            for alert in result.alerts:
                self._ingest_alert(alert, raw, run, summary)
            for pfz in result.pfz:
                self._ingest_pfz(pfz, raw, run, summary)
            for station in result.stations:
                self._ingest_station(station, raw, run, summary)
            for zone in result.marine_zones:
                self._ingest_marine_zone(zone, raw, run, summary)
            for obs in result.observations:
                self._ingest_observation(obs, raw, run, summary)
            for forecast in result.forecasts:
                self._ingest_forecast(forecast, raw, run, summary)
            # C5 fix: ingest cyclone and tsunami hazards as alerts.
            # These are critical safety data that must never be silently dropped.
            for cyclone in getattr(result, "cyclones", []):
                from ..sources.base import ParsedAlert  # noqa: PLC0415
                alert = ParsedAlert(
                    alert_uid=cyclone.cyclone_id,
                    event_type="cyclone",
                    severity="extreme",
                    certainty="observed",
                    urgency="immediate",
                    headline=f"Cyclone {cyclone.name or cyclone.cyclone_id}",
                    description=(
                        f"Category: {cyclone.intensity_category or 'unknown'}, "
                        f"Max wind: {cyclone.max_sustained_wind or '?'} km/h, "
                        f"Central pressure: {cyclone.central_pressure or '?'} hPa"
                    ),
                    area_description=None,
                    geometry=cyclone.track_geometry,
                    issued_at=cyclone.issue_time,
                    effective_from=cyclone.issue_time,
                    valid_until=None,
                    source_url=cyclone.source_url,
                    provider=cyclone.provider,
                    source_dataset=cyclone.source_dataset,
                    source_metadata=cyclone.source_metadata,
                )
                self._ingest_alert(alert, raw, run, summary)
            for tsunami in getattr(result, "tsunamis", []):
                from ..sources.base import ParsedAlert  # noqa: PLC0415
                geometry = None
                if tsunami.eq_lat is not None and tsunami.eq_lon is not None:
                    geometry = {
                        "type": "Point",
                        "coordinates": [tsunami.eq_lon, tsunami.eq_lat],
                    }
                alert = ParsedAlert(
                    alert_uid=tsunami.event_id,
                    event_type="tsunami",
                    severity=(
                        "extreme"
                        if tsunami.alert_level in ("warning", "watch")
                        else "severe"
                    ),
                    certainty="observed",
                    urgency="immediate",
                    headline=(
                        f"Tsunami {tsunami.alert_level or 'alert'}: "
                        f"M{tsunami.magnitude or '?'}"
                    ),
                    description=(
                        f"Magnitude: {tsunami.magnitude}, Depth: {tsunami.depth} km, "
                        f"Status: {tsunami.tsunami_status}, "
                        f"Regions: {', '.join(tsunami.affected_regions or [])}"
                    ),
                    area_description=", ".join(tsunami.affected_regions or []),
                    geometry=geometry,
                    issued_at=tsunami.earthquake_time,
                    effective_from=tsunami.earthquake_time,
                    valid_until=None,
                    source_url=tsunami.source_url,
                    provider=tsunami.provider,
                    source_dataset=tsunami.source_dataset,
                    source_metadata=tsunami.source_metadata,
                )
                self._ingest_alert(alert, raw, run, summary)
        except Exception as exc:  # noqa: BLE001
            # Mark lineage failed and emit a processing.failed event before
            # re-raising so callers still observe the error.
            run.status = JobStatus.FAILED.value
            run.finished_at = _now()
            run.duration_ms = int(
                (run.finished_at - run.started_at).total_seconds() * 1000
            )
            proc_job.status = JobStatus.FAILED.value
            proc_job.finished_at = _now()
            ingestion_job.status = JobStatus.FAILED.value
            ingestion_job.finished_at = _now()

            prev_status = dataset.status
            dataset.last_failure_at = _now()
            dataset.last_checked_at = _now()
            dataset.last_result_count = 0
            dataset.last_result_state = "processing_error"
            dataset.status_detail = str(exc)
            dataset.consecutive_failures = (dataset.consecutive_failures or 0) + 1
            dataset.status = "failed"

            fail_event = processing_failed(
                job_uid=proc_job.job_uid,
                dataset_key=dataset.key,
                error=str(exc),
            )
            summary.processing_events.append(fail_event)
            if self.queue is not None:
                self.queue.publish(
                    priority=QueuePriority.NORMAL_INGESTION,
                    payload=fail_event,
                    idempotency_key=f"event:{proc_job.job_uid}:failed",
                )
            self._emit_dataset_updated(dataset, prev_status, summary)
            self.session.flush()
            raise

        run.records_in = summary.accepted + summary.rejected + summary.quarantined
        run.records_accepted = summary.accepted
        run.records_rejected = summary.rejected
        run.records_quarantined = summary.quarantined
        run.status = JobStatus.SUCCEEDED.value
        run.finished_at = _now()
        # ``started_at`` may come back timezone-naive from the DB when this run
        # is reused on a repeat (idempotent) ingest; normalize to UTC before the
        # subtraction to avoid mixing naive/aware datetimes.
        _started = run.started_at
        if _started is not None and _started.tzinfo is None:
            _started = _started.replace(tzinfo=UTC)
        run.duration_ms = int((run.finished_at - _started).total_seconds() * 1000) \
            if _started is not None else 0

        proc_job.status = JobStatus.SUCCEEDED.value
        proc_job.finished_at = _now()
        ingestion_job.status = JobStatus.SUCCEEDED.value
        ingestion_job.finished_at = _now()

        prev_status = dataset.status
        dataset.last_success_at = raw.retrieved_at
        dataset.last_processed_at = _now()
        dataset.last_checked_at = _now()
        dataset.last_result_count = result.record_count
        dataset.last_result_state = result.result_state
        dataset.status_detail = json.dumps(
            {
                "detail": result.status_detail,
                "diagnostics": result.diagnostics,
            },
            separators=(",", ":"),
        )
        dataset.consecutive_failures = 0
        dataset.status = "degraded" if result.result_state == "degraded" else "healthy"

        # processing.completed event.
        completed_event = processing_completed(
            job_uid=proc_job.job_uid,
            dataset_key=dataset.key,
            records_accepted=summary.accepted,
            records_rejected=summary.rejected,
            duration_ms=run.duration_ms,
        )
        summary.processing_events.append(completed_event)
        if self.queue is not None:
            self.queue.publish(
                priority=QueuePriority.NORMAL_INGESTION,
                payload=completed_event,
                idempotency_key=f"event:{proc_job.job_uid}:completed",
            )

        # dataset.updated event when the status changed.
        self._emit_dataset_updated(dataset, prev_status, summary)

        self.session.flush()
        return summary

    def _emit_dataset_updated(
        self, dataset: Dataset, prev_status: str | None, summary: IngestSummary
    ) -> None:
        """Emit a dataset.updated event when the dataset status changed."""
        if dataset.status == prev_status:
            return
        event = dataset_updated(
            dataset_key=dataset.key,
            status=dataset.status,
            last_success_at=dataset.last_success_at,
        )
        summary.dataset_events.append(event)
        if self.queue is not None:
            self.queue.publish(
                priority=QueuePriority.NORMAL_INGESTION,
                payload=event,
                idempotency_key=f"event:dataset:{dataset.key}:{dataset.status}:"
                f"{dataset.last_processed_at}",
            )

    # ------------------------------------------------------------------ #
    def record_source_error(
        self, provider: str, dataset_key: str, error: Exception
    ) -> Dataset:
        """Persist a fetch failure/block without manufacturing a raw payload.

        Non-retryable disabled/license/contract states are operational facts,
        not successful empty polls. Transport and contract failures increment
        the failure counter; known blocks do not.
        """
        dataset = self._ensure_dataset(provider, dataset_key)
        state = getattr(error, "result_state", "source_unavailable")
        now = _now()
        dataset.last_checked_at = now
        dataset.last_result_count = 0
        dataset.last_result_state = state
        dataset.status_detail = str(error)
        if state in {"disabled", "contract_unavailable", "license_gated"}:
            dataset.status = "disabled"
        elif state == "auth_blocked":
            dataset.status = "degraded"
        elif state == "contract_error":
            dataset.status = "degraded"
            dataset.last_failure_at = now
            dataset.consecutive_failures = (dataset.consecutive_failures or 0) + 1
        else:
            dataset.status = "failed"
            dataset.last_failure_at = now
            dataset.consecutive_failures = (dataset.consecutive_failures or 0) + 1
        SOURCE_FETCH_TOTAL.labels(provider, dataset_key, state).inc()
        self.session.flush()
        return dataset

    # ------------------------------------------------------------------ #
    def _ensure_dataset(self, provider: str, dataset_key: str) -> Dataset:
        ds = self.session.execute(
            select(Dataset).where(Dataset.key == dataset_key)
        ).scalar_one_or_none()
        if ds is not None:
            return ds
        from .registry import ensure_source

        source = ensure_source(self.session, provider)
        ds = Dataset(
            key=dataset_key,
            source_id=source.id,
            product=dataset_key,
            parameters=[],
            expected_update_interval_s=6 * 3600,
            priority=QueuePriority.NORMAL_INGESTION.value,
            status="disabled",
            last_result_state="not_run",
        )
        self.session.add(ds)
        self.session.flush()
        return ds

    def _exists(self, model, idempotency_key: str) -> bool:
        return (
            self.session.execute(
                select(model.id).where(model.idempotency_key == idempotency_key)
            ).first()
            is not None
        )

    def _record_quality(
        self, entity_type: str, idem: str, dataset_key: str, qc, run: ProcessingRun
    ) -> None:
        self.session.add(
            DataQualityRecord(
                entity_type=entity_type,
                entity_idempotency_key=idem,
                dataset_key=dataset_key,
                quality_status=qc.status.value,
                quality_score=qc.score,
                checks=[c.as_dict() for c in qc.checks],
                reason=qc.reason,
                processing_version=PROCESSING_VERSION,
                processing_run_id=run.id,
            )
        )
        RECORDS_PROCESSED_TOTAL.labels(dataset_key, qc.status.value).inc()

    def _tally(self, summary: IngestSummary, qc) -> None:
        if qc.status == QCStatus.ACCEPTED:
            summary.accepted += 1
        elif qc.status == QCStatus.REJECTED:
            summary.rejected += 1
        else:
            summary.quarantined += 1

    # ------------------------------------------------------------------ #
    def _ingest_alert(
        self, alert: ParsedAlert, raw, run: ProcessingRun, summary: IngestSummary
    ) -> None:
        idem = make_idempotency_key(
            alert.provider, alert.source_dataset, alert.alert_uid, alert.issued_at
        )
        if self._exists(Alert, idem):
            summary.skipped_duplicates += 1
            return

        qc = qc_geometry_record(
            geometry=alert.geometry,
            valid_from=alert.effective_from,
            valid_until=alert.valid_until,
        )

        bbox = (None, None, None, None)
        if alert.geometry is not None:
            try:
                bbox = geometry_bbox(alert.geometry)
            except Exception:  # noqa: BLE001
                bbox = (None, None, None, None)

        row = Alert(
            alert_uid=alert.alert_uid,
            event_type=alert.event_type,
            severity=alert.severity,
            certainty=alert.certainty,
            urgency=alert.urgency,
            headline=alert.headline,
            description=alert.description,
            area_description=alert.area_description,
            geometry=alert.geometry,
            bbox_minx=bbox[0],
            bbox_miny=bbox[1],
            bbox_maxx=bbox[2],
            bbox_maxy=bbox[3],
            provider=alert.provider,
            source_dataset=alert.source_dataset,
            source_url=alert.source_url,
            source_metadata=alert.source_metadata,
            processing_version=PROCESSING_VERSION,
            issued_at=alert.issued_at,
            valid_from=alert.effective_from,
            valid_until=alert.valid_until,
            retrieved_at=raw.retrieved_at,
            processed_at=_now(),
            quality_status=qc.status.value,
            quality_score=qc.score,
            missing_flag=qc.missing_flag,
            outlier_flag=qc.outlier_flag,
            interpolated_flag=qc.interpolated_flag,
            idempotency_key=idem,
        )
        self.session.add(row)
        self._record_quality("alert", idem, raw.dataset, qc, run)
        self._tally(summary, qc)

        # Publish alert lifecycle event on the priority-isolated queue.
        if qc.status != QCStatus.REJECTED:
            priority = _severity_priority(alert.event_type, alert.severity)
            event = alert_created(
                alert_uid=alert.alert_uid,
                event_type=alert.event_type,
                severity=alert.severity,
                headline=alert.headline,
                issued_at=alert.issued_at,
            )
            summary.alert_events.append(event)
            if self.queue is not None:
                self.queue.publish(
                    priority=priority,
                    payload=event,
                    idempotency_key=f"event:{idem}",
                )
            # Feed any external sink (e.g. WebSocket AlertBroker). Failures in
            # the callback must never break ingestion.
            if self.alert_callback is not None:
                try:
                    self.alert_callback(event)
                except Exception:  # noqa: BLE001
                    pass

    def _ingest_pfz(
        self, pfz: ParsedPFZ, raw, run: ProcessingRun, summary: IngestSummary
    ) -> None:
        idem = make_idempotency_key(
            pfz.provider, pfz.source_dataset, pfz.pfz_uid, pfz.issue_time
        )
        if self._exists(PFZ, idem):
            summary.skipped_duplicates += 1
            return

        qc = qc_geometry_record(
            geometry=pfz.geometry, valid_from=pfz.valid_from, valid_until=pfz.valid_until
        )

        centroid = (None, None)
        if pfz.geometry is not None:
            try:
                centroid = geometry_centroid(pfz.geometry)
            except Exception:  # noqa: BLE001
                centroid = (None, None)

        row = PFZ(
            pfz_uid=pfz.pfz_uid,
            region=pfz.region,
            advisory_text=pfz.advisory_text,
            advisory_type=pfz.advisory_type,
            sst_context=pfz.sst_context,
            chlorophyll_context=pfz.chlorophyll_context,
            confidence=pfz.confidence,
            geometry=pfz.geometry,
            centroid_lat=centroid[0],
            centroid_lon=centroid[1],
            provider=pfz.provider,
            source_dataset=pfz.source_dataset,
            source_url=pfz.source_url,
            source_metadata=pfz.source_metadata,
            processing_version=PROCESSING_VERSION,
            issued_at=pfz.issue_time,
            valid_from=pfz.valid_from,
            valid_until=pfz.valid_until,
            retrieved_at=raw.retrieved_at,
            processed_at=_now(),
            quality_status=qc.status.value,
            quality_score=qc.score,
            missing_flag=qc.missing_flag,
            outlier_flag=qc.outlier_flag,
            interpolated_flag=qc.interpolated_flag,
            idempotency_key=idem,
        )
        self.session.add(row)
        self._record_quality("pfz", idem, raw.dataset, qc, run)
        self._tally(summary, qc)

        # Publish a pfz.updated lifecycle event for accepted/quarantined PFZ
        # geometry (rejected records are not broadcast).
        if qc.status != QCStatus.REJECTED:
            event = pfz_updated(
                pfz_uid=pfz.pfz_uid,
                region=pfz.region,
                valid_from=pfz.valid_from,
                valid_until=pfz.valid_until,
            )
            summary.pfz_events.append(event)
            if self.queue is not None:
                self.queue.publish(
                    priority=QueuePriority.NORMAL_INGESTION,
                    payload=event,
                    idempotency_key=f"event:pfz:{idem}",
                )

    def _ingest_station(
        self,
        station: ParsedStation,
        raw,
        run: ProcessingRun,
        summary: IngestSummary,
    ) -> None:
        """Upsert authoritative station metadata and preserve upstream status."""
        geometry = None
        if station.latitude is not None and station.longitude is not None:
            geometry = {
                "type": "Point",
                "coordinates": [station.longitude, station.latitude],
            }
        qc = qc_geometry_record(geometry=geometry, valid_from=None, valid_until=None)
        idem = make_idempotency_key(
            station.provider, station.source_dataset, station.station_uid
        )
        self._record_quality("station", idem, raw.dataset, qc, run)
        self._tally(summary, qc)
        if qc.status == QCStatus.REJECTED:
            return

        row = self.session.execute(
            select(Station).where(Station.station_uid == station.station_uid)
        ).scalar_one_or_none()
        if row is None:
            row = Station(station_uid=station.station_uid)
            self.session.add(row)
        row.name = station.name
        row.station_type = station.station_type
        row.latitude = station.latitude
        row.longitude = station.longitude
        row.provider = station.provider
        row.source_dataset = station.source_dataset
        row.source_url = station.source_url or raw.source_url
        row.status = station.status
        row.last_reported_at = station.last_reported_at
        row.retrieved_at = raw.retrieved_at
        row.source_metadata = station.source_metadata
        row.updated_at = _now()

    def _ingest_marine_zone(
        self,
        zone: ParsedMarineZone,
        raw,
        run: ProcessingRun,
        summary: IngestSummary,
    ) -> None:
        """Upsert only source-provided authoritative zone geometry."""
        qc = qc_geometry_record(
            geometry=zone.geometry,
            valid_from=zone.effective_from,
            valid_until=zone.effective_until,
        )
        idem = make_idempotency_key(
            zone.provider, zone.source_dataset, zone.zone_uid
        )
        self._record_quality("marine_zone", idem, raw.dataset, qc, run)
        self._tally(summary, qc)
        if qc.status == QCStatus.REJECTED:
            return

        row = self.session.execute(
            select(MarineZone).where(MarineZone.zone_uid == zone.zone_uid)
        ).scalar_one_or_none()
        if row is None:
            row = MarineZone(
                zone_uid=zone.zone_uid,
                zone_type=zone.zone_type,
                name=zone.name,
            )
            self.session.add(row)
        row.zone_type = zone.zone_type
        row.name = zone.name
        row.status = zone.status
        row.restriction = zone.restriction
        row.authority = zone.authority
        row.geometry = zone.geometry
        row.effective_from = zone.effective_from
        row.effective_until = zone.effective_until
        row.source = zone.provider
        row.source_dataset = zone.source_dataset
        row.source_url = zone.source_url or raw.source_url
        row.retrieved_at = raw.retrieved_at
        row.source_metadata = zone.source_metadata
        row.updated_at = _now()

    def _ingest_observation(
        self,
        obs: ParsedObservation,
        raw,
        run: ProcessingRun,
        summary: IngestSummary,
    ) -> None:
        """Map a :class:`ParsedObservation` -> ``Observation`` ORM row with QC."""
        idem = make_idempotency_key(
            obs.provider,
            obs.source_dataset,
            obs.station_id,
            obs.sensor_id or "",
            obs.parameter,
            obs.observed_at,
        )
        if self._exists(Observation, idem):
            summary.skipped_duplicates += 1
            return

        qc = qc_observation(
            parameter=obs.parameter,
            value=obs.value,
            latitude=obs.latitude,
            longitude=obs.longitude,
            observed_at=obs.observed_at,
        )

        row = Observation(
            station_id=obs.station_id,
            station_type=obs.station_type,
            sensor_id=obs.sensor_id,
            latitude=obs.latitude,
            longitude=obs.longitude,
            parameter=obs.parameter,
            value=obs.value,
            unit=obs.unit,
            provider=obs.provider,
            source_dataset=obs.source_dataset,
            source_url=obs.source_url or raw.source_url,
            source_metadata=obs.source_metadata,
            processing_version=PROCESSING_VERSION,
            observed_at=obs.observed_at,
            retrieved_at=raw.retrieved_at,
            processed_at=_now(),
            quality_status=qc.status.value,
            quality_score=qc.score,
            missing_flag=qc.missing_flag,
            outlier_flag=qc.outlier_flag,
            interpolated_flag=qc.interpolated_flag,
            idempotency_key=idem,
        )
        self.session.add(row)
        self._record_quality("observation", idem, raw.dataset, qc, run)
        self._tally(summary, qc)

        # Publish an observation.ingested event for non-rejected records.
        if qc.status != QCStatus.REJECTED:
            event = observation_ingested(
                station_id=obs.station_id,
                parameter=obs.parameter,
                value=obs.value,
                unit=obs.unit,
                observed_at=obs.observed_at,
            )
            summary.observation_events.append(event)
            if self.queue is not None:
                self.queue.publish(
                    priority=QueuePriority.NORMAL_INGESTION,
                    payload=event,
                    idempotency_key=f"event:obs:{idem}",
                )

    def _ingest_forecast(
        self,
        forecast: ParsedForecast,
        raw,
        run: ProcessingRun,
        summary: IngestSummary,
    ) -> None:
        """Map a :class:`ParsedForecast` -> ``Forecast`` ORM row with QC."""
        idem = make_idempotency_key(
            forecast.provider,
            forecast.source_dataset,
            forecast.model_name or "",
            forecast.parameter,
            forecast.latitude,
            forecast.longitude,
            forecast.valid_from,
        )
        if self._exists(Forecast, idem):
            summary.skipped_duplicates += 1
            return

        # A forecast's ``valid_from`` is legitimately in the future, so the
        # observation "no future timestamps" temporal check must NOT be applied
        # to it (that would reject every genuine NWP forecast as "in the
        # future"). Use the forecast's production/issue time (``forecast_time``
        # / model cycle) as the temporal reference instead — that is at or
        # before "now". Range/spatial/schema checks still apply to the value.
        qc = qc_observation(
            parameter=forecast.parameter,
            value=forecast.value,
            latitude=forecast.latitude,
            longitude=forecast.longitude,
            observed_at=forecast.forecast_time,
        )

        row = Forecast(
            model_name=forecast.model_name,
            model_cycle=forecast.model_cycle,
            forecast_hour=forecast.forecast_hour,
            latitude=forecast.latitude,
            longitude=forecast.longitude,
            parameter=forecast.parameter,
            value=forecast.value,
            unit=forecast.unit,
            resolution=forecast.resolution,
            provider=forecast.provider,
            source_dataset=forecast.source_dataset,
            source_url=forecast.source_url or raw.source_url,
            source_metadata=forecast.source_metadata,
            processing_version=PROCESSING_VERSION,
            valid_from=forecast.valid_from,
            forecast_time=forecast.forecast_time,
            retrieved_at=raw.retrieved_at,
            processed_at=_now(),
            quality_status=qc.status.value,
            quality_score=qc.score,
            missing_flag=qc.missing_flag,
            outlier_flag=qc.outlier_flag,
            interpolated_flag=qc.interpolated_flag,
            idempotency_key=idem,
        )
        self.session.add(row)
        self._record_quality("forecast", idem, raw.dataset, qc, run)
        self._tally(summary, qc)
