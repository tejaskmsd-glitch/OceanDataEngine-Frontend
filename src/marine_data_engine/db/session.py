"""Database engine and session management.

PostgreSQL only — no silent fallbacks. If the database is unreachable, callers
get a clear exception. The MCP tool layer catches these and returns SOURCE_GAP
responses so the server stays up, but no data is silently written to a throwaway
store.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from . import models  # noqa: F401  (ensure models are registered on Base.metadata)
from .base import Base

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine (lazy, created once).

    Uses ``pool_pre_ping`` so stale connections are recycled transparently.
    If the database is unreachable at first use, the exception propagates —
    callers (MCP tools, API endpoints) are responsible for catching it and
    returning an appropriate error/degraded response.
    """
    global _engine
    if _engine is not None:
        return _engine

    url = get_settings().database.url
    connect_args: dict = {}
    if url.startswith("sqlite"):
        # SQLite is only used in tests via MDE_DB_URL_OVERRIDE.
        connect_args["check_same_thread"] = False

    extra: dict = {}
    if not url.startswith("sqlite"):
        extra = {
            "pool_pre_ping": True,
            "pool_size": 5,
            "max_overflow": 10,
            "pool_recycle": 1800,
        }

    _engine = create_engine(url, future=True, connect_args=connect_args, **extra)
    logger.info("Database engine created: %s", url.split("@")[-1] if "@" in url else url)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the session factory bound to the engine."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session scope: commit on success, rollback on error."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all() -> None:
    """Create all tables (used for tests and local bootstrap).

    In production, schema management uses migrations (and PostGIS/Timescale
    extensions). This helper is portable and safe on SQLite/PostgreSQL.
    """
    Base.metadata.create_all(get_engine())


def reset_engine() -> None:
    """Dispose and clear the cached engine/session factory (test helper)."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
