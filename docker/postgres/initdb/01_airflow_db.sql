-- =============================================================================
-- 01_airflow_db.sql
-- Creates a dedicated `airflow` database on the same Postgres instance for the
-- Airflow metadata store, keeping it isolated from the canonical marine schema.
-- The owner is the primary POSTGRES_USER (set via the image env at init time).
-- =============================================================================

SELECT 'CREATE DATABASE airflow OWNER ' || quote_ident(current_user)
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec
