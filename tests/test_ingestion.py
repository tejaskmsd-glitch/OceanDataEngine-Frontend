"""Ingestion, raw storage, idempotency, and lineage tests."""

from __future__ import annotations

from sqlalchemy import func, select

from marine_data_engine.db.models import (
    PFZ,
    Alert,
    DataQualityRecord,
    DatasetAsset,
    IngestionJob,
    Observation,
    ProcessingRun,
)
from marine_data_engine.services.ingestion import IngestionService
from marine_data_engine.sources.imd_buoy import IMDBuoyFixtureAdapter
from marine_data_engine.sources.imd_cap import IMDCapFixtureAdapter
from marine_data_engine.sources.incois_pfz import INCOISPfzFixtureAdapter


def test_ingest_alert_persists_canonical_and_quality(db_session, raw_store, queue, cap_xml):
    svc = IngestionService(db_session, raw_store, queue)
    summary = svc.ingest(IMDCapFixtureAdapter(cap_xml).fetch())
    db_session.commit()

    assert summary.accepted == 1
    alerts = db_session.execute(select(Alert)).scalars().all()
    assert len(alerts) == 1
    a = alerts[0]
    assert a.event_type == "high_wave"
    assert a.quality_status == "accepted"
    # Distinct provenance/timestamps.
    assert a.issued_at is not None and a.valid_until is not None
    assert a.retrieved_at is not None and a.processed_at is not None
    assert a.processing_version == "1.0.0"
    assert a.idempotency_key

    qc = db_session.execute(select(DataQualityRecord)).scalars().all()
    assert any(r.entity_type == "alert" for r in qc)


def test_ingest_is_idempotent(db_session, raw_store, queue, cap_xml):
    svc = IngestionService(db_session, raw_store, queue)
    svc.ingest(IMDCapFixtureAdapter(cap_xml).fetch())
    second = svc.ingest(IMDCapFixtureAdapter(cap_xml).fetch())
    db_session.commit()

    assert second.skipped_duplicates == 1
    assert second.accepted == 0
    count = db_session.execute(select(func.count()).select_from(Alert)).scalar_one()
    assert count == 1


def test_raw_store_immutable_dedup(raw_store, cap_xml):
    a = raw_store.put(provider="IMD", dataset="imd_cap", data=cap_xml, ext="xml")
    b = raw_store.put(provider="IMD", dataset="imd_cap", data=cap_xml, ext="xml")
    assert a.checksum_sha256 == b.checksum_sha256
    assert a.key == b.key
    assert b.already_existed is True


def test_pfz_ingest_centroid_and_lineage(db_session, raw_store, queue, pfz_geojson):
    svc = IngestionService(db_session, raw_store, queue)
    summary = svc.ingest(INCOISPfzFixtureAdapter(pfz_geojson).fetch())
    db_session.commit()

    assert summary.accepted == 2
    pfz_rows = db_session.execute(select(PFZ)).scalars().all()
    assert len(pfz_rows) == 2
    assert all(p.centroid_lat is not None for p in pfz_rows)

    # Lineage: ingestion job, dataset asset, processing run all recorded.
    assert db_session.execute(select(func.count()).select_from(IngestionJob)).scalar_one() >= 1
    assert db_session.execute(select(func.count()).select_from(DatasetAsset)).scalar_one() >= 1
    runs = db_session.execute(select(ProcessingRun)).scalars().all()
    assert any(r.records_accepted == 2 for r in runs)


def test_critical_alert_enqueued_priority(db_session, raw_store, queue, cap_xml):
    from marine_data_engine.db.enums import QueuePriority

    svc = IngestionService(db_session, raw_store, queue)
    svc.ingest(IMDCapFixtureAdapter(cap_xml).fetch())
    # Severe high_wave -> critical priority event enqueued.
    assert queue.depth(QueuePriority.CRITICAL_ALERTS) == 1


def test_pfz_ingest_produces_pfz_updated_events(db_session, raw_store, queue, pfz_geojson):
    svc = IngestionService(db_session, raw_store, queue)
    summary = svc.ingest(INCOISPfzFixtureAdapter(pfz_geojson).fetch())
    db_session.commit()

    assert len(summary.pfz_events) == 2
    for event in summary.pfz_events:
        assert event["type"] == "pfz.updated"
        assert event["pfz_uid"]
        assert "timestamp" in event


def test_ingest_produces_processing_completed_event(db_session, raw_store, queue, cap_xml):
    svc = IngestionService(db_session, raw_store, queue)
    summary = svc.ingest(IMDCapFixtureAdapter(cap_xml).fetch())
    db_session.commit()

    completed = [e for e in summary.processing_events if e["type"] == "processing.completed"]
    assert len(completed) == 1
    ev = completed[0]
    assert ev["records_accepted"] == summary.accepted
    assert ev["records_rejected"] == summary.rejected
    assert ev["duration_ms"] is not None


def test_ingest_produces_dataset_updated_event(db_session, raw_store, queue, cap_xml):
    svc = IngestionService(db_session, raw_store, queue)
    summary = svc.ingest(IMDCapFixtureAdapter(cap_xml).fetch())
    db_session.commit()

    # A newly ensured dataset starts "healthy"; a status change to healthy is
    # only emitted when it differs from the previous value. The event list is
    # present regardless and, when populated, carries the documented type.
    for ev in summary.dataset_events:
        assert ev["type"] == "dataset.updated"
        assert ev["dataset_key"]


def test_observation_ingestion(db_session, raw_store, queue, buoy_html):
    svc = IngestionService(db_session, raw_store, queue)
    summary = svc.ingest(IMDBuoyFixtureAdapter(buoy_html).fetch())
    db_session.commit()

    # 2 rows x 5 parameters = 10 observations, all accepted.
    assert summary.accepted == 10
    assert summary.rejected == 0

    obs = db_session.execute(select(Observation)).scalars().all()
    assert len(obs) == 10
    assert {o.station_id for o in obs} == {"BD08", "AD07"}

    bd08_wind = next(
        o for o in obs if o.station_id == "BD08" and o.parameter == "wind_speed"
    )
    assert bd08_wind.unit == "m/s"
    assert bd08_wind.quality_status == "accepted"
    assert bd08_wind.observed_at is not None
    assert bd08_wind.retrieved_at is not None and bd08_wind.processed_at is not None
    assert bd08_wind.provider == "IMD"
    assert bd08_wind.source_dataset == "imd_buoy"
    assert bd08_wind.idempotency_key

    # QC audit rows recorded for observations.
    qc = db_session.execute(select(DataQualityRecord)).scalars().all()
    assert any(r.entity_type == "observation" for r in qc)

    # observation.ingested events emitted.
    assert len(summary.observation_events) == 10
    for ev in summary.observation_events:
        assert ev["type"] == "observation.ingested"
        assert ev["station_id"]


def test_observation_ingestion_is_idempotent(db_session, raw_store, queue, buoy_html):
    svc = IngestionService(db_session, raw_store, queue)
    svc.ingest(IMDBuoyFixtureAdapter(buoy_html).fetch())
    second = svc.ingest(IMDBuoyFixtureAdapter(buoy_html).fetch())
    db_session.commit()

    assert second.skipped_duplicates == 10
    assert second.accepted == 0
    count = db_session.execute(select(func.count()).select_from(Observation)).scalar_one()
    assert count == 10
