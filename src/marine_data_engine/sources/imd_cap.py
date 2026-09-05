"""IMD CAP source adapter.

The public IMD CAP feed is an RSS 2.0 index (S3-hosted) enumerating dated
CAP 1.2 XML documents (source_mapping §2.1, VERIFIED). This module parses a
single CAP 1.2 XML document into a :class:`ParsedAlert`.

Timestamp mapping (source_mapping §8):
    sent      -> issued_at
    effective / onset -> effective_from
    expires   -> valid_until

CAP polygon geometry is space-separated ``lat,lon`` pairs; GeoJSON requires
``[lon, lat]`` order with a closed ring (source_mapping §9).

The live connector is DISABLED by default: fetching over the network requires
``enable_live_sources`` and only then performs an HTTP GET. Tests use the
fixture connector and never touch the network.
"""

from __future__ import annotations

import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from dateutil import parser as dtparser

from ..config import get_settings
from .base import (
    FetchResult,
    LiveSourceDisabledError,
    ParsedAlert,
    RawPayload,
)

# Network timeout (seconds) for live HTTP fetches. Kept short so a slow/hung
# upstream never blocks a worker indefinitely.
_HTTP_TIMEOUT_S = 10
_USER_AGENT = "marine-data-engine/0.1 (+ingest)"

CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}

# Map CAP <event>/category text to canonical event_type families.
_EVENT_KEYWORDS: list[tuple[str, str]] = [
    ("cyclone", "cyclone"),
    ("high wave", "high_wave"),
    ("wave", "high_wave"),
    ("swell", "high_wave"),
    ("wind", "strong_wind"),
    ("rain", "heavy_rain"),
    ("thunder", "thunderstorm"),
    ("lightning", "lightning"),
    ("surge", "storm_surge"),
    ("tsunami", "tsunami"),
]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = dtparser.parse(value)
    return dt


def classify_event(event_text: str | None) -> str:
    """Classify free-text CAP event into a canonical event_type."""
    if not event_text:
        return "marine_hazard"
    low = event_text.lower()
    for kw, canonical in _EVENT_KEYWORDS:
        if kw in low:
            return canonical
    return "marine_hazard"


def cap_polygon_to_geojson(polygon_text: str) -> dict | None:
    """Convert a CAP polygon (``lat,lon lat,lon ...``) to GeoJSON Polygon.

    Swaps to ``[lon, lat]`` and closes the ring if necessary.
    """
    coords: list[list[float]] = []
    for pair in polygon_text.split():
        try:
            lat_s, lon_s = pair.split(",")
            coords.append([float(lon_s), float(lat_s)])
        except ValueError:
            continue
    if len(coords) < 3:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


def parse_cap_document(xml_bytes: bytes, *, source_url: str | None = None) -> ParsedAlert:
    """Parse a CAP 1.2 XML document into a :class:`ParsedAlert`."""
    root = ET.fromstring(xml_bytes)

    def find_text(path: str) -> str | None:
        el = root.find(path, CAP_NS)
        return el.text.strip() if el is not None and el.text else None

    identifier = find_text("cap:identifier") or ""
    sent = _parse_dt(find_text("cap:sent"))

    info = root.find("cap:info", CAP_NS)
    event = severity = certainty = urgency = headline = description = None
    effective = expires = onset = None
    geometry = None
    area_desc = None

    if info is not None:

        def info_text(tag: str) -> str | None:
            el = info.find(f"cap:{tag}", CAP_NS)
            return el.text.strip() if el is not None and el.text else None

        event = info_text("event")
        severity = (info_text("severity") or "Unknown").lower()
        certainty = (info_text("certainty") or "Unknown").lower()
        urgency = (info_text("urgency") or "Unknown").lower()
        headline = info_text("headline")
        description = info_text("description")
        effective = _parse_dt(info_text("effective"))
        onset = _parse_dt(info_text("onset"))
        expires = _parse_dt(info_text("expires"))

        area = info.find("cap:area", CAP_NS)
        if area is not None:
            adesc = area.find("cap:areaDesc", CAP_NS)
            area_desc = adesc.text.strip() if adesc is not None and adesc.text else None
            poly = area.find("cap:polygon", CAP_NS)
            if poly is not None and poly.text:
                geometry = cap_polygon_to_geojson(poly.text.strip())

    return ParsedAlert(
        alert_uid=identifier,
        event_type=classify_event(event),
        severity=severity or "unknown",
        certainty=certainty or "unknown",
        urgency=urgency or "unknown",
        headline=headline,
        description=description,
        area_description=area_desc,
        geometry=geometry,
        issued_at=sent,
        effective_from=effective or onset,
        valid_until=expires,
        source_url=source_url,
    )


class IMDCapFixtureAdapter:
    """Deterministic offline IMD CAP adapter reading a fixture CAP document."""

    provider = "IMD"
    dataset = "imd_cap"
    live_enabled = False

    def __init__(self, cap_xml: bytes, *, source_url: str | None = None) -> None:
        self._xml = cap_xml
        self._source_url = source_url or "fixture://imd/cap"

    def fetch(self) -> FetchResult:

        alert = parse_cap_document(self._xml, source_url=self._source_url)
        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=self._xml,
            ext="xml",
            media_type="application/cap+xml",
            source_url=self._source_url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw, alerts=[alert])


class IMDCapLiveAdapter:
    """Live IMD CAP connector — DISABLED unless explicitly enabled.

    Verified feed: RSS index at
    ``https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml`` linking dated
    CAP 1.2 XML documents. Network fetching is only attempted when
    ``enable_live_sources`` is true; otherwise it raises to prevent accidental
    live calls (tests never enable this).
    """

    provider = "IMD"
    dataset = "imd_cap"
    RSS_URL = "https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml"

    def __init__(self) -> None:
        self.live_enabled = get_settings().service.enable_live_sources

    @staticmethod
    def _http_get(url: str) -> bytes:
        """GET ``url`` and return the raw body bytes (stdlib only)."""
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:  # noqa: S310
            return resp.read()

    @staticmethod
    def latest_item_link(rss_bytes: bytes) -> str | None:
        """Return the link of the most recent ``<item>`` in an RSS 2.0 index.

        Parses with stdlib ``xml.etree.ElementTree`` (feedparser is NOT a
        dependency). RSS 2.0 ``<item>`` elements are conventionally ordered
        newest-first; we defensively prefer the item with the latest
        ``<pubDate>`` when parseable, otherwise fall back to document order.
        """
        root = ET.fromstring(rss_bytes)
        # RSS 2.0: rss > channel > item. Some feeds omit the channel wrapper.
        items = root.findall(".//item")
        if not items:
            return None

        def _link(item: ET.Element) -> str | None:
            link_el = item.find("link")
            if link_el is not None and link_el.text and link_el.text.strip():
                return link_el.text.strip()
            # Atom-style <link href="..."> fallback.
            for child in item:
                if child.tag.endswith("link"):
                    href = child.attrib.get("href")
                    if href:
                        return href.strip()
            return None

        def _pubdate(item: ET.Element) -> datetime | None:
            pd = item.find("pubDate")
            if pd is not None and pd.text:
                try:
                    dt = dtparser.parse(pd.text.strip())
                    # Normalize to UTC to avoid mixing aware/naive in comparisons
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)
                    return dt
                except (ValueError, OverflowError, TypeError):
                    return None
            return None

        dated = [(item, _pubdate(item)) for item in items]
        if all(dt is not None for _, dt in dated):
            newest = max(dated, key=lambda pair: pair[1])[0]
        else:
            newest = items[0]
        return _link(newest)

    def fetch(self) -> FetchResult:
        if not self.live_enabled:
            raise LiveSourceDisabledError(
                "IMD CAP live connector is disabled. Set MDE_ENABLE_LIVE_SOURCES=true "
                "to enable, or use the fixture adapter."
            )
        try:
            rss_bytes = self._http_get(self.RSS_URL)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise RuntimeError(f"IMD CAP RSS fetch failed: {exc}") from exc

        try:
            cap_url = self.latest_item_link(rss_bytes)
        except ET.ParseError as exc:
            raise RuntimeError(f"IMD CAP RSS parse failed: {exc}") from exc
        if not cap_url:
            raise RuntimeError("IMD CAP RSS contained no <item> links.")

        try:
            cap_bytes = self._http_get(cap_url)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise RuntimeError(f"IMD CAP document fetch failed ({cap_url}): {exc}") from exc

        try:
            alert = parse_cap_document(cap_bytes, source_url=cap_url)
        except ET.ParseError as exc:
            raise RuntimeError(f"IMD CAP document parse failed ({cap_url}): {exc}") from exc

        raw = RawPayload(
            provider=self.provider,
            dataset=self.dataset,
            data=cap_bytes,
            ext="xml",
            media_type="application/cap+xml",
            source_url=cap_url,
            retrieved_at=datetime.now(tz=UTC),
        )
        return FetchResult(raw=raw, alerts=[alert])
