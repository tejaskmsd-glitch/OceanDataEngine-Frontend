# =============================================================================
# api.Dockerfile — FastAPI application image for the Marine Data Layer.
# Includes the geospatial/scientific system libraries required by the stack
# (GDAL, PROJ, GEOS, ecCodes for GRIB2, HDF5/NetCDF) so the same base can be
# reused by workers. Versions are pinned via the base image tag + pip.
# =============================================================================
FROM python:3.12.8-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System libraries for geospatial + scientific decoding.
# gdal/proj/geos -> shapely, geoalchemy2, rasterio, pyproj
# libeccodes -> cfgrib/GRIB2 ; libhdf5/libnetcdf -> h5py/netCDF4/xarray
# ca-certificates + libpq for Postgres/psycopg and TLS (INCOIS intermediate).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libpq-dev \
        gdal-bin \
        libgdal-dev \
        libgeos-dev \
        libproj-dev \
        proj-data \
        libeccodes0 \
        libeccodes-dev \
        libhdf5-dev \
        libnetcdf-dev \
    && rm -rf /var/lib/apt/lists/*

# GDAL headers path for any source builds.
ENV GDAL_CONFIG=/usr/bin/gdal-config \
    CPLUS_INCLUDE_PATH=/usr/include/gdal \
    C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app

# Dependency layer: copy only project metadata first for build caching.
# The backend team owns pyproject.toml / src; this image installs the package
# in editable mode so backend source changes are picked up via the bind mount
# in development.
COPY pyproject.toml README.md* ./
COPY src ./src

# Install runtime + storage extras (boto3 for MinIO/S3), pinned in pyproject.
RUN pip install --upgrade "pip==24.3.1" \
    && pip install ".[storage]"

# Non-root runtime user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Container-level healthcheck hits the API liveness endpoint.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS "http://localhost:${API_PORT:-8000}/v1/health" || exit 1

# uvicorn serves the ASGI app; module path is overridable via API_APP_MODULE.
CMD ["sh", "-c", "opentelemetry-instrument uvicorn ${API_APP_MODULE:-marine_data_engine.api.app:app} --host ${API_HOST:-0.0.0.0} --port ${API_PORT:-8000} --workers ${API_WORKERS:-2}"]
