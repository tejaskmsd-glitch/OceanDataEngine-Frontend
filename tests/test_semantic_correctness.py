"""Semantic correctness tests.

These tests verify that query endpoints return *semantically correct* results:
no cross-contamination between alert types, strict (exact, case-sensitive)
event_type filtering, honest SOURCE_GAP warnings instead of silent empty
responses, correct spatial filtering, and correct active/expired handling.

They run against the CURRENT offline codebase (SQLite in-memory + fixtures).

Seeded fixture facts (see tests/fixtures/):
- IMD CAP fixture yields a single alert normalized to event_type == "high_wave"
  with a polygon over the Goa coast (lat ~15.1-15.6, lon ~73.6-74.0) and
  valid_until == 2026-09-04T06:00:00Z (in the past relative to test run time,
  so it is EXPIRED and excluded by active_only=True).
- INCOIS PFZ fixture yields PFZ advisories near Goa (~15.45N, 73.5E) and Kochi.
"""

from __future__ import annotations


# --------------------------------------------------------------------------- #
# 1. No cross-contamination: lightning query on high_wave-only data -> empty
# --------------------------------------------------------------------------- #
def test_lightning_query_returns_only_lightning_alerts(client, seeded):
    resp = client.get(
        "/v1/alerts", params={"event_type": "lightning", "active_only": False}
    )
    assert resp.status_code == 200
    body = resp.json()
    # Fixtures contain only a high_wave alert, so a lightning filter must be empty.
    assert body["data"] == []
    # And no lightning alert leaked through under a different type.
    assert all(a["event_type"] == "lightning" for a in body["data"])


# --------------------------------------------------------------------------- #
# 2. high_wave query returns the seeded high_wave alert(s)
# --------------------------------------------------------------------------- #
def test_high_wave_query_returns_high_wave_alerts(client, seeded):
    resp = client.get(
        "/v1/alerts", params={"event_type": "high_wave", "active_only": False}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) >= 1
    # Every returned alert must actually be a high_wave alert.
    for alert in body["data"]:
        assert alert["event_type"] == "high_wave"


# --------------------------------------------------------------------------- #
# 3. cyclone query on non-cyclone data -> strictly empty
# --------------------------------------------------------------------------- #
def test_cyclone_query_returns_only_cyclone_data(client, seeded):
    resp = client.get(
        "/v1/alerts", params={"event_type": "cyclone", "active_only": False}
    )
    assert resp.status_code == 200
    body = resp.json()
    # No cyclone data is seeded; the filter must be strict.
    assert body["data"] == []


# --------------------------------------------------------------------------- #
# 4. event_type filter is an EXACT, case-sensitive match
# --------------------------------------------------------------------------- #
def test_event_type_filter_is_exact_match(client, seeded):
    # Exact match returns data.
    exact = client.get(
        "/v1/alerts", params={"event_type": "high_wave", "active_only": False}
    )
    assert exact.status_code == 200
    assert len(exact.json()["data"]) >= 1

    # Substring ("wave") must NOT match "high_wave".
    substring = client.get(
        "/v1/alerts", params={"event_type": "wave", "active_only": False}
    )
    assert substring.status_code == 200
    assert substring.json()["data"] == []

    # Different case ("HIGH_WAVE") must NOT match "high_wave".
    wrong_case = client.get(
        "/v1/alerts", params={"event_type": "HIGH_WAVE", "active_only": False}
    )
    assert wrong_case.status_code == 200
    assert wrong_case.json()["data"] == []


# --------------------------------------------------------------------------- #
# 5. SOURCE_GAP endpoints answer with an explicit warning, not silent empty
# --------------------------------------------------------------------------- #
def test_source_gap_returned_not_empty_silence(client, seeded):
    resp = client.get("/v1/tides", params={"lat": 15.45, "lon": 73.5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    # The response must EXPLAIN the gap, not just return empty data.
    assert body["warnings"], "expected an explanatory warning, got none"
    warning_text = " ".join(body["warnings"])
    assert "SOURCE_GAP" in warning_text or "source gap" in warning_text.lower()


# --------------------------------------------------------------------------- #
# 6. PFZ query returns PFZ records (pfz_uid + geometry), not alert records
# --------------------------------------------------------------------------- #
def test_pfz_query_returns_pfz_data_not_alerts(client, seeded):
    resp = client.get(
        "/v1/fishing/pfz", params={"lat": 15.45, "lon": 73.5, "radius_km": 50}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) >= 1
    for record in body["data"]:
        # PFZ shape: has pfz_uid and geometry.
        assert "pfz_uid" in record and record["pfz_uid"]
        assert "geometry" in record and record["geometry"] is not None
        # Must NOT be an alert record (no alert-specific identifier).
        assert "alert_uid" not in record
        assert "event_type" not in record


# --------------------------------------------------------------------------- #
# 7. Weather conditions with no weather observations -> warning present
# --------------------------------------------------------------------------- #
def test_weather_source_gap_has_warning(client, seeded):
    resp = client.get(
        "/v1/weather/conditions", params={"lat": 15.45, "lon": 73.5}
    )
    assert resp.status_code == 200
    body = resp.json()
    # Only CAP alerts are seeded — no weather observations.
    assert body["data"] == []
    assert body["warnings"], "expected a SOURCE_GAP warning for weather conditions"


# --------------------------------------------------------------------------- #
# 8. Ocean conditions with no ocean observations -> warning present
# --------------------------------------------------------------------------- #
def test_ocean_source_gap_has_warning(client, seeded):
    resp = client.get(
        "/v1/ocean/conditions", params={"lat": 15.45, "lon": 73.5}
    )
    assert resp.status_code == 200
    body = resp.json()
    # No ocean observations are ingested.
    assert body["data"] == []
    assert body["warnings"], "expected a SOURCE_GAP warning for ocean conditions"


# --------------------------------------------------------------------------- #
# 9. Spatial filtering: near the alert returns it, far away returns nothing
# --------------------------------------------------------------------------- #
def test_alerts_spatial_filtering_correctness(client, seeded):
    # Near the seeded Goa-coast alert polygon (lat ~15.1-15.6, lon ~73.6-74.0).
    near = client.get(
        "/v1/alerts",
        params={
            "lat": 15.4,
            "lon": 73.8,
            "radius_km": 100,
            "event_type": "high_wave",
            "active_only": False,
        },
    )
    assert near.status_code == 200
    near_data = near.json()["data"]
    assert len(near_data) >= 1
    assert near_data[0]["distance_km"] is not None

    # Opposite side of the globe — far outside the radius.
    far = client.get(
        "/v1/alerts",
        params={
            "lat": -15.4,
            "lon": -106.2,
            "radius_km": 100,
            "event_type": "high_wave",
            "active_only": False,
        },
    )
    assert far.status_code == 200
    assert far.json()["data"] == []


# --------------------------------------------------------------------------- #
# 10. active_only excludes the seeded alert because its valid_until is in the past
# --------------------------------------------------------------------------- #
def test_active_only_filter_excludes_expired(client, seeded):
    # The seeded high_wave alert expired 2026-09-04T06:00:00Z, well before now.
    active = client.get(
        "/v1/alerts", params={"event_type": "high_wave", "active_only": True}
    )
    assert active.status_code == 200
    assert active.json()["data"] == [], "expired alert must be excluded when active_only=True"

    # Sanity check: it IS present when expired alerts are allowed.
    inactive = client.get(
        "/v1/alerts", params={"event_type": "high_wave", "active_only": False}
    )
    assert inactive.status_code == 200
    assert len(inactive.json()["data"]) >= 1
