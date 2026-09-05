"""FastAPI application: query-only endpoints + WebSocket alert stream.

Endpoints only read processed/canonical data via query repositories. No handler
fetches upstream sources or triggers ingestion. Every response uses the
canonical envelope and persists an Evidence record addressable at
``GET /v1/evidence/{request_id}``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import (
    Body,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy.orm import Session

from .. import __version__
from ..config import get_settings
from ..db.session import get_session_factory
from ..domain.risk import RiskThresholds, assess_marine_risk
from ..domain.suitability import assess_fishing_suitability
from ..logging_config import configure_logging
from ..services import geofence as geofence_service
from ..services import queries, stac
from ..services.routing import compute_safe_route
from .broker import AlertBroker, get_broker
from .schemas import (
    AdvisoryModel,
    AlertModel,
    DataHealthModel,
    DatasetModel,
    DatasetStatusModel,
    Envelope,
    EvidenceModel,
    FishingSuitabilityModel,
    ForecastModel,
    FreshnessModel,
    HealthData,
    IntersectionRequest,
    JobModel,
    MarineRiskModel,
    Meta,
    ObservationModel,
    PFZModel,
    SafeRouteModel,
    SafeRouteRequest,
    SourceRef,
    ZoneModel,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


# Advisory types treated as ecological hazards by the suitability engine.
_ECO_HAZARD_TYPES = frozenset(
    {"hab", "harmful_algal_bloom", "oil_spill", "jellyfish_bloom", "coral_bleaching"}
)


# --------------------------------------------------------------------------- #
# Alert event bridge: IngestionService (sync) -> AlertBroker (async WS)
# --------------------------------------------------------------------------- #
async def publish_ingest_alerts(summary, broker: AlertBroker | None = None) -> int:
    """Publish all alert events on an IngestSummary to the AlertBroker.

    Returns the number of events published. Intended to be awaited from an
    async context (e.g. an internal ingest-trigger endpoint or a worker bridge).
    """
    broker = broker or get_broker()
    events = getattr(summary, "alert_events", None) or []
    for event in events:
        await broker.publish(event)
    return len(events)


def publish_alert_sync(event: dict, broker: AlertBroker | None = None) -> None:
    """Schedule a broker publish from synchronous code.

    Safe to call from a sync producer (like IngestionService). If a running
    event loop exists, the publish is scheduled as a task on that loop;
    otherwise the event is silently dropped (logged) since there are no
    WebSocket subscribers to receive it without an active server loop.
    """
    broker = broker or get_broker()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        loop.create_task(broker.publish(event))
    else:
        # No running loop means no WebSocket subscribers — skip rather than
        # creating a transient loop that can't reach the server's queues.
        logging.getLogger(__name__).debug(
            "publish_alert_sync: no running event loop, alert event dropped"
        )


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.service.log_level, settings.service.log_json)

    app = FastAPI(
        title="Marine Data Engine API",
        version=__version__,
        description="Query-only marine data layer API (AI-agnostic).",
    )

    # CORS — allow the dashboard and any local dev frontend to call the API.
    # H19 fix: wildcard + credentials is invalid per W3C spec.
    # Use explicit origins only; in production set MDE_CORS_ORIGINS env var.
    import os as _os  # noqa: PLC0415

    from fastapi.middleware.cors import CORSMiddleware
    _cors_env = _os.environ.get("MDE_CORS_ORIGINS", "")
    cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------ #
    @app.get("/v1/health", response_model=Envelope[HealthData], tags=["system"])
    def health() -> Envelope[HealthData]:
        rid = uuid.uuid4().hex
        data = HealthData(
            status="ok",
            version=__version__,
            environment=settings.service.environment,
            live_sources_enabled=settings.service.enable_live_sources,
            time=_now(),
        )
        return Envelope[HealthData](
            data=data, meta=Meta(generated_at=_now(), request_id=rid)
        )

    # ------------------------------------------------------------------ #
    @app.get("/v1/datasets", response_model=Envelope[list[DatasetModel]], tags=["catalog"])
    def datasets(db: Session = Depends(get_db)) -> Envelope[list[DatasetModel]]:
        rid = uuid.uuid4().hex
        rows = queries.list_datasets(db)
        models = [DatasetModel(**r) for r in rows]
        return Envelope[list[DatasetModel]](
            data=models,
            meta=Meta(generated_at=_now(), request_id=rid),
            sources=[SourceRef(provider=r["provider"], dataset=r["key"]) for r in rows],
        )

    # ------------------------------------------------------------------ #
    @app.get("/v1/data-health", response_model=Envelope[list[DataHealthModel]], tags=["system"])
    def data_health(db: Session = Depends(get_db)) -> Envelope[list[DataHealthModel]]:
        rid = uuid.uuid4().hex
        rows = queries.data_health(
            db, default_stale_multiplier=settings.service.default_stale_multiplier
        )
        models = [
            DataHealthModel(**{**r, "freshness": FreshnessModel(**r["freshness"])}) for r in rows
        ]
        warnings = [f"{m.dataset} is {m.status}" for m in models if m.status != "healthy"]
        return Envelope[list[DataHealthModel]](
            data=models,
            meta=Meta(generated_at=_now(), request_id=rid),
            warnings=warnings,
        )

    # ------------------------------------------------------------------ #
    @app.get("/v1/jobs", response_model=Envelope[list[JobModel]], tags=["processing"])
    def jobs(
        limit: int = Query(200, ge=1, le=1000),
        db: Session = Depends(get_db),
    ) -> Envelope[list[JobModel]]:
        rid = uuid.uuid4().hex
        rows = queries.list_jobs(db, limit=limit)
        models = [JobModel(**r) for r in rows]
        return Envelope[list[JobModel]](
            data=models,
            meta=Meta(generated_at=_now(), request_id=rid),
        )

    # ------------------------------------------------------------------ #
    @app.get(
        "/v1/datasets/{key}/status",
        response_model=Envelope[DatasetStatusModel],
        tags=["catalog"],
    )
    def dataset_status(key: str, db: Session = Depends(get_db)) -> Envelope[DatasetStatusModel]:
        rid = uuid.uuid4().hex
        row = queries.get_dataset_status(
            db, key, default_stale_multiplier=settings.service.default_stale_multiplier
        )
        if row is None:
            raise HTTPException(404, f"Dataset {key!r} not found")
        model = DatasetStatusModel(**{**row, "freshness": FreshnessModel(**row["freshness"])})
        return Envelope[DatasetStatusModel](
            data=model,
            meta=Meta(generated_at=_now(), request_id=rid),
        )

    # ------------------------------------------------------------------ #
    @app.get("/metrics", tags=["system"], include_in_schema=False)
    def prometheus_metrics():
        from fastapi.responses import Response
        from prometheus_client import generate_latest

        from ..metrics import REGISTRY

        return Response(
            content=generate_latest(REGISTRY),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    # ------------------------------------------------------------------ #
    @app.get("/v1/fishing/pfz", response_model=Envelope[list[PFZModel]], tags=["fishing"])
    def fishing_pfz(
        lat: float = Query(..., ge=-90, le=90),
        lon: float = Query(..., ge=-180, le=180),
        radius_km: float = Query(100.0, gt=0, le=2000),
        include_expired: bool = Query(False),
        db: Session = Depends(get_db),
    ) -> Envelope[list[PFZModel]]:
        rid = uuid.uuid4().hex
        at = _now()
        rows = queries.query_pfz(
            db,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            at=at,
            include_expired=include_expired,
        )
        models = [PFZModel(**r) for r in rows]
        sources = [
            SourceRef(
                provider=r["provider"],
                dataset=r["source_dataset"],
                source_url=r.get("source_url"),
                issued_at=r.get("issued_at"),
                valid_from=r.get("valid_from"),
                valid_until=r.get("valid_until"),
                retrieved_at=r.get("retrieved_at"),
                processing_version=r.get("processing_version"),
            )
            for r in rows
        ]
        warnings, capability, source_states = _source_outcome(
            db,
            ("incois_pfz",),
            subject="PFZ destination points/advisory lines for this query",
            has_records=bool(rows),
        )
        _persist_evidence(
            db,
            rid,
            "/v1/fishing/pfz",
            {"lat": lat, "lon": lon, "radius_km": radius_km},
            sources,
            [{"pfz_uid": row["pfz_uid"]} for row in rows],
            warnings=warnings,
            capability_status=capability,
            source_states=source_states,
        )
        return Envelope[list[PFZModel]](
            data=models,
            meta=Meta(generated_at=_now(), request_id=rid),
            sources=sources,
            warnings=warnings,
        )

    # ------------------------------------------------------------------ #
    @app.get("/v1/alerts", response_model=Envelope[list[AlertModel]], tags=["alerts"])
    def alerts(
        lat: float | None = Query(None, ge=-90, le=90),
        lon: float | None = Query(None, ge=-180, le=180),
        radius_km: float | None = Query(None, gt=0, le=5000),
        event_type: str | None = Query(None),
        active_only: bool = Query(True),
        limit: int = Query(100, ge=1, le=1000),
        db: Session = Depends(get_db),
    ) -> Envelope[list[AlertModel]]:
        rid = uuid.uuid4().hex
        if (lat is None) ^ (lon is None):
            raise HTTPException(400, "lat and lon must be provided together")
        rows = queries.query_alerts(
            db,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            event_type=event_type,
            active_only=active_only,
            at=_now(),
            limit=limit,
        )
        models = [AlertModel(**r) for r in rows]
        sources = [
            SourceRef(
                provider=r["provider"],
                dataset=r["source_dataset"],
                source_url=r.get("source_url"),
                issued_at=r.get("issued_at"),
                valid_until=r.get("valid_until"),
                retrieved_at=r.get("retrieved_at"),
                processing_version=r.get("processing_version"),
            )
            for r in rows
        ]
        warnings, capability, source_states = _source_outcome(
            db,
            ("imd_cap", "incois_hwa"),
            subject="active marine alerts for this query",
            has_records=bool(rows),
        )
        _persist_evidence(
            db,
            rid,
            "/v1/alerts",
            {"lat": lat, "lon": lon, "radius_km": radius_km, "event_type": event_type},
            sources,
            [{"alert_uid": row["alert_uid"]} for row in rows],
            warnings=warnings,
            capability_status=capability,
            source_states=source_states,
        )
        return Envelope[list[AlertModel]](
            data=models,
            meta=Meta(generated_at=_now(), request_id=rid),
            sources=sources,
            warnings=warnings,
        )

    # ------------------------------------------------------------------ #
    @app.get(
        "/v1/evidence/{request_id}",
        response_model=Envelope[EvidenceModel],
        tags=["evidence"],
    )
    def evidence(request_id: str, db: Session = Depends(get_db)) -> Envelope[EvidenceModel]:
        rec = queries.get_evidence(db, request_id)
        if rec is None:
            raise HTTPException(404, f"No evidence for request_id {request_id}")
        model = EvidenceModel(**rec)
        return Envelope[EvidenceModel](
            data=model,
            meta=Meta(generated_at=_now(), request_id=uuid.uuid4().hex),
        )

    # ------------------------------------------------------------------ #
    @app.websocket("/v1/stream/alerts")
    async def stream_alerts(websocket: WebSocket) -> None:
        broker: AlertBroker = get_broker()
        await websocket.accept()
        queue = await broker.subscribe()
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            await broker.unsubscribe(queue)

    # ------------------------------------------------------------------ #
    # Ocean conditions / forecast
    # ------------------------------------------------------------------ #
    @app.get(
        "/v1/ocean/conditions",
        response_model=Envelope[list[ObservationModel]],
        tags=["ocean"],
    )
    def ocean_conditions(
        lat: float = Query(..., ge=-90, le=90),
        lon: float = Query(..., ge=-180, le=180),
        time: datetime | None = Query(None),
        radius_km: float = Query(100.0, gt=0, le=2000),
        db: Session = Depends(get_db),
    ) -> Envelope[list[ObservationModel]]:
        rid = uuid.uuid4().hex
        rows = queries.query_observations(
            db,
            parameters=queries.OCEAN_PARAMETERS,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            at=time or _now(),
        )
        return _observation_envelope(
            db, rid, "/v1/ocean/conditions",
            {"lat": lat, "lon": lon, "time": time.isoformat() if time else None,
             "radius_km": radius_km},
            rows,
            dataset_keys=("incois_buoy", "incois_erddap"),
            subject="ocean observations for the requested location/time",
        )

    @app.get(
        "/v1/ocean/forecast",
        response_model=Envelope[list[ForecastModel]],
        tags=["ocean"],
    )
    def ocean_forecast(
        lat: float = Query(..., ge=-90, le=90),
        lon: float = Query(..., ge=-180, le=180),
        time: datetime | None = Query(None),
        radius_km: float = Query(100.0, gt=0, le=2000),
        db: Session = Depends(get_db),
    ) -> Envelope[list[ForecastModel]]:
        rid = uuid.uuid4().hex
        rows = queries.query_forecasts(
            db,
            parameters=queries.OCEAN_PARAMETERS,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            at=time or _now(),
        )
        return _forecast_envelope(
            db, rid, "/v1/ocean/forecast",
            {"lat": lat, "lon": lon, "time": time.isoformat() if time else None,
             "radius_km": radius_km},
            rows,
            dataset_keys=("imd_nwp",),
            subject="numeric ocean forecasts for the requested location/time",
        )

    # ------------------------------------------------------------------ #
    # Weather conditions / forecast
    # ------------------------------------------------------------------ #
    @app.get(
        "/v1/weather/conditions",
        response_model=Envelope[list[ObservationModel]],
        tags=["weather"],
    )
    def weather_conditions(
        lat: float = Query(..., ge=-90, le=90),
        lon: float = Query(..., ge=-180, le=180),
        time: datetime | None = Query(None),
        radius_km: float = Query(100.0, gt=0, le=2000),
        db: Session = Depends(get_db),
    ) -> Envelope[list[ObservationModel]]:
        rid = uuid.uuid4().hex
        rows = queries.query_observations(
            db,
            parameters=queries.WEATHER_PARAMETERS,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            at=time or _now(),
        )
        return _observation_envelope(
            db, rid, "/v1/weather/conditions",
            {"lat": lat, "lon": lon, "time": time.isoformat() if time else None,
             "radius_km": radius_km},
            rows,
            dataset_keys=("incois_buoy",),
            subject="verified buoy weather observations for the requested location/time",
        )

    @app.get(
        "/v1/weather/forecast",
        response_model=Envelope[list[ForecastModel]],
        tags=["weather"],
    )
    def weather_forecast(
        lat: float = Query(..., ge=-90, le=90),
        lon: float = Query(..., ge=-180, le=180),
        time: datetime | None = Query(None),
        radius_km: float = Query(100.0, gt=0, le=2000),
        db: Session = Depends(get_db),
    ) -> Envelope[list[ForecastModel]]:
        rid = uuid.uuid4().hex
        rows = queries.query_forecasts(
            db,
            parameters=queries.WEATHER_PARAMETERS,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            at=time or _now(),
        )
        return _forecast_envelope(
            db, rid, "/v1/weather/forecast",
            {"lat": lat, "lon": lon, "time": time.isoformat() if time else None,
             "radius_km": radius_km},
            rows,
            dataset_keys=("imd_nwp",),
            subject="numeric IMD weather forecasts for the requested location/time",
        )

    # ------------------------------------------------------------------ #
    # Fishing advisories / suitability
    # ------------------------------------------------------------------ #
    @app.get(
        "/v1/fishing/advisories",
        response_model=Envelope[list[AdvisoryModel]],
        tags=["fishing"],
    )
    def fishing_advisories(
        lat: float | None = Query(None, ge=-90, le=90),
        lon: float | None = Query(None, ge=-180, le=180),
        radius_km: float | None = Query(None, gt=0, le=5000),
        db: Session = Depends(get_db),
    ) -> Envelope[list[AdvisoryModel]]:
        rid = uuid.uuid4().hex
        if (lat is None) ^ (lon is None):
            raise HTTPException(400, "lat and lon must be provided together")
        rows = queries.query_advisories(
            db, lat=lat, lon=lon, radius_km=radius_km, at=_now()
        )
        models = [AdvisoryModel(**r) for r in rows]
        sources = [
            SourceRef(
                provider=r["provider"],
                dataset=r["source_dataset"],
                source_url=r.get("source_url"),
                issued_at=r.get("issued_at"),
                valid_from=r.get("valid_from"),
                valid_until=r.get("valid_until"),
                retrieved_at=r.get("retrieved_at"),
                processing_version=r.get("processing_version"),
            )
            for r in rows
        ]
        warnings = (
            []
            if rows
            else [
                "SOURCE_NOT_INGESTED: no authoritative Tuna/Hilsa/HAB advisory "
                "dataset is registered or scheduled."
            ]
        )
        _persist_evidence(
            db, rid, "/v1/fishing/advisories",
            {"lat": lat, "lon": lon, "radius_km": radius_km},
            sources, [{"advisory_uid": r["advisory_uid"]} for r in rows],
            warnings=warnings,
        )
        return Envelope[list[AdvisoryModel]](
            data=models,
            meta=Meta(generated_at=_now(), request_id=rid),
            sources=sources,
            warnings=warnings,
        )

    @app.get(
        "/v1/fishing/suitability",
        response_model=Envelope[FishingSuitabilityModel],
        tags=["fishing"],
    )
    def fishing_suitability(
        lat: float = Query(..., ge=-90, le=90),
        lon: float = Query(..., ge=-180, le=180),
        radius_km: float = Query(100.0, gt=0, le=2000),
        db: Session = Depends(get_db),
    ) -> Envelope[FishingSuitabilityModel]:
        rid = uuid.uuid4().hex
        at = _now()

        env, env_sources = _collect_risk_inputs(db, lat=lat, lon=lon, radius_km=radius_km, at=at)
        obs = _collect_ocean_params(db, lat=lat, lon=lon, radius_km=radius_km, at=at)

        # Nearest PFZ advisory distance (if any ingested).
        pfz_rows = queries.query_pfz(db, lat=lat, lon=lon, radius_km=radius_km, at=at)
        pfz_distance_km = min((p["distance_km"] for p in pfz_rows), default=None)

        # Ecological hazards / fishery advisories from ingested advisories.
        adv_rows = queries.query_advisories(db, lat=lat, lon=lon, radius_km=radius_km, at=at)
        ecological_hazards = [
            a.get("species_or_ecosystem") or a.get("advisory_type")
            for a in adv_rows if (a.get("advisory_type") or "").lower() in _ECO_HAZARD_TYPES
        ]
        fishery_advisories = [
            a.get("recommendation") or a.get("advisory_type")
            for a in adv_rows if (a.get("advisory_type") or "").lower() not in _ECO_HAZARD_TYPES
        ]

        result = assess_fishing_suitability(
            sst=obs.get("sst"),
            chlorophyll=obs.get("chlorophyll"),
            current_speed=obs.get("current_speed"),
            wave_height=env.get("wave_height"),
            wind_speed=env.get("wind_speed"),
            pfz_distance_km=pfz_distance_km,
            ecological_hazards=ecological_hazards or None,
            fishery_advisories=fishery_advisories or None,
            sources=env_sources,
        )
        model = FishingSuitabilityModel(**result.as_dict())
        sources = [
            SourceRef(provider=s.get("provider", "unknown"),
                      dataset=s.get("dataset") or s.get("source_dataset", "unknown"),
                      source_url=s.get("source_url"))
            for s in env_sources
        ]
        warnings = list(result.negative_drivers) if not env and not obs and not pfz_rows else []
        _persist_evidence(
            db, rid, "/v1/fishing/suitability",
            {"lat": lat, "lon": lon, "radius_km": radius_km},
            sources,
            [{"score": result.score, "classification": result.classification}],
            warnings=warnings,
        )
        return Envelope[FishingSuitabilityModel](
            data=model,
            meta=Meta(generated_at=_now(), request_id=rid, confidence=result.confidence),
            sources=sources,
            warnings=warnings,
        )

    # ------------------------------------------------------------------ #
    # Tides
    # ------------------------------------------------------------------ #
    @app.get(
        "/v1/tides",
        response_model=Envelope[list[ObservationModel]],
        tags=["tides"],
    )
    def tides(
        lat: float = Query(..., ge=-90, le=90),
        lon: float = Query(..., ge=-180, le=180),
        time: datetime | None = Query(None),
        radius_km: float = Query(100.0, gt=0, le=2000),
        db: Session = Depends(get_db),
    ) -> Envelope[list[ObservationModel]]:
        rid = uuid.uuid4().hex
        rows = queries.query_observations(
            db,
            parameters=queries.TIDE_PARAMETERS,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            at=time or _now(),
        )
        return _observation_envelope(
            db, rid, "/v1/tides",
            {"lat": lat, "lon": lon, "time": time.isoformat() if time else None,
             "radius_km": radius_km},
            rows,
            dataset_keys=("incois_tide",),
            subject="TEWS tide-gauge observations for the requested location/time",
        )

    # ------------------------------------------------------------------ #
    # Geofence
    # ------------------------------------------------------------------ #
    @app.get(
        "/v1/geofence/check",
        response_model=Envelope[list[ZoneModel]],
        tags=["geofence"],
    )
    def geofence_check(
        lat: float = Query(..., ge=-90, le=90),
        lon: float = Query(..., ge=-180, le=180),
        db: Session = Depends(get_db),
    ) -> Envelope[list[ZoneModel]]:
        rid = uuid.uuid4().hex
        rows = geofence_service.check_point_in_zones(db, lat=lat, lon=lon)
        return _geofence_envelope(
            db, rid, "/v1/geofence/check", {"lat": lat, "lon": lon}, rows
        )

    @app.get(
        "/v1/geofence/nearby",
        response_model=Envelope[list[ZoneModel]],
        tags=["geofence"],
    )
    def geofence_nearby(
        lat: float = Query(..., ge=-90, le=90),
        lon: float = Query(..., ge=-180, le=180),
        radius_km: float = Query(50.0, gt=0, le=2000),
        db: Session = Depends(get_db),
    ) -> Envelope[list[ZoneModel]]:
        rid = uuid.uuid4().hex
        rows = geofence_service.find_nearby_zones(
            db, lat=lat, lon=lon, radius_km=radius_km
        )
        return _geofence_envelope(
            db, rid, "/v1/geofence/nearby",
            {"lat": lat, "lon": lon, "radius_km": radius_km}, rows
        )

    @app.post(
        "/v1/geofence/intersections",
        response_model=Envelope[list[ZoneModel]],
        tags=["geofence"],
    )
    def geofence_intersections(
        body: IntersectionRequest = Body(...),
        db: Session = Depends(get_db),
    ) -> Envelope[list[ZoneModel]]:
        rid = uuid.uuid4().hex
        try:
            rows = geofence_service.find_route_intersections(db, geometry=body.geometry)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return _geofence_envelope(
            db, rid, "/v1/geofence/intersections",
            {"geometry_type": body.geometry.get("type")}, rows
        )

    # ------------------------------------------------------------------ #
    # Marine risk
    # ------------------------------------------------------------------ #
    @app.get(
        "/v1/risk/marine",
        response_model=Envelope[MarineRiskModel],
        tags=["risk"],
    )
    def risk_marine(
        lat: float = Query(..., ge=-90, le=90),
        lon: float = Query(..., ge=-180, le=180),
        time: datetime | None = Query(None),
        radius_km: float = Query(100.0, gt=0, le=2000),
        vessel_type: str | None = Query(None),
        db: Session = Depends(get_db),
    ) -> Envelope[MarineRiskModel]:
        rid = uuid.uuid4().hex
        at = time or _now()

        # Gather whatever environmental factors and active hazards are available.
        env, env_sources = _collect_risk_inputs(db, lat=lat, lon=lon, radius_km=radius_km, at=at)
        alert_rows = queries.query_alerts(
            db, lat=lat, lon=lon, radius_km=radius_km, active_only=True, at=at, limit=100
        )
        active_warnings = [
            {"severity": a.get("severity"), "event_type": a.get("event_type"),
             "headline": a.get("headline")}
            for a in alert_rows
        ]
        cyclone_distance_km = _nearest_cyclone_distance_km(alert_rows)

        thresholds = RiskThresholds(vessel_type=vessel_type or "default")
        assessment = assess_marine_risk(
            active_warnings=active_warnings or None,
            cyclone_distance_km=cyclone_distance_km,
            thresholds=thresholds,
            valid_from=at,
            sources=env_sources,
            **env,
        )

        model = MarineRiskModel(**assessment.as_dict())
        sources = [
            SourceRef(provider=s.get("provider", "unknown"),
                      dataset=s.get("dataset") or s.get("source_dataset", "unknown"),
                      source_url=s.get("source_url"))
            for s in env_sources
        ]
        alert_sources = [
            SourceRef(provider=a["provider"], dataset=a["source_dataset"],
                      source_url=a.get("source_url"))
            for a in alert_rows
        ]
        sources.extend(alert_sources)
        warnings = list(assessment.warnings)
        _persist_evidence(
            db, rid, "/v1/risk/marine",
            {"lat": lat, "lon": lon, "radius_km": radius_km,
             "time": at.isoformat(), "vessel_type": vessel_type},
            sources,
            [{"risk_score": assessment.risk_score, "risk_level": assessment.risk_level}],
            warnings=warnings,
        )
        return Envelope[MarineRiskModel](
            data=model,
            meta=Meta(generated_at=_now(), request_id=rid,
                      valid_from=at, confidence=1.0 if env else None),
            sources=sources,
            warnings=warnings,
        )

    # ------------------------------------------------------------------ #
    # Safe routing
    # ------------------------------------------------------------------ #
    @app.post(
        "/v1/routes/safe",
        response_model=Envelope[SafeRouteModel],
        tags=["routes"],
    )
    def routes_safe(
        body: SafeRouteRequest = Body(...),
        db: Session = Depends(get_db),
    ) -> Envelope[SafeRouteModel]:
        rid = uuid.uuid4().hex

        def _zone_checker(geometry: dict) -> list[dict]:
            try:
                return geofence_service.find_route_intersections(db, geometry=geometry)
            except ValueError:
                return []

        result = compute_safe_route(
            start=(body.start.lat, body.start.lon),
            end=(body.end.lat, body.end.lon),
            departure_time=body.departure_time,
            vessel_type=body.vessel_type or "default",
            thresholds=RiskThresholds(vessel_type=body.vessel_type or "default"),
            zone_checker=_zone_checker,
        )
        model = SafeRouteModel(**result.as_dict())
        warnings = list(result.warnings)
        _persist_evidence(
            db, rid, "/v1/routes/safe",
            {"start": [body.start.lat, body.start.lon],
             "end": [body.end.lat, body.end.lon],
             "vessel_type": body.vessel_type},
            [],
            [{"route_risk_score": result.route_risk_score, "status": result.status}],
            warnings=warnings,
        )
        return Envelope[SafeRouteModel](
            data=model,
            meta=Meta(generated_at=_now(), request_id=rid),
            warnings=warnings,
        )

    # ------------------------------------------------------------------ #
    # Internal: ingest-trigger bridge (worker -> WS AlertBroker)
    # ------------------------------------------------------------------ #
    @app.post("/v1/internal/ingest-trigger", tags=["internal"], include_in_schema=False)
    async def internal_ingest_trigger(
        events: list[dict] = Body(default_factory=list),
        x_internal_token: str | None = Header(None),
    ) -> dict:
        """Receive alert events produced by a worker after ingestion and fan
        them out to WebSocket subscribers via the AlertBroker.
        """
        # C8 fix: require MDE_INTERNAL_TOKEN when configured.
        import os  # noqa: PLC0415
        expected = os.environ.get("MDE_INTERNAL_TOKEN", "")
        if expected and x_internal_token != expected:
            raise HTTPException(403, "Invalid or missing X-Internal-Token header")
        broker = get_broker()
        for event in events:
            await broker.publish(event)
        return {"published": len(events)}

    # ------------------------------------------------------------------ #
    # STAC catalog (raw STAC JSON — not wrapped in the canonical envelope)
    # ------------------------------------------------------------------ #
    @app.get("/v1/stac/collections", tags=["stac"])
    def stac_collections(db: Session = Depends(get_db)):
        from fastapi.responses import JSONResponse

        collections = stac.list_stac_collections(db)
        return JSONResponse(
            content={
                "collections": collections,
                "links": [
                    {"rel": "self", "type": "application/json",
                     "href": "/v1/stac/collections"},
                    {"rel": "root", "type": "application/json",
                     "href": "/v1/stac/collections"},
                ],
            }
        )

    @app.get("/v1/stac/collections/{collection_id}", tags=["stac"])
    def stac_collection(collection_id: str, db: Session = Depends(get_db)):
        from fastapi.responses import JSONResponse

        collection = stac.get_stac_collection(db, collection_id)
        if collection is None:
            raise HTTPException(404, f"STAC collection {collection_id!r} not found")
        return JSONResponse(content=collection)

    @app.get("/v1/stac/collections/{collection_id}/items", tags=["stac"])
    def stac_items(
        collection_id: str,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
    ):
        from fastapi.responses import JSONResponse

        if stac.get_stac_collection(db, collection_id) is None:
            raise HTTPException(404, f"STAC collection {collection_id!r} not found")
        items = stac.list_stac_items(db, collection_id, limit=limit, offset=offset)
        return JSONResponse(
            content={
                "type": "FeatureCollection",
                "features": items,
                "links": [
                    {"rel": "self", "type": "application/geo+json",
                     "href": f"/v1/stac/collections/{collection_id}/items"},
                    {"rel": "collection", "type": "application/json",
                     "href": f"/v1/stac/collections/{collection_id}"},
                    {"rel": "root", "type": "application/json",
                     "href": "/v1/stac/collections"},
                ],
            }
        )

    # ------------------------------------------------------------------ #
    # Tile serving placeholder (TiTiler integration pending)
    # ------------------------------------------------------------------ #
    @app.get("/v1/tiles/{layer}/{z}/{x}/{y}", tags=["tiles"])
    def tiles(layer: str, z: int, x: int, y: int):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=501,
            content={
                "detail": (
                    "Tile serving requires TiTiler integration with COG products. "
                    "Not yet implemented."
                ),
                "layer": layer,
                "tile": {"z": z, "x": x, "y": y},
                "status": "NOT_IMPLEMENTED",
            },
        )

    return app


def _persist_evidence(
    db: Session,
    rid: str,
    endpoint: str,
    params: dict,
    sources: list,
    refs: list,
    warnings: list | None = None,
    *,
    capability_status: str | None = None,
    source_states: list[dict] | None = None,
) -> None:
    """Persist an evidence package with aggregate freshness/quality."""
    src_dicts = [source.model_dump(mode="json") for source in sources]
    states = source_states or []
    json_states = json.loads(json.dumps(states, default=str))
    queries.save_evidence(
        db,
        request_id=rid,
        endpoint=endpoint,
        query_params=params,
        sources=src_dicts,
        record_refs=refs,
        confidence=1.0 if refs else None,
        freshness={"result_count": len(refs), "source_states": json_states},
        quality={"result_count": len(refs)},
        warnings=warnings or [],
        capability_status=capability_status or ("source_gap" if warnings else "available"),
        data_versions={
            state["dataset"]: str(
                state.get("last_success_at")
                or state.get("last_checked_at")
                or "not_run"
            )
            for state in states
        },
        data_lineage=[
            {
                "source_url": source.get("source_url"),
                "retrieved_at": source.get("retrieved_at"),
            }
            for source in src_dicts
        ],
    )


def _source_outcome(
    db: Session,
    dataset_keys: tuple[str, ...],
    *,
    subject: str,
    has_records: bool,
) -> tuple[list[str], str, list[dict]]:
    """Classify empty/partial API results from persisted source poll states."""
    states = queries.get_dataset_source_states(db, dataset_keys)
    blocked_states = {
        "auth_blocked",
        "contract_unavailable",
        "license_gated",
        "disabled",
        "source_unavailable",
        "contract_error",
        "processing_error",
        "not_run",
        "not_registered",
    }
    if has_records:
        partial = [state for state in states if state.get("state") in blocked_states]
        if partial:
            detail = ", ".join(
                f"{state['dataset']}={state.get('state')}" for state in partial
            )
            return [f"PARTIAL_SOURCE_COVERAGE: {detail}"], "partial", states
        return [], "available", states

    result_states = {str(state.get("state") or "not_run") for state in states}
    outcomes = (
        ("auth_blocked", "SOURCE_AUTH_BLOCKED", "auth_blocked"),
        ("contract_unavailable", "SOURCE_CONTRACT_UNAVAILABLE", "contract_unavailable"),
        ("license_gated", "SOURCE_LICENSE_GATED", "license_gated"),
        ("source_unavailable", "SOURCE_UNAVAILABLE", "source_unavailable"),
        ("contract_error", "SOURCE_CONTRACT_ERROR", "source_unavailable"),
        ("processing_error", "SOURCE_PROCESSING_ERROR", "source_unavailable"),
        ("disabled", "SOURCE_DISABLED", "disabled"),
    )
    if result_states and result_states <= {"empty"}:
        return (
            [f"SOURCE_HEALTHY_EMPTY: upstream source is healthy but has no {subject}."],
            "healthy_empty",
            states,
        )
    for state_name, warning_code, capability in outcomes:
        if state_name in result_states:
            return (
                [f"{warning_code}: {subject} is unavailable ({state_name})."],
                capability,
                states,
            )
    if result_states & {"not_run", "not_registered"} or not states:
        return (
            [f"SOURCE_NOT_INGESTED: {subject} has not yet been scheduled/ingested."],
            "not_ingested",
            states,
        )
    return (
        [f"NO_MATCHING_RECORDS: source data is available but no {subject} matched."],
        "available",
        states,
    )


def _sources_from_rows(rows: list[dict]) -> list[SourceRef]:
    return [
        SourceRef(
            provider=r["provider"],
            dataset=r["source_dataset"],
            source_url=r.get("source_url"),
            issued_at=r.get("issued_at"),
            valid_from=r.get("valid_from"),
            valid_until=r.get("valid_until"),
            retrieved_at=r.get("retrieved_at"),
            processing_version=r.get("processing_version"),
        )
        for r in rows
    ]


def _observation_envelope(
    db: Session,
    rid: str,
    endpoint: str,
    params: dict,
    rows: list[dict],
    *,
    dataset_keys: tuple[str, ...],
    subject: str,
) -> Envelope[list[ObservationModel]]:
    models = [ObservationModel(**row) for row in rows]
    sources = _sources_from_rows(rows)
    warnings, capability, source_states = _source_outcome(
        db,
        dataset_keys,
        subject=subject,
        has_records=bool(rows),
    )
    _persist_evidence(
        db,
        rid,
        endpoint,
        params,
        sources,
        [{"observation_uid": row["observation_uid"]} for row in rows],
        warnings=warnings,
        capability_status=capability,
        source_states=source_states,
    )
    return Envelope[list[ObservationModel]](
        data=models,
        meta=Meta(generated_at=_now(), request_id=rid),
        sources=sources,
        warnings=warnings,
    )


def _forecast_envelope(
    db: Session,
    rid: str,
    endpoint: str,
    params: dict,
    rows: list[dict],
    *,
    dataset_keys: tuple[str, ...],
    subject: str,
) -> Envelope[list[ForecastModel]]:
    models = [ForecastModel(**row) for row in rows]
    sources = _sources_from_rows(rows)
    warnings, capability, source_states = _source_outcome(
        db,
        dataset_keys,
        subject=subject,
        has_records=bool(rows),
    )
    _persist_evidence(
        db,
        rid,
        endpoint,
        params,
        sources,
        [{"forecast_uid": row["forecast_uid"]} for row in rows],
        warnings=warnings,
        capability_status=capability,
        source_states=source_states,
    )
    return Envelope[list[ForecastModel]](
        data=models,
        meta=Meta(generated_at=_now(), request_id=rid),
        sources=sources,
        warnings=warnings,
    )


def _geofence_envelope(
    db: Session, rid: str, endpoint: str, params: dict, rows: list[dict],
) -> Envelope[list[ZoneModel]]:
    """Convert geofence results without confusing no match with no source."""
    source_gap = [row for row in rows if row.get("source_gap")]
    zone_rows = [row for row in rows if not row.get("source_gap")]
    models = [ZoneModel(**row) for row in zone_rows]
    sources = [
        SourceRef(
            provider=row.get("source") or "unknown",
            dataset=row.get("source_dataset") or "marine_zone",
            source_url=row.get("source_url"),
            retrieved_at=row.get("retrieved_at"),
        )
        for row in zone_rows
    ]
    coverage = geofence_service.zone_coverage(db)
    source_states = queries.get_dataset_source_states(
        db, ("marine_regions_eez_india",)
    )
    warnings = [
        row.get("warning", geofence_service.SOURCE_GAP_NO_ZONES)
        for row in source_gap
    ]
    warnings.extend(
        f"ZONE_CATEGORY_NOT_LOADED: {category}"
        for category, state in coverage.items()
        if state.get("status") != "available"
    )
    eez_rows = [
        row
        for row in zone_rows
        if str(row.get("zone_type") or "").lower()
        in {"eez", "boundary", "international_boundary"}
    ]
    eez_warnings, eez_capability, _ = _source_outcome(
        db,
        ("marine_regions_eez_india",),
        subject="authoritative India EEZ boundary geometry for this query",
        has_records=bool(eez_rows),
    )
    warnings.extend(eez_warnings)
    warnings = list(dict.fromkeys(warnings))
    if zone_rows:
        capability = "partial" if warnings else "available"
    elif eez_capability not in {"available", "partial"}:
        capability = eez_capability
    else:
        capability = "source_gap" if warnings else "available"

    _persist_evidence(
        db,
        rid,
        endpoint,
        params,
        sources,
        [{"zone_uid": row["zone_uid"]} for row in zone_rows],
        warnings=warnings,
        capability_status=capability,
        source_states=source_states,
    )
    return Envelope[list[ZoneModel]](
        data=models,
        meta=Meta(generated_at=_now(), request_id=rid),
        sources=sources,
        warnings=warnings,
    )


# Canonical parameter name -> risk-engine keyword (environmental factors).
_RISK_PARAM_MAP: dict[str, str] = {
    "wave_height": "wave_height",
    "significant_wave_height": "wave_height",
    "wave": "wave_height",
    "swell": "swell_height",
    "wind_speed": "wind_speed",
    "wind": "wind_speed",
    "wind_gust": "wind_gust",
    "rainfall": "rainfall",
    "precipitation": "rainfall",
    "pressure": "pressure",
    "mslp": "pressure",
    "sea_level_pressure": "pressure",
}

# Canonical parameter name -> suitability ocean keyword.
_OCEAN_PARAM_MAP: dict[str, str] = {
    "sst": "sst",
    "sea_surface_temperature": "sst",
    "chlorophyll": "chlorophyll",
    "chlorophyll_a": "chlorophyll",
    "current_speed": "current_speed",
    "current": "current_speed",
}


def _nearest_value(rows: list[dict]) -> float | None:
    """Return the value of the nearest observation with a non-null value."""
    best = None
    best_dist = float("inf")
    for r in rows:
        if r.get("value") is None:
            continue
        d = r.get("distance_km")
        d = float("inf") if d is None else d
        if d < best_dist:
            best_dist = d
            best = r["value"]
    return best


def _collect_risk_inputs(
    db: Session, *, lat: float, lon: float, radius_km: float, at: datetime,
) -> tuple[dict, list[dict]]:
    """Collect environmental risk factors from ingested observations/forecasts.

    Returns a ``(factors, sources)`` tuple. ``factors`` maps risk-engine keyword
    arguments to nearest observed/forecast values. Empty when no matching
    canonical inputs are present; callers use persisted dataset poll states to
    distinguish not-run, healthy-empty, and blocked sources.
    """
    params = queries.OCEAN_PARAMETERS + queries.WEATHER_PARAMETERS
    factors: dict[str, float] = {}
    sources: list[dict] = []
    grouped: dict[str, list[dict]] = {}
    for row in queries.query_observations(
        db, parameters=params, lat=lat, lon=lon, radius_km=radius_km, at=at
    ):
        grouped.setdefault(row["parameter"], []).append(row)
        sources.append({"provider": row["provider"], "dataset": row["source_dataset"],
                        "source_url": row.get("source_url")})
    for row in queries.query_forecasts(
        db, parameters=params, lat=lat, lon=lon, radius_km=radius_km, at=at
    ):
        grouped.setdefault(row["parameter"], []).append(row)
        sources.append({"provider": row["provider"], "dataset": row["source_dataset"],
                        "source_url": row.get("source_url")})

    for param, rows in grouped.items():
        key = _RISK_PARAM_MAP.get(param)
        if key is None or key in factors:
            continue
        value = _nearest_value(rows)
        if value is not None:
            factors[key] = value
    return factors, sources


def _collect_ocean_params(
    db: Session, *, lat: float, lon: float, radius_km: float, at: datetime,
) -> dict:
    """Collect SST/chlorophyll/current values for the suitability engine."""
    out: dict[str, float] = {}
    grouped: dict[str, list[dict]] = {}
    for row in queries.query_observations(
        db, parameters=queries.OCEAN_PARAMETERS, lat=lat, lon=lon,
        radius_km=radius_km, at=at,
    ):
        grouped.setdefault(row["parameter"], []).append(row)
    for param, rows in grouped.items():
        key = _OCEAN_PARAM_MAP.get(param)
        if key is None or key in out:
            continue
        value = _nearest_value(rows)
        if value is not None:
            out[key] = value
    return out


def _nearest_cyclone_distance_km(alert_rows: list[dict]) -> float | None:
    """Distance (km) to the nearest cyclone-type active alert, if any."""
    distances = [
        a["distance_km"]
        for a in alert_rows
        if a.get("distance_km") is not None
        and "cyclone" in (a.get("event_type") or "").lower()
    ]
    return min(distances) if distances else None


app = create_app()
