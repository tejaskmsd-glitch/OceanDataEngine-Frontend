"""Source and dataset registry helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.enums import DatasetStatus, QueuePriority
from ..db.models import Dataset, Source

_PROVIDER_META: dict[str, dict] = {
    "IMD": {
        "name": "India Meteorological Department",
        "organization": "Ministry of Earth Sciences",
        "base_url": "https://mausam.imd.gov.in",
        "licensing_note": "CAP policy observed; other products require contract review.",
    },
    "INCOIS": {
        "name": "Indian National Centre for Ocean Information Services",
        "organization": "Ministry of Earth Sciences",
        "base_url": "https://incois.gov.in",
        "licensing_note": "INCOIS data policy applies; no license terms are inferred.",
    },
    "MOSDAC": {
        "name": "Meteorological & Oceanographic Satellite Data Archival Centre",
        "organization": "ISRO / SAC",
        "base_url": "https://mosdac.gov.in",
        "licensing_note": "Download requires token and license review.",
    },
    "Marine Regions": {
        "name": "Marine Regions",
        "organization": "Flanders Marine Institute (VLIZ)",
        "base_url": "https://www.marineregions.org",
        "licensing_note": "Reuse is operator-review/license gated; terms are not inferred.",
    },
}


def ensure_source(session: Session, code: str) -> Source:
    """Get or create a source without changing an operator's runtime flag."""
    source = session.execute(select(Source).where(Source.code == code)).scalar_one_or_none()
    if source is not None:
        return source
    metadata = _PROVIDER_META.get(code, {"name": code})
    source = Source(
        code=code,
        name=metadata.get("name", code),
        organization=metadata.get("organization"),
        base_url=metadata.get("base_url"),
        live_enabled=False,
        licensing_note=metadata.get("licensing_note"),
    )
    session.add(source)
    session.flush()
    return source


def seed_registry(session: Session) -> None:
    """Seed production datasets without implying that any have run."""
    imd = ensure_source(session, "IMD")
    incois = ensure_source(session, "INCOIS")
    mosdac = ensure_source(session, "MOSDAC")
    marine_regions = ensure_source(session, "Marine Regions")

    _upsert_dataset(
        session,
        key="imd_cap",
        source_id=imd.id,
        product="IMD CAP warnings",
        parameters=["warning"],
        spatial_coverage="India + surrounding seas",
        temporal_resolution="as issued",
        fmt="CAP 1.2 XML",
        access_method="RSS index + CAP XML",
        expected_update_interval_s=3600,
        priority=QueuePriority.CRITICAL_ALERTS.value,
    )
    _upsert_dataset(
        session,
        key="incois_erddap",
        source_id=incois.id,
        product="INCOIS ERDDAP catalog and per-dataset metadata",
        parameters=["catalog_metadata"],
        spatial_coverage="dataset dependent",
        spatial_resolution="dataset dependent",
        temporal_resolution="6-hour catalog checks",
        fmt="ERDDAP JSON",
        access_method="verified catalog + /info/{dataset}/index.json",
        expected_update_interval_s=6 * 3600,
        priority=QueuePriority.SCIENTIFIC.value,
    )
    _upsert_dataset(
        session,
        key="mosdac_search",
        source_id=mosdac.id,
        product="MOSDAC OpenSearch discovery catalog only",
        parameters=["catalog_only"],
        spatial_coverage="India / Indian Ocean satellite products",
        spatial_resolution="product dependent",
        temporal_resolution="12-hour discovery checks",
        fmt="OpenSearch JSON",
        access_method="open search; authenticated downloads excluded",
        expected_update_interval_s=12 * 3600,
        priority=QueuePriority.BACKFILL_ARCHIVE.value,
    )
    _upsert_dataset(
        session,
        key="incois_pfz",
        source_id=incois.id,
        product="INCOIS Potential Fishing Zone advisory geometry",
        parameters=["pfz_destination_point", "pfz_advisory_line"],
        spatial_coverage="Indian coast",
        spatial_resolution="Point destinations + LineString advisories",
        temporal_resolution="advisory snapshots",
        fmt="GeoJSON",
        access_method="verified Gemini /api/ws/pfz + /api/ws/pfzLines",
        expected_update_interval_s=6 * 3600,
        priority=QueuePriority.REALTIME_OBSERVATIONS.value,
    )
    _upsert_dataset(
        session,
        key="incois_hwa",
        source_id=incois.id,
        product="INCOIS high-wave and swell-surge coastal alerts",
        parameters=["high_wave", "swell_surge"],
        spatial_coverage="Indian coastal districts",
        temporal_resolution="as issued",
        fmt="nested JSON + GeoJSON",
        access_method="verified HWA/SSA REST + district polygons",
        expected_update_interval_s=30 * 60,
        priority=QueuePriority.CRITICAL_ALERTS.value,
    )
    _upsert_dataset(
        session,
        key="incois_tide",
        source_id=incois.id,
        product="INCOIS TEWS tide-gauge latest observations",
        parameters=["water_level"],
        spatial_coverage="TEWS tide-gauge stations",
        spatial_resolution="station point",
        temporal_resolution="minutes",
        fmt="XML station catalog + JSON latest-series metadata",
        access_method="verified TideStations.xml + JSONS/{STATION}_1.json",
        expected_update_interval_s=30 * 60,
        priority=QueuePriority.REALTIME_OBSERVATIONS.value,
    )
    _upsert_dataset(
        session,
        key="incois_buoy",
        source_id=incois.id,
        product="INCOIS OON moored-buoy latest observations",
        parameters=["significant_wave_height", "wind_speed"],
        spatial_coverage="Indian Ocean OON moored buoys",
        spatial_resolution="station point",
        temporal_resolution="3-hourly/source dependent",
        fmt="JSON catalog + server-rendered Highcharts HTML",
        access_method="verified dynamic OON catalog/status/chart pages",
        expected_update_interval_s=6 * 3600,
        priority=QueuePriority.REALTIME_OBSERVATIONS.value,
    )
    _upsert_dataset(
        session,
        key="imd_nwp",
        source_id=imd.id,
        product="IMD numeric marine NWP forecasts",
        parameters=["wind", "wave", "pressure", "rainfall"],
        spatial_coverage="unknown until official contract access",
        temporal_resolution="unknown",
        fmt="unverified",
        access_method="no verified numeric endpoint/auth contract",
        auth_required=True,
        expected_update_interval_s=None,
        priority=QueuePriority.NORMAL_INGESTION.value,
        initial_status=DatasetStatus.DISABLED.value,
        initial_result_state="contract_unavailable",
        initial_status_detail=(
            "Official textual marine APIs return HTTP 401; credential scheme and "
            "numeric NWP endpoint/schema are undocumented"
        ),
    )
    _upsert_dataset(
        session,
        key="marine_regions_eez_india",
        source_id=marine_regions.id,
        product="India EEZ boundaries (Marine Regions World EEZ v12)",
        parameters=["eez_boundary"],
        spatial_coverage="India mainland and Andaman/Nicobar EEZ",
        spatial_resolution="authoritative MultiPolygon",
        temporal_resolution="versioned release (2023-10-25)",
        fmt="WFS GeoJSON",
        access_method="MarineRegions:eez sovereign ISO filter",
        expected_update_interval_s=30 * 24 * 3600,
        priority=QueuePriority.BACKFILL_ARCHIVE.value,
        initial_status=DatasetStatus.DISABLED.value,
        initial_result_state="license_gated",
        initial_status_detail=(
            "Production ingestion requires operator-reviewed reusable license/attribution terms"
        ),
    )


def _upsert_dataset(session: Session, *, key: str, source_id: int, **fields) -> Dataset:
    initial_status = fields.pop("initial_status", DatasetStatus.DISABLED.value)
    initial_result_state = fields.pop("initial_result_state", "not_run")
    initial_status_detail = fields.pop("initial_status_detail", None)
    dataset = session.execute(select(Dataset).where(Dataset.key == key)).scalar_one_or_none()
    if dataset is None:
        dataset = Dataset(
            key=key,
            source_id=source_id,
            status=initial_status,
            last_result_state=initial_result_state,
            status_detail=initial_status_detail,
            **fields,
        )
        session.add(dataset)
        session.flush()
        return dataset

    dataset.source_id = source_id
    for name, value in fields.items():
        setattr(dataset, name, value)
    if dataset.last_checked_at is None and dataset.last_result_state in {None, "not_run"}:
        dataset.status = initial_status
        dataset.last_result_state = initial_result_state
        dataset.status_detail = initial_status_detail
    return dataset
