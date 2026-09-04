"""Shared pytest fixtures.

Tests are deterministic and offline: the database is SQLite in-memory with
StaticPool (so every connection shares the same DB), object storage is
in-process, live source connectors are disabled, and all data comes from
fixture files. No network access is performed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Configure environment BEFORE importing the app/config (settings are cached).
os.environ["MDE_DB_URL_OVERRIDE"] = "sqlite+pysqlite:///:memory:"
os.environ["MDE_S3_IN_MEMORY"] = "true"
os.environ["MDE_ENABLE_LIVE_SOURCES"] = "false"
os.environ["MDE_LOG_JSON"] = "false"

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def cap_xml() -> bytes:
    return (FIXTURES / "imd_cap_high_wave.xml").read_bytes()


@pytest.fixture()
def pfz_geojson() -> bytes:
    return (FIXTURES / "incois_pfz.geojson").read_bytes()


@pytest.fixture()
def erddap_catalog_json() -> bytes:
    return (FIXTURES / "incois_erddap_catalog.json").read_bytes()


@pytest.fixture()
def mosdac_search_json() -> bytes:
    return (FIXTURES / "mosdac_search_sst.json").read_bytes()


@pytest.fixture()
def buoy_html() -> bytes:
    return (FIXTURES / "imd_buoy_sample.html").read_bytes()


@pytest.fixture()
def cyclone_json() -> bytes:
    return (FIXTURES / "cyclone_advisory.json").read_bytes()


@pytest.fixture()
def tsunami_json() -> bytes:
    return (FIXTURES / "tsunami_bulletin.json").read_bytes()


@pytest.fixture()
def imd_nwp_json() -> bytes:
    return (FIXTURES / "imd_nwp_forecast.json").read_bytes()


@pytest.fixture()
def tide_json() -> bytes:
    return (FIXTURES / "incois_tide_obs.json").read_bytes()


@pytest.fixture()
def hwa_json() -> bytes:
    return (FIXTURES / "incois_hwa.json").read_bytes()


# A single shared engine with StaticPool guarantees all connections see the
# same in-memory SQLite database — including the TestClient running in a
# background thread.
_test_engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)


@event.listens_for(_test_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _):
    """Enable WAL and FK for SQLite test connections."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_TestSessionFactory = sessionmaker(bind=_test_engine, expire_on_commit=False, future=True)


@pytest.fixture()
def db_session():
    """A fresh in-memory database session.

    Tables are recreated per test so each test is isolated.
    """
    import marine_data_engine.db.models  # noqa: F401 — register models on Base.metadata
    from marine_data_engine.db.base import Base

    Base.metadata.drop_all(_test_engine)
    Base.metadata.create_all(_test_engine)
    session = _TestSessionFactory()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture()
def raw_store():
    from marine_data_engine.storage.raw_store import InMemoryRawStore

    return InMemoryRawStore(bucket="marine-raw-test")


@pytest.fixture()
def queue():
    from marine_data_engine.messaging.queue import InMemoryQueue

    return InMemoryQueue(backoff_base=0.0, backoff_max=0.0)


@pytest.fixture()
def seeded(db_session, raw_store, queue, cap_xml, pfz_geojson):
    """Seed the registry and ingest both fixtures. Returns the summaries."""
    from marine_data_engine.services.ingestion import IngestionService
    from marine_data_engine.services.registry import seed_registry
    from marine_data_engine.sources.imd_cap import IMDCapFixtureAdapter
    from marine_data_engine.sources.incois_pfz import INCOISPfzFixtureAdapter

    seed_registry(db_session)
    svc = IngestionService(db_session, raw_store, queue)
    cap_summary = svc.ingest(IMDCapFixtureAdapter(cap_xml).fetch())
    pfz_summary = svc.ingest(INCOISPfzFixtureAdapter(pfz_geojson).fetch())
    db_session.commit()
    return {"cap": cap_summary, "pfz": pfz_summary}


@pytest.fixture()
def client(seeded, db_session):
    """A TestClient that uses the same SQLite in-memory DB as ``seeded``.

    The app's ``get_db`` dependency is overridden to yield sessions from the
    shared StaticPool engine so the API sees the seeded tables and data.
    """
    from fastapi.testclient import TestClient

    from marine_data_engine.api.app import create_app, get_db

    app = create_app()

    def _override_get_db():
        s = _TestSessionFactory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
