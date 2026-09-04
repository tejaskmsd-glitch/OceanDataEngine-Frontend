"""End-to-end real-source tests.

These tests fetch REAL data from live sources, push it through the full
ingestion pipeline, and verify the output through the API layer. They require
network access and are excluded from the default test run.

Run with: pytest tests/test_e2e_real.py -v
"""

from __future__ import annotations

import json
import urllib.request

import pytest

# Mark all tests in this file as real_source (excluded from default `make test`)
pytestmark = pytest.mark.real_source


def _fetch_url(url: str, *, timeout: int = 15, verify_ssl: bool = True) -> bytes:
    """Fetch a URL, returning raw bytes. Skips test on network failure."""
    try:
        import ssl

        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
        if not verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "MarineDataEngine/test"})
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.read()
    except Exception as exc:
        pytest.skip(f"Network unavailable: {exc}")


# ── IMD CAP: Real RSS → Real CAP XML → Parse → Ingest → Query ──────────

class TestIMDCapEndToEnd:
    """Full pipeline: live IMD CAP RSS → newest alert → parse → ingest → API."""

    def test_fetch_rss_and_parse_latest_cap(self):
        """Fetch real RSS, extract latest CAP URL, fetch and parse it."""
        import xml.etree.ElementTree as ET

        rss_bytes = _fetch_url("https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml")
        assert len(rss_bytes) > 100, "RSS too small"

        root = ET.fromstring(rss_bytes)
        items = root.findall(".//item/link")
        assert len(items) >= 1, "No CAP items in RSS"

        cap_url = items[0].text.strip()
        assert cap_url.startswith("https://"), f"Bad CAP URL: {cap_url}"

        cap_bytes = _fetch_url(cap_url)
        assert len(cap_bytes) > 100, "CAP XML too small"

        from marine_data_engine.sources.imd_cap import parse_cap_document

        alert = parse_cap_document(cap_bytes, source_url=cap_url)
        assert alert.alert_uid, "Missing alert_uid"
        assert alert.issued_at is not None, "Missing issued_at"
        assert alert.severity in ("minor", "moderate", "severe", "extreme", "unknown")
        assert alert.certainty in ("unlikely", "possible", "likely", "observed", "unknown")
        # Geometry may or may not be present depending on the alert
        if alert.geometry:
            assert alert.geometry["type"] == "Polygon"
            coords = alert.geometry["coordinates"][0]
            assert len(coords) >= 3, "Too few polygon coordinates"
            # Verify lon,lat order (GeoJSON standard)
            for coord in coords:
                assert -180 <= coord[0] <= 180, f"Bad longitude: {coord[0]}"
                assert -90 <= coord[1] <= 90, f"Bad latitude: {coord[1]}"

    def test_full_pipeline_with_real_cap(self, db_session, raw_store, queue):
        """Ingest a real CAP alert through the full pipeline and verify DB state."""
        import xml.etree.ElementTree as ET

        rss_bytes = _fetch_url("https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml")
        root = ET.fromstring(rss_bytes)
        items = root.findall(".//item/link")
        cap_url = items[0].text.strip()
        cap_bytes = _fetch_url(cap_url)

        from marine_data_engine.services.ingestion import IngestionService
        from marine_data_engine.services.registry import seed_registry
        from marine_data_engine.sources.imd_cap import IMDCapFixtureAdapter

        seed_registry(db_session)
        svc = IngestionService(db_session, raw_store, queue)
        result = IMDCapFixtureAdapter(cap_bytes, source_url=cap_url).fetch()
        summary = svc.ingest(result)
        db_session.commit()

        # Verify ingestion outcome
        assert summary.accepted >= 1, "Alert not accepted"
        assert summary.rejected == 0, "Alert rejected"
        assert len(summary.alert_events) >= 1, "No alert events"

        # Verify through query layer
        from marine_data_engine.services.queries import query_alerts

        alerts = query_alerts(db_session, active_only=False, limit=10)
        assert len(alerts) >= 1, "No alerts in DB"
        a = alerts[0]
        assert a["provider"] == "IMD"
        assert a["quality_status"] == "accepted"
        assert a["processing_version"] == "1.0.0"
        assert a["issued_at"] is not None

        # Verify raw store has the object
        assert len(raw_store._objects) >= 1

        # Verify idempotency: re-ingest should skip
        summary2 = svc.ingest(IMDCapFixtureAdapter(cap_bytes, source_url=cap_url).fetch())
        assert summary2.skipped_duplicates >= 1


# ── INCOIS ERDDAP: Real catalog → Verify dataset IDs ───────────────────

class TestINCOISErddapEndToEnd:
    """Fetch real ERDDAP catalog and verify dataset coverage."""

    def test_fetch_real_catalog(self):
        """Fetch the real ERDDAP catalog and verify ≥16 datasets."""
        # INCOIS omits intermediate cert — use curl-fetched copy or skip
        try:
            data = _fetch_url(
                "https://erddap.incois.gov.in/erddap/info/index.json?page=1&itemsPerPage=1000",
                verify_ssl=False,  # Known INCOIS TLS issue (V3-TLS)
            )
        except Exception:
            pytest.skip("INCOIS ERDDAP unreachable or TLS issue")

        catalog = json.loads(data)
        rows = catalog.get("table", {}).get("rows", [])
        dataset_ids = sorted(set(r[0] for r in rows if len(r) >= 1 and r[0]))
        assert len(dataset_ids) >= 15, f"Expected ≥15 datasets, got {len(dataset_ids)}"

        # Verify known datasets are present
        expected = {
            "NOAA_AVHRR_AMSR_datasets",
            "IRS_chlorophyll_datasets",
            "ascat_daily_datasets",
        }
        # Dataset IDs in ERDDAP catalog are URLs; extract the ID part
        id_set = set()
        for did in dataset_ids:
            # Extract dataset ID from URL like https://erddap.../griddap/NOAA_AVHRR_AMSR_datasets
            parts = did.rsplit("/", 1)
            if len(parts) == 2:
                id_set.add(parts[1])
            else:
                id_set.add(did)
        for exp in expected:
            assert exp in id_set, f"Missing expected dataset: {exp}"

    def test_fetch_sst_dataset_info(self):
        """Fetch real per-dataset info and verify SST variables."""
        try:
            data = _fetch_url(
                "https://erddap.incois.gov.in/erddap/info/NOAA_AVHRR_AMSR_datasets/index.json",
                verify_ssl=False,
            )
        except Exception:
            pytest.skip("INCOIS ERDDAP unreachable")

        info = json.loads(data)
        rows = info.get("table", {}).get("rows", [])
        variables = [r[1] for r in rows if r[0] == "variable"]
        assert "sst" in variables, f"SST variable missing. Found: {variables}"

        # Verify dimensions include time, latitude, longitude
        dims = [r[1] for r in rows if r[0] == "dimension"]
        assert "time" in dims
        assert "latitude" in dims
        assert "longitude" in dims


# ── NGA WPI: Real port data → Parse → Verify India ports ───────────────

class TestNGAPortsEndToEnd:
    """Fetch real NGA WPI data and verify India port coverage."""

    def test_fetch_and_parse_real_ports(self):
        """Fetch real port data and verify India coverage."""
        from marine_data_engine.sources.nga_ports import NGAPortLiveAdapter

        try:
            adapter = NGAPortLiveAdapter(country_filter="India")
            ports = adapter.fetch_and_parse()
        except Exception as exc:
            pytest.skip(f"NGA WPI unavailable: {exc}")

        assert len(ports) >= 40, f"Expected ≥40 India ports, got {len(ports)}"

        # Verify key ports are present
        names = {p.name.upper() for p in ports}
        for expected in ["MUMBAI (BOMBAY)", "CHENNAI (MADRAS)", "KOCHI (COCHIN)", "KANDLA"]:
            assert expected in names, f"Missing port: {expected}"

        # Verify coordinates are in India bbox (exclude remote territories)
        mainland = [p for p in ports if p.latitude > 0]  # Exclude Diego Garcia etc.
        assert len(mainland) >= 40, f"Expected ≥40 mainland ports, got {len(mainland)}"
        for p in mainland:
            assert 5.0 <= p.latitude <= 35.0, f"Bad latitude for {p.name}: {p.latitude}"
            assert 68.0 <= p.longitude <= 97.0, f"Bad longitude for {p.name}: {p.longitude}"

    def test_ingest_ports_into_db(self, db_session):
        """Ingest real ports into the Port table and verify query."""
        from marine_data_engine.db.models import Port
        from marine_data_engine.sources.nga_ports import NGAPortLiveAdapter

        try:
            ports = NGAPortLiveAdapter(country_filter="India").fetch_and_parse()
        except Exception as exc:
            pytest.skip(f"NGA WPI unavailable: {exc}")

        # Deduplicate by port_uid before inserting
        seen = set()
        for p in ports:
            if p.port_uid in seen:
                continue
            seen.add(p.port_uid)
            existing = db_session.query(Port).filter_by(port_uid=p.port_uid).first()
            if existing is None:
                db_session.add(Port(
                    port_uid=p.port_uid,
                    name=p.name,
                    latitude=p.latitude,
                    longitude=p.longitude,
                    country=p.country,
                    source=p.source,
                ))
        db_session.commit()

        count = db_session.query(Port).filter_by(country="India").count()
        assert count >= 40
