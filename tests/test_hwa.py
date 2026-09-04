"""Tests for the INCOIS High Wave Alert adapter."""

from __future__ import annotations

import pytest

from marine_data_engine.sources.base import LiveSourceDisabledError
from marine_data_engine.sources.incois_hwa import (
    INCOISHighWaveFixtureAdapter,
    INCOISHighWaveLiveAdapter,
    parse_high_wave_alerts,
)


def test_parse_high_wave_alerts(hwa_json):
    alerts = parse_high_wave_alerts(hwa_json)
    assert len(alerts) == 2
    first = alerts[0]
    assert first.alert_uid == "HWA-2026-09-04-001"
    assert first.event_type == "high_wave"
    assert first.severity == "severe"
    assert first.geometry is not None
    assert first.geometry["type"] == "Polygon"
    assert first.effective_from is not None
    assert first.valid_until is not None
    assert first.description is not None
    assert first.provider == "INCOIS"
    assert first.source_dataset == "incois_hwa"


def test_fixture_adapter_fetch(hwa_json):
    result = INCOISHighWaveFixtureAdapter(hwa_json).fetch()
    assert result.raw.dataset == "incois_hwa"
    assert len(result.alerts) == 2
    assert all(a.event_type == "high_wave" for a in result.alerts)


def test_hwa_ingests_into_pipeline(db_session, raw_store, queue, hwa_json):
    """The parsed HWA alerts flow through the ingestion pipeline as alerts."""
    from marine_data_engine.services.ingestion import IngestionService
    from marine_data_engine.services.registry import seed_registry

    seed_registry(db_session)
    svc = IngestionService(db_session, raw_store, queue)
    summary = svc.ingest(INCOISHighWaveFixtureAdapter(hwa_json).fetch())
    db_session.commit()
    assert summary.accepted + summary.quarantined == 2


def test_live_adapter_disabled():
    with pytest.raises(LiveSourceDisabledError):
        INCOISHighWaveLiveAdapter().fetch()
