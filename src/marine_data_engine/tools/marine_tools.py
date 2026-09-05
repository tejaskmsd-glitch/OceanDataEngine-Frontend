"""Typed tool wrappers over existing query/domain services.

Each tool:
- takes a flat ``dict`` of parameters (matching its JSON Schema),
- manages its own DB session via :func:`session_scope` when DB-backed,
- calls an existing service/domain function (no logic duplication),
- returns a uniform ``{"data": ..., "evidence": {...}, "warnings": [...]}`` dict,
- registers itself in :data:`TOOL_REGISTRY`.

Tools never raise: failures are captured and reported in ``warnings`` with a
``capability_status`` of ``"error"`` or ``"source_gap"``. This is the typed
callable surface an MCP transport binds to — it does *not* start a server.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from ..db.session import session_scope
from ..domain import risk as risk_mod
from ..domain import suitability as suitability_mod
from ..services import geofence, queries
from .registry import ToolDefinition, register_tool

# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
_FLOAT = {"type": "number"}
_STR = {"type": "string"}
_BOOL = {"type": "boolean"}


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _capability_status(warnings: list[str]) -> str:
    """Derive a coarse capability status from accumulated warnings."""
    for w in warnings:
        text = str(w).lower()
        if "error" in text or "failed" in text:
            return "error"
    for w in warnings:
        text = str(w).lower()
        if "source_gap" in text or "source_unavailable" in text:
            return "source_gap"
    return "available"


def _evidence(tool_name: str, warnings: list[str], *, sources: list | None = None) -> dict:
    return {
        "request_id": str(uuid.uuid4()),
        "tool_name": tool_name,
        "capability_status": _capability_status(warnings),
        "sources": sources or [],
        "generated_at": _now_iso(),
    }


def _wrap(tool_name: str, data: Any, warnings: list[str], *, sources: list | None = None) -> dict:
    return {
        "data": data,
        "evidence": _evidence(tool_name, warnings, sources=sources),
        "warnings": warnings,
    }


def _source_gap_warnings(rows: Any) -> list[str]:
    """Extract SOURCE_GAP sentinel warnings emitted by geofence helpers."""
    warnings: list[str] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("source_gap") and row.get("warning"):
                warnings.append(str(row["warning"]))
    return warnings


# --------------------------------------------------------------------------- #
# Output schema fragment shared by the standard {data, evidence, warnings} shape
# --------------------------------------------------------------------------- #
def _standard_output_schema(data_schema: dict) -> dict:
    return {
        "type": "object",
        "properties": {
            "data": data_schema,
            "evidence": {
                "type": "object",
                "properties": {
                    "request_id": _STR,
                    "tool_name": _STR,
                    "capability_status": _STR,
                    "sources": {"type": "array"},
                    "generated_at": _STR,
                },
                "required": ["request_id", "tool_name", "capability_status", "generated_at"],
            },
            "warnings": {"type": "array", "items": _STR},
        },
        "required": ["data", "evidence", "warnings"],
    }


_LIST_OF_OBJECTS = {"type": "array", "items": {"type": "object"}}


# --------------------------------------------------------------------------- #
# 1. tool_query_pfz
# --------------------------------------------------------------------------- #
def tool_query_pfz(params: dict) -> dict:
    """Return PFZ advisories near a point."""
    tool = "tool_query_pfz"
    warnings: list[str] = []
    try:
        lat = float(params["lat"])
        lon = float(params["lon"])
        radius_km = float(params.get("radius_km", 50))
        include_expired = bool(params.get("include_expired", False))
        with session_scope() as session:
            data = queries.query_pfz(
                session,
                lat=lat,
                lon=lon,
                radius_km=radius_km,
                include_expired=include_expired,
            )
        if not data:
            warnings.append("no PFZ advisories found within radius")
        return _wrap(tool, data, warnings)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"error: {type(exc).__name__}: {exc}")
        return _wrap(tool, [], warnings)


# --------------------------------------------------------------------------- #
# 2. tool_query_alerts
# --------------------------------------------------------------------------- #
def tool_query_alerts(params: dict) -> dict:
    """Return active (or all) alerts, optionally within a radius."""
    tool = "tool_query_alerts"
    warnings: list[str] = []
    try:
        event_type = params.get("event_type")
        active_only = bool(params.get("active_only", True))
        lat = params.get("lat")
        lon = params.get("lon")
        radius_km = params.get("radius_km")
        with session_scope() as session:
            data = queries.query_alerts(
                session,
                lat=float(lat) if lat is not None else None,
                lon=float(lon) if lon is not None else None,
                radius_km=float(radius_km) if radius_km is not None else None,
                event_type=str(event_type) if event_type is not None else None,
                active_only=active_only,
            )
        if not data:
            warnings.append("no alerts matched the query")
        return _wrap(tool, data, warnings)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"error: {type(exc).__name__}: {exc}")
        return _wrap(tool, [], warnings)


# --------------------------------------------------------------------------- #
# Observation/forecast parameter resolution
# --------------------------------------------------------------------------- #
def _resolve_parameters(raw: Any) -> tuple[str, ...]:
    """Return the requested parameter tuple, defaulting to ocean+weather."""
    if raw:
        return tuple(str(p) for p in raw)
    return queries.OCEAN_PARAMETERS + queries.WEATHER_PARAMETERS


def _parse_at(raw: Any, warnings: list[str]) -> datetime | None:
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        warnings.append(f"could not parse 'at' timestamp: {raw!r}; ignoring")
        return None


# --------------------------------------------------------------------------- #
# 3. tool_query_observations
# --------------------------------------------------------------------------- #
def tool_query_observations(params: dict) -> dict:
    """Return observations for a parameter group near a point/time."""
    tool = "tool_query_observations"
    warnings: list[str] = []
    try:
        parameters = _resolve_parameters(params.get("parameters"))
        at = _parse_at(params.get("at"), warnings)
        lat = params.get("lat")
        lon = params.get("lon")
        radius_km = params.get("radius_km")
        with session_scope() as session:
            data = queries.query_observations(
                session,
                parameters=parameters,
                lat=float(lat) if lat is not None else None,
                lon=float(lon) if lon is not None else None,
                radius_km=float(radius_km) if radius_km is not None else None,
                at=at,
            )
        if not data:
            warnings.append("no observations matched the query")
        return _wrap(tool, data, warnings)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"error: {type(exc).__name__}: {exc}")
        return _wrap(tool, [], warnings)


# --------------------------------------------------------------------------- #
# 4. tool_query_forecasts
# --------------------------------------------------------------------------- #
def tool_query_forecasts(params: dict) -> dict:
    """Return forecast values for a parameter group near a point/time."""
    tool = "tool_query_forecasts"
    warnings: list[str] = []
    try:
        parameters = _resolve_parameters(params.get("parameters"))
        at = _parse_at(params.get("at"), warnings)
        lat = params.get("lat")
        lon = params.get("lon")
        radius_km = params.get("radius_km")
        with session_scope() as session:
            data = queries.query_forecasts(
                session,
                parameters=parameters,
                lat=float(lat) if lat is not None else None,
                lon=float(lon) if lon is not None else None,
                radius_km=float(radius_km) if radius_km is not None else None,
                at=at,
            )
        if not data:
            warnings.append("no forecasts matched the query")
        return _wrap(tool, data, warnings)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"error: {type(exc).__name__}: {exc}")
        return _wrap(tool, [], warnings)


# --------------------------------------------------------------------------- #
# 5. tool_assess_risk (pure domain — no DB)
# --------------------------------------------------------------------------- #
def tool_assess_risk(params: dict) -> dict:
    """Assess marine risk from environmental factors and hazards (pure)."""
    tool = "tool_assess_risk"
    warnings: list[str] = []
    try:
        thresholds = None
        vessel_type = params.get("vessel_type")
        if vessel_type:
            thresholds = risk_mod.RiskThresholds(vessel_type=str(vessel_type))
        assessment = risk_mod.assess_marine_risk(
            wave_height=params.get("wave_height_m"),
            wave_period=params.get("wave_period_s"),
            swell_height=params.get("swell_height_m"),
            wind_speed=params.get("wind_speed_ms"),
            wind_gust=params.get("gust_speed_ms"),
            rainfall=params.get("rainfall_mm_hr"),
            pressure=params.get("pressure_hpa"),
            pressure_trend=params.get("pressure_trend_hpa_3h"),
            active_warnings=params.get("active_warnings"),
            cyclone_distance_km=params.get("nearest_cyclone_km"),
            thresholds=thresholds,
        )
        result = assessment.as_dict()
        warnings.extend(result.get("warnings", []))
        return _wrap(tool, result, warnings)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"error: {type(exc).__name__}: {exc}")
        return _wrap(tool, None, warnings)


# --------------------------------------------------------------------------- #
# 6. tool_assess_suitability (pure domain — no DB)
# --------------------------------------------------------------------------- #
def tool_assess_suitability(params: dict) -> dict:
    """Assess fishing suitability from oceanographic + safety inputs (pure)."""
    tool = "tool_assess_suitability"
    warnings: list[str] = []
    try:
        result_obj = suitability_mod.assess_fishing_suitability(
            sst=params.get("sst"),
            chlorophyll=params.get("chlorophyll"),
            sst_anomaly=params.get("sst_anomaly"),
            chlorophyll_anomaly=params.get("chl_anomaly"),
            current_speed=params.get("current_speed_ms"),
            wave_height=params.get("wave_height_m"),
            wind_speed=params.get("wind_speed_ms"),
            pfz_distance_km=params.get("nearest_pfz_km"),
            ecological_hazards=params.get("ecological_hazards"),
            fishery_advisories=params.get("fishery_advisories"),
        )
        result = result_obj.as_dict()
        for neg in result.get("negative_drivers", []):
            if "source_gap" in str(neg).lower():
                warnings.append(str(neg))
        return _wrap(tool, result, warnings)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"error: {type(exc).__name__}: {exc}")
        return _wrap(tool, None, warnings)


# --------------------------------------------------------------------------- #
# 7. tool_check_geofence
# --------------------------------------------------------------------------- #
def tool_check_geofence(params: dict) -> dict:
    """Return marine zones whose polygon contains the point."""
    tool = "tool_check_geofence"
    warnings: list[str] = []
    try:
        lat = float(params["lat"])
        lon = float(params["lon"])
        with session_scope() as session:
            rows = geofence.check_point_in_zones(session, lat, lon)
        gap = _source_gap_warnings(rows)
        if gap:
            warnings.extend(gap)
            return _wrap(tool, [], warnings)
        if not rows:
            warnings.append("point is outside all loaded marine zones")
        return _wrap(tool, rows, warnings)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"error: {type(exc).__name__}: {exc}")
        return _wrap(tool, [], warnings)


# --------------------------------------------------------------------------- #
# 8. tool_find_nearby_zones
# --------------------------------------------------------------------------- #
def tool_find_nearby_zones(params: dict) -> dict:
    """Return marine zones within a radius of a point."""
    tool = "tool_find_nearby_zones"
    warnings: list[str] = []
    try:
        lat = float(params["lat"])
        lon = float(params["lon"])
        radius_km = float(params.get("radius_km", 50))
        with session_scope() as session:
            rows = geofence.find_nearby_zones(session, lat, lon, radius_km)
        gap = _source_gap_warnings(rows)
        if gap:
            warnings.extend(gap)
            return _wrap(tool, [], warnings)
        if not rows:
            warnings.append("no marine zones within radius")
        return _wrap(tool, rows, warnings)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"error: {type(exc).__name__}: {exc}")
        return _wrap(tool, [], warnings)


# --------------------------------------------------------------------------- #
# 9. tool_data_health
# --------------------------------------------------------------------------- #
def tool_data_health(params: dict) -> dict:
    """Return per-dataset freshness/health status."""
    tool = "tool_data_health"
    warnings: list[str] = []
    try:
        with session_scope() as session:
            data = queries.data_health(session)
        for row in data:
            status = str(row.get("status", "")).lower()
            if status in ("stale", "failing", "unavailable"):
                warnings.append(f"dataset {row.get('dataset')} is {status}")
        return _wrap(tool, data, warnings)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"error: {type(exc).__name__}: {exc}")
        return _wrap(tool, [], warnings)


# --------------------------------------------------------------------------- #
# 10. tool_get_evidence
# --------------------------------------------------------------------------- #
def tool_get_evidence(params: dict) -> dict:
    """Fetch a previously persisted evidence record by request_id."""
    tool = "tool_get_evidence"
    warnings: list[str] = []
    try:
        request_id = str(params["request_id"])
        with session_scope() as session:
            data = queries.get_evidence(session, request_id)
        if data is None:
            warnings.append(f"no evidence found for request_id {request_id}")
        return _wrap(tool, data, warnings)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"error: {type(exc).__name__}: {exc}")
        return _wrap(tool, None, warnings)


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
_SPATIAL_POINT_PROPS = {"lat": _FLOAT, "lon": _FLOAT}

register_tool(
    ToolDefinition(
        name="query_pfz",
        description="Return Potential Fishing Zone (PFZ) advisories within a radius of a point.",
        input_schema={
            "type": "object",
            "properties": {
                "lat": _FLOAT,
                "lon": _FLOAT,
                "radius_km": {**_FLOAT, "default": 50},
                "include_expired": {**_BOOL, "default": False},
            },
            "required": ["lat", "lon"],
        },
        output_schema=_standard_output_schema(_LIST_OF_OBJECTS),
        handler=tool_query_pfz,
        category="query",
        requires_db=True,
    )
)

register_tool(
    ToolDefinition(
        name="query_alerts",
        description="Return marine alerts/warnings, optionally filtered by event type and radius.",
        input_schema={
            "type": "object",
            "properties": {
                "event_type": _STR,
                "active_only": {**_BOOL, "default": True},
                "lat": _FLOAT,
                "lon": _FLOAT,
                "radius_km": _FLOAT,
            },
            "required": [],
        },
        output_schema=_standard_output_schema(_LIST_OF_OBJECTS),
        handler=tool_query_alerts,
        category="query",
        requires_db=True,
    )
)

register_tool(
    ToolDefinition(
        name="query_observations",
        description="Return observations for a parameter group near a point and/or time.",
        input_schema={
            "type": "object",
            "properties": {
                "parameters": {"type": "array", "items": _STR},
                "at": {**_STR, "description": "ISO 8601 datetime"},
                "lat": _FLOAT,
                "lon": _FLOAT,
                "radius_km": _FLOAT,
            },
            "required": [],
        },
        output_schema=_standard_output_schema(_LIST_OF_OBJECTS),
        handler=tool_query_observations,
        category="query",
        requires_db=True,
    )
)

register_tool(
    ToolDefinition(
        name="query_forecasts",
        description="Return forecast values for a parameter group near a point and/or time.",
        input_schema={
            "type": "object",
            "properties": {
                "parameters": {"type": "array", "items": _STR},
                "at": {**_STR, "description": "ISO 8601 datetime"},
                "lat": _FLOAT,
                "lon": _FLOAT,
                "radius_km": _FLOAT,
            },
            "required": [],
        },
        output_schema=_standard_output_schema(_LIST_OF_OBJECTS),
        handler=tool_query_forecasts,
        category="query",
        requires_db=True,
    )
)

register_tool(
    ToolDefinition(
        name="assess_risk",
        description="Assess marine risk (0-100) from environmental factors, warnings, and cyclone proximity.",
        input_schema={
            "type": "object",
            "properties": {
                "wave_height_m": _FLOAT,
                "wind_speed_ms": _FLOAT,
                "gust_speed_ms": _FLOAT,
                "swell_height_m": _FLOAT,
                "wave_period_s": _FLOAT,
                "rainfall_mm_hr": _FLOAT,
                "pressure_hpa": _FLOAT,
                "pressure_trend_hpa_3h": _FLOAT,
                "active_warnings": {"type": "array", "items": {"type": "object"}},
                "nearest_cyclone_km": _FLOAT,
                "vessel_type": _STR,
            },
            "required": [],
        },
        output_schema=_standard_output_schema({"type": "object"}),
        handler=tool_assess_risk,
        category="domain",
        requires_db=False,
    )
)

register_tool(
    ToolDefinition(
        name="assess_suitability",
        description="Assess fishing suitability (0-100) from oceanographic and safety inputs.",
        input_schema={
            "type": "object",
            "properties": {
                "sst": _FLOAT,
                "chlorophyll": _FLOAT,
                "current_speed_ms": _FLOAT,
                "wave_height_m": _FLOAT,
                "wind_speed_ms": _FLOAT,
                "nearest_pfz_km": _FLOAT,
                "sst_anomaly": _FLOAT,
                "chl_anomaly": _FLOAT,
                "ecological_hazards": {"type": "array", "items": _STR},
                "fishery_advisories": {"type": "array", "items": _STR},
            },
            "required": [],
        },
        output_schema=_standard_output_schema({"type": "object"}),
        handler=tool_assess_suitability,
        category="domain",
        requires_db=False,
    )
)

register_tool(
    ToolDefinition(
        name="check_geofence",
        description="Return marine zones whose polygon contains the given point.",
        input_schema={
            "type": "object",
            "properties": dict(_SPATIAL_POINT_PROPS),
            "required": ["lat", "lon"],
        },
        output_schema=_standard_output_schema(_LIST_OF_OBJECTS),
        handler=tool_check_geofence,
        category="query",
        requires_db=True,
    )
)

register_tool(
    ToolDefinition(
        name="find_nearby_zones",
        description="Return marine zones within a radius of the given point.",
        input_schema={
            "type": "object",
            "properties": {
                "lat": _FLOAT,
                "lon": _FLOAT,
                "radius_km": {**_FLOAT, "default": 50},
            },
            "required": ["lat", "lon"],
        },
        output_schema=_standard_output_schema(_LIST_OF_OBJECTS),
        handler=tool_find_nearby_zones,
        category="query",
        requires_db=True,
    )
)

register_tool(
    ToolDefinition(
        name="data_health",
        description="Return per-dataset freshness and health status.",
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=_standard_output_schema(_LIST_OF_OBJECTS),
        handler=tool_data_health,
        category="admin",
        requires_db=True,
    )
)

register_tool(
    ToolDefinition(
        name="get_evidence",
        description="Fetch a previously persisted evidence record by request_id.",
        input_schema={
            "type": "object",
            "properties": {"request_id": _STR},
            "required": ["request_id"],
        },
        output_schema=_standard_output_schema({"type": ["object", "null"]}),
        handler=tool_get_evidence,
        category="admin",
        requires_db=True,
    )
)
