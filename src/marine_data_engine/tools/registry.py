"""Tool registry — typed definitions with JSON schemas for MCP exposure."""
from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any


@dataclasses.dataclass(frozen=True)
class ToolDefinition:
    """A registered tool with its schema and callable."""

    name: str
    description: str
    input_schema: dict  # JSON Schema for inputs
    output_schema: dict  # JSON Schema for outputs
    handler: Callable  # The actual function to call
    category: str = "query"  # query | domain | admin
    requires_db: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "category": self.category,
            "requires_db": self.requires_db,
        }


TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def register_tool(defn: ToolDefinition) -> ToolDefinition:
    """Register a tool definition in the global registry."""
    TOOL_REGISTRY[defn.name] = defn
    return defn


def get_tool(name: str) -> ToolDefinition | None:
    return TOOL_REGISTRY.get(name)


def list_tools(category: str | None = None) -> list[dict]:
    tools: Any = TOOL_REGISTRY.values()
    if category:
        tools = [t for t in tools if t.category == category]
    return [t.to_dict() for t in tools]
