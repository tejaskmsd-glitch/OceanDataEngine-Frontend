"""Tool-registry layer for future MCP server exposure.

Each tool wraps an existing service/domain function with:
- A typed JSON Schema for inputs and outputs
- DB session lifecycle management
- Evidence enrichment (request_id, sources, freshness)
- Structured capability reporting (source_gap, blocked, etc.)

This module does NOT start an MCP server — it provides the typed callable
surface that an MCP transport will bind to.
"""
from .marine_tools import (
    tool_assess_risk,
    tool_assess_suitability,
    tool_check_geofence,
    tool_data_health,
    tool_find_nearby_zones,
    tool_get_evidence,
    tool_query_alerts,
    tool_query_forecasts,
    tool_query_observations,
    tool_query_pfz,
)
from .registry import TOOL_REGISTRY, ToolDefinition, get_tool, list_tools

__all__ = [
    "TOOL_REGISTRY",
    "ToolDefinition",
    "get_tool",
    "list_tools",
    "tool_query_pfz",
    "tool_query_alerts",
    "tool_query_observations",
    "tool_query_forecasts",
    "tool_assess_risk",
    "tool_assess_suitability",
    "tool_check_geofence",
    "tool_find_nearby_zones",
    "tool_data_health",
    "tool_get_evidence",
]
