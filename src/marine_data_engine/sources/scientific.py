"""Scientific data format parsers (NetCDF, HDF5, GRIB2).

These parsers handle the common scientific formats from MOSDAC/INCOIS/IMD.
Actual file processing requires xarray/h5py/cfgrib which are optional heavy
dependencies — these functions gracefully degrade when libs are unavailable
by raising a clear :class:`RuntimeError` describing the missing dependency.

The framework is intentionally thin: once the heavy deps are installed the
extraction bodies run; until then, importing this module never fails and the
parsers raise actionable errors only when actually invoked.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class GridPoint:
    """A single decoded grid cell value with coordinates and time."""

    latitude: float
    longitude: float
    parameter: str
    value: float | None
    unit: str | None
    observed_at: datetime | None


def _coerce_time(raw) -> datetime | None:
    """Best-effort convert a numpy/pandas/py datetime to an aware datetime."""
    if raw is None:
        return None
    # numpy.datetime64 / pandas.Timestamp expose isoformat() via .astype / str.
    try:
        import pandas as pd  # type: ignore

        ts = pd.Timestamp(raw)
        dt = ts.to_pydatetime()
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except Exception:  # noqa: BLE001
        pass
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    return None


def parse_netcdf_grid(
    data: bytes,
    *,
    variable: str,
    lat_var: str = "latitude",
    lon_var: str = "longitude",
    time_var: str = "time",
) -> list[GridPoint]:
    """Parse a NetCDF file into grid points. Requires ``xarray``.

    Reads ``variable`` over the ``lat_var``/``lon_var`` grid at the first time
    step (when a time dimension is present) and flattens it into
    :class:`GridPoint` records.
    """
    try:
        import numpy as np  # type: ignore
        import xarray as xr  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "xarray is required for NetCDF parsing. "
            "Install with: pip install xarray netcdf4"
        ) from exc

    ds = xr.open_dataset(io.BytesIO(data))
    try:
        if variable not in ds.variables:
            raise RuntimeError(f"variable {variable!r} not found in NetCDF dataset")

        da = ds[variable]
        observed_at = None
        if time_var in da.dims:
            da = da.isel({time_var: 0})
            observed_at = _coerce_time(ds[time_var].values[0]) if time_var in ds else None

        lats = np.asarray(ds[lat_var].values).ravel()
        lons = np.asarray(ds[lon_var].values).ravel()
        values = np.asarray(da.values)
        unit = da.attrs.get("units")

        points: list[GridPoint] = []
        flat = values.ravel()
        # Rectilinear grid: build the lat/lon meshgrid to align with flattened
        # values. Falls back to zip when shapes already align 1:1.
        if values.ndim == 2 and lats.size * lons.size == flat.size:
            lon_mesh, lat_mesh = np.meshgrid(lons, lats)
            lat_flat = lat_mesh.ravel()
            lon_flat = lon_mesh.ravel()
        else:
            n = flat.size
            lat_flat = np.resize(lats, n)
            lon_flat = np.resize(lons, n)

        for lat, lon, val in zip(lat_flat, lon_flat, flat, strict=False):
            v = None if val is None or (isinstance(val, float) and np.isnan(val)) else float(val)
            points.append(
                GridPoint(
                    latitude=float(lat),
                    longitude=float(lon),
                    parameter=variable,
                    value=v,
                    unit=unit,
                    observed_at=observed_at,
                )
            )
        return points
    finally:
        ds.close()


def parse_hdf5_grid(
    data: bytes,
    *,
    dataset_path: str,
    lat_path: str = "Latitude",
    lon_path: str = "Longitude",
) -> list[GridPoint]:
    """Parse an HDF5 file into grid points. Requires ``h5py``."""
    try:
        import h5py  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "h5py is required for HDF5 parsing. Install with: pip install h5py"
        ) from exc

    with h5py.File(io.BytesIO(data), "r") as f:
        if dataset_path not in f:
            raise RuntimeError(f"dataset {dataset_path!r} not found in HDF5 file")
        values = np.asarray(f[dataset_path][()]).ravel()
        lats = np.asarray(f[lat_path][()]).ravel() if lat_path in f else np.array([])
        lons = np.asarray(f[lon_path][()]).ravel() if lon_path in f else np.array([])
        n = values.size
        lat_flat = np.resize(lats, n) if lats.size else np.zeros(n)
        lon_flat = np.resize(lons, n) if lons.size else np.zeros(n)

        points: list[GridPoint] = []
        for lat, lon, val in zip(lat_flat, lon_flat, values, strict=False):
            v = None if isinstance(val, float) and np.isnan(val) else float(val)
            points.append(
                GridPoint(
                    latitude=float(lat),
                    longitude=float(lon),
                    parameter=dataset_path,
                    value=v,
                    unit=None,
                    observed_at=None,
                )
            )
        return points


def parse_grib2_grid(data: bytes, *, parameter: str) -> list[GridPoint]:
    """Parse a GRIB2 file into grid points. Requires ``cfgrib`` (+ xarray)."""
    try:
        import cfgrib  # type: ignore  # noqa: F401
        import numpy as np  # type: ignore
        import xarray as xr  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "cfgrib is required for GRIB2 parsing. "
            "Install with: pip install cfgrib xarray"
        ) from exc

    # cfgrib reads from a filesystem path, so buffer the bytes to a temp file.
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".grib2") as tmp:
        tmp.write(data)
        tmp.flush()
        ds = xr.open_dataset(tmp.name, engine="cfgrib")
        try:
            if parameter not in ds.variables:
                raise RuntimeError(f"parameter {parameter!r} not found in GRIB2 file")
            da = ds[parameter]
            lats = np.asarray(ds["latitude"].values).ravel()
            lons = np.asarray(ds["longitude"].values).ravel()
            values = np.asarray(da.values).ravel()
            unit = da.attrs.get("units")
            n = values.size
            lat_flat = np.resize(lats, n)
            lon_flat = np.resize(lons, n)
            points: list[GridPoint] = []
            for lat, lon, val in zip(lat_flat, lon_flat, values, strict=False):
                v = None if isinstance(val, float) and np.isnan(val) else float(val)
                points.append(
                    GridPoint(
                        latitude=float(lat),
                        longitude=float(lon),
                        parameter=parameter,
                        value=v,
                        unit=unit,
                        observed_at=None,
                    )
                )
            return points
        finally:
            ds.close()
