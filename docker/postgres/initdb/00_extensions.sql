-- =============================================================================
-- 00_extensions.sql
-- Runs once on first Postgres init (docker-entrypoint-initdb.d).
-- Enables PostGIS (spatial) and TimescaleDB (time-series) in the primary DB.
-- The base image is `timescale/timescaledb-ha` which ships both PostGIS and
-- TimescaleDB, so both extensions are available.
-- =============================================================================

\connect marine

-- Spatial types, indexes, and predicates (geofencing, PFZ, routing, zones).
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Time-series hypertables for observations / forecasts / freshness metrics.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Useful helpers.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Report versions to the init log for verifiability.
DO $$
DECLARE
    postgis_ver text;
    timescale_ver text;
BEGIN
    SELECT extversion INTO postgis_ver FROM pg_extension WHERE extname = 'postgis';
    SELECT extversion INTO timescale_ver FROM pg_extension WHERE extname = 'timescaledb';
    RAISE NOTICE 'PostGIS extension version: %', postgis_ver;
    RAISE NOTICE 'TimescaleDB extension version: %', timescale_ver;
END
$$;
