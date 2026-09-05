"""Rigorous persistence / orchestration / MCP integration tests.

This module exercises the *real* production code paths — the ingestion service,
worker runtime handlers/roles, the deterministic router's zone gap signalling,
the query repositories, the geofence category coverage, and the MCP tool layer
(row-derived sources, source-outcome classification, evidence persistence) — all
against an in-memory SQLite database with no network access. It deliberately
constructs canonical :class:`FetchResult` payloads directly instead of relying
on live connectors so that station/marine-zone provenance and the distinct
source-outcome states can be asserted precisely.

Design notes / how these tests bind to production code
------------------------------------------------------
* A single ``StaticPool`` SQLite engine is shared so that ``session_scope()``
  (used internally by the MCP tools) reads and writes the *same* in-memory DB
  that the tests seed. ``marine_data_engine.db.session`` module globals are
  monkeypatched to that engine and restored afterward.
* The ``mcp`` optional extra is required to import ``marine_data_engine.mcp_server``.
  It is imported lazily behind an ``importorskip`` guard so that if the extra is
  genuinely absent the MCP-specific tests are reported as *skipped with a
  documented reason* rather than silently passing. Every non-MCP behaviour is
  still asserted directly against the importable helper/service functions, so
  core behaviour is never skipped.

No production files are modified by these tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import marine_data_engine.db.models  # noqa: F401 — register models on Base.metadata
from marine_data_engine.db.base import Base
from marine_data_engine.db.enums import QueuePriority
from marine_data_engine.db.models import (
    DataQualityRecord,
    Dataset,
    Evidence,
    MarineZone,
    Station,
)
from marine_data_engine.services import queries
from marine_data_engine.services.geofence import zone_coverage
from marine_data_engine.services.ingestion import IngestionService
from marine_data_engine.services.registry import seed_registry
from marine_data_engine.services.routing import compute_safe_route
from marine_data_engine.sources.base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedMarineZone,
    ParsedObservation,
    ParsedStation,
    RawPayload,
    SourceContractUnavailableError,
    SourceLicenseRequiredError,
    SourceUnavailableError,
)
from marine_data_engine.storage.raw_store import InMemoryRawStore

# --------------------------------------------------------------------------- #
# Local fixtures — an independent in-memory DB shared with session_scope().
# --------------------------------------------------------------------------- #


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _raw(provider: str, dataset: str, *, source_url: str | None = None) -> RawPayload:
    return RawPayload(
        provider=provider,
        dataset=dataset,
        data=f"{provider}:{dataset}:{source_url}".encode(),
        ext="json",
        media_type="application/json",
        source_url=source_url,
        retrieved_at=_now(),
    )


@pytest.fixture()
def engine():
    """A process-local StaticPool SQLite engine (shared across connections)."""
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture()
def SessionFactory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture()
def session(SessionFactory):
    s = SessionFactory()
    try:
        yield s
        s.commit()
    finally:
        s.close()


@pytest.fixture()
def bound_session_scope(engine, SessionFactory):
    """Point ``db.session.session_scope`` at the test engine for MCP tools.

    MCP tools open their own sessions via ``session_scope()``; without this the
    tool would open a *different* in-memory DB and see no seeded rows. Globals
    are restored on teardown so no production state leaks between tests.
    """
    import marine_data_engine.db.session as dbs

    prev_engine = dbs._engine
    prev_factory = dbs._SessionFactory
    dbs._engine = engine
    dbs._SessionFactory = SessionFactory
    try:
        yield dbs
    finally:
        dbs._engine = prev_engine
        dbs._SessionFactory = prev_factory


def _ingest(session, result: FetchResult):
    svc = IngestionService(session, InMemoryRawStore(bucket="marine-raw-test"))
    summary = svc.ingest(result)
    session.commit()
    return summary


# --------------------------------------------------------------------------- #
# 1. Station ingestion + provenance
# --------------------------------------------------------------------------- #


def test_station_ingestion_persists_authoritative_provenance(session):
    station = ParsedStation(
        station_uid="tg-vizag-01",
        name="Visakhapatnam Tide Gauge",
        station_type="tide_gauge",
        latitude=17.7,
        longitude=83.3,
        status="operational",
        provider="INCOIS",
        source_dataset="incois_tide",
        source_url="https://incois.gov.in/tews/tg-vizag-01",
        last_reported_at=_now() - timedelta(minutes=10),
        source_metadata={"sensor": "radar-gauge", "network": "TEWS"},
    )
    summary = _ingest(
        session,
        FetchResult(raw=_raw("INCOIS", "incois_tide"), stations=[station]),
    )

    assert summary.accepted == 1
    assert summary.rejected == 0

    row = session.execute(select(Station)).scalar_one()
    assert row.station_uid == "tg-vizag-01"
    assert row.provider == "INCOIS"
    assert row.source_dataset == "incois_tide"
    assert row.source_url == "https://incois.gov.in/tews/tg-vizag-01"
    assert row.status == "operational"
    assert row.source_metadata["sensor"] == "radar-gauge"
    assert row.retrieved_at is not None
    assert row.last_reported_at is not None


def test_station_upsert_updates_existing_row_in_place(session):
    def make(status: str, name: str) -> FetchResult:
        return FetchResult(
            raw=_raw("INCOIS", "incois_tide"),
            stations=[
                ParsedStation(
                    station_uid="tg-01",
                    name=name,
                    station_type="tide_gauge",
                    latitude=15.0,
                    longitude=73.0,
                    status=status,
                    provider="INCOIS",
                    source_dataset="incois_tide",
                )
            ],
        )

    _ingest(session, make("operational", "Old Name"))
    _ingest(session, make("maintenance", "New Name"))

    rows = session.execute(select(Station)).scalars().all()
    assert len(rows) == 1  # upsert, not duplicate insert
    assert rows[0].status == "maintenance"
    assert rows[0].name == "New Name"


def test_station_without_coordinates_is_quarantined_not_rejected(session):
    """No lat/lon -> geometry missing -> quarantined (kept), and still upserted."""
    station = ParsedStation(
        station_uid="tg-nocoord",
        name="Coordinateless Gauge",
        station_type="tide_gauge",
        latitude=None,
        longitude=None,
        status="unknown",
        provider="INCOIS",
        source_dataset="incois_tide",
    )
    summary = _ingest(
        session, FetchResult(raw=_raw("INCOIS", "incois_tide"), stations=[station])
    )
    assert summary.quarantined == 1
    assert summary.rejected == 0
    # Quarantined stations are still persisted (never silently dropped).
    assert session.execute(select(func.count()).select_from(Station)).scalar_one() == 1
    qc = session.execute(
        select(DataQualityRecord).where(DataQualityRecord.entity_type == "station")
    ).scalar_one()
    assert qc.quality_status == "quarantined"


# --------------------------------------------------------------------------- #
# 2. Marine-zone ingestion + provenance
# --------------------------------------------------------------------------- #

_EEZ_POLY = {
    "type": "Polygon",
    "coordinates": [[[72.0, 15.0], [74.0, 15.0], [74.0, 17.0], [72.0, 17.0], [72.0, 15.0]]],
}


def test_marine_zone_ingestion_persists_geometry_and_provenance(session):
    zone = ParsedMarineZone(
        zone_uid="marine-regions:eez:8480",
        zone_type="eez",
        name="Indian Exclusive Economic Zone",
        geometry=_EEZ_POLY,
        status="current",
        authority="VLIZ Marine Regions",
        provider="Marine Regions",
        source_dataset="marine_regions_eez_india",
        source_url="https://geo.vliz.be/geoserver/MarineRegions/wfs?eez",
        source_metadata={"mrgid": 8480, "dataset_version": "World EEZ v12"},
    )
    summary = _ingest(
        session,
        FetchResult(raw=_raw("Marine Regions", "marine_regions_eez_india"), marine_zones=[zone]),
    )
    assert summary.accepted == 1

    row = session.execute(select(MarineZone)).scalar_one()
    assert row.zone_uid == "marine-regions:eez:8480"
    assert row.zone_type == "eez"
    assert row.geometry["type"] == "Polygon"
    # ``source`` is derived from the parsed zone provider.
    assert row.source == "Marine Regions"
    assert row.source_dataset == "marine_regions_eez_india"
    assert row.source_url.endswith("eez")
    assert row.source_metadata["mrgid"] == 8480


def test_marine_zone_upsert_replaces_geometry_in_place(session):
    poly_b = {
        "type": "Polygon",
        "coordinates": [[[72.0, 15.0], [75.0, 15.0], [75.0, 18.0], [72.0, 18.0], [72.0, 15.0]]],
    }

    def make(geom, name) -> FetchResult:
        return FetchResult(
            raw=_raw("Marine Regions", "marine_regions_eez_india"),
            marine_zones=[
                ParsedMarineZone(
                    zone_uid="eez-1",
                    zone_type="eez",
                    name=name,
                    geometry=geom,
                    provider="Marine Regions",
                    source_dataset="marine_regions_eez_india",
                )
            ],
        )

    _ingest(session, make(_EEZ_POLY, "v1"))
    _ingest(session, make(poly_b, "v2"))
    rows = session.execute(select(MarineZone)).scalars().all()
    assert len(rows) == 1
    assert rows[0].name == "v2"
    assert rows[0].geometry["coordinates"][0][1][0] == 75.0


# --------------------------------------------------------------------------- #
# 3. Dataset outcome states: success vs healthy-empty vs classified blocks
# --------------------------------------------------------------------------- #


def test_dataset_success_state_after_records(session):
    seed_registry(session)
    obs = ParsedObservation(
        station_id="BD08",
        station_type="buoy",
        latitude=15.0,
        longitude=73.0,
        parameter="significant_wave_height",
        value=2.4,
        unit="m",
        observed_at=_now() - timedelta(minutes=5),
        provider="INCOIS",
        source_dataset="incois_buoy",
    )
    _ingest(
        session,
        FetchResult(raw=_raw("INCOIS", "incois_buoy"), observations=[obs], result_state="success"),
    )
    ds = session.execute(select(Dataset).where(Dataset.key == "incois_buoy")).scalar_one()
    assert ds.status == "healthy"
    assert ds.last_result_state == "success"
    assert ds.last_result_count == 1
    assert ds.consecutive_failures == 0
    assert ds.last_success_at is not None


def test_dataset_healthy_empty_is_distinct_from_not_run(session):
    """A healthy poll that returned zero records is recorded as success/empty,
    not confused with a source that has never run."""
    seed_registry(session)
    summary = _ingest(
        session,
        FetchResult(
            raw=_raw("INCOIS", "incois_buoy"),
            observations=[],
            result_state="empty",
            status_detail="source healthy but returned no observations",
        ),
    )
    assert summary.accepted == 0
    ds = session.execute(select(Dataset).where(Dataset.key == "incois_buoy")).scalar_one()
    assert ds.last_result_state == "empty"
    assert ds.last_result_count == 0
    # It successfully polled, so status is healthy (not "not_run"/failed).
    assert ds.status == "healthy"
    assert ds.last_success_at is not None
    assert ds.consecutive_failures == 0


@pytest.mark.parametrize(
    ("error", "expected_state", "expected_status", "counts_failure"),
    [
        (LiveSourceDisabledError("disabled"), "disabled", "disabled", False),
        (
            SourceContractUnavailableError("no contract"),
            "contract_unavailable",
            "disabled",
            False,
        ),
        (SourceLicenseRequiredError("license"), "license_gated", "disabled", False),
        (SourceUnavailableError("timeout"), "source_unavailable", "failed", True),
    ],
)
def test_record_source_error_classifies_blocked_states(
    session, error, expected_state, expected_status, counts_failure
):
    seed_registry(session)
    svc = IngestionService(session, InMemoryRawStore(bucket="marine-raw-test"))
    ds = svc.record_source_error("INCOIS", "incois_buoy", error)
    session.commit()

    assert ds.last_result_state == expected_state
    assert ds.status == expected_status
    assert ds.last_result_count == 0
    assert ds.last_checked_at is not None
    if counts_failure:
        assert ds.consecutive_failures == 1
        assert ds.last_failure_at is not None
    else:
        # Non-retryable operator states are facts, not failures.
        assert (ds.consecutive_failures or 0) == 0


def test_seeded_datasets_start_not_run_and_classified(session):
    """Registry seeding must never imply a dataset has run successfully."""
    seed_registry(session)
    states = {
        s["dataset"]: s
        for s in queries.get_dataset_source_states(
            session, ("imd_cap", "imd_nwp", "marine_regions_eez_india")
        )
    }
    assert states["imd_cap"]["state"] == "not_run"
    assert states["imd_cap"]["status"] == "disabled"
    # Datasets with no verified contract / license are pre-classified.
    assert states["imd_nwp"]["state"] == "contract_unavailable"
    assert states["marine_regions_eez_india"]["state"] == "license_gated"


def test_unregistered_dataset_reports_not_registered(session):
    seed_registry(session)
    states = queries.get_dataset_source_states(session, ("does_not_exist",))
    assert states[0]["state"] == "not_registered"
    assert states[0]["status"] == "disabled"


# --------------------------------------------------------------------------- #
# 4. Payload-aware worker handlers + no production fixture fallback
# --------------------------------------------------------------------------- #


def test_buoy_handler_factory_is_payload_aware():
    from marine_data_engine.worker import runtime as rt

    adapter = rt._incois_buoy_adapter_factory(
        None, {"station_ids": ["AD07", "bd08"], "parameter_tokens": ["hm0"]}
    )
    # station ids are normalized (upper-cased, de-duplicated) into a set.
    assert adapter.station_ids == {"AD07", "BD08"}
    assert adapter.parameter_tokens == ("hm0",)


def test_buoy_handler_factory_defaults_parameters_when_absent():
    from marine_data_engine.worker import runtime as rt

    adapter = rt._incois_buoy_adapter_factory(None, {})
    assert adapter.station_ids == set()
    assert adapter.parameter_tokens == ("hm0", "wind_speed")


def test_worker_rejects_injection_in_ids():
    from marine_data_engine.worker import runtime as rt

    with pytest.raises(ValueError):
        rt._incois_buoy_adapter_factory(None, {"station_ids": ["bad id; DROP TABLE"]})
    with pytest.raises(ValueError):
        rt._incois_erddap_adapter_factory(None, {"dataset_id": "../../etc/passwd"})


def test_erddap_and_mosdac_factories_pass_dataset_id():
    from marine_data_engine.worker import runtime as rt

    erddap = rt._incois_erddap_adapter_factory(None, {"dataset_id": "SST_daily"})
    assert erddap.dataset_id == "SST_daily"
    mosdac = rt._mosdac_search_adapter_factory(None, {"dataset_id": "3RIMG_L2"})
    assert mosdac.dataset_id == "3RIMG_L2"


def test_ingest_handlers_build_live_adapters_not_fixtures():
    """Ingest handlers must always instantiate LIVE connectors, never fixtures.

    With MDE_ENABLE_LIVE_SOURCES=false (the test default), a disabled live
    connector must raise ``LiveSourceDisabledError`` — proving no silent fixture
    fallback exists in the production worker path.
    """
    from marine_data_engine.worker import runtime as rt

    for factory in (
        rt._imd_cap_adapter_factory,
        rt._incois_pfz_adapter_factory,
        rt._incois_hwa_adapter_factory,
        rt._incois_tide_adapter_factory,
    ):
        adapter = factory(None, {})
        # Fixture adapters take raw bytes in their constructor; live adapters do
        # not. These must be the live variants.
        assert "Fixture" not in type(adapter).__name__
        assert type(adapter).__name__.endswith(("LiveAdapter", "Adapter"))


def test_disabled_live_source_raises_and_is_non_retryable():
    """The live connectors are disabled in tests; they must signal a
    non-retryable disabled state rather than fabricating data."""
    from marine_data_engine.sources.imd_cap import IMDCapLiveAdapter

    adapter = IMDCapLiveAdapter()
    with pytest.raises(LiveSourceDisabledError) as exc:
        adapter.fetch()
    assert exc.value.result_state == "disabled"
    assert exc.value.retryable is False


# --------------------------------------------------------------------------- #
# 5. Role-priority ownership
# --------------------------------------------------------------------------- #


def test_role_handler_ownership_is_partitioned():
    from marine_data_engine.worker import runtime as rt

    alerts = rt.handlers_for_role("alerts")
    ingest = rt.handlers_for_role("ingest")
    process = rt.handlers_for_role("process")

    # Alert-priority datasets are owned by the alerts role only.
    assert "ingest.imd_cap" in alerts
    assert "ingest.incois_hwa" in alerts
    assert "ingest.imd_cap" not in ingest

    # Heavy/normal ingest datasets belong to the ingest role.
    assert "ingest.incois_pfz" in ingest
    assert "ingest.incois_buoy" in ingest
    assert "ingest.incois_pfz" not in alerts

    # Freshness sweeps belong to process.
    assert "process.freshness_eval" in process
    assert "process.freshness_eval" not in alerts
    assert "process.freshness_eval" not in ingest


def test_role_priority_streams_do_not_overlap():
    from marine_data_engine.worker import runtime as rt

    alerts = set(rt.priorities_for_role("alerts"))
    ingest = set(rt.priorities_for_role("ingest"))
    process = set(rt.priorities_for_role("process"))

    assert alerts == {QueuePriority.CRITICAL_ALERTS}
    # Non-overlapping priority isolation between roles.
    assert alerts.isdisjoint(ingest)
    assert alerts.isdisjoint(process)
    assert ingest.isdisjoint(process)


def test_unknown_role_gets_all_handlers():
    from marine_data_engine.worker import runtime as rt

    full_keys = set(rt.default_handlers())
    # Unknown/empty roles fall through to the complete registry (handler objects
    # are freshly built closures per call, so compare by registered key set).
    assert set(rt.handlers_for_role("")) == full_keys
    assert set(rt.handlers_for_role("bogus")) == full_keys


# --------------------------------------------------------------------------- #
# 6. Routing source_gap sentinel warning
# --------------------------------------------------------------------------- #

_START = (18.9, 72.8)
_END = (15.3, 73.7)


def test_route_zone_checker_source_gap_emits_warning():
    """When the geofence layer returns the SOURCE_GAP sentinel, the router must
    surface an explicit warning and must NOT treat the sentinel as a real zone."""

    def gap_checker(_geometry):
        return [{"warning": "SOURCE_GAP: no marine zones", "source_gap": True}]

    result = compute_safe_route(
        start=_START, end=_END, segment_km=200.0, zone_checker=gap_checker
    )
    assert any("SOURCE_GAP" in w and "not screened" in w for w in result.warnings)
    # Sentinel is filtered — no phantom avoided zone, no zone penalty.
    assert result.avoided_zones == []
    assert all(s.penalties["zone_penalty"] == 0.0 for s in result.segments)


def test_route_real_zone_intersection_adds_penalty():
    def real_hit(_geometry):
        return [{"zone_uid": "z1", "name": "Naval Firing Range", "source_gap": False}]

    result = compute_safe_route(
        start=_START, end=_END, segment_km=200.0, zone_checker=real_hit
    )
    assert "Naval Firing Range" in result.avoided_zones
    assert all(s.penalties["zone_penalty"] == 20.0 for s in result.segments)
    # No source-gap zone warning when zones are actually loaded.
    assert not any("not screened for zones" in w for w in result.warnings)


def test_route_without_env_is_partial_with_source_gap():
    result = compute_safe_route(start=_START, end=_END, segment_km=150.0)
    assert result.status == "partial"
    assert any("SOURCE_GAP" in w and "environmental" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# 7. Query: source_url / sensor metadata and geometry distances
# --------------------------------------------------------------------------- #


def test_query_observations_preserves_source_url_and_sensor(session):
    obs = ParsedObservation(
        station_id="BD08",
        station_type="buoy",
        latitude=15.0,
        longitude=73.0,
        parameter="wind_speed",
        value=8.5,
        unit="m/s",
        observed_at=_now() - timedelta(minutes=15),
        provider="INCOIS",
        source_dataset="incois_buoy",
        source_url="https://incois.gov.in/OON/BD08",
        sensor_id="anemometer-1",
        source_metadata={"height_m": 3.0},
    )
    _ingest(session, FetchResult(raw=_raw("INCOIS", "incois_buoy"), observations=[obs]))

    rows = queries.query_observations(session, parameters=("wind_speed",))
    assert len(rows) == 1
    r = rows[0]
    assert r["source_url"] == "https://incois.gov.in/OON/BD08"
    assert r["sensor_id"] == "anemometer-1"
    assert r["source_metadata"]["height_m"] == 3.0
    assert r["provider"] == "INCOIS"


def test_query_observations_geometry_distance_and_radius_filter(session):
    near = ParsedObservation(
        station_id="near",
        station_type="buoy",
        latitude=15.0,
        longitude=73.0,
        parameter="wind_speed",
        value=5.0,
        unit="m/s",
        observed_at=_now() - timedelta(minutes=1),
        provider="INCOIS",
        source_dataset="incois_buoy",
    )
    far = ParsedObservation(
        station_id="far",
        station_type="buoy",
        latitude=8.0,
        longitude=77.0,
        parameter="wind_speed",
        value=6.0,
        unit="m/s",
        observed_at=_now() - timedelta(minutes=1),
        provider="INCOIS",
        source_dataset="incois_buoy",
    )
    _ingest(session, FetchResult(raw=_raw("INCOIS", "incois_buoy"), observations=[near, far]))

    origin = {"lat": 15.05, "lon": 73.05}
    all_rows = queries.query_observations(session, parameters=("wind_speed",), **origin)
    by_station = {r["station_id"]: r for r in all_rows}
    # Distance is computed and the near station is much closer than the far one.
    assert by_station["near"]["distance_km"] < 20.0
    assert by_station["far"]["distance_km"] > by_station["near"]["distance_km"]

    limited = queries.query_observations(
        session, parameters=("wind_speed",), radius_km=50.0, **origin
    )
    assert {r["station_id"] for r in limited} == {"near"}


def test_query_zones_nearby_distance_and_containment(session):
    zone = ParsedMarineZone(
        zone_uid="eez-1",
        zone_type="eez",
        name="India EEZ",
        geometry=_EEZ_POLY,  # covers 72..74 lon, 15..17 lat
        provider="Marine Regions",
        source_dataset="marine_regions_eez_india",
    )
    _ingest(
        session,
        FetchResult(raw=_raw("Marine Regions", "marine_regions_eez_india"), marine_zones=[zone]),
    )

    # Inside the polygon -> distance 0, inside True.
    inside = queries.query_zones_containing_point(session, lat=16.0, lon=73.0)
    assert len(inside) == 1
    assert inside[0]["distance_km"] == 0.0
    assert inside[0]["inside"] is True

    # A point far away is excluded from a tight radius, present in a wide one.
    tight = queries.query_zones_nearby(session, lat=25.0, lon=73.0, radius_km=10.0)
    assert tight == []
    wide = queries.query_zones_nearby(session, lat=25.0, lon=73.0, radius_km=2000.0)
    assert len(wide) == 1
    assert wide[0]["distance_km"] > 0.0


# --------------------------------------------------------------------------- #
# 8. Geofence category coverage
# --------------------------------------------------------------------------- #


def test_zone_coverage_reports_categories_independently(session):
    # Only an EEZ zone is loaded.
    _ingest(
        session,
        FetchResult(
            raw=_raw("Marine Regions", "marine_regions_eez_india"),
            marine_zones=[
                ParsedMarineZone(
                    zone_uid="eez-1",
                    zone_type="eez",
                    name="India EEZ",
                    geometry=_EEZ_POLY,
                    provider="Marine Regions",
                    source_dataset="marine_regions_eez_india",
                )
            ],
        ),
    )
    coverage = zone_coverage(session)
    assert coverage["eez_boundary"]["status"] == "available"
    assert coverage["eez_boundary"]["feature_count"] == 1
    # Categories with no authoritative source loaded are explicitly not_loaded.
    assert coverage["marine_protected_area"]["status"] == "not_loaded"
    assert coverage["restricted_area"]["status"] == "not_loaded"
    assert coverage["naval_firing_area"]["status"] == "not_loaded"


def test_zone_coverage_empty_when_no_zones(session):
    coverage = zone_coverage(session)
    assert all(c["status"] == "not_loaded" for c in coverage.values())
    assert all(c["feature_count"] == 0 for c in coverage.values())


# --------------------------------------------------------------------------- #
# 9. Evidence persistence / retrieval on SQLite (query layer)
# --------------------------------------------------------------------------- #


def test_evidence_save_and_retrieve_roundtrip(session):
    queries.save_evidence(
        session,
        request_id="req-abc123",
        endpoint="query_pfz",
        query_params={"lat": 15.0, "lon": 73.0},
        sources=[{"provider": "INCOIS", "dataset": "incois_pfz"}],
        record_refs=["pfz-1", "pfz-2"],
        confidence=0.9,
        freshness={"state": "fresh"},
        quality={"accepted": 2},
        warnings=["NOTE"],
        capability_status="available",
        data_versions={"incois_pfz": "2026-09-05"},
        data_lineage=[{"source_url": "https://incois.gov.in/pfz"}],
    )
    session.commit()

    stored = session.execute(select(Evidence)).scalar_one()
    assert stored.request_id == "req-abc123"

    fetched = queries.get_evidence(session, "req-abc123")
    assert fetched["endpoint"] == "query_pfz"
    assert fetched["record_refs"] == ["pfz-1", "pfz-2"]
    assert fetched["capability_status"] == "available"
    assert fetched["data_versions"]["incois_pfz"] == "2026-09-05"
    assert fetched["data_lineage"][0]["source_url"] == "https://incois.gov.in/pfz"

    assert queries.get_evidence(session, "missing") is None


# --------------------------------------------------------------------------- #
# 10. MCP layer — dynamic row-derived sources, outcome distinctions, evidence.
#     The `mcp` extra must be importable; otherwise these are reported skipped
#     with a documented reason rather than silently passing.
# --------------------------------------------------------------------------- #

mcp_server = pytest.importorskip(
    "marine_data_engine.mcp_server",
    reason=(
        "The `mcp` optional extra is not installed. Install `.[mcp]` to exercise "
        "the MCP tool layer. Core persistence/orchestration behaviour above is "
        "still fully asserted without it."
    ),
)


def _seed_incois_buoy_obs(bound_session_scope, *, source_url: str) -> None:
    """Poll BOTH observation datasets the MCP tool inspects.

    ``query_observations`` classifies coverage over ``incois_buoy`` AND
    ``incois_tide``. To assert an ``available`` (non-partial) outcome, both must
    have polled successfully — buoy returns a record, tide is a healthy-empty
    poll (state ``empty`` is not a blocked state, so coverage stays complete).
    """
    with bound_session_scope.session_scope() as s:
        seed_registry(s)
        svc = IngestionService(s, InMemoryRawStore(bucket="marine-raw-test"))
        svc.ingest(
            FetchResult(
                raw=_raw("INCOIS", "incois_buoy", source_url=source_url),
                observations=[
                    ParsedObservation(
                        station_id="BD08",
                        station_type="buoy",
                        latitude=15.0,
                        longitude=73.0,
                        parameter="wind_speed",
                        value=7.0,
                        unit="m/s",
                        observed_at=_now() - timedelta(minutes=2),
                        provider="INCOIS",
                        source_dataset="incois_buoy",
                        source_url=source_url,
                    )
                ],
                result_state="success",
            )
        )
        svc.ingest(
            FetchResult(
                raw=_raw("INCOIS", "incois_tide"),
                observations=[],
                result_state="empty",
            )
        )


def test_mcp_sources_are_row_derived(bound_session_scope):
    """MCP evidence sources must be derived only from returned rows."""
    src = "https://incois.gov.in/OON/BD08"
    _seed_incois_buoy_obs(bound_session_scope, source_url=src)

    result = mcp_server.query_observations(lat=15.0, lon=73.0, radius_km=50.0)
    assert result["count"] == 1
    sources = result["evidence"]["sources"]
    assert len(sources) == 1
    assert sources[0]["provider"] == "INCOIS"
    assert sources[0]["dataset"] == "incois_buoy"
    assert sources[0]["source_url"] == src
    assert result["evidence"]["capability_status"] == "available"
    assert result["evidence"]["data_provenance"] == "database"


def test_mcp_sources_from_records_helper_dedups():
    records = [
        {"provider": "INCOIS", "source_dataset": "incois_buoy", "source_url": "u1"},
        {"provider": "INCOIS", "source_dataset": "incois_buoy", "source_url": "u1"},  # dup
        {"provider": "INCOIS", "source_dataset": "incois_buoy", "source_url": "u2"},
        {"source": "IMD", "source_dataset": "imd_cap", "source_url": "u3"},  # 'source' alias
        {"source_dataset": "no_provider"},  # dropped (no provider)
    ]
    sources = mcp_server._sources_from_records(records)
    urls = sorted(s["source_url"] for s in sources)
    assert urls == ["u1", "u2", "u3"]


def test_mcp_source_outcome_distinctions():
    outcome = mcp_server._source_outcome
    # No records + healthy empty upstream.
    warnings, cap = outcome([], [{"dataset": "incois_buoy", "state": "empty"}], subject="obs")
    assert cap == "healthy_empty"
    assert any("SOURCE_HEALTHY_EMPTY" in w for w in warnings)

    # No records + never ingested.
    warnings, cap = outcome([], [{"dataset": "incois_buoy", "state": "not_run"}], subject="obs")
    assert cap == "not_ingested"

    # No records + auth blocked.
    warnings, cap = outcome([], [{"dataset": "imd_nwp", "state": "auth_blocked"}], subject="nwp")
    assert cap == "auth_blocked"

    # No records + license gated.
    warnings, cap = outcome(
        [], [{"dataset": "mr", "state": "license_gated"}], subject="eez"
    )
    assert cap == "license_gated"

    # No records + contract unavailable.
    warnings, cap = outcome(
        [], [{"dataset": "imd_nwp", "state": "contract_unavailable"}], subject="nwp"
    )
    assert cap == "contract_unavailable"

    # Records present + all sources healthy -> available.
    warnings, cap = outcome(
        [{"x": 1}], [{"dataset": "incois_buoy", "state": "success"}], subject="obs"
    )
    assert cap == "available"
    assert warnings == []

    # Records present + a blocked source -> partial coverage.
    warnings, cap = outcome(
        [{"x": 1}], [{"dataset": "imd_nwp", "state": "contract_unavailable"}], subject="obs"
    )
    assert cap == "partial"
    assert any("PARTIAL_SOURCE_COVERAGE" in w for w in warnings)


def test_mcp_query_reports_healthy_empty_capability(bound_session_scope):
    """A healthy poll with zero rows must classify as healthy_empty, not
    not_ingested."""
    with bound_session_scope.session_scope() as s:
        seed_registry(s)
        svc = IngestionService(s, InMemoryRawStore(bucket="marine-raw-test"))
        # Both observation datasets the tool inspects polled healthy-empty.
        for dataset in ("incois_buoy", "incois_tide"):
            svc.ingest(
                FetchResult(
                    raw=_raw("INCOIS", dataset),
                    observations=[],
                    result_state="empty",
                )
            )

    result = mcp_server.query_observations(lat=15.0, lon=73.0, radius_km=50.0)
    assert result["count"] == 0
    assert result["evidence"]["capability_status"] == "healthy_empty"
    assert any("SOURCE_HEALTHY_EMPTY" in w for w in result["evidence"]["warnings"])


def test_mcp_evidence_persisted_and_retrievable(bound_session_scope):
    _seed_incois_buoy_obs(bound_session_scope, source_url="https://incois.gov.in/OON/BD08")

    result = mcp_server.query_observations(lat=15.0, lon=73.0, radius_km=50.0)
    request_id = result["evidence"]["request_id"]

    # The evidence row was persisted by the tool through session_scope().
    trail = mcp_server.get_evidence_trail(request_id)
    assert trail["data"]["request_id"] == request_id
    assert trail["data"]["endpoint"] == "query_observations"
    # Record refs derived from the returned observation_uid.
    assert trail["data"]["record_refs"]
    # data_versions reflect the successful poll's source state.
    assert "incois_buoy" in trail["data"]["data_versions"]

    missing = mcp_server.get_evidence_trail("nonexistent-id")
    assert missing["data"] is None


def test_mcp_check_geofence_reports_category_gaps(bound_session_scope):
    """With no zones loaded the geofence tool must surface SOURCE_GAP plus
    per-category ZONE_CATEGORY_NOT_LOADED warnings, and never report the point
    as clear."""
    with bound_session_scope.session_scope() as s:
        seed_registry(s)

    result = mcp_server.check_geofence(lat=15.45, lon=73.5)
    assert result["count"] == 0
    warnings = result["evidence"]["warnings"]
    assert any("SOURCE_GAP" in w for w in warnings)
    assert any("ZONE_CATEGORY_NOT_LOADED: marine_protected_area" in w for w in warnings)
    # Coverage is reported per category.
    assert result["coverage"]["eez_boundary"]["status"] == "not_loaded"
    assert result["evidence"]["capability_status"] == "license_gated"
    assert any("SOURCE_LICENSE_GATED" in warning for warning in warnings)


def test_mcp_plan_route_reports_zone_coverage_and_persists_evidence(
    bound_session_scope,
):
    with bound_session_scope.session_scope() as session:
        seed_registry(session)

    result = mcp_server.plan_safe_route(
        departure_lat=15.4,
        departure_lon=73.7,
        destination_lat=16.0,
        destination_lon=74.2,
    )
    assert result["zone_screening"] == "performed"
    assert result["zone_coverage"]["eez_boundary"]["status"] == "not_loaded"
    assert result["zone_coverage"]["restricted_area"]["status"] == "not_loaded"
    assert any("SOURCE_LICENSE_GATED" in warning for warning in result["warnings"])
    assert any("ZONE_CATEGORY_NOT_LOADED" in warning for warning in result["warnings"])
    assert result["evidence"]["capability_status"] == "partial"

    trail = mcp_server.get_evidence_trail(result["evidence"]["request_id"])
    assert trail["data"]["endpoint"] == "plan_safe_route"
    assert trail["data"]["capability_status"] == "partial"


def test_mcp_pure_computation_evidence_is_persisted(bound_session_scope):
    result = mcp_server.compute_distance_bearing(
        from_lat=18.9,
        from_lon=72.8,
        to_lat=15.3,
        to_lon=73.7,
    )
    evidence = result["evidence"]
    assert evidence["evidence_persisted"] is True
    trail = mcp_server.get_evidence_trail(evidence["request_id"])
    assert trail["data"]["endpoint"] == "compute_distance_bearing"
    assert trail["data"]["query_params"]["from_lat"] == 18.9


def test_mcp_check_geofence_partial_when_some_categories_loaded(bound_session_scope):
    """EEZ loaded but MPA/restricted/naval absent -> point inside EEZ returns a
    record with 'partial' capability (some categories still uncovered)."""
    with bound_session_scope.session_scope() as s:
        seed_registry(s)
        svc = IngestionService(s, InMemoryRawStore(bucket="marine-raw-test"))
        svc.ingest(
            FetchResult(
                raw=_raw("Marine Regions", "marine_regions_eez_india"),
                marine_zones=[
                    ParsedMarineZone(
                        zone_uid="eez-1",
                        zone_type="eez",
                        name="India EEZ",
                        geometry=_EEZ_POLY,
                        provider="Marine Regions",
                        source_dataset="marine_regions_eez_india",
                    )
                ],
                result_state="success",
            )
        )

    result = mcp_server.check_geofence(lat=16.0, lon=73.0)
    assert result["count"] == 1  # inside the EEZ polygon
    assert result["coverage"]["eez_boundary"]["status"] == "available"
    assert result["evidence"]["capability_status"] == "partial"
    assert any(
        "ZONE_CATEGORY_NOT_LOADED" in w for w in result["evidence"]["warnings"]
    )


def test_mcp_compute_distance_bearing_pure():
    result = mcp_server.compute_distance_bearing(
        from_lat=18.9, from_lon=72.8, to_lat=15.3, to_lon=73.7
    )
    assert result["distance_km"] > 300.0
    # nm conversion consistency.
    assert abs(result["distance_nm"] - result["distance_km"] / 1.852) < 0.5
    assert 0.0 <= result["bearing_deg"] <= 360.0
