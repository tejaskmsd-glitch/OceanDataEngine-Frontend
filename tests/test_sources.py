"""Tests for source adapters and parsers (offline, deterministic)."""

from __future__ import annotations

import pytest

from marine_data_engine.sources.base import LiveSourceDisabledError
from marine_data_engine.sources.imd_cap import (
    IMDCapFixtureAdapter,
    IMDCapLiveAdapter,
    cap_polygon_to_geojson,
    classify_event,
    parse_cap_document,
)
from marine_data_engine.sources.incois_erddap import (
    INCOISErddapCatalogAdapter,
    INCOISErddapLiveAdapter,
)
from marine_data_engine.sources.incois_erddap import (
    parse_catalog as parse_erddap_catalog,
)
from marine_data_engine.sources.incois_pfz import (
    INCOISPfzFixtureAdapter,
    INCOISPfzLiveAdapter,
    parse_pfz_featurecollection,
)
from marine_data_engine.sources.mosdac_search import (
    MOSDACSearchAdapter,
    MOSDACSearchFixtureAdapter,
)
from marine_data_engine.sources.mosdac_search import (
    parse_search_response as parse_mosdac_search,
)


def test_classify_event():
    assert classify_event("High Wave Warning") == "high_wave"
    assert classify_event("Cyclone Alert") == "cyclone"
    assert classify_event("Something Else") == "marine_hazard"
    assert classify_event(None) == "marine_hazard"


def test_cap_polygon_conversion_swaps_and_closes():
    geo = cap_polygon_to_geojson("15.6,73.6 15.6,74.0 15.1,74.0")
    assert geo["type"] == "Polygon"
    ring = geo["coordinates"][0]
    # lon,lat order and closed ring.
    assert ring[0] == [73.6, 15.6]
    assert ring[0] == ring[-1]


def test_parse_cap_document(cap_xml):
    alert = parse_cap_document(cap_xml, source_url="fixture://imd")
    assert alert.alert_uid == "IMD-CAP-FIXTURE-0001"
    assert alert.event_type == "high_wave"
    assert alert.severity == "severe"
    assert alert.issued_at is not None
    assert alert.valid_until is not None
    # Distinct timestamps preserved.
    assert alert.issued_at != alert.valid_until
    assert alert.geometry["type"] == "Polygon"


def test_imd_fixture_adapter_fetch(cap_xml):
    result = IMDCapFixtureAdapter(cap_xml).fetch()
    assert len(result.alerts) == 1
    assert result.raw.provider == "IMD"
    assert result.raw.media_type == "application/cap+xml"


def test_parse_pfz_featurecollection(pfz_geojson):
    parsed = parse_pfz_featurecollection(pfz_geojson, source_url="fixture://incois")
    assert len(parsed) == 2
    first = parsed[0]
    assert first.pfz_uid == "PFZ-GOA-2026-09-03-01"
    assert first.region == "Goa"
    assert first.geometry["type"] == "Polygon"
    assert first.valid_from is not None
    assert first.valid_until is not None


def test_pfz_fixture_adapter_fetch(pfz_geojson):
    result = INCOISPfzFixtureAdapter(pfz_geojson).fetch()
    assert len(result.pfz) == 2
    assert result.raw.provider == "INCOIS"


def test_live_connectors_disabled():
    with pytest.raises((LiveSourceDisabledError, NotImplementedError)):
        IMDCapLiveAdapter().fetch()
    with pytest.raises(LiveSourceDisabledError):
        INCOISPfzLiveAdapter().fetch()
    with pytest.raises(LiveSourceDisabledError):
        INCOISErddapLiveAdapter().fetch()
    with pytest.raises(LiveSourceDisabledError):
        INCOISErddapLiveAdapter().list_datasets()
    with pytest.raises(LiveSourceDisabledError):
        MOSDACSearchAdapter().fetch()
    with pytest.raises(LiveSourceDisabledError):
        MOSDACSearchAdapter().search("3RIMG_L2B_SST")


def test_erddap_catalog_parse(erddap_catalog_json):
    datasets = parse_erddap_catalog(erddap_catalog_json)
    ids = {d.dataset_id for d in datasets}
    assert ids == {"SST_Daily", "SSH_Daily", "Argo_Profiles", "Waves_Forecast"}
    sst = next(d for d in datasets if d.dataset_id == "SST_Daily")
    assert sst.title == "INCOIS Daily Sea Surface Temperature"
    assert sst.institution == "INCOIS"


def test_erddap_fixture_adapter(erddap_catalog_json):
    adapter = INCOISErddapCatalogAdapter(erddap_catalog_json)
    datasets = adapter.list_datasets()
    assert len(datasets) == 4
    result = adapter.fetch()
    assert result.raw.provider == "INCOIS"
    assert result.raw.media_type == "application/json"


def test_mosdac_search_parse(mosdac_search_json):
    entries = parse_mosdac_search(mosdac_search_json)
    assert len(entries) == 2
    sst = entries[0]
    assert sst.dataset_id == "3RIMG_L2B_SST"
    assert sst.title.startswith("INSAT-3D")
    assert "sea_surface_temperature" in sst.parameters


def test_mosdac_fixture_adapter(mosdac_search_json):
    adapter = MOSDACSearchFixtureAdapter(mosdac_search_json)
    entries = adapter.search("3RIMG_L2B_SST")
    assert len(entries) == 2
    result = adapter.fetch()
    assert result.raw.provider == "MOSDAC"
    assert result.raw.media_type == "application/json"
