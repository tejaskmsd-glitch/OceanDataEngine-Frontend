"""Authoritative Marine Regions EEZ ingestion, license-gated by design.

Marine Regions WFS layer ``MarineRegions:eez`` (World EEZ v12, 2023) is the
verified geometry source for India's mainland and Andaman/Nicobar EEZ features.
The public capabilities ask users to contact VLIZ regarding layer use, and the
exact reusable terms have not been established for this deployment. Production
therefore requires an operator-supplied license/attribution acknowledgement
before any bytes are fetched or persisted.

This module does not provide MPA, naval, firing-range, or other restricted-zone
geometry. Those categories remain explicitly unavailable pending authoritative
licensed sources.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from ..config import get_settings
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedMarineZone,
    RawPayload,
    SourceContractError,
    SourceLicenseRequiredError,
    SourceUnavailableError,
)

WFS_BASE_URL = "https://geo.vliz.be/geoserver/MarineRegions/wfs"
EEZ_LAYER = "MarineRegions:eez"
EEZ_VERSION = "World EEZ v12"
EEZ_RELEASE_DATE = "2023-10-25"
INDIA_CQL_FILTER = "iso_sov1='IND' OR iso_sov2='IND'"
_HTTP_TIMEOUT_S = 60
_USER_AGENT = "marine-data-engine/0.1 (+marine-regions-eez)"


def build_india_eez_url(base_url: str = WFS_BASE_URL) -> str:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": EEZ_LAYER,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "CQL_FILTER": INDIA_CQL_FILTER,
    }
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def _casefold_properties(properties: dict) -> dict[str, object]:
    return {str(key).lower(): value for key, value in properties.items()}


def parse_india_eez(
    data: bytes,
    *,
    source_url: str,
    license_acknowledgement: str,
) -> list[ParsedMarineZone]:
    """Parse sovereign-filtered India EEZ features without inferring geometry."""
    try:
        collection = json.loads(data)
    except json.JSONDecodeError as exc:
        raise SourceContractError("Marine Regions WFS response is not valid JSON") from exc
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise SourceContractError("Marine Regions response must be a FeatureCollection")
    features = collection.get("features") or []
    if not isinstance(features, list):
        raise SourceContractError("Marine Regions features must be an array")

    zones: list[ParsedMarineZone] = []
    seen: set[str] = set()
    for feature in features:
        if not isinstance(feature, dict):
            raise SourceContractError("Marine Regions contains a non-object feature")
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            raise SourceContractError("Marine Regions feature lacks properties/geometry")
        if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            raise SourceContractError(
                f"Marine Regions EEZ feature has unexpected geometry {geometry.get('type')!r}"
            )
        folded = _casefold_properties(properties)
        sovereign_codes = {
            str(folded.get("iso_sov1") or "").upper(),
            str(folded.get("iso_sov2") or "").upper(),
        }
        if "IND" not in sovereign_codes:
            raise SourceContractError("WFS sovereign filter returned a non-India feature")
        mrgid = folded.get("mrgid") or folded.get("mrgid_eez")
        name = folded.get("geoname") or folded.get("name") or folded.get("eez")
        if mrgid is None or not name:
            raise SourceContractError("Marine Regions EEZ feature lacks MRGID/name")
        uid = f"marine-regions:eez:{mrgid}"
        if uid in seen:
            raise SourceContractError(f"duplicate Marine Regions MRGID {mrgid}")
        seen.add(uid)
        zones.append(
            ParsedMarineZone(
                zone_uid=uid,
                zone_type="eez",
                name=str(name),
                status="current_dataset_version",
                restriction=None,
                authority="VLIZ Marine Regions",
                geometry=geometry,
                effective_from=None,
                effective_until=None,
                provider="Marine Regions",
                source_dataset="marine_regions_eez_india",
                source_url=source_url,
                source_metadata={
                    "mrgid": mrgid,
                    "properties": properties,
                    "dataset_version": EEZ_VERSION,
                    "dataset_release_date": EEZ_RELEASE_DATE,
                    "crs": "EPSG:4326",
                    "filter": INDIA_CQL_FILTER,
                    "license_acknowledgement": license_acknowledgement,
                    "coverage_caveat": (
                        "EEZ only; does not provide MPA, restricted, naval, or firing zones"
                    ),
                },
            )
        )
    return zones


class MarineRegionsEEZLiveAdapter:
    """License-gated authoritative India EEZ WFS connector."""

    provider = "Marine Regions"
    dataset = "marine_regions_eez_india"

    def __init__(
        self,
        *,
        base_url: str = WFS_BASE_URL,
        license_acknowledgement: str | None = None,
        live_enabled: bool | None = None,
    ) -> None:
        self.live_enabled = (
            get_settings().service.enable_live_sources if live_enabled is None else live_enabled
        )
        self.base_url = base_url
        self.license_acknowledgement = (
            license_acknowledgement
            if license_acknowledgement is not None
            else os.environ.get("MARINE_REGIONS_LICENSE_ACKNOWLEDGEMENT", "")
        ).strip()

    @staticmethod
    def _http_get(url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/geo+json,application/json"},
        )
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) as response:  # noqa: S310
            if getattr(response, "status", response.getcode()) != 200:
                raise SourceUnavailableError(f"Marine Regions WFS HTTP failure for {url}")
            return response.read()

    def fetch(self) -> FetchResult:
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "Marine Regions EEZ connector is disabled by MDE_ENABLE_LIVE_SOURCES"
            )
        if not self.license_acknowledgement:
            raise SourceLicenseRequiredError(
                "Marine Regions EEZ ingestion is license-gated. Set "
                "MARINE_REGIONS_LICENSE_ACKNOWLEDGEMENT to the operator-reviewed "
                "permission/attribution reference before enabling ingestion."
            )
        url = build_india_eez_url(self.base_url)
        try:
            data = self._http_get(url)
        except SourceUnavailableError:
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise SourceUnavailableError(f"Marine Regions WFS fetch failed: {exc}") from exc
        zones = parse_india_eez(
            data,
            source_url=url,
            license_acknowledgement=self.license_acknowledgement,
        )
        retrieved_at = datetime.now(tz=UTC)
        return FetchResult(
            raw=RawPayload(
                provider=self.provider,
                dataset=self.dataset,
                data=data,
                ext="geojson",
                media_type="application/geo+json",
                source_url=url,
                retrieved_at=retrieved_at,
            ),
            marine_zones=zones,
            result_state="empty" if not zones else "success",
            status_detail=(
                "source healthy but sovereign filter returned no features"
                if not zones
                else None
            ),
        )
