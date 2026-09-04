"""Processed data writers (Zarr, Parquet, COG).

These produce cloud-optimized representations of processed marine data. Heavy
scientific dependencies (``zarr``/``numpy``, ``pyarrow``, ``rasterio``) are
optional and imported lazily so importing this module never requires them.
Each writer is a real implementation that works when its dependency is
installed and raises a clear :class:`RuntimeError` with an install hint when it
is not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def write_zarr(data: dict, output_path: str, *, chunks: dict | None = None) -> str:
    """Write a dict of array-like values to a Zarr store.

    ``chunks`` may map a key to a chunk shape/size; keys not present use Zarr's
    default chunking. Returns ``output_path``.
    """
    try:
        import numpy as np
        import zarr
    except ImportError as exc:
        raise RuntimeError("zarr + numpy required. pip install zarr numpy") from exc

    store = zarr.open(output_path, mode="w")
    chunks = chunks or {}
    for key, values in data.items():
        arr = np.asarray(values)
        chunk = chunks.get(key)
        if chunk is not None:
            store.create_dataset(key, data=arr, chunks=chunk, overwrite=True)
        else:
            store[key] = arr
    store.attrs["created_at"] = datetime.now(UTC).isoformat()
    return output_path


def write_parquet(records: list[dict], output_path: str) -> str:
    """Write a list of row dicts to a Parquet file. Returns ``output_path``."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("pyarrow required. pip install pyarrow") from exc

    table = pa.Table.from_pylist(records)
    pq.write_table(table, output_path)
    return output_path


def write_cog(
    data: Any,
    output_path: str,
    *,
    crs: str = "EPSG:4326",
    bounds: tuple[float, float, float, float] | None = None,
) -> str:
    """Write a 2D array to a Cloud-Optimized GeoTIFF (COG).

    ``data`` is any array-like coercible by numpy to a 2D array. ``bounds`` is
    ``(west, south, east, north)`` in ``crs`` units; when omitted a unit-degree
    grid anchored at the origin is used. Returns ``output_path``.
    """
    try:
        import numpy as np
        import rasterio
        from rasterio.transform import from_bounds
    except ImportError as exc:
        raise RuntimeError("rasterio required. pip install rasterio") from exc

    arr = np.asarray(data)
    if arr.ndim != 2:
        raise ValueError("write_cog expects a 2D array")
    height, width = arr.shape
    west, south, east, north = bounds or (0.0, 0.0, float(width), float(height))
    transform = from_bounds(west, south, east, north, width, height)

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=arr.dtype,
        crs=crs,
        transform=transform,
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="deflate",
    ) as dst:
        dst.write(arr, 1)
        dst.build_overviews([2, 4, 8], rasterio.enums.Resampling.nearest)
        dst.update_tags(ns="rio_overview", resampling="nearest")
    return output_path
