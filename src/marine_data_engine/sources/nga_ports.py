"""NGA World Port Index (Pub 150) source adapter.

The NGA WPI is a public-domain dataset of ~5,400 worldwide maritime ports with
coordinates, depth soundings, facilities, and 110+ attributes. India coverage
includes all major and many minor ports.

Source: https://msi.nga.mil/Publications/WPI
Mirror: https://github.com/tayljordan/ports
License: US Government work — public domain.
Authority level: OFFICIAL_REFERENCE.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class PortRecord:
    """A parsed port from the NGA WPI."""

    port_uid: str
    name: str
    latitude: float
    longitude: float
    country: str
    source: str = "NGA_WPI_PUB150"

    # Optional enrichment fields from WPI
    harbor_size: str | None = None
    harbor_type: str | None = None
    max_vessel_length: float | None = None
    max_vessel_draft: float | None = None


def parse_wpi_json(data: bytes, *, country_filter: str | None = None) -> list[PortRecord]:
    """Parse the NGA WPI JSON dataset into PortRecord instances.

    Args:
        data: Raw JSON bytes (the full WPI dataset).
        country_filter: If set, only include ports for this country name
                        (case-insensitive substring match).
    """
    obj = json.loads(data)
    ports_list = obj.get("ports", obj) if isinstance(obj, dict) else obj
    if not isinstance(ports_list, list):
        return []

    results: list[PortRecord] = []
    for p in ports_list:
        if not isinstance(p, dict):
            continue
        country = str(p.get("country", ""))
        if country_filter and country_filter.lower() not in country.lower():
            continue

        lat = p.get("latitude")
        lon = p.get("longitude")
        if lat is None or lon is None:
            continue

        name = p.get("wpi_port_name") or p.get("port_name") or "UNKNOWN"
        port_id = p.get("wpi_port_id") or f"{name}-{lat}-{lon}"

        results.append(
            PortRecord(
                port_uid=f"WPI-{port_id}",
                name=name,
                latitude=float(lat),
                longitude=float(lon),
                country=country,
                harbor_size=p.get("harbor_size"),
                harbor_type=p.get("harbor_type"),
            )
        )
    return results


class NGAPortFixtureAdapter:
    """Fixture adapter reading a local WPI JSON file."""

    provider = "NGA"
    dataset = "nga_wpi"
    live_enabled = False

    def __init__(self, json_bytes: bytes, *, country_filter: str | None = "India") -> None:
        self._data = json_bytes
        self._country_filter = country_filter

    def parse(self) -> list[PortRecord]:
        return parse_wpi_json(self._data, country_filter=self._country_filter)


class NGAPortLiveAdapter:
    """Live adapter that fetches from the NGA WPI GitHub mirror.

    The official NGA site (msi.nga.mil) may be intermittently unavailable;
    the GitHub mirror provides a stable JSON snapshot.
    """

    provider = "NGA"
    dataset = "nga_wpi"
    MIRROR_URL = "https://raw.githubusercontent.com/tayljordan/ports/main/ports.json"

    def __init__(self, *, country_filter: str | None = "India") -> None:
        self._country_filter = country_filter

    def fetch_and_parse(self) -> list[PortRecord]:
        import urllib.request

        req = urllib.request.Request(
            self.MIRROR_URL,
            headers={"User-Agent": "MarineDataEngine/0.1", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        return parse_wpi_json(data, country_filter=self._country_filter)
