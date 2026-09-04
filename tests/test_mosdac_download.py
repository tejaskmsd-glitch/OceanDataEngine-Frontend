"""Tests for the MOSDAC download connector (fixture + credential gating)."""

from __future__ import annotations

import pytest

from marine_data_engine.sources.base import (
    AuthenticationRequiredError,
    LiveSourceDisabledError,
)
from marine_data_engine.sources.mosdac_download import (
    MOSDACDownloadAdapter,
    MOSDACDownloadFixtureAdapter,
)


def test_fixture_adapter_downloads_bytes():
    payload = b"NETCDF-FIXTURE-BYTES"
    adapter = MOSDACDownloadFixtureAdapter(payload)

    result = adapter.fetch("record-1")

    assert result.raw.provider == "MOSDAC"
    assert result.raw.dataset == "mosdac_download"
    assert result.raw.data == payload


def test_fixture_adapter_token_dance():
    adapter = MOSDACDownloadFixtureAdapter(b"x")
    assert adapter.access_token is None
    token = adapter.authenticate("u", "p")
    assert token
    assert adapter.check_released("3RIMG_L2B_SST") is True
    refreshed = adapter.refresh_token()
    assert refreshed != token
    adapter.logout()
    assert adapter.access_token is None


def test_live_adapter_disabled_by_default():
    # In the test env, MDE_ENABLE_LIVE_SOURCES=false.
    adapter = MOSDACDownloadAdapter()
    with pytest.raises(LiveSourceDisabledError):
        adapter.fetch("record-1")


def test_live_adapter_requires_credentials_when_enabled(monkeypatch):
    adapter = MOSDACDownloadAdapter(username="", password="")
    # Force the enabled path but leave credentials blank.
    adapter.live_enabled = True
    with pytest.raises(AuthenticationRequiredError):
        adapter.fetch("record-1")
    with pytest.raises(AuthenticationRequiredError):
        adapter.download("record-1")
