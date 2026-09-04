"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from . import models  # noqa: F401  (ensure models are registered on Base.metadata)
from .base import Base

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine."""
    global _engine
    if _engine is None:
        url = get_settings().database.url
        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(url, future=True, connect_args=connect_args)
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
