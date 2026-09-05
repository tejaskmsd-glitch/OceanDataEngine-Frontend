# =============================================================================
# mcp.Dockerfile — Marine Data Engine MCP server image.
# Exposes the engine as MCP tools/resources/prompts over Streamable HTTP.
# Shares the geospatial/scientific system libraries with the API/worker images
# because the MCP server imports the full engine (shapely/geo/services).
# Installs the `mcp` extra (the MCP SDK) which the API/worker images omit.
# =============================================================================
FROM python:3.12.8-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System libraries for geospatial + scientific decoding (same set as api/worker).
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

# Install runtime + storage + the MCP SDK extra.
RUN pip install --upgrade "pip==24.3.1" \
    && pip install ".[storage,mcp]"

# Non-root runtime user.
RUN useradd --create-home --uid 10003 mcp
USER mcp

# Streamable HTTP transport; host/port/transport overridable via env.
ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=9100 \
    MCP_TRANSPORT=streamable-http

EXPOSE 9100

# Liveness: the MCP endpoint is POST-only and requires session headers, so a
# plain request returns an HTTP error code (e.g. 400) — that still proves the
# server is listening and serving. Treat any HTTP status reply as healthy and
# only fail when the socket is unreachable (curl exit != 0 / connection error).
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS -o /dev/null "http://localhost:${MCP_PORT:-9100}/mcp" \
        || curl -s -o /dev/null -w "%{http_code}" "http://localhost:${MCP_PORT:-9100}/mcp" | grep -qE '^[1-5][0-9][0-9]$' \
        || exit 1

CMD ["sh", "-c", "opentelemetry-instrument marine-mcp"]
