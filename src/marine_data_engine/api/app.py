"""FastAPI application: query-only endpoints + WebSocket alert stream.

Endpoints only read processed/canonical data via query repositories. No handler
fetches upstream sources or triggers ingestion. Every response uses the
canonical envelope and persists an Evidence record addressable at
``GET /v1/evidence/{request_id}``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import Body, Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
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
    event loop exists, the publish is scheduled as a task; otherwise the event
    is published synchronously via a transient loop. Never raises to callers.
    """
    broker = broker or get_broker()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        loop.create_task(broker.publish(event))
    else:
        try:
            asyncio.run(broker.publish(event))
        except Exception:  # noqa: BLE001
            pass


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
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8000",
            "*",  # dev convenience; tighten in production
        ],
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
        _persist_evidence(
            db, rid, "/v1/fishing/pfz",
            {"lat": lat, "lon": lon, "radius_km": radius_km},
            sources, [{"pfz_uid": r["pfz_uid"]} for r in rows],
        )
        return Envelope[list[PFZModel]](
            data=models,
            meta=Meta(generated_at=_now(), request_id=rid),
            sources=sources,
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
        _persist_evidence(
            db, rid, "/v1/alerts",
            {"lat": lat, "lon": lon, "radius_km": radius_km, "event_type": event_type},
            sources, [{"alert_uid": r["alert_uid"]} for r in rows],
        )
        return Envelope[list[AlertModel]](
            data=models,
            meta=Meta(generated_at=_now(), request_id=rid),
            sources=sources,
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
            empty_warning=(
                "No ocean observations ingested yet (SST/chlorophyll/current/wave). "
                "Ocean gridded connectors (INCOIS ERDDAP) are not yet enabled — see SOURCE_GAPS.md."
            ),
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
            empty_warning=(
                "No ocean forecast data ingested yet. INCOIS ocean forecast connectors "
                "are not yet enabled — see SOURCE_GAPS.md."
            ),
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
            empty_warning=(
                "No weather observations ingested yet (wind/pressure/rainfall). "
                "IMD observation connectors are not yet enabled — see SOURCE_GAPS.md."
            ),
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
            empty_warning=(
                "No weather forecast data ingested yet. IMD/GFS forecast connectors "
                "are not yet enabled — see SOURCE_GAPS.md."
            ),
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
                "No fisheries/ecosystem advisories ingested yet. "
                "Tuna/Hilsa/HAB advisory connectors are not yet enabled — see SOURCE_GAPS.md."
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
            empty_warning=(
                "No tide/water-level data available. INCOIS tide-gauge machine access "
                "is blocked pending HAR-D capture (entry-page-only source) — see "
                "SOURCE_GAPS.md. Tide predictions are not inferred."
            ),
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
    ) -> dict:
        """Receive alert events produced by a worker after ingestion and fan
        them out to WebSocket subscribers via the AlertBroker.
        """
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
) -> None:
    """Persist an evidence package with aggregate freshness/quality."""
    src_dicts = [s.model_dump(mode="json") for s in sources]
    queries.save_evidence(
        db,
        request_id=rid,
        endpoint=endpoint,
        query_params=params,
        sources=src_dicts,
        record_refs=refs,
        confidence=1.0 if refs else None,
        freshness={"result_count": len(refs)},
        quality={"result_count": len(refs)},
        warnings=warnings or [],
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
    db: Session, rid: str, endpoint: str, params: dict, rows: list[dict],
    *, empty_warning: str,
) -> Envelope[list[ObservationModel]]:
    models = [ObservationModel(**r) for r in rows]
    sources = _sources_from_rows(rows)
    warnings = [] if rows else [empty_warning]
    _persist_evidence(
        db, rid, endpoint, params, sources,
        [{"observation_uid": r["observation_uid"]} for r in rows],
        warnings=warnings,
    )
    return Envelope[list[ObservationModel]](
        data=models,
        meta=Meta(generated_at=_now(), request_id=rid),
        sources=sources,
        warnings=warnings,
    )


def _forecast_envelope(
    db: Session, rid: str, endpoint: str, params: dict, rows: list[dict],
    *, empty_warning: str,
) -> Envelope[list[ForecastModel]]:
    models = [ForecastModel(**r) for r in rows]
    sources = _sources_from_rows(rows)
    warnings = [] if rows else [empty_warning]
    _persist_evidence(
        db, rid, endpoint, params, sources,
        [{"forecast_uid": r["forecast_uid"]} for r in rows],
        warnings=warnings,
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
    """Convert geofence-service results into a zone envelope.

    The service returns a single-element ``source_gap`` sentinel when no zones
    are loaded; that is surfaced as an empty data list plus a SOURCE_GAP warning
    rather than a phantom zone row.
    """
    source_gap = [r for r in rows if r.get("source_gap")]
    zone_rows = [r for r in rows if not r.get("source_gap")]
    models = [ZoneModel(**r) for r in zone_rows]
    sources = [
        SourceRef(provider=r.get("source") or "operator", dataset="marine_zone",
                  source_url=r.get("source_url"))
        for r in zone_rows
    ]
    if source_gap:
        warnings = [r.get("warning", geofence_service.SOURCE_GAP_NO_ZONES) for r in source_gap]
    elif not zone_rows:
        warnings = [geofence_service.SOURCE_GAP_NO_ZONES]
    else:
        warnings = []
    _persist_evidence(
        db, rid, endpoint, params, sources,
        [{"zone_uid": r["zone_uid"]} for r in zone_rows],
        warnings=warnings,
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
    arguments to nearest observed/forecast values. Empty when nothing is
    ingested (the ocean/weather connectors are SOURCE_GAP-blocked).
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
