"""Tests for the processed-data writer stubs (Zarr / Parquet / COG).

The heavy optional deps (zarr, pyarrow, rasterio) are not installed in the test
environment, so the writers must raise a clear :class:`RuntimeError` with an
install hint. When a dep happens to be present the raise-assertion is skipped.
"""

from __future__ import annotations

import importlib.util

import pytest

from marine_data_engine.storage.writers import write_cog, write_parquet, write_zarr


def _installed(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


@pytest.mark.skipif(_installed("zarr"), reason="zarr installed")
def test_write_zarr_raises_without_dep(tmp_path):
    with pytest.raises(RuntimeError, match="zarr"):
        write_zarr({"sst": [1, 2, 3]}, str(tmp_path / "out.zarr"))


@pytest.mark.skipif(_installed("pyarrow"), reason="pyarrow installed")
def test_write_parquet_raises_without_dep(tmp_path):
    with pytest.raises(RuntimeError, match="pyarrow"):
        write_parquet([{"a": 1}], str(tmp_path / "out.parquet"))


@pytest.mark.skipif(_installed("rasterio"), reason="rasterio installed")
def test_write_cog_raises_without_dep(tmp_path):
    with pytest.raises(RuntimeError, match="rasterio"):
        write_cog([[1, 2], [3, 4]], str(tmp_path / "out.tif"))


@pytest.mark.skipif(not _installed("pyarrow"), reason="pyarrow not installed")
def test_write_parquet_roundtrip(tmp_path):
    out = write_parquet([{"a": 1, "b": "x"}], str(tmp_path / "out.parquet"))
    assert out.endswith("out.parquet")
