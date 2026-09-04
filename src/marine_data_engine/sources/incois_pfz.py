"""INCOIS PFZ source adapter.

The INCOIS PFZ advisory entry page is wire-verified
(``https://incois.gov.in/MarineFisheries/PfzAdvisory``) but the machine
geometry/XHR endpoint is UNVERIFIED (source_mapping §5.1, HAR-A). Therefore:

- the fixture adapter parses a deterministic GeoJSON FeatureCollection that
  mirrors the documented ``pfz`` entity contract; and
- the live connector is DISABLED and refuses to run, since fabricating a
  geometry endpoint is explicitly prohibited until HAR-A confirms it.

PFZ fields (source_mapping §5.1 / §7.5): geometry, issue_time,
valid_from/until, region, advisory_text, species/advisory_type, sst_context,
chlorophyll_context, confidence, source_url.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from dateutil import parser as dtparser

from ..config import get_settings
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedPFZ,
    RawPayload,
)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return dtparser.parse(value)


def parse_pfz_featurecollection(
    geojson_bytes: bytes, *, source_url: str | None = None
) -> list[ParsedPFZ]:
    """Parse a GeoJSON FeatureCollection of PFZ advisories."""
    fc = json.loads(geojson_bytes)
    features = fc.get("features", []) if isinstance(fc, dict) else []
    parsed: list[ParsedPFZ] = []
    for feat in features:
        props = feat.get("properties", {}) or {}
        geom = feat.get("geometry")
        parsed.append(
            ParsedPFZ(
                pfz_uid=str(props.get("pfz_id") or props.get("id") or ""),
                region=props.get("region"),
                advisory_text=props.get("advisory_text"),
                advisory_type=props.get("advisory_type") or props.get("species"),
                geometry=geom,
                issue_time=_parse_dt(props.get("issue_time")),
                valid_from=_parse_dt(props.get("valid_from")),
                valid_until=_parse_dt(props.get("valid_until")),
                sst_context=props.get("sst_context"),
                chlorophyll_context=props.get("chlorophyll_context"),
                confidence=props.get("confidence"),
                source_url=source_url,
            )
        )
    return parsed


class INCOISPfzFixtureAdapter:
    """Deterministic offline INCOIS PFZ adapter reading a fixture GeoJSON."""

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
        return FetchResult(raw=raw, pfz=pfz)


class INCOISPfzLiveAdapter:
    """Live INCOIS PFZ connector — DISABLED (machine endpoint unverified).

    Per source_mapping §5.1, the PFZ machine geometry endpoint is a P0
    prerequisite that requires HAR-A verification. Until confirmed, this
    connector refuses to run rather than guessing an endpoint or fabricating
    geometry.
    """

    provider = "INCOIS"
    dataset = "incois_pfz"
    ENTRY_PAGE = "https://incois.gov.in/MarineFisheries/PfzAdvisory"

    def __init__(self) -> None:
        self.live_enabled = get_settings().service.enable_live_sources

    def fetch(self) -> FetchResult:
        raise LiveSourceDisabledError(
            "INCOIS PFZ live connector is disabled: the machine geometry endpoint "
            "is UNVERIFIED (requires HAR-A). Use the fixture adapter until the "
            "endpoint is confirmed. Legal/authoritative geometry must not be "
            "fabricated (requirements rule 11)."
        )
