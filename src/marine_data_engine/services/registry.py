"""Source and dataset registry helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.enums import DatasetStatus, QueuePriority
from ..db.models import Dataset, Source

# Known in-scope providers (source_mapping §1).
_PROVIDER_META: dict[str, dict] = {
    "IMD": {
        "name": "India Meteorological Department",
        "organization": "Ministry of Earth Sciences",
        "base_url": "https://mausam.imd.gov.in",
        "licensing_note": "CAP feed observed 'public domain'; other products policy-observed.",
    },
    "INCOIS": {
        "name": "Indian National Centre for Ocean Information Services",
        "organization": "Ministry of Earth Sciences",
        "base_url": "https://incois.gov.in",
        "licensing_note": "Bulk data may be chargeable; policy observed, no legal conclusion.",
    },
    "MOSDAC": {
        "name": "Meteorological & Oceanographic Satellite Data Archival Centre",
        "organization": "ISRO / SAC",
        "base_url": "https://mosdac.gov.in",
        "licensing_note": "Download requires token; policy observed.",
    },
}


def ensure_source(session: Session, code: str) -> Source:
    """Get-or-create a Source by provider code."""
    src = session.execute(select(Source).where(Source.code == code)).scalar_one_or_none()
    if src is not None:
        return src
    meta = _PROVIDER_META.get(code, {"name": code})
    src = Source(
        code=code,
        name=meta.get("name", code),
        organization=meta.get("organization"),
        base_url=meta.get("base_url"),
        live_enabled=False,
        licensing_note=meta.get("licensing_note"),
    )
    session.add(src)
    session.flush()
    return src


def seed_registry(session: Session) -> None:
    """Seed the dataset registry with the P0 vertical-slice datasets.

    Live sources are disabled; datasets start HEALTHY only after successful
    fixture ingestion (handled by the ingestion service).
    """
    imd = ensure_source(session, "IMD")
    incois = ensure_source(session, "INCOIS")

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
        key="incois_pfz",
        source_id=incois.id,
        product="INCOIS PFZ advisory",
        parameters=["pfz"],
        spatial_coverage="Indian coast sectors",
        temporal_resolution="advisory days",
        fmt="GeoJSON",
        access_method="entry page (machine endpoint unverified — HAR-A)",
        expected_update_interval_s=24 * 3600,
        priority=QueuePriority.NORMAL_INGESTION.value,
    )


def _upsert_dataset(session: Session, *, key: str, source_id: int, **fields) -> Dataset:
    ds = session.execute(select(Dataset).where(Dataset.key == key)).scalar_one_or_none()
    if ds is None:
        ds = Dataset(key=key, source_id=source_id, status=DatasetStatus.DISABLED.value, **fields)
        session.add(ds)
        session.flush()
    return ds
