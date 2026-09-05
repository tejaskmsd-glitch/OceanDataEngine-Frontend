"""INCOIS Potential Fishing Zone (PFZ) live adapter.

The verified current machine contract exposes advisory destination ``Point``
features at ``/api/ws/pfz`` and advisory ``LineString`` features at
``/api/ws/pfzLines``. These geometries are preserved exactly: lines are never
closed, buffered, or relabelled as polygons.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from dateutil import parser as dtparser

from ..config import get_settings
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedPFZ,
    RawPayload,
    SourceContractError,
    SourceUnavailableError,
)

PFZ_POINTS_URL = "https://gemini.incois.gov.in/api/ws/pfz"
PFZ_LINES_URL = "https://gemini.incois.gov.in/api/ws/pfzLines"
_HTTP_TIMEOUT_S = 30
_USER_AGENT = "marine-data-engine/0.1 (+incois-pfz)"
_COLLECTION_DATE_RE = re.compile(r"^(?P<date>\d{2}[A-Za-z]{3}\d{4})[A-Za-z]*$")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return dtparser.parse(value)
    except (ValueError, OverflowError, TypeError):
        return None


def parse_pfz_featurecollection(
    geojson_bytes: bytes, *, source_url: str | None = None
) -> list[ParsedPFZ]:
    """Parse the deterministic legacy fixture contract used by unit tests."""
    fc = json.loads(geojson_bytes)
    features = fc.get("features", []) if isinstance(fc, dict) else []
    parsed: list[ParsedPFZ] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties", {}) or {}
        if not isinstance(props, dict):
            continue
        parsed.append(
            ParsedPFZ(
                pfz_uid=str(props.get("pfz_id") or props.get("id") or ""),
                region=props.get("region"),
                advisory_text=props.get("advisory_text"),
                advisory_type=props.get("advisory_type") or props.get("species"),
                geometry=feat.get("geometry"),
                issue_time=_parse_dt(props.get("issue_time")),
                valid_from=_parse_dt(props.get("valid_from")),
                valid_until=_parse_dt(props.get("valid_until")),
                sst_context=props.get("sst_context"),
                chlorophyll_context=props.get("chlorophyll_context"),
                confidence=props.get("confidence"),
                source_url=source_url,
                source_metadata={"fixture_contract": True},
            )
        )
    return parsed


def _geometry_digest(geometry: dict) -> str:
    canonical = json.dumps(geometry, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _collection_date(name: object) -> str | None:
    match = _COLLECTION_DATE_RE.fullmatch(str(name or ""))
    if match is None:
        return None
    try:
        return datetime.strptime(match.group("date"), "%d%b%Y").date().isoformat()
    except ValueError:
        return None


def _number_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def parse_live_pfz(
    point_data: bytes,
    line_data: bytes,
    *,
    point_url: str = PFZ_POINTS_URL,
    line_url: str = PFZ_LINES_URL,
) -> tuple[list[ParsedPFZ], list[str]]:
    """Parse verified PFZ point and line FeatureCollections."""
    try:
        point_fc = json.loads(point_data)
        line_fc = json.loads(line_data)
    except json.JSONDecodeError as exc:
        raise SourceContractError("INCOIS PFZ response is not valid JSON") from exc
    for label, collection in (("pfz", point_fc), ("pfzLines", line_fc)):
        if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
            raise SourceContractError(f"INCOIS {label} must be a GeoJSON FeatureCollection")
        if not isinstance(collection.get("features", []), list):
            raise SourceContractError(f"INCOIS {label}.features must be an array")

    snapshot_name = str(line_fc.get("name") or "unversioned")
    snapshot_date = _collection_date(snapshot_name)
    diagnostics: list[str] = []
    records: list[ParsedPFZ] = []

    for index, feature in enumerate(point_fc.get("features") or []):
        if not isinstance(feature, dict):
            diagnostics.append(f"pfz point feature {index} is not an object")
            continue
        geometry = feature.get("geometry")
        props = feature.get("properties") or {}
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            diagnostics.append(f"pfz point feature {index} has non-Point geometry")
            continue
        if not isinstance(props, dict):
            diagnostics.append(f"pfz point feature {index} has invalid properties")
            continue
        coords = geometry.get("coordinates")
        if not isinstance(coords, list) or len(coords) < 2:
            diagnostics.append(f"pfz point feature {index} has invalid coordinates")
            continue

        landing = str(props.get("LANDINGNAM") or "").strip() or None
        state = str(props.get("STATENAME") or "").strip() or None
        country_code = str(props.get("COUNTRY") or "").strip() or None
        uid_seed = country_code or landing or _number_text(feature.get("id")) or str(index)
        uid = f"pfz-point:{snapshot_name}:{uid_seed}:{_geometry_digest(geometry)}"
        detail_parts: list[str] = []
        if props.get("Distance") is not None:
            detail_parts.append(f"{props['Distance']} km")
        if props.get("Direction"):
            detail_parts.append(str(props["Direction"]))
        if props.get("Angle") is not None:
            detail_parts.append(f"{props['Angle']} degrees")
        if props.get("Depth") is not None:
            detail_parts.append(f"depth {props['Depth']} m")
        advisory_text = (
            f"PFZ destination point from {landing}: " + ", ".join(detail_parts)
            if landing and detail_parts
            else None
        )
        records.append(
            ParsedPFZ(
                pfz_uid=uid,
                region=", ".join(part for part in (landing, state) if part) or None,
                advisory_text=advisory_text,
                advisory_type="destination_point",
                geometry=geometry,
                # Neither feed exposes an issue timestamp or validity interval.
                issue_time=None,
                valid_from=None,
                valid_until=None,
                source_url=point_url,
                provider="INCOIS",
                source_dataset="incois_pfz",
                source_metadata={
                    "geometry_type": "Point",
                    "snapshot_name": snapshot_name,
                    "snapshot_date": snapshot_date,
                    "feature_id": feature.get("id"),
                    "properties": props,
                    "crs": point_fc.get("crs"),
                },
            )
        )

    for index, feature in enumerate(line_fc.get("features") or []):
        if not isinstance(feature, dict):
            diagnostics.append(f"pfz line feature {index} is not an object")
            continue
        geometry = feature.get("geometry")
        props = feature.get("properties") or {}
        if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
            diagnostics.append(f"pfz line feature {index} has non-LineString geometry")
            continue
        if not isinstance(props, dict):
            diagnostics.append(f"pfz line feature {index} has invalid properties")
            continue
        coords = geometry.get("coordinates")
        if not isinstance(coords, list) or len(coords) < 2:
            diagnostics.append(f"pfz line feature {index} has invalid coordinates")
            continue

        upstream_uid = _number_text(props.get("UID"))
        uid_seed = upstream_uid or _number_text(feature.get("id")) or str(index)
        upstream_year = _number_text(props.get("Year"))
        year_conflict = bool(
            snapshot_date
            and upstream_year
            and upstream_year != snapshot_date[:4]
        )
        records.append(
            ParsedPFZ(
                pfz_uid=(
                    f"pfz-line:{snapshot_name}:{uid_seed}:{_geometry_digest(geometry)}"
                ),
                region=props.get("SECTORNAME"),
                advisory_text=None,
                advisory_type="advisory_line",
                geometry=geometry,
                issue_time=None,
                valid_from=None,
                valid_until=None,
                source_url=line_url,
                provider="INCOIS",
                source_dataset="incois_pfz",
                source_metadata={
                    "geometry_type": "LineString",
                    "snapshot_name": snapshot_name,
                    "snapshot_date": snapshot_date,
                    "properties": props,
                    "crs": line_fc.get("crs"),
                    "metadata_year_conflicts_with_snapshot": year_conflict,
                    "geometry_policy": "preserved LineString; not closed or buffered",
                },
            )
        )
    return records, diagnostics


class INCOISPfzFixtureAdapter:
    """Explicit deterministic fixture adapter; never selected in production."""

    provider = "INCOIS"
    dataset = "incois_pfz"
    live_enabled = False

    def __init__(self, geojson_bytes: bytes, *, source_url: str | None = None) -> None:
        self._data = geojson_bytes
        self._source_url = source_url or "fixture://incois/pfz"

    def fetch(self) -> FetchResult:
        pfz = parse_pfz_featurecollection(self._data, source_url=self._source_url)
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=self._data,
            ext="geojson",
            media_type="application/geo+json",
            source_url=self._source_url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw, pfz=pfz, result_state="empty" if not pfz else "success")


class INCOISPfzLiveAdapter:
    """Verified live PFZ destination-point and advisory-line connector."""

    provider = "INCOIS"
    dataset = "incois_pfz"

    def __init__(
        self,
        *,
        point_url: str = PFZ_POINTS_URL,
        line_url: str = PFZ_LINES_URL,
        live_enabled: bool | None = None,
    ) -> None:
        self.live_enabled = (
            get_settings().service.enable_live_sources if live_enabled is None else live_enabled
        )
        self.point_url = point_url
        self.line_url = line_url

    @staticmethod
    def _http_get(url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/geo+json,application/json"},
        )
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) as response:  # noqa: S310
            status = getattr(response, "status", response.getcode())
            if status not in {200, 202}:
                raise SourceUnavailableError(f"INCOIS PFZ HTTP {status} for {url}")
            return response.read()

    def fetch(self) -> FetchResult:
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "INCOIS PFZ live connector is disabled by MDE_ENABLE_LIVE_SOURCES"
            )
        try:
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="incois-pfz") as pool:
                points_future = pool.submit(self._http_get, self.point_url)
                lines_future = pool.submit(self._http_get, self.line_url)
                point_data = points_future.result()
                line_data = lines_future.result()
        except SourceUnavailableError:
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise SourceUnavailableError(f"INCOIS PFZ fetch failed: {exc}") from exc

        pfz, diagnostics = parse_live_pfz(
            point_data,
            line_data,
            point_url=self.point_url,
            line_url=self.line_url,
        )
        retrieved_at = datetime.now(tz=UTC)
        raw_envelope = json.dumps(
            {
                "retrieved_at": retrieved_at.isoformat(),
                "responses": {
                    self.point_url: json.loads(point_data),
                    self.line_url: json.loads(line_data),
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        state = "degraded" if diagnostics else ("empty" if not pfz else "success")
        return FetchResult(
            raw=RawPayload(
                provider=self.provider,
                dataset=self.dataset,
                data=raw_envelope,
                ext="json",
                media_type="application/json",
                source_url=self.point_url,
                retrieved_at=retrieved_at,
            ),
            pfz=pfz,
            result_state=state,
            status_detail="source healthy but PFZ feeds are empty" if state == "empty" else None,
            diagnostics=diagnostics,
        )
