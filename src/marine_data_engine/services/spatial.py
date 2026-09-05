"""PostGIS-aware spatial query helpers with a portable fallback contract.

This module provides an *optional* optimized path for the query/geofence
services. When the active database is PostgreSQL (assumed to carry the PostGIS
extension in this platform, per the deployment described in the README/migrations),
callers can push spatial predicates down into SQL via ``ST_DWithin`` /
``ST_Distance`` / ``ST_Contains`` instead of loading every row and filtering in
Python with Shapely.

Dual-path design
----------------
* PostGIS path (production PostgreSQL): build SQL filter/expression clauses using
  :func:`sqlalchemy.text` with **bound parameters** (``:lat``, ``:lon``,
  ``:radius_m``) — never string formatting — so the values are safely escaped by
  the driver. The spatial columns are the native PostGIS geometry columns that
  production migrations install: a ``location`` point column on the
  observation/forecast tables, or a ``geometry`` polygon column on the
  alert/advisory/pfz/marine_zone tables.
* Fallback path (SQLite / tests / any non-PostgreSQL dialect): callers keep their
  existing Shapely + haversine logic untouched. :func:`is_postgis` returns
  ``False`` so the optimized branch is never taken.

The helpers here only *construct* clauses; they do not decide which path to take.
Callers gate on :func:`is_postgis` and choose the branch. This keeps the Shapely
fallback path completely intact for SQLite/test compatibility.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, literal_column
from sqlalchemy.orm import Session
from sqlalchemy.types import UserDefinedType

# WGS84 SRID used across the canonical schema (EPSG:4326).
_SRID = 4326
# ST_DWithin on geography measures in metres; radius_km is converted at bind time.
_KM_TO_M = 1000.0


class _Geography(UserDefinedType):
    """Minimal PostGIS ``geography`` type for CAST(... AS geography).

    Used only to render metre-accurate ``ST_DWithin`` / ``ST_Distance`` on the
    geography spheroid. Never instantiated against SQLite (the PostGIS branch is
    gated behind :func:`is_postgis`).
    """

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:  # noqa: D401
        return "geography"


_GEOGRAPHY = _Geography()

# Cache of engine identity -> bool (is this engine PostgreSQL/PostGIS?).
# Keyed by id(engine) so distinct engines (e.g. a test SQLite engine and a
# production PostgreSQL engine) are tracked independently within a process.
_postgis_cache: dict[int, bool] = {}


def is_postgis(session: Session) -> bool:
    """Return True when the session's backend is PostgreSQL (PostGIS assumed).

    The result is cached per engine so repeated calls on hot query paths do not
    re-inspect the dialect. On SQLite (tests) and any non-PostgreSQL dialect this
    returns ``False``, which keeps callers on their portable Shapely fallback.
    """
    bind = session.get_bind()
    engine = getattr(bind, "engine", bind)
    key = id(engine)
    cached = _postgis_cache.get(key)
    if cached is not None:
        return cached
    dialect_name = getattr(getattr(engine, "dialect", None), "name", "") or ""
    result = dialect_name.startswith("postgresql")
    _postgis_cache[key] = result
    return result


# Backwards/forwards-compatible alias matching the task's requested name.
def is_postgis_available(session: Session) -> bool:
    """Alias for :func:`is_postgis` (checks PostgreSQL+PostGIS availability)."""
    return is_postgis(session)


def _geom_column_name(model_class: Any, geom_col: str | None = None) -> str:
    """Pick the spatial column name for a model.

    If ``geom_col`` is given it is used verbatim (caller knows the deployment
    column, e.g. observation/forecast get a native point ``location`` column in
    PostGIS even though the portable ORM exposes ``latitude``/``longitude``).
    Otherwise prefers a native point ``location`` column when the model declares
    one; else falls back to the polygon ``geometry`` column
    (alert/advisory/pfz/marine_zone). The name is only ever used to build a
    ``text()`` clause referencing a real PostGIS column, never interpolated with
    user data.
    """
    if geom_col is not None:
        return geom_col
    if hasattr(model_class, "location"):
        return "location"
    return "geometry"


def _geom_col(model_class: Any, geom_col: str | None = None):
    """Return a SQLAlchemy column expression for the model's spatial column.

    ``literal_column`` references a real, internal PostGIS column identifier
    (``location`` / ``geometry``) — never user-supplied data. See
    :func:`_geom_column_name` for how the name is chosen.
    """
    return literal_column(_geom_column_name(model_class, geom_col))


def _point(lat: float, lon: float):
    """Build the query point as a PostGIS geometry (SRID 4326).

    ``lat``/``lon`` are passed as **bound parameters** through ``func`` (no
    string formatting), so the driver escapes them safely.
    """
    # func.ST_MakePoint(lon, lat) binds lon/lat as parameters.
    return func.ST_SetSRID(func.ST_MakePoint(lon, lat), _SRID)


def st_dwithin_filter(
    model_class: Any, lat: float, lon: float, radius_km: float, geom_col: str | None = None
):
    """Return a PostGIS ``ST_DWithin`` filter clause for a radius search.

    Emits ``ST_DWithin(<col>::geography, <point>::geography, :radius_m)`` so the
    distance threshold is measured in metres on the WGS84 spheroid. ``<col>`` is
    ``geom_col`` when supplied, else the model's ``location`` point column when
    present, else its ``geometry`` column. Coordinates and the radius are passed
    as bound parameters (no string formatting).

    Only meaningful when :func:`is_postgis` is True; callers must keep their
    Shapely fallback for non-PostgreSQL backends.
    """
    col = _geom_col(model_class, geom_col)
    return func.ST_DWithin(
        func.cast(col, _GEOGRAPHY),
        func.cast(_point(lat, lon), _GEOGRAPHY),
        radius_km * _KM_TO_M,
    )


def st_distance_km(model_class: Any, lat: float, lon: float, geom_col: str | None = None):
    """Return a SQL expression giving distance (km) from the point to each row.

    Uses ``ST_Distance(<col>::geography, <point>::geography) / 1000.0`` (metres
    -> kilometres). Returns a composable/labelable SQLAlchemy expression suitable
    for a SELECT column or ORDER BY. Coordinates are bound parameters.

    Only meaningful when :func:`is_postgis` is True.
    """
    col = _geom_col(model_class, geom_col)
    return (
        func.ST_Distance(func.cast(col, _GEOGRAPHY), func.cast(_point(lat, lon), _GEOGRAPHY))
        / _KM_TO_M
    )


def st_contains_filter(model_class: Any, lat: float, lon: float):
    """Return a PostGIS point-in-polygon expression.

    Emits ``ST_Contains(<col>, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))`` so
    rows whose polygon contains the query point match. ``<col>`` is the model's
    ``geometry`` (polygon) column when present, else ``location``. Returns a
    composable/labelable expression (usable in ``.where()`` and as a labeled
    SELECT column). Coordinates are bound parameters.

    Only meaningful when :func:`is_postgis` is True.
    """
    # For containment we prefer a polygon column; models with only a point
    # `location` column would not contain a point, but we still honour the
    # generic column selection for symmetry.
    name = "geometry" if hasattr(model_class, "geometry") else _geom_column_name(model_class)
    col = literal_column(name)
    return func.ST_Contains(col, _point(lat, lon))


def st_intersects_filter(model_class: Any, geojson: dict):
    """Return a PostGIS ``ST_Intersects`` filter expression against a GeoJSON probe.

    Emits ``ST_Intersects(<col>, ST_SetSRID(ST_GeomFromGeoJSON(:probe), 4326))``.
    The probe geometry is passed as a bound JSON string parameter. ``<col>`` is
    the model's ``geometry`` column when present.

    Only meaningful when :func:`is_postgis` is True.
    """
    import json

    name = "geometry" if hasattr(model_class, "geometry") else _geom_column_name(model_class)
    col = literal_column(name)
    probe_json = json.dumps(geojson, separators=(",", ":"))
    # probe_json is bound as a parameter by func.ST_GeomFromGeoJSON.
    return func.ST_Intersects(col, func.ST_SetSRID(func.ST_GeomFromGeoJSON(probe_json), _SRID))


def reset_postgis_cache() -> None:
    """Clear the cached dialect detection (test helper; mirrors reset_engine)."""
    _postgis_cache.clear()
