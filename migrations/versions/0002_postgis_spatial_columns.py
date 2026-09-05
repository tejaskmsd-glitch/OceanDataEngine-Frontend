"""postgis spatial columns + dataset_freshness

Promotes the portable ``latitude``/``longitude`` float pair on the high-volume
time-series tables ``observation`` and ``forecast`` to a native PostGIS point
geometry (``location geometry(Point, 4326)``, WGS84 — the canonical output CRS),
backfills it from the existing lat/lon, and adds a GIST index for spatial
queries. The original float columns are retained (the portable GeoJSON/lat-lon
contract is unchanged); ``location`` is an additive spatial accelerator.

Also creates the ``dataset_freshness`` table documented in the README /
requirements (the ``dataset_freshness_sweep`` DAG recomputes staleness into it)
but never materialized by the initial migration.

Design notes
------------
* All DDL is idempotent: ``IF NOT EXISTS`` on tables/indexes/columns and guarded
  ``DO $$`` blocks elsewhere, matching the 0001 style so the migration is safe
  to re-run.
* Alembic runs each migration inside a transaction (see ``env.py`` ->
  ``context.begin_transaction()``). ``CREATE INDEX CONCURRENTLY`` is **not**
  permitted inside a transaction block, so the GIST indexes are created with a
  plain guarded ``CREATE INDEX IF NOT EXISTS`` (identical to the geometry GIST
  indexes in 0001, e.g. ``ix_alert_geometry``). Switch to CONCURRENTLY only if
  these tables are backfilled online outside a migration transaction.
* The backfill ``UPDATE`` is wrapped in a ``DO $$`` block that first confirms
  the ``location`` column exists, so the statement is safe even if the ADD
  COLUMN was a no-op on a partially-migrated database.

Revision ID: 0002_postgis_spatial_columns
Revises: 0001_initial_canonical
Create Date: 2026-09-05
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_postgis_spatial_columns"
down_revision = "0001_initial_canonical"
branch_labels = None
depends_on = None


def _add_location_column(table: str) -> str:
    """Idempotently add a ``location geometry(Point, 4326)`` column."""
    return f"""
        ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS location geometry(Point, 4326);
    """


def _backfill_location(table: str) -> str:
    """Backfill ``location`` from lat/lon, guarded on the column existing."""
    return f"""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = '{table}' AND column_name = 'location'
        ) THEN
            UPDATE {table}
               SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
             WHERE latitude IS NOT NULL
               AND longitude IS NOT NULL
               AND location IS NULL;
        END IF;
    END
    $$;
    """


def upgrade() -> None:
    # PostGIS is required for geometry types (idempotent; created in 0001 too).
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    # --------------------------------------------------------------------- #
    # observation.location
    # --------------------------------------------------------------------- #
    op.execute(_add_location_column("observation"))
    op.execute(_backfill_location("observation"))
    # NOTE: non-CONCURRENT because migrations run inside a transaction.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_observation_location "
        "ON observation USING GIST (location);"
    )

    # --------------------------------------------------------------------- #
    # forecast.location
    # --------------------------------------------------------------------- #
    op.execute(_add_location_column("forecast"))
    op.execute(_backfill_location("forecast"))
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_forecast_location "
        "ON forecast USING GIST (location);"
    )

    # --------------------------------------------------------------------- #
    # dataset_freshness (documented in README, never materialized in 0001)
    # --------------------------------------------------------------------- #
    op.execute("""
        CREATE TABLE IF NOT EXISTS dataset_freshness (
            id                  SERIAL PRIMARY KEY,
            dataset_key         VARCHAR(128) NOT NULL,
            last_data_at        TIMESTAMPTZ,
            expected_interval_s INTEGER,
            freshness_score     DOUBLE PRECISION,
            is_stale            BOOLEAN NOT NULL DEFAULT FALSE,
            evaluated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_dataset_freshness_key UNIQUE (dataset_key)
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dataset_freshness_dataset_key "
        "ON dataset_freshness (dataset_key);"
    )


def downgrade() -> None:
    # Reverse order of upgrade().
    op.execute("DROP TABLE IF EXISTS dataset_freshness CASCADE;")

    op.execute("DROP INDEX IF EXISTS ix_forecast_location;")
    op.execute("DROP INDEX IF EXISTS ix_observation_location;")

    op.execute("ALTER TABLE forecast DROP COLUMN IF EXISTS location;")
    op.execute("ALTER TABLE observation DROP COLUMN IF EXISTS location;")
