"""API contract tests (query-only endpoints + evidence)."""

from __future__ import annotations


def test_health(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["status"] == "ok"
    assert body["data"]["live_sources_enabled"] is False
    assert "generated_at" in body["meta"]


def test_datasets(client):
    r = client.get("/v1/datasets")
    assert r.status_code == 200
    keys = {d["key"] for d in r.json()["data"]}
    assert {"imd_cap", "incois_pfz"} <= keys


def test_data_health_reports_freshness(client):
    r = client.get("/v1/data-health")
    assert r.status_code == 200
    rows = r.json()["data"]
    assert all("freshness" in row for row in rows)
    imd = next(row for row in rows if row["dataset"] == "imd_cap")
    assert imd["status"] in {"healthy", "stale", "degraded", "failed", "disabled"}


def test_pfz_near_goa_returns_zone(client):
    r = client.get("/v1/fishing/pfz", params={"lat": 15.45, "lon": 73.5, "radius_km": 50})
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) >= 1
    zone = body["data"][0]
    assert zone["inside"] is True
    assert zone["distance_km"] >= 0.0
    assert body["sources"]
    # Envelope evidence is addressable.
    rid = body["meta"]["request_id"]
    ev = client.get(f"/v1/evidence/{rid}")
    assert ev.status_code == 200
    assert ev.json()["data"]["endpoint"] == "/v1/fishing/pfz"


def test_pfz_far_away_returns_empty(client):
    r = client.get("/v1/fishing/pfz", params={"lat": 0.0, "lon": 0.0, "radius_km": 10})
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_alerts_returns_high_wave(client):
    r = client.get("/v1/alerts", params={"active_only": False})
    assert r.status_code == 200
    events = {a["event_type"] for a in r.json()["data"]}
    assert "high_wave" in events


def test_alerts_lat_lon_must_pair(client):
    r = client.get("/v1/alerts", params={"lat": 15.0})
    assert r.status_code == 400


def test_alerts_spatial_filter(client):
    r = client.get(
        "/v1/alerts",
        params={"lat": 15.4, "lon": 73.8, "radius_km": 100, "active_only": False},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) >= 1
    assert data[0]["distance_km"] is not None


def test_evidence_unknown_request_id_404(client):
    r = client.get("/v1/evidence/does-not-exist")
    assert r.status_code == 404


def test_pfz_invalid_coords_422(client):
    r = client.get("/v1/fishing/pfz", params={"lat": 999, "lon": 73.5})
    assert r.status_code == 422


def test_jobs_returns_ingestion_and_processing(client):
    r = client.get("/v1/jobs")
    assert r.status_code == 200
    body = r.json()
    jobs = body["data"]
    assert len(jobs) >= 2  # at least one ingestion + one processing job from seeded data
    # Every job has the fields the dashboard expects.
    for j in jobs:
        assert "job_id" in j
        assert "status" in j
        assert "job_type" in j
    # At least one ingestion and one processing job type present.
    types = {j["job_type"] for j in jobs}
    assert "ingestion" in types
    assert any(t for t in types if t and t.startswith("normalize_"))


def test_dataset_status_returns_freshness(client):
    r = client.get("/v1/datasets/imd_cap/status")
    assert r.status_code == 200
    body = r.json()
    ds = body["data"]
    assert ds["dataset_id"] == "imd_cap"
    assert ds["provider"] == "IMD"
    assert "freshness" in ds
    assert ds["freshness"]["expected_update_interval_s"] is not None


def test_dataset_status_unknown_404(client):
    r = client.get("/v1/datasets/does_not_exist/status")
    assert r.status_code == 404


def test_metrics_endpoint(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    text = r.text
    assert "mde_source_fetch_total" in text or "mde_" in text


# --------------------------------------------------------------------------- #
# New query-only endpoints — envelope contract
# --------------------------------------------------------------------------- #
def _assert_envelope(body: dict) -> None:
    """Assert the canonical envelope structure is present."""
    assert "data" in body
    assert "meta" in body
    assert "warnings" in body
    assert "generated_at" in body["meta"]
    assert "request_id" in body["meta"]


def test_ocean_conditions_returns_envelope(client):
    r = client.get("/v1/ocean/conditions", params={"lat": 15.45, "lon": 73.5})
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    # No ocean observations are ingested; expect empty data + freshness warning.
    assert body["data"] == []
    assert body["warnings"]


def test_ocean_forecast_returns_envelope(client):
    r = client.get("/v1/ocean/forecast", params={"lat": 15.45, "lon": 73.5})
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    assert body["data"] == []
    assert body["warnings"]


def test_weather_conditions_returns_envelope(client):
    r = client.get("/v1/weather/conditions", params={"lat": 15.45, "lon": 73.5})
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    assert body["data"] == []
    assert body["warnings"]


def test_weather_forecast_returns_envelope(client):
    r = client.get("/v1/weather/forecast", params={"lat": 15.45, "lon": 73.5})
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    assert body["data"] == []
    assert body["warnings"]


def test_fishing_advisories_returns_envelope(client):
    r = client.get("/v1/fishing/advisories", params={"lat": 15.45, "lon": 73.5})
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    # No advisories ingested — empty with warning.
    assert body["data"] == []
    assert body["warnings"]


def test_fishing_suitability_reports_not_started(client):
    r = client.get("/v1/fishing/suitability", params={"lat": 15.45, "lon": 73.5})
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    # Real computation: a seeded PFZ advisory sits near this point, so the
    # engine returns a scored, classified result driven by PFZ proximity.
    data = body["data"]
    assert data["classification"] in {
        "EXCELLENT", "GOOD", "MODERATE", "POOR", "UNSUITABLE"
    }
    assert 0.0 <= data["score"] <= 100.0
    assert any("PFZ" in d for d in data["positive_drivers"])


def test_tides_returns_envelope(client):
    r = client.get("/v1/tides", params={"lat": 15.45, "lon": 73.5})
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    assert body["data"] == []
    # HAR-D blocker is reported honestly.
    assert any("HAR-D" in w for w in body["warnings"])


def test_geofence_check_returns_envelope(client):
    r = client.get("/v1/geofence/check", params={"lat": 15.45, "lon": 73.5})
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    # No zones configured -> SOURCE_GAP warning.
    assert body["data"] == []
    assert any("SOURCE_GAP" in w for w in body["warnings"])


def test_geofence_nearby_returns_envelope(client):
    r = client.get(
        "/v1/geofence/nearby", params={"lat": 15.45, "lon": 73.5, "radius_km": 100}
    )
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    assert body["data"] == []


def test_geofence_intersections_returns_envelope(client):
    geom = {
        "type": "Polygon",
        "coordinates": [[[73.0, 15.0], [74.0, 15.0], [74.0, 16.0], [73.0, 16.0], [73.0, 15.0]]],
    }
    r = client.post("/v1/geofence/intersections", json={"geometry": geom})
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    assert body["data"] == []


def test_risk_marine_returns_envelope(client):
    r = client.get("/v1/risk/marine", params={"lat": 15.45, "lon": 73.5})
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    # Real computation: a seeded active CAP warning near this point drives the
    # risk assessment (no environmental factors ingested, so score is
    # warning-only).
    data = body["data"]
    assert data["risk_level"] in {"LOW", "MODERATE", "HIGH", "EXTREME"}
    assert 0.0 <= data["risk_score"] <= 100.0
    assert any("SOURCE_GAP" in w for w in data["warnings"])


def test_routes_safe_returns_envelope(client):
    r = client.post(
        "/v1/routes/safe",
        json={
            "start": {"lat": 15.0, "lon": 73.0},
            "end": {"lat": 16.0, "lon": 74.0},
            "departure_time": "2026-01-01T00:00:00Z",
            "vessel_type": "trawler",
        },
    )
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    # Real deterministic route: geometry-only scoring without env data.
    assert body["data"]["status"] == "partial"
    assert body["data"]["geometry"]["type"] == "LineString"
    assert body["data"]["total_distance_km"] > 0
    assert body["data"]["segments"]
    assert any("SOURCE_GAP" in w for w in body["data"]["warnings"])


# --------------------------------------------------------------------------- #
# STAC catalog + tile placeholder
# --------------------------------------------------------------------------- #
def test_stac_collections_returns_list(client):
    r = client.get("/v1/stac/collections")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["collections"], list)
    # One collection per seeded dataset (imd_cap, incois_pfz, ...).
    ids = {c["id"] for c in body["collections"]}
    assert {"imd_cap", "incois_pfz"} <= ids
    for c in body["collections"]:
        assert c["type"] == "Collection"
        assert c["stac_version"] == "1.0.0"
        assert "extent" in c
        assert "providers" in c


def test_stac_collection_by_id(client):
    r = client.get("/v1/stac/collections/imd_cap")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "imd_cap"
    assert body["type"] == "Collection"
    assert body["stac_version"] == "1.0.0"
    assert body["extent"]["spatial"]["bbox"]
    assert body["extent"]["temporal"]["interval"]

    # Unknown collection -> 404.
    r404 = client.get("/v1/stac/collections/does_not_exist")
    assert r404.status_code == 404


def test_stac_items_for_collection(client):
    r = client.get("/v1/stac/collections/incois_pfz/items")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert isinstance(body["features"], list)
    # Ingestion of the PFZ fixture creates at least one raw asset -> one item.
    assert len(body["features"]) >= 1
    item = body["features"][0]
    assert item["type"] == "Feature"
    assert item["stac_version"] == "1.0.0"
    assert item["collection"] == "incois_pfz"
    assert "datetime" in item["properties"]
    assert item["assets"]


def test_tiles_returns_501(client):
    r = client.get("/v1/tiles/sst/3/4/5")
    assert r.status_code == 501
    body = r.json()
    assert body["status"] == "NOT_IMPLEMENTED"
    assert body["layer"] == "sst"
    assert body["tile"] == {"z": 3, "x": 4, "y": 5}
    assert "TiTiler" in body["detail"]
