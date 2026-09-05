"""Rigorous contract tests for the rewritten real-time source connectors.

These tests exercise the *live* parsers/adapters of the rewritten INCOIS HWA/SSA,
INCOIS PFZ, INCOIS TEWS tide, INCOIS OON buoy, IMD NWP, and Marine Regions EEZ
connectors against synthetic representations of their verified upstream
contracts.

All fixtures under ``tests/fixtures/realtime_contracts/`` are explicitly
synthetic and TEST-ONLY: they reproduce the *shape* of each verified contract
(nested double-encoded JSON, GeoJSON geometry types, TEWS station XML,
server-rendered Highcharts pages, WFS FeatureCollections) without asserting any
real-world value.

The tests deliberately do not perform network I/O. Live adapter transport is
either disabled (raising the documented state error) or monkeypatched with an
``_http_get`` that returns fixture bytes, so no outbound request is ever made.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import ssl
import subprocess
import sys
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from marine_data_engine.sources.base import (
    LiveSourceDisabledError,
    SourceContractError,
    SourceContractUnavailableError,
    SourceLicenseRequiredError,
)

CONTRACTS = Path(__file__).parent / "fixtures" / "realtime_contracts"
_IST = ZoneInfo("Asia/Kolkata")


def _load(name: str) -> bytes:
    return (CONTRACTS / name).read_bytes()


# ---------------------------------------------------------------------------
# INCOIS High Wave Alert / Swell Surge (nested double-decoded JSON)
# ---------------------------------------------------------------------------


class TestIncoisHwaLiveContract:
    def _fixtures(self) -> tuple[bytes, bytes]:
        return _load("incois_hwa_live.json"), _load("incois_hwa_districts.geojson")

    def test_double_decoded_json_and_geometry_join(self):
        from marine_data_engine.sources.incois_hwa import parse_live_high_wave_alerts

        alert_data, geometry_data = self._fixtures()
        alerts, diagnostics = parse_live_high_wave_alerts(alert_data, geometry_data)

        # 2 HWA + 1 SSA entries, all with joinable geometry.
        assert len(alerts) == 3
        by_area = {a.area_description: a for a in alerts}

        tn = by_area["KANNIYAKUMARI, TAMIL NADU"]
        assert tn.event_type == "high_wave"
        assert tn.severity == "severe"  # ORANGE
        assert tn.geometry is not None and tn.geometry["type"] == "Polygon"

        kl = by_area["THIRUVANANTHAPURAM, KERALA"]
        assert kl.event_type == "high_wave"
        assert kl.severity == "moderate"  # YELLOW
        assert kl.geometry is not None and kl.geometry["type"] == "MultiPolygon"

        ap = by_area["NELLORE, ANDHRA PRADESH"]
        assert ap.event_type == "swell_surge"
        assert ap.severity == "extreme"  # RED
        assert ap.geometry is not None

        # Every alert has a joined, unambiguous geometry -> no missing-geometry
        # diagnostics were raised.
        assert not any("missing unambiguous geometry" in d for d in diagnostics)

    def test_validity_parsed_as_india_standard_time(self):
        from marine_data_engine.sources.incois_hwa import parse_live_high_wave_alerts

        alert_data, geometry_data = self._fixtures()
        alerts, diagnostics = parse_live_high_wave_alerts(alert_data, geometry_data)

        tn = next(a for a in alerts if a.area_description.startswith("KANNIYAKUMARI"))
        # "during 11:30 hours on 04-09-2026 to 23:30 hours on 04-09-2026" (IST).
        assert tn.effective_from == datetime(2026, 9, 4, 11, 30, tzinfo=_IST)
        assert tn.valid_until == datetime(2026, 9, 4, 23, 30, tzinfo=_IST)
        # IST is UTC+5:30 -> the UTC instant must reflect that offset.
        assert tn.effective_from.astimezone(UTC) == datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
        assert tn.source_metadata["validity_timezone"] == "Asia/Kolkata"
        # Kerala window crosses midnight into the next day and must still parse.
        kl = next(a for a in alerts if a.area_description.startswith("THIRUVANANTHAPURAM"))
        assert kl.valid_until == datetime(2026, 9, 5, 2, 0, tzinfo=_IST)
        assert not any("unparsed validity" in d for d in diagnostics)

    def test_issue_time_is_never_invented(self):
        from marine_data_engine.sources.incois_hwa import parse_live_high_wave_alerts

        alert_data, geometry_data = self._fixtures()
        alerts, _ = parse_live_high_wave_alerts(alert_data, geometry_data)
        # The source exposes only an issue *date*, so issued_at stays None.
        assert all(a.issued_at is None for a in alerts)

    def test_validity_helper_rejects_reversed_and_nonmatching(self):
        from marine_data_engine.sources.incois_hwa import parse_alert_validity

        assert parse_alert_validity(None) == (None, None)
        assert parse_alert_validity("no validity phrase here") == (None, None)
        reversed_phrase = (
            "during 23:30 hours on 04-09-2026 to 11:30 hours on 04-09-2026"
        )
        assert parse_alert_validity(reversed_phrase) == (None, None)

    def test_unknown_colour_and_alert_type_are_flagged_not_guessed(self):
        from marine_data_engine.sources.incois_hwa import parse_live_high_wave_alerts

        alert_doc = {
            "LatestHWADate": "2026-09-04",
            "HWAJson": json.dumps(
                [
                    {
                        "OBJECTID": 9,
                        "STATE": "Goa",
                        "District": "North Goa",
                        "Alert": "MYSTERY ALERT",
                        "Color": "PURPLE",
                        "Message": "no validity phrase",
                    }
                ]
            ),
            "SSAJson": "[]",
        }
        geometry_doc = {"type": "FeatureCollection", "features": []}
        alerts, diagnostics = parse_live_high_wave_alerts(
            json.dumps(alert_doc).encode(), json.dumps(geometry_doc).encode()
        )
        assert len(alerts) == 1
        assert alerts[0].severity == "unknown"
        assert alerts[0].event_type == "marine_hazard"
        assert any("unknown HWA colour" in d for d in diagnostics)
        assert any("unknown HWA alert type" in d for d in diagnostics)
        assert any("missing unambiguous geometry" in d for d in diagnostics)

    def test_ambiguous_district_geometry_is_dropped(self):
        from marine_data_engine.sources.incois_hwa import parse_live_high_wave_alerts

        alert_doc = {
            "LatestHWADate": "2026-09-04",
            "HWAJson": json.dumps(
                [
                    {
                        "OBJECTID": 1,
                        "STATE": "Kerala",
                        "District": "Ernakulam",
                        "Alert": "HIGH WAVE WARNING",
                        "Color": "ORANGE",
                        "Message": (
                            "waves during 06:00 hours on 04-09-2026 to "
                            "12:00 hours on 04-09-2026"
                        ),
                    }
                ]
            ),
            "SSAJson": "[]",
        }
        poly = {
            "type": "Polygon",
            "coordinates": [[[76.0, 9.0], [76.5, 9.0], [76.5, 9.5], [76.0, 9.5], [76.0, 9.0]]],
        }
        feat = {
            "type": "Feature",
            "properties": {"STATE": "Kerala", "District": "Ernakulam"},
            "geometry": poly,
        }
        geometry_doc = {
            "type": "FeatureCollection",
            "features": [feat, dict(feat)],
        }
        alerts, diagnostics = parse_live_high_wave_alerts(
            json.dumps(alert_doc).encode(), json.dumps(geometry_doc).encode()
        )
        assert len(alerts) == 1
        assert alerts[0].geometry is None
        assert any("ambiguous district geometry" in d for d in diagnostics)
        assert any("missing unambiguous geometry" in d for d in diagnostics)

    def test_healthy_empty_response(self):
        from marine_data_engine.sources.incois_hwa import parse_live_high_wave_alerts

        alert_doc = {"LatestHWADate": None, "HWAJson": "[]", "SSAJson": "[]"}
        geometry_doc = {"type": "FeatureCollection", "features": []}
        alerts, diagnostics = parse_live_high_wave_alerts(
            json.dumps(alert_doc).encode(), json.dumps(geometry_doc).encode()
        )
        assert alerts == []
        assert diagnostics == []

    def test_embedded_list_rejects_non_json_and_non_array(self):
        from marine_data_engine.sources.incois_hwa import parse_live_high_wave_alerts

        geometry_doc = json.dumps({"type": "FeatureCollection", "features": []}).encode()
        bad_embedded = json.dumps(
            {"LatestHWADate": "x", "HWAJson": "{not json", "SSAJson": "[]"}
        ).encode()
        with pytest.raises(SourceContractError):
            parse_live_high_wave_alerts(bad_embedded, geometry_doc)

        non_array = json.dumps({"HWAJson": json.dumps({"a": 1}), "SSAJson": "[]"}).encode()
        with pytest.raises(SourceContractError):
            parse_live_high_wave_alerts(non_array, geometry_doc)

    def test_top_level_and_geometry_shape_enforced(self):
        from marine_data_engine.sources.incois_hwa import parse_live_high_wave_alerts

        good_geo = json.dumps({"type": "FeatureCollection", "features": []}).encode()
        with pytest.raises(SourceContractError):
            parse_live_high_wave_alerts(json.dumps([1, 2, 3]).encode(), good_geo)
        with pytest.raises(SourceContractError):
            parse_live_high_wave_alerts(
                json.dumps({"HWAJson": "[]", "SSAJson": "[]"}).encode(),
                json.dumps({"type": "NotACollection"}).encode(),
            )

    def test_live_adapter_disabled_makes_no_request(self):
        from marine_data_engine.sources.incois_hwa import INCOISHighWaveLiveAdapter

        adapter = INCOISHighWaveLiveAdapter(live_enabled=False)
        with pytest.raises(LiveSourceDisabledError):
            adapter.fetch()

    def test_http_transport_decodes_gzip_magic(self, monkeypatch):
        from marine_data_engine.sources.incois_hwa import INCOISHighWaveLiveAdapter

        expected = b'{"HWAJson":"[]","SSAJson":"[]"}'

        class Response:
            status = 200
            headers = {}

            @staticmethod
            def getcode():
                return 200

            @staticmethod
            def read():
                return gzip.compress(expected)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        monkeypatch.setattr(
            "marine_data_engine.sources.incois_hwa.urllib.request.urlopen",
            lambda *_args, **_kwargs: Response(),
        )
        assert INCOISHighWaveLiveAdapter._http_get("https://example.test/hwa") == expected

    def test_live_adapter_fetch_via_monkeypatched_transport(self, monkeypatch):
        from marine_data_engine.sources import incois_hwa
        from marine_data_engine.sources.incois_hwa import INCOISHighWaveLiveAdapter

        alert_data, geometry_data = self._fixtures()

        def fake_get(url: str) -> bytes:
            return alert_data if "hwassalatestdata" in url else geometry_data

        monkeypatch.setattr(
            incois_hwa.INCOISHighWaveLiveAdapter, "_http_get", staticmethod(fake_get)
        )
        adapter = INCOISHighWaveLiveAdapter(live_enabled=True)
        result = adapter.fetch()
        assert result.result_state == "success"
        assert len(result.alerts) == 3
        # The raw envelope preserves both decoded upstream responses verbatim.
        envelope = json.loads(result.raw.data)
        assert set(envelope["responses"]) == {adapter.alert_url, adapter.geometry_url}


# ---------------------------------------------------------------------------
# INCOIS PFZ (source-native Point + LineString preservation)
# ---------------------------------------------------------------------------


class TestIncoisPfzLiveContract:
    def _fixtures(self) -> tuple[bytes, bytes]:
        return _load("incois_pfz_points.geojson"), _load("incois_pfz_lines.geojson")

    def test_point_and_line_geometry_preserved_exactly(self):
        from marine_data_engine.sources.incois_pfz import parse_live_pfz

        point_data, line_data = self._fixtures()
        records, diagnostics = parse_live_pfz(point_data, line_data)
        assert diagnostics == []

        points = [r for r in records if r.advisory_type == "destination_point"]
        lines = [r for r in records if r.advisory_type == "advisory_line"]
        assert len(points) == 2
        assert len(lines) == 2

        for p in points:
            assert p.geometry["type"] == "Point"
            assert p.source_metadata["geometry_type"] == "Point"
        for line in lines:
            assert line.geometry["type"] == "LineString"
            assert line.source_metadata["geometry_type"] == "LineString"
            # LineString must never be closed/buffered/relabelled.
            coords = line.geometry["coordinates"]
            assert coords[0] != coords[-1]
            assert line.source_metadata["geometry_policy"].startswith("preserved LineString")

    def test_line_coordinates_are_byte_for_byte_intact(self):
        from marine_data_engine.sources.incois_pfz import parse_live_pfz

        point_data, line_data = self._fixtures()
        original = json.loads(line_data)
        records, _ = parse_live_pfz(point_data, line_data)
        line_geoms = [r.geometry for r in records if r.advisory_type == "advisory_line"]
        original_geoms = [f["geometry"] for f in original["features"]]
        assert line_geoms == original_geoms

    def test_conflicting_upstream_year_metadata_is_flagged_without_mutation(self):
        from marine_data_engine.sources.incois_pfz import parse_live_pfz

        point_data, line_data = self._fixtures()
        records, _ = parse_live_pfz(point_data, line_data)
        lines = [r for r in records if r.advisory_type == "advisory_line"]
        by_sector = {r.region: r for r in lines}
        # Line with Year=2026 agrees with the 04Sep2026 snapshot.
        assert by_sector["Karnataka North"].source_metadata[
            "metadata_year_conflicts_with_snapshot"
        ] is False
        # Line with Year=2025 conflicts and must be flagged (metadata only).
        assert by_sector["Maharashtra South"].source_metadata[
            "metadata_year_conflicts_with_snapshot"
        ] is True
        assert by_sector["Maharashtra South"].source_metadata["snapshot_date"] == "2026-09-04"

    def test_non_point_and_non_linestring_geometry_rejected_as_diagnostics(self):
        from marine_data_engine.sources.incois_pfz import parse_live_pfz

        point_fc = {
            "type": "FeatureCollection",
            "name": "PFZ_04Sep2026",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"LANDINGNAM": "X"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                    },
                }
            ],
        }
        line_fc = {
            "type": "FeatureCollection",
            "name": "04Sep2026",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"UID": 1},
                    "geometry": {"type": "Point", "coordinates": [1, 1]},
                }
            ],
        }
        records, diagnostics = parse_live_pfz(
            json.dumps(point_fc).encode(), json.dumps(line_fc).encode()
        )
        assert records == []
        assert any("non-Point geometry" in d for d in diagnostics)
        assert any("non-LineString geometry" in d for d in diagnostics)

    def test_invalid_json_and_non_featurecollection_rejected(self):
        from marine_data_engine.sources.incois_pfz import parse_live_pfz

        good = json.dumps({"type": "FeatureCollection", "features": []}).encode()
        with pytest.raises(SourceContractError):
            parse_live_pfz(b"{not json", good)
        with pytest.raises(SourceContractError):
            parse_live_pfz(json.dumps({"type": "Nope"}).encode(), good)

    def test_live_adapter_disabled_makes_no_request(self):
        from marine_data_engine.sources.incois_pfz import INCOISPfzLiveAdapter

        with pytest.raises(LiveSourceDisabledError):
            INCOISPfzLiveAdapter(live_enabled=False).fetch()

    def test_live_adapter_fetch_via_monkeypatched_transport(self, monkeypatch):
        from marine_data_engine.sources import incois_pfz
        from marine_data_engine.sources.incois_pfz import INCOISPfzLiveAdapter

        point_data, line_data = self._fixtures()

        def fake_get(url: str) -> bytes:
            return line_data if url.endswith("pfzLines") else point_data

        monkeypatch.setattr(incois_pfz.INCOISPfzLiveAdapter, "_http_get", staticmethod(fake_get))
        result = INCOISPfzLiveAdapter(live_enabled=True).fetch()
        assert result.result_state == "success"
        assert result.record_count == 4


# ---------------------------------------------------------------------------
# INCOIS TEWS tide (station XML + explicit latest sensor values)
# ---------------------------------------------------------------------------


class TestIncoisTewsLiveContract:
    def test_station_xml_parsed_with_diagnostics(self):
        from marine_data_engine.sources.incois_tide import parse_tews_station_xml

        stations, diagnostics = parse_tews_station_xml(_load("tews_stations.xml"))
        # 5 station nodes; the out-of-range one is dropped, bad-date kept with note.
        codes = {s.code for s in stations}
        assert {"chnn", "vskp", "okha", "baddate"} <= codes
        assert "badcoord" not in codes
        assert any("out of range" in d for d in diagnostics)
        assert any("unparsed station date" in d for d in diagnostics)

        chennai = next(s for s in stations if s.code == "chnn")
        assert chennai.parsed.station_uid == "TEWS:chnn"
        assert chennai.parsed.status == "reporting"
        assert chennai.parsed.station_type == "tide_gauge"
        assert chennai.parsed.source_metadata["catalog_date_timezone"] == "UTC"

    def test_not_reporting_date_sentinel_is_not_a_parse_diagnostic(self):
        from marine_data_engine.sources.incois_tide import parse_tews_station_xml

        data = b"""<stations><station status="notreporting">
          <statname>off</statname><statrealName>Offline</statrealName>
          <latitude>10</latitude><longitude>70</longitude>
          <date>Not Reporting</date>
        </station></stations>"""
        stations, diagnostics = parse_tews_station_xml(data)
        assert diagnostics == []
        assert len(stations) == 1
        assert stations[0].parsed.status == "notreporting"
        assert stations[0].parsed.last_reported_at is None
        assert stations[0].parsed.source_metadata["catalog_date"] == "Not Reporting"

    def test_station_xml_rejects_non_xml_and_wrong_root(self):
        from marine_data_engine.sources.incois_tide import parse_tews_station_xml

        with pytest.raises(SourceContractError):
            parse_tews_station_xml(b"<<<not xml")
        with pytest.raises(SourceContractError):
            parse_tews_station_xml(b"<root></root>")

    def _station(self):
        from marine_data_engine.sources.incois_tide import parse_tews_station_xml

        stations, _ = parse_tews_station_xml(_load("tews_stations.xml"))
        return next(s for s in stations if s.code == "chnn")

    def _series_bytes(self, rad_dt, prs_dt, enc_dt) -> bytes:
        template = _load("tews_observation_series.json").decode()
        template = template.replace("__RAD_TIME__", rad_dt)
        template = template.replace("__PRS_TIME__", prs_dt)
        template = template.replace("__ENC_TIME__", enc_dt)
        return template.encode()

    def test_only_explicit_latest_rad_prs_enc_values_used(self):
        from marine_data_engine.sources.incois_tide import parse_tews_observation_series

        retrieved_at = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
        fresh = "2026-09-04 11:30"
        data = self._series_bytes(fresh, fresh, fresh)
        observations, diagnostics = parse_tews_observation_series(
            data, self._station(), source_url="test://tews", retrieved_at=retrieved_at
        )
        # RAD and PRS are numeric+fresh; ENC is non-numeric -> rejected.
        # Predicted/Residual are never treated as observations.
        sensors = {o.sensor_id for o in observations}
        assert sensors == {"RAD", "PRS"}
        assert all(o.parameter == "water_level" and o.unit == "m" for o in observations)
        assert all(o.station_id == "TEWS:chnn" for o in observations)
        assert any("ENC" in d for d in diagnostics)
        # Predicted/Residual must never appear in diagnostics as rejected obs.
        assert not any("Predicted" in d or "Residual" in d for d in diagnostics)

    def test_malformed_historical_x_values_are_never_used(self):
        from marine_data_engine.sources.incois_tide import parse_tews_observation_series

        retrieved_at = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
        fresh = "2026-09-04 11:30"
        data = self._series_bytes(fresh, fresh, fresh)
        observations, _ = parse_tews_observation_series(
            data, self._station(), source_url="test://tews", retrieved_at=retrieved_at
        )
        # Values come only from explicit lastreportedvalue, never the malformed
        # 'data' arrays (which contain non-epoch x-values like "bad-x-0").
        rad = next(o for o in observations if o.sensor_id == "RAD")
        assert rad.value == pytest.approx(1.234)
        assert rad.observed_at == datetime(2026, 9, 4, 11, 30, tzinfo=UTC)
        assert rad.source_metadata["historical_data_x_values_ignored"] is True

    def test_stale_and_future_values_rejected(self):
        from marine_data_engine.sources.incois_tide import parse_tews_observation_series

        retrieved_at = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
        stale = "2026-09-01 11:30"  # > 24h old
        future = "2026-09-04 14:00"  # > 15 min ahead
        enc = "2026-09-04 11:30"  # non-numeric value anyway
        data = self._series_bytes(stale, future, enc)
        observations, diagnostics = parse_tews_observation_series(
            data, self._station(), source_url="test://tews", retrieved_at=retrieved_at
        )
        assert observations == []
        assert any("outside freshness policy" in d for d in diagnostics)

    def test_empty_series_is_healthy_empty(self):
        from marine_data_engine.sources.incois_tide import parse_tews_observation_series

        observations, diagnostics = parse_tews_observation_series(
            b"[]",
            self._station(),
            source_url="test://tews",
            retrieved_at=datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
        )
        assert observations == []
        assert diagnostics == []

    def test_series_rejects_non_json_and_non_array(self):
        from marine_data_engine.sources.incois_tide import parse_tews_observation_series

        rat = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
        with pytest.raises(SourceContractError):
            parse_tews_observation_series(
                b"{not json", self._station(), source_url="t", retrieved_at=rat
            )
        with pytest.raises(SourceContractError):
            parse_tews_observation_series(
                b"{\"a\": 1}", self._station(), source_url="t", retrieved_at=rat
            )

    def test_live_adapter_disabled_makes_no_request(self):
        from marine_data_engine.sources.incois_tide import INCOISTideLiveAdapter

        with pytest.raises(LiveSourceDisabledError):
            INCOISTideLiveAdapter(live_enabled=False).fetch()

    def test_tls_module_imports_cleanly_in_fresh_interpreter(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import ssl; "
                    "from marine_data_engine.tls import build_incois_ssl_context; "
                    "context = build_incois_ssl_context(); "
                    "assert context.verify_mode == ssl.CERT_REQUIRED; "
                    "assert context.check_hostname is True"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_tls_context_bundles_intermediate_and_transport_uses_it(self, monkeypatch):
        from marine_data_engine.sources.incois_tide import INCOISTideLiveAdapter
        from marine_data_engine.tls import build_incois_ssl_context

        context = build_incois_ssl_context()
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True
        common_names = {
            value
            for certificate in context.get_ca_certs()
            for rdn in certificate.get("subject", ())
            for key, value in rdn
            if key == "commonName"
        }
        assert "GlobalSign RSA OV SSL CA 2018" in common_names

        captured = {}

        class Response:
            status = 200

            @staticmethod
            def getcode():
                return 200

            @staticmethod
            def read():
                return b"<stations/>"

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        def fake_urlopen(_request, *, timeout, context):
            captured.update(timeout=timeout, context=context)
            return Response()

        monkeypatch.setattr(
            "marine_data_engine.sources.incois_tide.urllib.request.urlopen", fake_urlopen
        )
        adapter = INCOISTideLiveAdapter(live_enabled=True, ssl_context=context)
        assert adapter._http_get("https://example.test/stations.xml") == b"<stations/>"
        assert captured["context"] is context
        assert captured["timeout"] > 0

    def test_live_adapter_fetch_via_monkeypatched_transport(self, monkeypatch):
        from marine_data_engine.sources import incois_tide
        from marine_data_engine.sources.incois_tide import INCOISTideLiveAdapter

        station_xml = _load("tews_stations.xml")
        # Build fresh series relative to "now" so the freshness gate passes.
        now = datetime.now(tz=UTC)
        fresh = (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M")
        template = _load("tews_observation_series.json").decode()
        series = (
            template.replace("__RAD_TIME__", fresh)
            .replace("__PRS_TIME__", fresh)
            .replace("__ENC_TIME__", fresh)
            .encode()
        )

        def fake_get(url: str) -> bytes:
            return station_xml if url.endswith(".xml") else series

        monkeypatch.setattr(
            incois_tide.INCOISTideLiveAdapter, "_http_get", staticmethod(fake_get)
        )
        result = INCOISTideLiveAdapter(live_enabled=True).fetch()
        # Only "reporting" stations are queried for observations.
        # chnn + vskp are reporting -> RAD/PRS observations for each (ENC rejected).
        assert all(o.parameter == "water_level" for o in result.observations)
        assert result.raw.media_type == "application/gzip"
        # Raw archive bundles the station XML.
        with tarfile.open(fileobj=io.BytesIO(result.raw.data), mode="r:gz") as tar:
            assert "TideStations.xml" in tar.getnames()


# ---------------------------------------------------------------------------
# INCOIS OON dynamic buoy (catalog, backend status, charts)
# ---------------------------------------------------------------------------


class TestIncoisOonLiveContract:
    def test_dynamic_station_catalog(self):
        from marine_data_engine.sources.imd_buoy import parse_oon_station_catalog

        stations = parse_oon_station_catalog(_load("oon_station_catalog.json"))
        assert {s.station_uid for s in stations} == {"BD08", "BD11", "BD09"}
        bd08 = next(s for s in stations if s.station_uid == "BD08")
        assert bd08.station_type == "buoy_omni"
        assert bd08.status == "new"
        assert bd08.source_metadata["status_semantics"] == {
            "new": "active",
            "old": "inactive",
        }
        bd11 = next(s for s in stations if s.station_uid == "BD11")
        assert bd11.station_type == "buoy_mored"

    def test_catalog_rejects_bad_identity_type_coords_and_duplicates(self):
        from marine_data_engine.sources.imd_buoy import parse_oon_station_catalog

        def _entry(**over):
            base = {
                "buoyId": "X",
                "type": "OMNI",
                "status": "new",
                "latitude": "1",
                "longitude": "1",
            }
            base.update(over)
            return base

        with pytest.raises(SourceContractError):
            parse_oon_station_catalog(b"{}")  # not an array
        with pytest.raises(SourceContractError):
            parse_oon_station_catalog(json.dumps([_entry(type="DRIFT")]).encode())
        with pytest.raises(SourceContractError):
            parse_oon_station_catalog(json.dumps([_entry(latitude="999")]).encode())
        with pytest.raises(SourceContractError):
            parse_oon_station_catalog(
                json.dumps(
                    [
                        _entry(latitude="1", longitude="1"),
                        _entry(status="old", latitude="2", longitude="2"),
                    ]
                ).encode()
            )

    def test_backend_status_keeps_latest_marker(self):
        from marine_data_engine.sources.imd_buoy import parse_oon_backend_status

        template = _load("oon_backend_status.json").decode()
        body = (
            template.replace("__BD08_OLD__", "2026-09-04 06:00:00")
            .replace("__BD08_NEW__", "2026-09-04 11:00:00")
            .replace("__BD11__", "2026-09-04 10:00:00")
            .encode()
        )
        status = parse_oon_backend_status(body)
        assert set(status) == {"BD08", "BD11"}
        # Latest marker wins for the duplicated station.
        assert status["BD08"]["reported_at"] == datetime(2026, 9, 4, 11, 0, tzinfo=UTC)

    def test_current_chart_extracts_only_final_valid_pair(self):
        from marine_data_engine.sources.imd_buoy import parse_oon_chart, parse_oon_station_catalog

        station = parse_oon_station_catalog(_load("oon_station_catalog.json"))[0]
        retrieved_at = datetime.now(tz=UTC)
        base = int((retrieved_at - timedelta(hours=2)).timestamp() * 1000)
        e1 = base
        e2 = base + 3_600_000
        e3 = int((retrieved_at - timedelta(minutes=20)).timestamp() * 1000)
        html = (
            _load("oon_chart_hm0.html")
            .decode()
            .replace("__EPOCH1__", str(e1))
            .replace("__EPOCH2__", str(e2))
            .replace("__EPOCH3__", str(e3))
            .encode()
        )
        obs = parse_oon_chart(
            html,
            station=station,
            parameter_token="hm0",
            source_url="test://oon",
            retrieved_at=retrieved_at,
        )
        assert obs is not None
        assert obs.parameter == "significant_wave_height"
        assert obs.unit == "m"
        assert obs.value == pytest.approx(1.42)  # only the final pair
        assert obs.observed_at == datetime.fromtimestamp(e3 / 1000, tz=UTC)
        assert obs.source_metadata["chart_time_axis"] == "UTC"
        assert obs.source_metadata["history_policy"] == "only final valid pair parsed"

    def test_empty_chart_is_healthy_empty(self):
        from marine_data_engine.sources.imd_buoy import parse_oon_chart, parse_oon_station_catalog

        station = parse_oon_station_catalog(_load("oon_station_catalog.json"))[0]
        html = re.sub(
            r"data:\s*\[[\s\S]*?\],\s*tooltip:",
            "data: [], tooltip:",
            _load("oon_chart_hm0.html").decode(),
        ).encode()
        obs = parse_oon_chart(
            html,
            station=station,
            parameter_token="hm0",
            source_url="test://oon",
            retrieved_at=datetime.now(tz=UTC),
        )
        assert obs is None

    def test_stale_chart_value_rejected(self):
        from marine_data_engine.sources.imd_buoy import (
            BuoyStructureError,
            parse_oon_chart,
            parse_oon_station_catalog,
        )

        station = parse_oon_station_catalog(_load("oon_station_catalog.json"))[0]
        retrieved_at = datetime.now(tz=UTC)
        stale = int((retrieved_at - timedelta(days=3)).timestamp() * 1000)
        html = (
            _load("oon_chart_hm0.html")
            .decode()
            .replace("__EPOCH1__", str(stale))
            .replace("__EPOCH2__", str(stale))
            .replace("__EPOCH3__", str(stale))
            .encode()
        )
        with pytest.raises(BuoyStructureError):
            parse_oon_chart(
                html,
                station=station,
                parameter_token="hm0",
                source_url="test://oon",
                retrieved_at=retrieved_at,
            )

    def test_unverified_parameter_token_rejected(self):
        from marine_data_engine.sources.imd_buoy import parse_oon_chart, parse_oon_station_catalog

        station = parse_oon_station_catalog(_load("oon_station_catalog.json"))[0]
        with pytest.raises(SourceContractError):
            parse_oon_chart(
                _load("oon_chart_hm0.html"),
                station=station,
                parameter_token="salinity",
                source_url="t",
                retrieved_at=datetime.now(tz=UTC),
            )

    def test_selected_token_mismatch_rejected(self):
        from marine_data_engine.sources.imd_buoy import (
            BuoyStructureError,
            parse_oon_chart,
            parse_oon_station_catalog,
        )

        station = parse_oon_station_catalog(_load("oon_station_catalog.json"))[0]
        # Request wind_speed but the page has hm0 selected -> mismatch.
        with pytest.raises(BuoyStructureError):
            parse_oon_chart(
                _load("oon_chart_hm0.html"),
                station=station,
                parameter_token="wind_speed",
                source_url="t",
                retrieved_at=datetime.now(tz=UTC),
            )

    def test_selected_label_mismatch_rejected(self):
        from marine_data_engine.sources.imd_buoy import (
            BuoyStructureError,
            parse_oon_chart,
            parse_oon_station_catalog,
        )

        station = parse_oon_station_catalog(_load("oon_station_catalog.json"))[0]
        html = _load("oon_chart_hm0.html").decode().replace(
            ">Significant Wave Height</option>", ">Mystery Parameter</option>"
        )
        with pytest.raises(BuoyStructureError):
            parse_oon_chart(
                html.encode(),
                station=station,
                parameter_token="hm0",
                source_url="t",
                retrieved_at=datetime.now(tz=UTC),
            )

    def test_unit_mismatch_rejected(self):
        from marine_data_engine.sources.imd_buoy import (
            BuoyStructureError,
            parse_oon_chart,
            parse_oon_station_catalog,
        )

        station = parse_oon_station_catalog(_load("oon_station_catalog.json"))[0]
        html = _load("oon_chart_hm0.html").decode().replace("['m']", "['knots']")
        with pytest.raises(BuoyStructureError):
            parse_oon_chart(
                html.encode(),
                station=station,
                parameter_token="hm0",
                source_url="t",
                retrieved_at=datetime.now(tz=UTC),
            )

    def test_missing_utc_declaration_rejected(self):
        from marine_data_engine.sources.imd_buoy import (
            BuoyStructureError,
            parse_oon_chart,
            parse_oon_station_catalog,
        )

        station = parse_oon_station_catalog(_load("oon_station_catalog.json"))[0]
        html = (
            _load("oon_chart_hm0.html")
            .decode()
            .replace("useUTC: true", "useUTC: false")
            .replace("Time (UTC)", "Time (IST)")
        )
        with pytest.raises(BuoyStructureError):
            parse_oon_chart(
                html.encode(),
                station=station,
                parameter_token="hm0",
                source_url="t",
                retrieved_at=datetime.now(tz=UTC),
            )

    def test_live_adapter_disabled_makes_no_request(self):
        from marine_data_engine.sources.imd_buoy import INCOISBuoyLiveAdapter

        with pytest.raises(LiveSourceDisabledError):
            INCOISBuoyLiveAdapter(live_enabled=False).fetch()

    def test_adapter_rejects_unverified_parameter_tokens_at_construction(self):
        from marine_data_engine.sources.imd_buoy import INCOISBuoyLiveAdapter

        with pytest.raises(SourceContractError):
            INCOISBuoyLiveAdapter(parameter_tokens=("salinity",), live_enabled=False)


# ---------------------------------------------------------------------------
# IMD numeric NWP (fail-closed; no outbound guessed request)
# ---------------------------------------------------------------------------


class TestImdNwpContractUnavailable:
    def test_disabled_state(self):
        from marine_data_engine.sources.imd_nwp import IMDNwpAdapter

        with pytest.raises(LiveSourceDisabledError):
            IMDNwpAdapter(live_enabled=False).fetch()

    def test_enabled_fails_closed_as_contract_unavailable(self):
        from marine_data_engine.sources.imd_nwp import IMDNwpAdapter

        adapter = IMDNwpAdapter(live_enabled=True)
        with pytest.raises(SourceContractUnavailableError):
            adapter.fetch()
        with pytest.raises(SourceContractUnavailableError):
            adapter.fetch_marine_forecast()

    def test_no_outbound_request_even_with_legacy_token(self, monkeypatch):
        """Providing a legacy token/path must never trigger a guessed request."""
        import urllib.request

        from marine_data_engine.sources.imd_nwp import IMDNwpAdapter

        def _boom(*args, **kwargs):  # pragma: no cover - must not be called
            raise AssertionError("IMD NWP must not perform any outbound HTTP request")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        adapter = IMDNwpAdapter(
            base_url="https://api.imd.gov.in/api/v1/seabulletin",
            token="guessed-token",
            forecast_path="/nwp/marine/forecast",
            live_enabled=True,
        )
        with pytest.raises(SourceContractUnavailableError):
            adapter.fetch()
        # Legacy args are recorded but never used for a request.
        assert adapter._legacy_token_supplied is True
        assert adapter._legacy_path_supplied is True

    def test_contract_unavailable_result_state_metadata(self):
        from marine_data_engine.sources.base import SourceContractUnavailableError

        assert SourceContractUnavailableError.result_state == "contract_unavailable"
        assert SourceContractUnavailableError.retryable is False


# ---------------------------------------------------------------------------
# Marine Regions EEZ (license gate + India sovereign parser)
# ---------------------------------------------------------------------------


class TestMarineRegionsEezContract:
    def test_license_gate_blocks_before_any_fetch(self, monkeypatch):
        import urllib.request

        from marine_data_engine.sources.marine_regions import MarineRegionsEEZLiveAdapter

        def _boom(*args, **kwargs):  # pragma: no cover - must not be called
            raise AssertionError("Marine Regions must not fetch before license ack")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        adapter = MarineRegionsEEZLiveAdapter(license_acknowledgement="", live_enabled=True)
        with pytest.raises(SourceLicenseRequiredError):
            adapter.fetch()

    def test_disabled_state_takes_precedence(self):
        from marine_data_engine.sources.marine_regions import MarineRegionsEEZLiveAdapter

        adapter = MarineRegionsEEZLiveAdapter(
            license_acknowledgement="ops-reviewed-ref-123", live_enabled=False
        )
        with pytest.raises(LiveSourceDisabledError):
            adapter.fetch()

    def test_india_sovereign_parser(self):
        from marine_data_engine.sources.marine_regions import parse_india_eez

        zones = parse_india_eez(
            _load("marine_regions_india_eez.geojson"),
            source_url="test://wfs",
            license_acknowledgement="ops-reviewed-ref-123",
        )
        assert len(zones) == 2
        assert all(z.zone_type == "eez" for z in zones)
        assert all(z.geometry["type"] in {"Polygon", "MultiPolygon"} for z in zones)
        uids = {z.zone_uid for z in zones}
        assert uids == {"marine-regions:eez:8480", "marine-regions:eez:8481"}
        z = next(z for z in zones if z.zone_uid == "marine-regions:eez:8480")
        assert z.source_metadata["license_acknowledgement"] == "ops-reviewed-ref-123"
        assert z.source_metadata["dataset_version"] == "World EEZ v12"
        assert "does not provide MPA" in z.source_metadata["coverage_caveat"]

    def test_non_india_feature_rejected(self):
        from marine_data_engine.sources.marine_regions import parse_india_eez

        collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"mrgid": 1, "geoname": "Foreign EEZ", "iso_sov1": "PAK"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[60, 20], [62, 20], [62, 22], [60, 20]]],
                    },
                }
            ],
        }
        with pytest.raises(SourceContractError):
            parse_india_eez(
                json.dumps(collection).encode(),
                source_url="t",
                license_acknowledgement="ref",
            )

    def test_non_polygon_geometry_rejected(self):
        from marine_data_engine.sources.marine_regions import parse_india_eez

        collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"mrgid": 1, "geoname": "Line EEZ", "iso_sov1": "IND"},
                    "geometry": {"type": "LineString", "coordinates": [[60, 20], [62, 22]]},
                }
            ],
        }
        with pytest.raises(SourceContractError):
            parse_india_eez(
                json.dumps(collection).encode(),
                source_url="t",
                license_acknowledgement="ref",
            )

    def test_invalid_json_and_non_featurecollection_rejected(self):
        from marine_data_engine.sources.marine_regions import parse_india_eez

        with pytest.raises(SourceContractError):
            parse_india_eez(b"{not json", source_url="t", license_acknowledgement="r")
        with pytest.raises(SourceContractError):
            parse_india_eez(
                json.dumps({"type": "Nope"}).encode(),
                source_url="t",
                license_acknowledgement="r",
            )

    def test_feature_missing_mrgid_or_name_rejected(self):
        from marine_data_engine.sources.marine_regions import parse_india_eez

        collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"iso_sov1": "IND"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[60, 20], [62, 20], [62, 22], [60, 20]]],
                    },
                }
            ],
        }
        with pytest.raises(SourceContractError):
            parse_india_eez(
                json.dumps(collection).encode(),
                source_url="t",
                license_acknowledgement="ref",
            )
