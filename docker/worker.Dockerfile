# =============================================================================
# worker.Dockerfile — Python background worker image.
# Shares the geospatial/scientific system libraries with the API image so heavy
# decoding/normalization/QC/derived-product jobs run OUTSIDE API processes.
# The worker ROLE (ingest | process | alerts) is selected at runtime via the
# WORKER_ROLE env var, allowing independently scaled, queue-separated workers.
# =============================================================================
FROM python:3.12.8-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

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

ENV GDAL_CONFIG=/usr/bin/gdal-config \
    CPLUS_INCLUDE_PATH=/usr/include/gdal \
    C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app

COPY pyproject.toml README.md* ./
COPY src ./src

RUN pip install --upgrade "pip==24.3.1" \
    && pip install ".[storage]"

RUN useradd --create-home --uid 10002 worker
USER worker

# Default role; override per compose service (ingest/process/alerts).
ENV WORKER_ROLE=process

# Liveness: the worker runtime writes a heartbeat file; a healthy worker keeps
# it fresh. Fallback to process presence check if the runtime is not yet built.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD test -f /tmp/worker_heartbeat && find /tmp/worker_heartbeat -mmin -2 | grep -q . || exit 1

# Entry point is the console script defined in pyproject:
#   marine-worker = "marine_data_engine.worker.runtime:main"
# The runtime reads WORKER_ROLE to select queue/subject bindings.
CMD ["sh", "-c", "opentelemetry-instrument marine-worker --role ${WORKER_ROLE:-process}"]
