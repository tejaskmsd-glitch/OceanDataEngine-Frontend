"""Query repositories used by the query-only API.

These functions read canonical/processed data only. They never fetch from
upstream sources and never mutate ingestion state. Geospatial filtering uses
the portable haversine/point-in-polygon helpers; in production these map to
PostGIS ``ST_DWithin``/``ST_Distance``/``ST_Contains``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.enums import QCStatus
from ..db.models import (
    PFZ,
    Advisory,
    Alert,
    Dataset,
    Evidence,
    Forecast,
    IngestionJob,
    MarineZone,
    Observation,
    ProcessingJob,
    ProcessingRun,
    Source,
)
from ..domain.freshness import compute_freshness
from ..domain.geo import (
    geometry_centroid,
    haversine_km,
    point_in_geometry,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


# --------------------------------------------------------------------------- #
# Datasets / data-health
# --------------------------------------------------------------------------- #
def list_datasets(session: Session) -> list[dict]:
    rows = session.execute(select(Dataset, Source).join(Source)).all()
    out: list[dict] = []
    for ds, src in rows:
        out.append(
            {
                "key": ds.key,
                "dataset_id": ds.key,  # dashboard alias
                "provider": src.code,
                "product": ds.product,
                "parameters": ds.parameters or [],
                "status": ds.status,
                "fmt": ds.fmt,
                "format": ds.fmt,  # dashboard alias
                "spatial_coverage": ds.spatial_coverage,
                "spatial_resolution": ds.spatial_resolution,
                "temporal_resolution": ds.temporal_resolution,
                "expected_update_interval_s": ds.expected_update_interval_s,
                "last_success_at": ds.last_success_at,
                "last_success": ds.last_success_at.isoformat() if ds.last_success_at else None,
                "last_processed_at": ds.last_processed_at,
                "last_updated": ds.last_processed_at.isoformat() if ds.last_processed_at else None,
                "consecutive_failures": ds.consecutive_failures,
            }
        )
    return out


def data_health(session: Session, *, default_stale_multiplier: float = 3.0) -> list[dict]:
    now = _now()
    rows = session.execute(select(Dataset, Source).join(Source)).all()
    out: list[dict] = []
    for ds, src in rows:
        fr = compute_freshness(
            ds.last_success_at,
            now=now,
            expected_update_interval_s=ds.expected_update_interval_s,
            stale_multiplier=ds.stale_multiplier or default_stale_multiplier,
        )
        status = ds.status
        if fr.is_stale and status == "healthy":
            status = "stale"
        out.append(
            {
                "dataset": ds.key,
                "dataset_id": ds.key,  # dashboard alias
                "provider": src.code,
                "status": status,
                "consecutive_failures": ds.consecutive_failures,
                "last_success_at": ds.last_success_at,
                "last_success": ds.last_success_at.isoformat() if ds.last_success_at else None,
                "freshness": fr.as_dict(),
            }
        )
    return out


# --------------------------------------------------------------------------- #
# PFZ
# --------------------------------------------------------------------------- #
def query_pfz(
    session: Session,
    *,
    lat: float,
    lon: float,
    radius_km: float,
    at: datetime | None = None,
    include_expired: bool = False,
) -> list[dict]:
    """Return accepted PFZ advisories within radius, with distance and validity.

    Distance is centroid-based (portable stand-in for PostGIS polygon distance).
    """
    at = at or _now()
    stmt = select(PFZ).where(PFZ.quality_status != QCStatus.REJECTED.value)
    results: list[dict] = []
    for pfz in session.execute(stmt).scalars():
        if pfz.centroid_lat is None or pfz.centroid_lon is None:
            continue
        dist = haversine_km(lat, lon, pfz.centroid_lat, pfz.centroid_lon)
        if dist > radius_km:
            continue

        valid = _within_validity(pfz.valid_from, pfz.valid_until, at)
        if not include_expired and valid is False:
            continue

        inside = False
        if pfz.geometry is not None:
            try:
                inside = point_in_geometry(lat, lon, pfz.geometry)
            except Exception:  # noqa: BLE001
                inside = False

        results.append(
            {
                "pfz_uid": pfz.pfz_uid,
                "pfz_id": pfz.pfz_uid,  # dashboard alias
                "region": pfz.region,
                "advisory_text": pfz.advisory_text,
                "advisory_type": pfz.advisory_type,
                "geometry": pfz.geometry,
                "distance_km": round(dist, 3),
                "inside": inside,
                "valid": valid,
                "issued_at": pfz.issued_at,
                "issue_time": pfz.issued_at,  # dashboard alias
                "valid_from": pfz.valid_from,
                "valid_until": pfz.valid_until,
                "confidence": pfz.confidence,
                "quality_status": pfz.quality_status,
                "provider": pfz.provider,
                "source": pfz.provider,  # dashboard alias
                "source_dataset": pfz.source_dataset,
                "source_url": pfz.source_url,
                "processing_version": pfz.processing_version,
                "retrieved_at": pfz.retrieved_at,
            }
        )
    results.sort(key=lambda r: r["distance_km"])
    return results


def _within_validity(valid_from, valid_until, at: datetime) -> bool | None:
    if valid_from is None and valid_until is None:
        return None
    vf = valid_from
    vu = valid_until
    if vf and vf.tzinfo is None:
        vf = vf.replace(tzinfo=UTC)
    if vu and vu.tzinfo is None:
        vu = vu.replace(tzinfo=UTC)
    if vf and at < vf:
        return False
    if vu and at > vu:
        return False
    return True


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #
def query_alerts(
    session: Session,
    *,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float | None = None,
    event_type: str | None = None,
    active_only: bool = True,
    at: datetime | None = None,
    limit: int = 100,
) -> list[dict]:
    at = at or _now()
    stmt = select(Alert).where(Alert.quality_status != QCStatus.REJECTED.value)
    if event_type:
        stmt = stmt.where(Alert.event_type == event_type)

    out: list[dict] = []
    for alert in session.execute(stmt).scalars():
        if active_only and alert.valid_until is not None:
            vu = alert.valid_until
            if vu.tzinfo is None:
                vu = vu.replace(tzinfo=UTC)
            if vu < at:
                continue

        distance = None
        if lat is not None and lon is not None:
            distance = _alert_distance_km(alert, lat, lon)
            if radius_km is not None and distance is not None and distance > radius_km:
                continue

        out.append(
            {
                "alert_uid": alert.alert_uid,
                "warning_id": alert.alert_uid,  # dashboard alias
                "event_type": alert.event_type,
                "severity": alert.severity,
                "certainty": alert.certainty,
                "urgency": alert.urgency,
                "headline": alert.headline,
                "description": alert.description,
                "area_description": alert.area_description,
                "geometry": alert.geometry,
                "distance_km": round(distance, 3) if distance is not None else None,
                "issued_at": alert.issued_at,
                "valid_from": alert.valid_from,
                "effective_from": alert.valid_from,  # dashboard alias
                "valid_until": alert.valid_until,
                "expires_at": alert.valid_until,  # dashboard alias
                "quality_status": alert.quality_status,
                "provider": alert.provider,
                "source": alert.provider,  # dashboard alias
                "source_dataset": alert.source_dataset,
                "source_url": alert.source_url,
                "processing_version": alert.processing_version,
                "retrieved_at": alert.retrieved_at,
            }
        )
    out.sort(key=lambda r: (r["distance_km"] is None, r["distance_km"] or 0.0))
    return out[:limit]


def _alert_distance_km(alert: Alert, lat: float, lon: float) -> float | None:
    if alert.geometry is None:
        return None
    try:
        if point_in_geometry(lat, lon, alert.geometry):
            return 0.0
        from ..domain.geo import geometry_centroid

        clat, clon = geometry_centroid(alert.geometry)
        return haversine_km(lat, lon, clat, clon)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Jobs (ingestion + processing)
# --------------------------------------------------------------------------- #
def list_jobs(session: Session, *, limit: int = 200) -> list[dict]:
    """Return recent ingestion and processing jobs merged into a single list."""
    out: list[dict] = []

    for ij in session.execute(
        select(IngestionJob).order_by(IngestionJob.queued_at.desc()).limit(limit)
    ).scalars():
        out.append(
            {
                "job_id": ij.job_uid,
                "source": ij.dataset_key.split("_")[0].upper() if ij.dataset_key else None,
                "dataset": ij.dataset_key,
                "job_type": "ingestion",
                "status": ij.status,
                "queued_at": ij.queued_at,
                "started_at": ij.started_at,
                "finished_at": ij.finished_at,
                "duration_ms": _job_duration_ms(ij.started_at, ij.finished_at),
                "worker": "ingestion-service",
                "error": ij.error_detail,
                "retry_count": ij.attempts,
            }
        )

    for pj in session.execute(
        select(ProcessingJob).order_by(ProcessingJob.queued_at.desc()).limit(limit)
    ).scalars():
        runs = session.execute(
            select(ProcessingRun)
            .where(ProcessingRun.processing_job_id == pj.id)
            .order_by(ProcessingRun.started_at.desc())
            .limit(1)
        ).scalars().all()
        run = runs[0] if runs else None
        out.append(
            {
                "job_id": pj.job_uid,
                "source": pj.dataset_key.split("_")[0].upper() if pj.dataset_key else None,
                "dataset": pj.dataset_key,
                "job_type": pj.job_type,
                "status": pj.status,
                "queued_at": pj.queued_at,
                "started_at": pj.started_at,
                "finished_at": pj.finished_at,
                "duration_ms": (
                    run.duration_ms if run
                    else _job_duration_ms(pj.started_at, pj.finished_at)
                ),
                "worker": run.worker if run else None,
                "error": pj.error_detail,
                "retry_count": pj.attempts,
            }
        )

    out.sort(key=lambda j: j["queued_at"] or _now(), reverse=True)
    return out[:limit]


def _job_duration_ms(started, finished) -> int | None:
    if started and finished:
        return int((finished - started).total_seconds() * 1000)
    return None


# --------------------------------------------------------------------------- #
# Dataset by key
# --------------------------------------------------------------------------- #
def get_dataset_status(
    session: Session, key: str, *, default_stale_multiplier: float = 3.0
) -> dict | None:
    """Return a single dataset with its freshness state."""
    row = session.execute(
        select(Dataset, Source).join(Source).where(Dataset.key == key)
    ).first()
    if row is None:
        return None
    ds, src = row
    now = _now()
    fr = compute_freshness(
        ds.last_success_at,
        now=now,
        expected_update_interval_s=ds.expected_update_interval_s,
        stale_multiplier=ds.stale_multiplier or default_stale_multiplier,
    )
    status = ds.status
    if fr.is_stale and status == "healthy":
        status = "stale"
    return {
        "dataset_id": ds.key,
        "key": ds.key,
        "provider": src.code,
        "product": ds.product,
        "parameters": ds.parameters or [],
        "status": status,
        "fmt": ds.fmt,
        "spatial_coverage": ds.spatial_coverage,
        "temporal_resolution": ds.temporal_resolution,
        "expected_update_interval_s": ds.expected_update_interval_s,
        "last_success_at": ds.last_success_at,
        "last_processed_at": ds.last_processed_at,
        "consecutive_failures": ds.consecutive_failures,
        "freshness": fr.as_dict(),
    }


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #
def get_evidence(session: Session, request_id: str) -> dict | None:
    ev = session.execute(
        select(Evidence).where(Evidence.request_id == request_id)
    ).scalar_one_or_none()
    if ev is None:
        return None
    return {
        "request_id": ev.request_id,
        "endpoint": ev.endpoint,
        "query_params": ev.query_params,
        "sources": ev.sources,
        "record_refs": ev.record_refs,
        "confidence": ev.confidence,
        "freshness": ev.freshness,
        "quality": ev.quality,
        "warnings": ev.warnings,
        "generated_at": ev.generated_at,
    }


def save_evidence(
    session: Session,
    *,
    request_id: str,
    endpoint: str,
    query_params: dict,
    sources: list,
    record_refs: list,
    confidence: float | None,
    freshness: dict,
    quality: dict,
    warnings: list,
) -> None:
    session.add(
        Evidence(
            request_id=request_id,
            endpoint=endpoint,
            query_params=query_params,
            sources=sources,
            record_refs=record_refs,
            confidence=confidence,
            freshness=freshness,
            quality=quality,
            warnings=warnings,
        )
    )


# --------------------------------------------------------------------------- #
# Observations (ocean + weather share the Observation table by parameter)
# --------------------------------------------------------------------------- #
# Canonical parameter groupings. These map dashboard-facing "domains" onto the
# normalized ``parameter`` field of the Observation/Forecast tables.
OCEAN_PARAMETERS: tuple[str, ...] = (
    "sst",
    "sea_surface_temperature",
    "chlorophyll",
    "chlorophyll_a",
    "current",
    "current_speed",
    "current_direction",
    "wave",
    "wave_height",
    "significant_wave_height",
    "swell",
    "sea_level",
    "salinity",
    "mixed_layer_depth",
)
WEATHER_PARAMETERS: tuple[str, ...] = (
    "wind",
    "wind_speed",
    "wind_direction",
    "wind_gust",
    "pressure",
    "mslp",
    "sea_level_pressure",
    "rainfall",
    "precipitation",
    "air_temperature",
    "humidity",
    "cloud_cover",
    "visibility",
)
TIDE_PARAMETERS: tuple[str, ...] = (
    "tide",
    "tide_height",
    "water_level",
    "tidal_current",
)


def _observation_to_dict(obs: Observation, distance_km: float | None) -> dict:
    return {
        "observation_uid": obs.idempotency_key,
        "parameter": obs.parameter,
        "value": obs.value,
        "unit": obs.unit,
        "latitude": obs.latitude,
        "longitude": obs.longitude,
        "station_id": obs.station_id,
        "station_type": obs.station_type,
        "distance_km": round(distance_km, 3) if distance_km is not None else None,
        "observed_at": obs.observed_at,
        "issued_at": obs.issued_at,
        "valid_from": obs.valid_from,
        "valid_until": obs.valid_until,
        "retrieved_at": obs.retrieved_at,
        "quality_status": obs.quality_status,
        "quality_score": obs.quality_score,
        "provider": obs.provider,
        "source_dataset": obs.source_dataset,
        "source_url": obs.source_url,
        "processing_version": obs.processing_version,
    }


def query_observations(
    session: Session,
    *,
    parameters: tuple[str, ...],
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float | None = None,
    at: datetime | None = None,
    limit: int = 500,
) -> list[dict]:
    """Return accepted observations for the given parameter group.

    Distance filtering uses the point lat/lon when present. Records without
    coordinates are still returned (distance ``None``) when no radius is given.
    """
    stmt = (
        select(Observation)
        .where(Observation.quality_status != QCStatus.REJECTED.value)
        .where(Observation.parameter.in_(parameters))
    )
    out: list[dict] = []
    for obs in session.execute(stmt).scalars():
        distance = None
        if (
            lat is not None
            and lon is not None
            and obs.latitude is not None
            and obs.longitude is not None
        ):
            distance = haversine_km(lat, lon, obs.latitude, obs.longitude)
            if radius_km is not None and distance > radius_km:
                continue
        out.append(_observation_to_dict(obs, distance))
    out.sort(key=lambda r: (r["distance_km"] is None, r["distance_km"] or 0.0))
    return out[:limit]


def _forecast_to_dict(fc: Forecast, distance_km: float | None) -> dict:
    return {
        "forecast_uid": fc.idempotency_key,
        "parameter": fc.parameter,
        "value": fc.value,
        "unit": fc.unit,
        "latitude": fc.latitude,
        "longitude": fc.longitude,
        "model_name": fc.model_name,
        "model_cycle": fc.model_cycle,
        "forecast_hour": fc.forecast_hour,
        "resolution": fc.resolution,
        "distance_km": round(distance_km, 3) if distance_km is not None else None,
        "forecast_time": fc.forecast_time,
        "issued_at": fc.issued_at,
        "valid_from": fc.valid_from,
        "valid_until": fc.valid_until,
        "retrieved_at": fc.retrieved_at,
        "quality_status": fc.quality_status,
        "quality_score": fc.quality_score,
        "provider": fc.provider,
        "source_dataset": fc.source_dataset,
        "source_url": fc.source_url,
        "processing_version": fc.processing_version,
    }


def query_forecasts(
    session: Session,
    *,
    parameters: tuple[str, ...],
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float | None = None,
    at: datetime | None = None,
    limit: int = 500,
) -> list[dict]:
    """Return accepted forecast values for the given parameter group."""
    stmt = (
        select(Forecast)
        .where(Forecast.quality_status != QCStatus.REJECTED.value)
        .where(Forecast.parameter.in_(parameters))
    )
    out: list[dict] = []
    for fc in session.execute(stmt).scalars():
        distance = None
        if (
            lat is not None
            and lon is not None
            and fc.latitude is not None
            and fc.longitude is not None
        ):
            distance = haversine_km(lat, lon, fc.latitude, fc.longitude)
            if radius_km is not None and distance > radius_km:
                continue
        out.append(_forecast_to_dict(fc, distance))
    out.sort(key=lambda r: (r["distance_km"] is None, r["distance_km"] or 0.0))
    return out[:limit]


# --------------------------------------------------------------------------- #
# Fishing advisories
# --------------------------------------------------------------------------- #
def query_advisories(
    session: Session,
    *,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float | None = None,
    at: datetime | None = None,
    limit: int = 200,
) -> list[dict]:
    """Return accepted fisheries/ecosystem advisories, optionally within radius."""
    at = at or _now()
    stmt = select(Advisory).where(Advisory.quality_status != QCStatus.REJECTED.value)
    out: list[dict] = []
    for adv in session.execute(stmt).scalars():
        distance = None
        if lat is not None and lon is not None and adv.geometry is not None:
            try:
                if point_in_geometry(lat, lon, adv.geometry):
                    distance = 0.0
                else:
                    clat, clon = geometry_centroid(adv.geometry)
                    distance = haversine_km(lat, lon, clat, clon)
            except Exception:  # noqa: BLE001
                distance = None
            if radius_km is not None and distance is not None and distance > radius_km:
                continue
        out.append(
            {
                "advisory_uid": adv.advisory_uid,
                "advisory_type": adv.advisory_type,
                "species_or_ecosystem": adv.species_or_ecosystem,
                "region": adv.region,
                "recommendation": adv.recommendation,
                "geometry": adv.geometry,
                "distance_km": round(distance, 3) if distance is not None else None,
                "issued_at": adv.issued_at,
                "valid_from": adv.valid_from,
                "valid_until": adv.valid_until,
                "retrieved_at": adv.retrieved_at,
                "quality_status": adv.quality_status,
                "provider": adv.provider,
                "source_dataset": adv.source_dataset,
                "source_url": adv.source_url,
                "processing_version": adv.processing_version,
            }
        )
    out.sort(key=lambda r: (r["distance_km"] is None, r["distance_km"] or 0.0))
    return out[:limit]


# --------------------------------------------------------------------------- #
# Geofence / marine zones
# --------------------------------------------------------------------------- #
def _zone_to_dict(zone: MarineZone, *, distance_km: float | None, inside: bool | None) -> dict:
    return {
        "zone_uid": zone.zone_uid,
        "zone_type": zone.zone_type,
        "name": zone.name,
        "status": zone.status,
        "restriction": zone.restriction,
        "authority": zone.authority,
        "geometry": zone.geometry,
        "distance_km": round(distance_km, 3) if distance_km is not None else None,
        "inside": inside,
        "effective_from": zone.effective_from,
        "effective_until": zone.effective_until,
        "source": zone.source,
        "source_url": zone.source_url,
    }


def query_zones_containing_point(session: Session, *, lat: float, lon: float) -> list[dict]:
    """Return marine zones whose polygon contains the point (point-in-polygon)."""
    out: list[dict] = []
    for zone in session.execute(select(MarineZone)).scalars():
        if zone.geometry is None:
            continue
        try:
            inside = point_in_geometry(lat, lon, zone.geometry)
        except Exception:  # noqa: BLE001
            inside = False
        if inside:
            out.append(_zone_to_dict(zone, distance_km=0.0, inside=True))
    return out


def query_zones_nearby(
    session: Session, *, lat: float, lon: float, radius_km: float
) -> list[dict]:
    """Return marine zones within ``radius_km`` (centroid distance stand-in)."""
    out: list[dict] = []
    for zone in session.execute(select(MarineZone)).scalars():
        if zone.geometry is None:
            continue
        try:
            if point_in_geometry(lat, lon, zone.geometry):
                distance = 0.0
                inside = True
            else:
                clat, clon = geometry_centroid(zone.geometry)
                distance = haversine_km(lat, lon, clat, clon)
                inside = False
        except Exception:  # noqa: BLE001
            continue
        if distance > radius_km:
            continue
        out.append(_zone_to_dict(zone, distance_km=distance, inside=inside))
    out.sort(key=lambda r: r["distance_km"] if r["distance_km"] is not None else float("inf"))
    return out


def query_zones_intersecting(session: Session, *, geometry: dict) -> list[dict]:
    """Return marine zones intersecting the supplied GeoJSON geometry."""
    from ..domain.geo import load_geometry

    try:
        probe = load_geometry(geometry)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid geometry: {exc}") from exc

    out: list[dict] = []
    for zone in session.execute(select(MarineZone)).scalars():
        if zone.geometry is None:
            continue
        try:
            zgeom = load_geometry(zone.geometry)
        except Exception:  # noqa: BLE001
            continue
        if probe.intersects(zgeom):
            out.append(_zone_to_dict(zone, distance_km=0.0, inside=None))
    return out
