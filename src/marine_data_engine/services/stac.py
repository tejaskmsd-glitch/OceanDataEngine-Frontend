"""Lightweight STAC-compatible catalog built from the dataset registry.

This module exposes the canonical :class:`Dataset` registry as STAC
Collections and each :class:`DatasetAsset` as a STAC Item, without introducing
any new tables. It is intentionally minimal — a read-only projection that
follows the SpatioTemporal Asset Catalog (STAC) 1.0.0 object shapes so that
downstream clients (tile servers, catalogs, notebooks) can consume the
registry through a familiar contract.

STAC objects are returned as plain ``dict`` values (raw STAC JSON), not wrapped
in the canonical response envelope — STAC defines its own specification.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Dataset, DatasetAsset, Source

STAC_VERSION = "1.0.0"

# A world bbox / open temporal interval is used when a dataset does not carry
# concrete spatial or temporal bounds in the registry. STAC requires the
# extent object to be present on every collection.
_WORLD_BBOX: list[float] = [-180.0, -90.0, 180.0, 90.0]


def _isoformat(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _collection_extent(dataset: Dataset) -> dict[str, Any]:
    """Build a STAC extent object for a dataset.

    Spatial extent falls back to a world bbox; temporal extent uses the
    dataset's last-success/last-processed timestamps when available.
    """
    start = dataset.last_success_at or dataset.created_at
    end = dataset.last_processed_at or dataset.last_success_at
    return {
        "spatial": {"bbox": [list(_WORLD_BBOX)]},
        "temporal": {"interval": [[_isoformat(start), _isoformat(end)]]},
    }


def _collection_links(collection_id: str) -> list[dict[str, Any]]:
    return [
        {"rel": "self", "type": "application/json",
         "href": f"/v1/stac/collections/{collection_id}"},
        {"rel": "root", "type": "application/json", "href": "/v1/stac/collections"},
        {"rel": "parent", "type": "application/json", "href": "/v1/stac/collections"},
        {"rel": "items", "type": "application/geo+json",
         "href": f"/v1/stac/collections/{collection_id}/items"},
    ]


def _providers(source: Source | None) -> list[dict[str, Any]]:
    if source is None:
        return []
    provider: dict[str, Any] = {
        "name": source.name or source.code,
        "roles": ["producer", "licensor"],
    }
    if source.base_url:
        provider["url"] = source.base_url
    return [provider]


def _dataset_to_collection(dataset: Dataset, source: Source | None) -> dict[str, Any]:
    """Project a Dataset registry row into a STAC Collection object."""
    provider_code = source.code if source is not None else "unknown"
    description = (
        f"{dataset.product} from {provider_code}."
        if dataset.product
        else f"Dataset {dataset.key} from {provider_code}."
    )
    return {
        "type": "Collection",
        "stac_version": STAC_VERSION,
        "id": dataset.key,
        "title": dataset.product or dataset.key,
        "description": description,
        "license": "proprietary",
        "keywords": list(dataset.parameters or []),
        "extent": _collection_extent(dataset),
        "providers": _providers(source),
        "links": _collection_links(dataset.key),
        "summaries": {
            "status": [dataset.status],
            "spatial_coverage": [dataset.spatial_coverage] if dataset.spatial_coverage else [],
            "temporal_resolution": (
                [dataset.temporal_resolution] if dataset.temporal_resolution else []
            ),
        },
    }


def _asset_to_item(
    asset: DatasetAsset, dataset: Dataset, source: Source | None
) -> dict[str, Any]:
    """Project a DatasetAsset row into a STAC Item (Feature) object."""
    provider_code = source.code if source is not None else "unknown"
    dt = asset.retrieved_at or asset.created_at
    item_id = f"{dataset.key}-{asset.id}"
    media_type = asset.media_type or "application/octet-stream"
    return {
        "type": "Feature",
        "stac_version": STAC_VERSION,
        "id": item_id,
        # Registry assets do not carry per-asset geometry; STAC permits null
        # geometry with an accompanying null bbox for non-spatial items.
        "geometry": None,
        "bbox": None,
        "collection": dataset.key,
        "properties": {
            "datetime": _isoformat(dt),
            "provider": provider_code,
            "dataset": dataset.key,
            "processing_version": None,
            "checksum": asset.checksum_sha256,
            "role": asset.role,
            "size_bytes": asset.size_bytes,
        },
        "assets": {
            asset.role: {
                "href": asset.storage_uri,
                "type": media_type,
                "roles": [asset.role],
                "title": f"{dataset.key} {asset.role} asset",
            }
        },
        "links": [
            {"rel": "self", "type": "application/geo+json",
             "href": f"/v1/stac/collections/{dataset.key}/items/{item_id}"},
            {"rel": "parent", "type": "application/json",
             "href": f"/v1/stac/collections/{dataset.key}"},
            {"rel": "collection", "type": "application/json",
             "href": f"/v1/stac/collections/{dataset.key}"},
            {"rel": "root", "type": "application/json", "href": "/v1/stac/collections"},
        ],
    }


# --------------------------------------------------------------------------- #
# Query functions
# --------------------------------------------------------------------------- #
def list_stac_collections(session: Session) -> list[dict]:
    """Return one STAC Collection per dataset in the registry."""
    rows = session.execute(select(Dataset, Source).join(Source)).all()
    return [_dataset_to_collection(ds, src) for ds, src in rows]


def get_stac_collection(session: Session, collection_id: str) -> dict | None:
    """Return a single STAC Collection keyed by dataset key, or ``None``."""
    row = session.execute(
        select(Dataset, Source).join(Source).where(Dataset.key == collection_id)
    ).first()
    if row is None:
        return None
    ds, src = row
    return _dataset_to_collection(ds, src)


def list_stac_items(
    session: Session,
    collection_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Return STAC Items (from DatasetAsset rows) for a collection.

    Returns an empty list when the collection does not exist or has no assets.
    """
    row = session.execute(
        select(Dataset, Source).join(Source).where(Dataset.key == collection_id)
    ).first()
    if row is None:
        return []
    dataset, source = row
    stmt = (
        select(DatasetAsset)
        .where(DatasetAsset.dataset_id == dataset.id)
        .order_by(DatasetAsset.id)
        .offset(offset)
        .limit(limit)
    )
    return [
        _asset_to_item(asset, dataset, source)
        for asset in session.execute(stmt).scalars()
    ]
