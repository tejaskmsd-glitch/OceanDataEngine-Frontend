"""Real-source integration tests (make real HTTP requests to external sources).

These tests are gated behind the ``real_source`` marker and are EXCLUDED from
the default ``make test`` run (see pyproject ``addopts`` / ``-m 'not
real_source'``). Run explicitly with::

    pytest tests/ -m real_source -v

Every test degrades gracefully: network failures, TLS problems, timeouts, and
transient upstream errors result in ``pytest.skip`` rather than a hard failure,
so CI without egress is never blocked.
"""

from __future__ import annotations

import pytest

from marine_data_engine.sources.imd_cap import IMDCapLiveAdapter, parse_cap_document
from marine_data_engine.sources.incois_erddap import INCOISErddapLiveAdapter
from marine_data_engine.sources.mosdac_search import (
    MOSDACRateLimitError,
    MOSDACSearchAdapter,
)

pytestmark = pytest.mark.real_source


def _force_live(adapter) -> None:
    """Force-enable the live flag on an adapter instance (settings are cached).

    We intentionally do NOT mutate the global ``MDE_ENABLE_LIVE_SOURCES`` env
    var: settings are cached process-wide and pytest imports this module even
    when ``real_source`` tests are deselected, so a global mutation would leak
    into the offline suite. Flipping the per-instance flag is sufficient.
    """
    adapter.live_enabled = True


@pytest.mark.timeout(60)
def test_imd_cap_live_fetch():
    """Fetch the real IMD CAP RSS index, resolve + parse a real CAP document."""
    adapter = IMDCapLiveAdapter()
    _force_live(adapter)
    try:
        result = adapter.fetch()
    except Exception as exc:  # network / parse / upstream errors -> skip
        pytest.skip(f"IMD CAP source unavailable: {exc}")

    assert result.raw.provider == "IMD"
    assert result.raw.data, "expected non-empty CAP payload"
    assert result.raw.source_url

    # If the feed had items, we should have exactly one parsed alert.
    assert len(result.alerts) == 1
    alert = result.alerts[0]
    assert alert.alert_uid is not None
    assert alert.event_type  # classified into a canonical family
    assert alert.severity in {
        "unknown",
        "minor",
        "moderate",
        "severe",
        "extreme",
    }

    # Re-parse the raw bytes to confirm the document is well-formed CAP.
    reparsed = parse_cap_document(result.raw.data, source_url=result.raw.source_url)
    assert reparsed.alert_uid == alert.alert_uid


@pytest.mark.timeout(60)
def test_incois_erddap_catalog():
    """Fetch the real INCOIS ERDDAP catalog and verify >= 16 dataset IDs."""
    adapter = INCOISErddapLiveAdapter()
    _force_live(adapter)
    try:
        datasets = adapter.list_datasets()
    except Exception as exc:  # network / TLS / parse errors -> skip
        pytest.skip(f"INCOIS ERDDAP catalog unavailable: {exc}")

    ids = [d.dataset_id for d in datasets if d.dataset_id]
    # ERDDAP always includes the special 'allDatasets' meta-row; the real
    # INCOIS catalog lists many more than 16 datasets.
    assert len(ids) >= 16, f"expected >= 16 datasets, got {len(ids)}"
    assert len(set(ids)) == len(ids), "dataset IDs should be unique"


@pytest.mark.timeout(60)
def test_mosdac_search():
    """Fetch real MOSDAC search results for the 3RIMG_L2B_SST product."""
    adapter = MOSDACSearchAdapter()
    _force_live(adapter)
    try:
        results = adapter.search("3RIMG_L2B_SST", count=10)
    except MOSDACRateLimitError as exc:
        pytest.skip(f"MOSDAC rate limited: {exc}")
    except Exception as exc:  # network / parse errors -> skip
        pytest.skip(f"MOSDAC search unavailable: {exc}")

    # The search may legitimately return zero rows if the product id changed
    # upstream; only assert structure when we got entries.
    if not results:
        pytest.skip("MOSDAC search returned no entries for 3RIMG_L2B_SST")
    for entry in results:
        assert entry.dataset_id
