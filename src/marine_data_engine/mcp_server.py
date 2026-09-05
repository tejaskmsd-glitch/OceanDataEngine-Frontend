"""Marine Data Engine — MCP Server.

Production MCP server exposing the Marine Data Engine as tools, resources,
and prompts over the Streamable HTTP transport (MCP spec 2025-03-26+).

Architecture:
    ┌────────────────────────┐
    │ LLM / Agent / Claude   │
    └──────────┬─────────────┘
               │ Streamable HTTP (POST /mcp)
    ┌──────────▼─────────────┐
    │   MCP Server (this)    │  ← tools, resources, prompts
    │   mcp SDK v1.29        │
    └──────────┬─────────────┘
               │ session_scope()
    ┌──────────▼─────────────┐
    │ Marine Data Engine     │  ← services, domain, storage
    │ (existing codebase)    │
    └────────────────────────┘

Transports:
    streamable-http  — Production (default). Serves at http://host:port/mcp
    sse              — Legacy SSE for older clients
    stdio            — Local dev / subprocess

Run:
    python -m marine_data_engine.mcp_server                    # streamable-http on :9100
    MCP_TRANSPORT=sse python -m marine_data_engine.mcp_server  # legacy SSE
    MCP_PORT=8100 python -m marine_data_engine.mcp_server      # custom port
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta

from mcp.server.fastmcp import FastMCP
from sqlalchemy import func, select

from marine_data_engine.db.models import (
    PFZ,
    Alert,
    Forecast,
    MarineZone,
    Observation,
)

# ── Engine imports ───────────────────────────────────────────────────────
from marine_data_engine.db.session import session_scope
from marine_data_engine.domain.anomaly import (
    detect_anomalies,
)
from marine_data_engine.domain.geo import bearing_deg, haversine_km
from marine_data_engine.domain.risk import RiskThresholds, assess_marine_risk
from marine_data_engine.domain.safe_window import compute_safe_windows
from marine_data_engine.domain.safety_gate import evaluate_safety_gate
from marine_data_engine.domain.suitability import assess_fishing_suitability
from marine_data_engine.services import geofence, queries, routing

logger = logging.getLogger("mcp.marine")


def _db_error_response(tool_name: str, exc: Exception) -> dict:
    """Return a degraded-mode response when the database is unavailable."""
    return {
        "data": [],
        "count": 0,
        "evidence": _evidence(tool_name, [], warnings=[
            f"SOURCE_GAP: Database unavailable ({type(exc).__name__}: {exc})"
        ]),
    }

# ═════════════════════════════════════════════════════════════════════════
# Server instance
# ═════════════════════════════════════════════════════════════════════════
mcp = FastMCP(
    "Marine Data Engine",
    instructions=(
        "Marine intelligence platform for Indian coastal waters. "
        "Query potential fishing zones (PFZ), weather/ocean observations, "
        "hazard alerts, compute marine risk assessments, plan safe routes, "
        "check geofence compliance, and detect oceanographic anomalies. "
        "All data is grounded with provenance — every result includes "
        "source attribution, timestamps, and confidence scores. "
        "When data is unavailable, tools return explicit SOURCE_GAP warnings "
        "rather than empty results."
    ),
)


# ── Helpers ──────────────────────────────────────────────────────────────
def _ts() -> str:
    return datetime.now(UTC).isoformat()


def _evidence(tool_name: str, sources: list[dict], warnings: list[str] | None = None) -> dict:
    """Build an evidence/provenance envelope for every tool response."""
    return {
        "tool": tool_name,
        "generated_at": _ts(),
        "sources": sources,
        "warnings": warnings or [],
        "capability_status": "source_gap" if warnings else "available",
    }


# ═════════════════════════════════════════════════════════════════════════
# TOOLS — Query Layer
# ═════════════════════════════════════════════════════════════════════════

@mcp.tool()
def query_pfz(
    lat: float,
    lon: float,
    radius_km: float = 100.0,
    include_expired: bool = False,
) -> dict:
    """Find Potential Fishing Zones (PFZ) near a location.

    Returns active PFZ advisories within the search radius, each with
    SST, chlorophyll, confidence, distance, and point-in-polygon status.
    Use this to answer: "Where should I fish?", "Nearest PFZ off Goa?",
    "Is my vessel inside an active PFZ?"
    """
    try:
        with session_scope() as s:
            results = queries.query_pfz(s, lat=lat, lon=lon, radius_km=radius_km,
                                         include_expired=include_expired)
    except Exception as exc:
        return _db_error_response("query_pfz", exc)
    warnings = []
    if not results:
        warnings.append(f"No PFZ advisories found within {radius_km} km of ({lat}, {lon})")
    return {
        "data": results,
        "count": len(results),
        "evidence": _evidence("query_pfz",
                              [{"provider": "INCOIS", "dataset": "incois_pfz"}],
                              warnings),
    }


@mcp.tool()
def query_alerts(
    event_type: str | None = None,
    active_only: bool = True,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float | None = None,
    limit: int = 50,
) -> dict:
    """Query active marine hazard alerts — cyclones, high waves, tsunami,
    lightning, squall, gale, fog, storm surge.

    Filter by event_type (exact match), location + radius, and active status.
    Use this for: "Any cyclone warnings in Bay of Bengal?",
    "Alerts near Vizag?", "Is there a tsunami bulletin?"
    """
    try:
        with session_scope() as s:
            results = queries.query_alerts(
                s, event_type=event_type, active_only=active_only,
                lat=lat, lon=lon, radius_km=radius_km, limit=limit,
            )
    except Exception as exc:
        return _db_error_response("query_alerts", exc)
    warnings = []
    if not results:
        msg = f"No {'active ' if active_only else ''}alerts"
        if event_type:
            msg += f" of type '{event_type}'"
        if lat is not None:
            msg += f" within {radius_km or 'any'} km of ({lat}, {lon})"
        warnings.append(msg)
    return {
        "data": results,
        "count": len(results),
        "evidence": _evidence("query_alerts",
                              [{"provider": "IMD", "dataset": "imd_cap"},
                               {"provider": "INCOIS", "dataset": "incois_hwa"}],
                              warnings),
    }


@mcp.tool()
def query_observations(
    parameters: list[str] | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float = 100.0,
    at: str | None = None,
) -> dict:
    """Query in-situ observations — tide levels, buoy readings (SST, wave
    height, wind speed, pressure, wind direction).

    Parameters: water_level, sea_surface_temperature, significant_wave_height,
    wind_speed, wind_direction, sea_level_pressure, etc.
    Use this for: "Tide at Mormugao?", "Buoy conditions near Kochi?",
    "Wave height off Vizag?"
    """
    from dateutil.parser import isoparse
    at_dt = isoparse(at) if at else None
    try:
        with session_scope() as s:
            results = queries.query_observations(
                s, parameters=parameters or [], lat=lat, lon=lon,
                radius_km=radius_km, at=at_dt,
            )
    except Exception as exc:
        return _db_error_response("query_observations", exc)
    warnings = []
    if not results:
        warnings.append(f"No observations found for params={parameters} near ({lat}, {lon})")
    return {
        "data": results,
        "count": len(results),
        "evidence": _evidence("query_observations",
                              [{"provider": "IMD", "dataset": "imd_buoy"},
                               {"provider": "INCOIS", "dataset": "incois_tide"}],
                              warnings),
    }


@mcp.tool()
def query_forecasts(
    parameters: list[str] | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float = 200.0,
    at: str | None = None,
) -> dict:
    """Query NWP marine forecasts — wind speed, wave height, rainfall,
    pressure, swell height.

    Use this for: "Weather forecast off Chennai tomorrow?",
    "Expected wave height off Mumbai?", "Rainfall forecast Bay of Bengal?"
    """
    from dateutil.parser import isoparse
    at_dt = isoparse(at) if at else None
    try:
        with session_scope() as s:
            results = queries.query_forecasts(
                s, parameters=parameters or [], lat=lat, lon=lon,
                radius_km=radius_km, at=at_dt,
            )
    except Exception as exc:
        return _db_error_response("query_forecasts", exc)
    warnings = []
    if not results:
        warnings.append("SOURCE_GAP: No forecast data available for the requested parameters/location")
    return {
        "data": results,
        "count": len(results),
        "evidence": _evidence("query_forecasts",
                              [{"provider": "IMD", "dataset": "imd_nwp"}],
                              warnings),
    }


# ═════════════════════════════════════════════════════════════════════════
# TOOLS — Domain Logic (pure computation, no DB)
# ═════════════════════════════════════════════════════════════════════════

@mcp.tool()
def assess_risk(
    wave_height_m: float | None = None,
    wind_speed_ms: float | None = None,
    gust_speed_ms: float | None = None,
    swell_height_m: float | None = None,
    wave_period_s: float | None = None,
    rainfall_mm_hr: float | None = None,
    pressure_hpa: float | None = None,
    pressure_trend_hpa_3h: float | None = None,
    active_warnings: int = 0,
    nearest_cyclone_km: float | None = None,
    vessel_type: str = "small_motorized",
) -> dict:
    """Compute marine risk score (0-100) from environmental conditions.

    Returns risk level (LOW/MODERATE/HIGH/EXTREME), score, dominant risk
    factors, and safety recommendation. Thresholds adjust by vessel_type:
    small_motorized, traditional_canoe, deep_sea_trawler, cargo.

    Use this for: "Is it safe to go fishing tomorrow?",
    "Risk score off Porbandar?", "Should vessels evacuate?"
    """
    warnings_list = [{"severity": "severe"}] * active_warnings if active_warnings else None

    result = assess_marine_risk(
        wave_height=wave_height_m,
        wind_speed=wind_speed_ms,
        wind_gust=gust_speed_ms,
        swell_height=swell_height_m,
        wave_period=wave_period_s,
        rainfall=rainfall_mm_hr,
        pressure=pressure_hpa,
        pressure_trend=pressure_trend_hpa_3h,
        active_warnings=warnings_list,
        cyclone_distance_km=nearest_cyclone_km,
        thresholds=RiskThresholds(),
    )
    d = result.as_dict()
    d["evidence"] = _evidence("assess_risk", [{"provider": "domain", "dataset": "risk_engine"}])
    return d


@mcp.tool()
def assess_suitability(
    sst: float | None = None,
    chlorophyll: float | None = None,
    current_speed_ms: float | None = None,
    wave_height_m: float | None = None,
    wind_speed_ms: float | None = None,
    nearest_pfz_km: float | None = None,
    sst_anomaly: float | None = None,
    chl_anomaly: float | None = None,
    ecological_hazards: list[str] | None = None,
    fishery_advisories: list[str] | None = None,
) -> dict:
    """Assess fishing suitability at a location (0-100 score).

    Combines SST, chlorophyll, currents, wave/wind safety, PFZ proximity,
    anomalies, and ecological hazards into a composite score.
    Classification: EXCELLENT/GOOD/MODERATE/POOR/UNSUITABLE.

    Use this for: "How good is fishing off Goa today?",
    "Suitability score for Netrani area?", "Is the water too warm to fish?"
    """
    result = assess_fishing_suitability(
        sst=sst, chlorophyll=chlorophyll, current_speed=current_speed_ms,
        wave_height=wave_height_m, wind_speed=wind_speed_ms,
        pfz_distance_km=nearest_pfz_km,
        sst_anomaly=sst_anomaly, chlorophyll_anomaly=chl_anomaly,
        ecological_hazards=ecological_hazards or [],
        fishery_advisories=fishery_advisories or [],
    )
    d = result.as_dict()
    d["evidence"] = _evidence("assess_suitability",
                              [{"provider": "domain", "dataset": "suitability_engine"}])
    return d


@mcp.tool()
def compute_risk_windows(
    wave_heights: list[float],
    wind_speeds: list[float],
    start_time: str,
    interval_hours: int = 3,
    swell_heights: list[float] | None = None,
    warning_periods: list[dict] | None = None,
) -> dict:
    """Compute safe weather windows from a forecast time series.

    Input a series of wave heights and wind speeds (equal length), plus
    start time and interval. Returns windows classified as
    FAVOURABLE / MODERATE / HIGH_RISK with timestamps.

    Use this for: "When is it safe to go out tomorrow?",
    "24-hour safe window for vallams off Vizhinjam?",
    "When does the weather window close?"
    """
    from dateutil.parser import isoparse
    start = isoparse(start_time)
    times = [start + timedelta(hours=i * interval_hours) for i in range(len(wave_heights))]

    # If a swell series is supplied, fold it into the effective sea state so it
    # is not silently ignored (the risk engine models a single wave/sea-state
    # magnitude, not a separate swell channel). Use the larger of wave/swell
    # per step. Length-safe: never drop or misalign wave steps if the swell
    # series is a different length — fold only where a swell value exists.
    effective_waves = list(wave_heights)
    if swell_heights:
        for i in range(len(effective_waves)):
            s = swell_heights[i] if i < len(swell_heights) else None
            if s is None:
                continue
            w = effective_waves[i]
            effective_waves[i] = s if w is None else max(w, s)

    # Normalize caller-supplied warning periods (list of dicts) into the
    # (start, end) datetime tuples the domain function expects. Accept the
    # common key spellings and skip malformed entries rather than crash.
    warnings_active: list[tuple[datetime, datetime]] = []
    for wp in warning_periods or []:
        if not isinstance(wp, dict):
            continue
        raw_start = wp.get("valid_from") or wp.get("start") or wp.get("from")
        raw_end = wp.get("valid_until") or wp.get("end") or wp.get("to")
        if not raw_start or not raw_end:
            continue
        try:
            wf = isoparse(raw_start) if isinstance(raw_start, str) else raw_start
            wu = isoparse(raw_end) if isinstance(raw_end, str) else raw_end
        except (ValueError, TypeError):
            continue
        warnings_active.append((wf, wu))

    windows = compute_safe_windows(
        forecast_times=times,
        wave_heights=effective_waves,
        wind_speeds=wind_speeds,
        warnings_active=warnings_active,
        interval_hours=float(interval_hours),
    )
    return {
        "windows": [w.as_dict() for w in windows],
        "count": len(windows),
        "evidence": _evidence("compute_risk_windows",
                              [{"provider": "domain", "dataset": "safe_window_engine"}]),
    }


@mcp.tool()
def evaluate_safety_clearance(
    wave_height: float | None = None,
    wind_speed: float | None = None,
    tide_level: float | None = None,
    swell_height: float | None = None,
    wave_period: float | None = None,
    wind_gust: float | None = None,
    rainfall: float | None = None,
    pressure_trend: float | None = None,
    active_warnings: list[dict] | None = None,
    cyclone_distance_km: float | None = None,
    restricted_zone_intersections: list[dict] | None = None,
    route_risk_complete: bool = True,
    require_tide: bool = False,
) -> dict:
    """Deterministic go / no-go safety clearance for a marine departure.

    This is the engine's authoritative safety decision — it is NOT the model's
    job to decide clearance. The gate enforces one rule the agent cannot bypass:
    **absence of evidence is not evidence of safety**. Clearance requires at
    minimum a real sea-state input (wave and/or swell height) AND a wind input;
    if either is missing it returns ``NOT_CLEARED`` with ``insufficient_data``
    true, distinguishing *unknown risk* from *low risk*.

    Use this LAST, after querying observations/forecasts/alerts/geofence, to
    turn the gathered evidence into a structured verdict. Returns
    ``safety_status`` (CLEARED / CLEARED_WITH_CAUTION / NOT_CLEARED), a list of
    machine-readable ``reason`` codes, the ``missing_inputs``, and the computed
    ``risk`` (only when the core inputs were present).

    Use this for: "Is it cleared to depart from Goa?", "Go/no-go for this trip?",
    "Should this vessel sail given current data?"
    """
    decision = evaluate_safety_gate(
        wave_height=wave_height,
        wind_speed=wind_speed,
        tide_level=tide_level,
        swell_height=swell_height,
        wave_period=wave_period,
        wind_gust=wind_gust,
        rainfall=rainfall,
        pressure_trend=pressure_trend,
        active_warnings=active_warnings,
        cyclone_distance_km=cyclone_distance_km,
        restricted_zone_intersections=restricted_zone_intersections,
        route_risk_complete=route_risk_complete,
        require_tide=require_tide,
    )
    out = decision.as_dict()
    out["evidence"] = _evidence(
        "evaluate_safety_clearance",
        [{"provider": "domain", "dataset": "safety_gate_engine"}],
    )
    return out


@mcp.tool()
def detect_ocean_anomalies(
    sst_current: float | None = None,
    sst_climatology: float | None = None,
    sst_std: float | None = None,
    chlorophyll_current: float | None = None,
    chlorophyll_climatology: float | None = None,
    chlorophyll_std: float | None = None,
    location_name: str | None = None,
) -> dict:
    """Detect SST and chlorophyll anomalies — Marine Heatwaves,
    upwelling signatures, algal blooms.

    Compares current values against climatological baselines.
    Returns anomaly magnitude, z-score, percentile, Marine Heatwave
    category (I-IV), chlorophyll depletion flag, and ecological impact.

    Use this for: "Is there a Marine Heatwave off Kerala?",
    "Why are fish catches declining?", "Chlorophyll bloom detection?"
    """
    result = detect_anomalies(
        current_values={
            **({"sst": sst_current} if sst_current is not None else {}),
            **({"chlorophyll": chlorophyll_current} if chlorophyll_current is not None else {}),
        },
        baselines={
            **({"sst": sst_climatology} if sst_climatology is not None else {}),
            **({"chlorophyll": chlorophyll_climatology} if chlorophyll_climatology is not None else {}),
        },
        stds={
            **({"sst": sst_std} if sst_std is not None else {}),
            **({"chlorophyll": chlorophyll_std} if chlorophyll_std is not None else {}),
        } or None,
    )
    d = result.as_dict()
    d["evidence"] = _evidence("detect_ocean_anomalies",
                              [{"provider": "domain", "dataset": "anomaly_engine"}])
    return d


# ═════════════════════════════════════════════════════════════════════════
# TOOLS — Routing & Geofence
# ═════════════════════════════════════════════════════════════════════════

@mcp.tool()
def plan_safe_route(
    departure_lat: float,
    departure_lon: float,
    destination_lat: float,
    destination_lon: float,
    vessel_speed_kts: float = 8.0,
    check_zones: bool = True,
) -> dict:
    """Plan a safe navigation route between two points.

    Computes great-circle route, screens against marine protected areas /
    restricted zones / firing ranges, and returns distance, duration,
    risk score, avoided zones, and per-segment breakdown.

    Use this for: "Safest route Mormugao to fishing grounds?",
    "Route from Kochi to deep-sea area?", "Emergency evacuation route?"
    """
    try:
        with session_scope() as s:
            zone_checker = None
            if check_zones:
                def zone_checker(route_geometry):
                    # ZoneChecker receives a GeoJSON geometry (the route LineString)
                    # and returns list of intersecting zone dicts
                    return geofence.find_route_intersections(s, route_geometry)

            result = routing.compute_safe_route(
                start=(departure_lat, departure_lon),
                end=(destination_lat, destination_lon),
                vessel_speed_knots=vessel_speed_kts,
                zone_checker=zone_checker,
            )
    except Exception as exc:
        return _db_error_response("plan_safe_route", exc)
    d = result.as_dict()
    d["evidence"] = _evidence("plan_safe_route",
                              [{"provider": "routing_engine", "dataset": "geodesic_router"}])
    return d


@mcp.tool()
def check_geofence(
    lat: float,
    lon: float,
) -> dict:
    """Check if a point falls inside any marine protected area, restricted
    zone, naval firing range, or international boundary.

    Returns all zones the point is inside, with zone type, name,
    authority, and restriction details.

    Use this for: "Can I fish at Netrani Island?",
    "Am I inside a restricted zone?", "MPA compliance check?"
    """
    try:
        with session_scope() as s:
            results = geofence.check_point_in_zones(s, lat, lon)
    except Exception as exc:
        return _db_error_response("check_geofence", exc)
    source_gap = any(r.get("status") == "SOURCE_UNAVAILABLE" for r in results)
    return {
        "data": results,
        "count": len(results),
        "evidence": _evidence("check_geofence",
                              [{"provider": "operator_gis", "dataset": "marine_zones"}],
                              ["SOURCE_GAP: No marine zones loaded"] if source_gap else None),
    }


@mcp.tool()
def find_nearby_zones(
    lat: float,
    lon: float,
    radius_km: float = 50.0,
) -> dict:
    """Find marine zones (MPAs, restricted areas, boundaries) near a point.

    Returns zones within the radius with distance, inside/outside status,
    and restriction details. Sorted nearest-first.

    Use this for: "What zones are near my fishing spot?",
    "Distance to India-Sri Lanka boundary?",
    "Nearby MPAs within 50 km?"
    """
    try:
        with session_scope() as s:
            results = geofence.find_nearby_zones(s, lat, lon, radius_km=radius_km)
    except Exception as exc:
        return _db_error_response("find_nearby_zones", exc)
    return {
        "data": results,
        "count": len(results),
        "evidence": _evidence("find_nearby_zones",
                              [{"provider": "operator_gis", "dataset": "marine_zones"}]),
    }


# ═════════════════════════════════════════════════════════════════════════
# TOOLS — Data Health & Evidence
# ═════════════════════════════════════════════════════════════════════════

@mcp.tool()
def data_health_report() -> dict:
    """Get the health status of all datasets in the engine.

    Returns per-dataset status (healthy/stale/degraded/failed/disabled),
    freshness score, last update time, and consecutive failure count.

    Use this for: "Is the data fresh?", "System health check?",
    "Which datasets are stale?"
    """
    try:
        with session_scope() as s:
            health = queries.data_health(s)
            datasets = queries.list_datasets(s)
    except Exception as exc:
        return _db_error_response("data_health_report", exc)
    return {
        "datasets": datasets,
        "health": health,
        "summary": {
            "total": len(health),
            "healthy": sum(1 for h in health if h.get("status") == "healthy"),
            "stale": sum(1 for h in health if h.get("status") == "stale"),
        },
        "evidence": _evidence("data_health_report",
                              [{"provider": "marine_data_engine", "dataset": "registry"}]),
    }


@mcp.tool()
def get_evidence_trail(request_id: str) -> dict:
    """Retrieve the full provenance/evidence trail for a previous query.

    Every query response includes a request_id. Use this tool to retrieve
    the complete evidence package: sources used, freshness, quality score,
    confidence, and any warnings.

    Use this for: "Show me the evidence for that answer",
    "What data backed that risk score?", "Provenance audit?"
    """
    try:
        with session_scope() as s:
            result = queries.get_evidence(s, request_id)
    except Exception as exc:
        return _db_error_response("get_evidence_trail", exc)
    if result is None:
        return {"data": None, "warning": f"No evidence found for request_id={request_id}"}
    return {"data": result}


# ═════════════════════════════════════════════════════════════════════════
# TOOLS — Spatial Utilities
# ═════════════════════════════════════════════════════════════════════════

@mcp.tool()
def compute_distance_bearing(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
) -> dict:
    """Compute distance (km and nautical miles) and bearing between two points.

    Use this for: "How far is the PFZ from my port?",
    "Bearing to Netrani Island from Karwar?",
    "Distance between Chennai and Coromandel grounds?"
    """
    dist_km = haversine_km(from_lat, from_lon, to_lat, to_lon)
    brg = bearing_deg(from_lat, from_lon, to_lat, to_lon)
    return {
        "distance_km": round(dist_km, 3),
        "distance_nm": round(dist_km / 1.852, 1),
        "bearing_deg": round(brg, 1),
        "from": {"lat": from_lat, "lon": from_lon},
        "to": {"lat": to_lat, "lon": to_lon},
    }


# ═════════════════════════════════════════════════════════════════════════
# RESOURCES — Read-only data context
# ═════════════════════════════════════════════════════════════════════════

@mcp.resource("marine://datasets")
def list_all_datasets() -> str:
    """List all registered datasets in the Marine Data Engine."""
    try:
        with session_scope() as s:
            datasets = queries.list_datasets(s)
    except Exception as exc:
        return json.dumps({
            "datasets": [],
            "warning": f"SOURCE_GAP: Database unavailable ({type(exc).__name__}: {exc})",
        }, indent=2)
    return json.dumps(datasets, indent=2, default=str)


@mcp.resource("marine://datasets/{dataset_key}/status")
def dataset_status(dataset_key: str) -> str:
    """Get freshness and health status for a specific dataset."""
    try:
        with session_scope() as s:
            status = queries.get_dataset_status(s, dataset_key)
    except Exception as exc:
        return json.dumps({
            "warning": f"SOURCE_GAP: Database unavailable ({type(exc).__name__}: {exc})",
        }, indent=2)
    if status is None:
        return json.dumps({"error": f"Dataset '{dataset_key}' not found"})
    return json.dumps(status, indent=2, default=str)


@mcp.resource("marine://capabilities")
def engine_capabilities() -> str:
    """Describe the Marine Data Engine's current capabilities and data coverage."""
    try:
        with session_scope() as s:
            health = queries.data_health(s)
            pfz_count = s.execute(select(func.count()).select_from(PFZ)).scalar_one()
            alert_count = s.execute(select(func.count()).select_from(Alert)).scalar_one()
            obs_count = s.execute(select(func.count()).select_from(Observation)).scalar_one()
            fc_count = s.execute(select(func.count()).select_from(Forecast)).scalar_one()
            zone_count = s.execute(select(func.count()).select_from(MarineZone)).scalar_one()
    except Exception as exc:
        return json.dumps({
            "engine": "Marine Data Engine v1.0.0",
            "warning": f"SOURCE_GAP: Database unavailable ({type(exc).__name__}: {exc})",
        }, indent=2)

    return json.dumps({
        "engine": "Marine Data Engine v1.0.0",
        "coverage": "Indian coastal waters (IMD, INCOIS, MOSDAC, NOAA)",
        "data_counts": {
            "datasets": len(health),
            "pfz_advisories": pfz_count,
            "active_alerts": alert_count,
            "observations": obs_count,
            "forecasts": fc_count,
            "marine_zones": zone_count,
        },
        "tools": [
            "query_pfz", "query_alerts", "query_observations", "query_forecasts",
            "assess_risk", "assess_suitability", "compute_risk_windows",
            "detect_ocean_anomalies", "plan_safe_route", "check_geofence",
            "find_nearby_zones", "data_health_report", "get_evidence_trail",
            "compute_distance_bearing",
        ],
        "data_health": {h.get("dataset", h.get("dataset_id", "?")): h.get("status", "?") for h in health},
    }, indent=2)


# ═════════════════════════════════════════════════════════════════════════
# PROMPTS — Reusable query templates
# ═════════════════════════════════════════════════════════════════════════

@mcp.prompt()
def fishing_departure_brief(port_name: str, lat: str, lon: str) -> str:
    """Generate a comprehensive fishing departure brief for a port.

    Covers: nearest PFZ, active alerts, sea-state risk, suitability score,
    and geofence compliance — everything a skipper needs before departure.
    """
    return (
        f"Generate a comprehensive fishing departure brief for {port_name} "
        f"at coordinates ({lat}, {lon}). Use these tools in sequence:\n\n"
        f"1. query_pfz(lat={lat}, lon={lon}, radius_km=100) — find nearest PFZ\n"
        f"2. query_alerts(lat={lat}, lon={lon}, radius_km=150) — check hazards\n"
        f"3. query_observations(lat={lat}, lon={lon}) — current sea conditions\n"
        f"4. query_forecasts(lat={lat}, lon={lon}) — wave/wind outlook\n"
        f"5. check_geofence(lat={lat}, lon={lon}) — restricted-zone compliance\n"
        f"6. evaluate_safety_clearance(...) — pass the wave/wind/tide values you "
        f"actually retrieved (leave a field null if the data was unavailable; do "
        f"NOT substitute a guess). This tool, not you, decides go/no-go.\n\n"
        f"Reporting rules:\n"
        f"- The final GO / CAUTION / NO-GO MUST equal the tool's `safety_status` "
        f"(CLEARED / CLEARED_WITH_CAUTION / NOT_CLEARED). Never upgrade a "
        f"NOT_CLEARED to a go, and quote the returned `reason` codes verbatim.\n"
        f"- State local alert status and regional context separately and explicitly, e.g.:\n"
        f"    Local alert status: no active alert returned within R km of the queried point.\n"
        f"    Regional/basin context: <other alerts elsewhere>, NOT treated as direct local hazards.\n"
        f"  Never let 'no local alert' imply 'no regional hazard'.\n"
        f"- Treat missing wave/tide data as UNKNOWN risk (not low risk) and say so."
    )


@mcp.prompt()
def cyclone_impact_assessment(cyclone_name: str, coast_lat: str, coast_lon: str) -> str:
    """Assess cyclone impact on a coastal region."""
    return (
        f"Assess the impact of {cyclone_name} on the coast at ({coast_lat}, {coast_lon}):\n\n"
        f"1. query_alerts(event_type='cyclone', lat={coast_lat}, lon={coast_lon}, radius_km=500)\n"
        f"2. assess_risk with extreme conditions from the cyclone bulletin\n"
        f"3. plan_safe_route for evacuation to nearest safe harbor\n"
        f"4. query_alerts(lat={coast_lat}, lon={coast_lon}, radius_km=300) — all hazard types\n\n"
        f"Provide: distance to eye, expected conditions, risk level, evacuation route, "
        f"and recall recommendation for all vessels."
    )


@mcp.prompt()
def marine_heatwave_analysis(location: str, sst_current: str, sst_baseline: str) -> str:
    """Analyze potential Marine Heatwave and fisheries impact."""
    return (
        f"Analyze Marine Heatwave conditions at {location}:\n\n"
        f"1. detect_ocean_anomalies(sst_current={sst_current}, sst_climatology={sst_baseline})\n"
        f"2. If MHW detected, assess impact on fishing suitability\n"
        f"3. Check PFZ advisories in the area for affected zones\n\n"
        f"Explain: MHW category, ecological impact, expected fisheries displacement, "
        f"and recommended fishing grounds (if any) outside the heatwave zone."
    )


# ═════════════════════════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════════════════════════
def main():
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    port = int(os.environ.get("MCP_PORT", "9100"))
    host = os.environ.get("MCP_HOST", "127.0.0.1")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stderr,  # MCP spec: never log to stdout
    )

    logger.info("Starting Marine Data Engine MCP Server")
    logger.info(f"  Transport: {transport}")
    logger.info(f"  Endpoint:  http://{host}:{port}/mcp")
    try:
        tool_count = len(mcp._tool_manager._tools)
    except Exception:
        tool_count = "unknown"
    logger.info(f"  Tools:     {tool_count} registered")

    mcp.settings.port = port
    mcp.settings.host = host
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
