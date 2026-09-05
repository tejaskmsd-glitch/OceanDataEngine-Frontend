"""Contract tests for the IMD marine bulletin source, cache and sea-state gate.

These lock in the behaviour that makes the source trustworthy:

* wind is numeric and converted by an exact factor;
* sea state stays a *category* and is never persisted as a wave height;
* unverified vocabulary, centres, and units fail loudly;
* the Redis cache is fail-open and single-flight;
* a categorical sea state can satisfy the safety gate but never earn a full
  clearance, and unknown vocabulary is treated as missing evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from marine_data_engine.cache import BulletinCache
from marine_data_engine.domain.safety_gate import (
    REASON_SEA_STATE_CATEGORY_UNRECOGNISED,
    REASON_SEA_STATE_FROM_CATEGORY,
    REASON_SEA_STATE_UNKNOWN,
    STATUS_CLEARED,
    STATUS_CLEARED_WITH_CAUTION,
    STATUS_NOT_CLEARED,
    evaluate_safety_gate,
)
from marine_data_engine.domain.sea_state import (
    DERIVATION_BASIS,
    parse_sea_state_category,
)
from marine_data_engine.sources.base import SourceContractError
from marine_data_engine.sources.imd_marine_bulletin import (
    KIND_COASTAL,
    KIND_SEA_AREA,
    IMDMarineBulletinLiveAdapter,
    build_records,
    parse_bulletin,
    parse_wind_text,
)

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "realtime_contracts"
    / "imd_coastal_bulletin_mumbai.html"
)

KNOTS_TO_MS = 1852.0 / 3600.0


def _doc() -> str:
    return FIXTURE.read_text(encoding="utf-8")


# ── sea-state vocabulary ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("term", "low", "high"),
    [
        ("SMOOTH", 0.1, 0.5),
        ("SLIGHT", 0.5, 1.25),
        ("MODERATE", 1.25, 2.5),
        ("ROUGH", 2.5, 4.0),
        ("VERY ROUGH", 4.0, 6.0),
        ("MODERATE TO ROUGH", 1.25, 4.0),
        ("moderate becoming rough", 1.25, 4.0),
    ],
)
def test_sea_state_maps_to_published_wmo_band(term, low, high):
    band = parse_sea_state_category(term)
    assert band is not None
    assert band.min_height_m == low
    assert band.max_height_m == high
    # The only scalar exposed for decisions is the pessimistic bound.
    assert band.conservative_height_m == high
    payload = band.as_dict()
    assert payload["derivation_basis"] == DERIVATION_BASIS
    assert payload["is_measurement"] is False
    assert payload["sea_state_category"] == " ".join(term.split())


@pytest.mark.parametrize("term", ["", "   ", None, "PLEASANT", "quite choppy", "7"])
def test_unverified_sea_state_vocabulary_is_rejected(term):
    """Unknown wording must be unknown — never silently mapped to calm."""
    assert parse_sea_state_category(term) is None


# ── wind parsing ───────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("text", "low_kt", "high_kt", "gust_kt"),
    [
        ("WESTERLY 10 TO 15 GUSTING TO 20 KNOTS", 10, 15, 20),
        ("MAINLY SOUTHWESTERLY 15 - 20 KTS", 15, 20, None),
        ("Southerly to Southwesterly 15 to 20 Gusting to 25 Knots", 15, 20, 25),
    ],
)
def test_wind_converts_knots_exactly(text, low_kt, high_kt, gust_kt):
    wind = parse_wind_text(text)
    assert wind is not None
    assert wind.low_ms == pytest.approx(low_kt * KNOTS_TO_MS, abs=1e-4)
    assert wind.high_ms == pytest.approx(high_kt * KNOTS_TO_MS, abs=1e-4)
    # The conservative value is the upper bound of the sustained range.
    assert wind.conservative_ms == wind.high_ms
    if gust_kt is None:
        assert wind.gust_ms is None
    else:
        assert wind.gust_ms == pytest.approx(gust_kt * KNOTS_TO_MS, abs=1e-4)


def test_wind_without_numeric_range_returns_none():
    """A qualitative statement yields no number rather than a guess."""
    assert parse_wind_text("LIGHT AND VARIABLE") is None
    assert parse_wind_text("") is None


# ── bulletin parsing ───────────────────────────────────────────────────────
def test_parses_verified_coastal_bulletin():
    bulletin = parse_bulletin(
        _doc(), kind=KIND_COASTAL, centre_id=4, source_url="https://example.invalid/b"
    )
    assert bulletin.centre == "ACWC MUMBAI"
    assert bulletin.valid_from == datetime(2026, 1, 2, 15, tzinfo=UTC)
    assert bulletin.valid_until == datetime(2026, 1, 3, 3, tzinfo=UTC)
    # 20:55 IST == 15:25 UTC
    assert bulletin.issued_at == datetime(2026, 1, 2, 15, 25, tzinfo=UTC)
    assert [a.area_name for a in bulletin.areas] == [
        "North Maharashtra coast",
        "South Maharashtra and Goa coast",
    ]


def test_records_keep_sea_state_categorical_and_area_scoped():
    bulletin = parse_bulletin(
        _doc(), kind=KIND_COASTAL, centre_id=4, source_url="https://example.invalid/b"
    )
    forecasts, alerts, _diagnostics = build_records(bulletin)

    sea = [f for f in forecasts if f.parameter == "sea_state_category"]
    assert len(sea) == 2
    for record in sea:
        # A category must never be persisted as a numeric height.
        assert record.value is None
        assert record.unit is None
        assert record.source_metadata["is_measurement"] is False
        # Area-scoped, never a point forecast.
        assert record.latitude is None and record.longitude is None
        assert record.source_metadata["area_scoped"] is True
        assert record.source_metadata["point_forecast"] is False

    goa = next(
        f
        for f in forecasts
        if f.parameter == "sea_state_category"
        and f.source_metadata["area_description"] == "South Maharashtra and Goa coast"
    )
    assert goa.source_metadata["sea_state_category"] == "MODERATE TO ROUGH"
    assert goa.source_metadata["derived_height_band_m"] == [1.25, 4.0]

    wind = next(
        f
        for f in forecasts
        if f.parameter == "wind_speed"
        and f.source_metadata["area_description"] == "South Maharashtra and Goa coast"
    )
    assert wind.unit == "m/s"
    assert wind.value == pytest.approx(25 * KNOTS_TO_MS, abs=1e-4)
    assert wind.source_metadata["value_selection"] == "range_upper_bound_conservative"


def test_nil_warnings_are_not_emitted_but_real_ones_are():
    bulletin = parse_bulletin(
        _doc(), kind=KIND_COASTAL, centre_id=4, source_url="https://example.invalid/b"
    )
    _forecasts, alerts, _diagnostics = build_records(bulletin)
    # North coast is NIL for both warning rows; Goa coast has one of each.
    assert {a.event_type for a in alerts} == {"port_signal", "storm_surge"}
    assert all(a.area_description == "South Maharashtra and Goa coast" for a in alerts)
    # IMD publishes no CAP severity; it must be explicitly unknown, not invented.
    assert all(a.severity == "unknown" for a in alerts)


def test_wrong_centre_id_raises_contract_error():
    with pytest.raises(SourceContractError, match="did not identify expected centre"):
        parse_bulletin(_doc(), kind=KIND_COASTAL, centre_id=1, source_url="x")


def test_unmapped_area_vocabulary_raises_contract_error():
    with pytest.raises(SourceContractError):
        parse_bulletin(_doc(), kind=KIND_SEA_AREA, centre_id=99, source_url="x")


def test_document_without_verified_areas_raises():
    doc = "<html><body><p>ACWC MUMBAI</p><p>Wind</p><p>10 TO 15 KNOTS</p></body></html>"
    with pytest.raises(SourceContractError, match="no verified area blocks"):
        parse_bulletin(doc, kind=KIND_COASTAL, centre_id=4, source_url="x")


def test_adapter_is_offline_and_uses_injected_cache():
    """The adapter must read through the cache and never touch the network here."""
    calls: list[str] = []

    class _FakeClient:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value, ex=None, nx=False):
            if nx and key in self.store:
                return False
            self.store[key] = value
            return True

        def delete(self, key):
            self.store.pop(key, None)

    cache = BulletinCache(_FakeClient())
    adapter = IMDMarineBulletinLiveAdapter(
        centre_ids=[4], kinds=[KIND_COASTAL], live_enabled=True, cache=cache
    )
    document = _doc()

    def _fake_get(_url: str) -> str:
        calls.append(_url)
        return document

    adapter._http_get = _fake_get  # type: ignore[method-assign]

    first = adapter.fetch()
    second = adapter.fetch()
    assert first.result_state == "success"
    assert first.forecasts and second.forecasts
    # Second fetch is served from cache: exactly one upstream request.
    assert len(calls) == 1
    assert cache.hits >= 1


# ── cache semantics ────────────────────────────────────────────────────────
def test_cache_without_client_always_calls_loader():
    cache = BulletinCache(None)
    assert cache.get_or_fetch(key="k", loader=lambda: "v1") == "v1"
    assert cache.get_or_fetch(key="k", loader=lambda: "v2") == "v2"


def test_cache_is_fail_open_when_redis_errors():
    """A broken Redis must degrade to a direct fetch, never raise."""

    class _Broken:
        def get(self, *a, **k):
            raise RuntimeError("redis down")

        def set(self, *a, **k):
            raise RuntimeError("redis down")

        def delete(self, *a, **k):
            raise RuntimeError("redis down")

    cache = BulletinCache(_Broken())
    assert cache.get_or_fetch(key="k", loader=lambda: "fresh") == "fresh"


def test_cache_single_flight_elects_one_fetcher():
    class _Client:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value, ex=None, nx=False):
            if nx and key in self.store:
                return False
            self.store[key] = value
            return True

        def delete(self, key):
            self.store.pop(key, None)

    client = _Client()
    a = BulletinCache(client, wait_timeout_s=0.2)
    # Simulate a lock already held by another worker.
    client.set(a._lock_key("k"), "1", nx=True)
    loads: list[int] = []

    def loader() -> str:
        loads.append(1)
        return "value"

    # Waiter times out and fetches itself rather than failing.
    assert a.get_or_fetch(key="k", loader=loader) == "value"
    assert loads == [1]
    assert a.degraded_fetches == 1


# ── safety gate integration ────────────────────────────────────────────────
def test_category_satisfies_sea_state_but_caps_at_caution():
    decision = evaluate_safety_gate(
        wind_speed=5.0, sea_state_category="SLIGHT", route_risk_complete=True
    )
    assert decision.safety_status == STATUS_CLEARED_WITH_CAUTION
    assert decision.insufficient_data is False
    assert REASON_SEA_STATE_FROM_CATEGORY in decision.reasons
    assert decision.sea_state is not None
    assert decision.sea_state.conservative_height_m == 1.25


def test_measured_height_still_earns_full_clearance():
    decision = evaluate_safety_gate(
        wind_speed=5.0, wave_height=0.4, route_risk_complete=True
    )
    assert decision.safety_status == STATUS_CLEARED
    assert REASON_SEA_STATE_FROM_CATEGORY not in decision.reasons


def test_unrecognised_category_is_missing_evidence_not_calm():
    decision = evaluate_safety_gate(wind_speed=5.0, sea_state_category="PLEASANT")
    assert decision.safety_status == STATUS_NOT_CLEARED
    assert decision.insufficient_data is True
    assert "sea_state" in decision.missing_inputs
    assert REASON_SEA_STATE_CATEGORY_UNRECOGNISED in decision.reasons
    assert REASON_SEA_STATE_UNKNOWN in decision.reasons


def test_measured_height_takes_precedence_over_category():
    decision = evaluate_safety_gate(
        wind_speed=5.0,
        wave_height=0.3,
        sea_state_category="VERY ROUGH",
        route_risk_complete=True,
    )
    # A real measurement must not be overridden by a coarse category.
    assert decision.sea_state is None
    assert decision.safety_status == STATUS_CLEARED


def test_rough_category_raises_risk_and_blocks_clearance():
    decision = evaluate_safety_gate(
        wind_speed=18.0, sea_state_category="VERY ROUGH", route_risk_complete=True
    )
    assert decision.safety_status == STATUS_NOT_CLEARED
    assert decision.risk is not None
    assert decision.risk.risk_level in {"HIGH", "EXTREME"}
