"""SQLAlchemy declarative base and portable column helpers.

Persistence targets PostgreSQL + PostGIS + TimescaleDB in production. To keep
tests deterministic and dependency-light we use portable column types:

- Geometry is stored as canonical GeoJSON text (``GeometryJSON``) plus an
  optional envelope bbox for coarse spatial filtering. In production a
  migration promotes these to PostGIS ``geometry(Geometry, 4326)`` columns and
  GIST indexes; the ORM attribute name and canonical GeoJSON contract stay the
  same so services and schemas are unaffected.
- Timestamps are timezone-aware UTC (``DateTime(timezone=True)``).
- JSON payloads use the portable ``JSON`` type.

The ORM is an internal implementation detail and is never returned from the
API; explicit Pydantic response schemas are used at the boundary.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Text, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Declarative base for all canonical models."""

    type_annotation_map = {dict: JSON, list: JSON}


class GeometryJSON(TypeDecorator):
    """Store a GeoJSON geometry dict as text.

    The canonical contract is always a GeoJSON geometry object (WGS84 /
    EPSG:4326). This decorator is the portable stand-in for a PostGIS geometry
    column; production migrations replace it without changing the Python API.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            # Assume already-serialized GeoJSON.
            return value
        return json.dumps(value, separators=(",", ":"))

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return json.loads(value)


def utcnow() -> datetime:
    """Return a timezone-aware UTC now (single source of truth)."""
    return datetime.now(tz=UTC)


def ts_column(**kwargs: Any):
    """Timezone-aware timestamp column helper."""
    return mapped_column(DateTime(timezone=True), **kwargs)
