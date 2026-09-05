"""initial canonical marine schema

Creates the canonical marine data model that mirrors the backend SQLAlchemy
ORM (``src/marine_data_engine/db/models.py``) EXACTLY — same table names,
column names, and semantics. The migration is explicit SQL (it does not import
the ORM) but is kept in lock-step with it.

Design notes
------------
* PostGIS geometry columns use SRID 4326 (WGS84) — the canonical output CRS.
  The ORM stores geometry portably as GeoJSON text (``GeometryJSON``); in this
  production migration the same attribute is promoted to a native PostGIS
  ``geometry(Geometry, 4326)`` column with a GIST index. The Python attribute
  name and GeoJSON contract are unchanged.
* TimescaleDB hypertables back the high-volume time series ``observation``
  (partitioned on ``observed_at``) and ``forecast`` (on ``forecast_time``).
  Hypertable creation is guarded so the migration still succeeds on a plain
  PostGIS-only database.
* Timestamp columns keep the distinct provenance semantics required by the
  docs: observed_at / issued_at / valid_from / valid_until / forecast_time /
  retrieved_at / processed_at (never conflated).
* Enum-valued columns are stored as TEXT to match the ORM (which persists the
  string ``.value`` of each Python Enum); allowed values are documented inline
  and enforced in the application layer, matching the ORM contract.

Revision ID: 0001_initial_canonical
Revises:
Create Date: 2026-09-03
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial_canonical"
down_revision = None
branch_labels = None
depends_on = None


# Canonical enum value sets (mirror src/marine_data_engine/db/enums.py). Stored
# as TEXT in the ORM; documented here for reference / optional CHECK use.
_QC_STATUS = ("accepted", "rejected", "quarantined", "unknown")
_DATASET_STATUS = ("healthy", "stale", "degraded", "failed", "disabled")
_JOB_STATUS = (
    "queued",
    "running",
    "succeeded",
    "failed",
    "retrying",
    "cancelled",
    "dead_letter",
)
_QUEUE_PRIORITY = (
    "critical_alerts",
    "realtime_observations",
    "normal_ingestion",
    "scientific",
    "backfill_archive",
)


def _hypertable(table: str, time_col: str) -> str:
    """Return a guarded create_hypertable statement (no-op without TimescaleDB)."""
    return f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
            PERFORM create_hypertable('{table}', '{time_col}',
                                      if_not_exists => TRUE, migrate_data => TRUE);
        END IF;
    END
    $$;
    """


# Shared provenance/QC columns present on observation/forecast/alert/advisory/pfz
# (mirrors _ProvenanceMixin in the ORM). Emitted verbatim inside each CREATE.
_PROVENANCE_COLS = """
        provider            TEXT NOT NULL,
        source_dataset      TEXT NOT NULL,
        source_url          TEXT,
        processing_version  TEXT NOT NULL DEFAULT '1.0.0',
        observed_at         TIMESTAMPTZ,
        issued_at           TIMESTAMPTZ,
        valid_from          TIMESTAMPTZ,
        valid_until         TIMESTAMPTZ,
        forecast_time       TIMESTAMPTZ,
        retrieved_at        TIMESTAMPTZ,
        processed_at        TIMESTAMPTZ,
        quality_status      TEXT NOT NULL DEFAULT 'unknown',
        quality_score       DOUBLE PRECISION,
        missing_flag        BOOLEAN NOT NULL DEFAULT FALSE,
        outlier_flag        BOOLEAN NOT NULL DEFAULT FALSE,
        interpolated_flag   BOOLEAN NOT NULL DEFAULT FALSE,
        idempotency_key     TEXT NOT NULL
"""


def upgrade() -> None:
    # ---- extensions (idempotent; also created by docker initdb) -------------
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    # --------------------------------------------------------------------- #
    # Provenance / registry
    # --------------------------------------------------------------------- #
    # ---- source ----------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS source (
            id             SERIAL PRIMARY KEY,
            code           VARCHAR(64) NOT NULL,
            name           VARCHAR(255) NOT NULL,
            organization   VARCHAR(255),
            base_url       VARCHAR(1024),
            live_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
            licensing_note TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_source_code ON source (code);")

    # ---- dataset_collection ---------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS dataset_collection (
            id          SERIAL PRIMARY KEY,
            key         VARCHAR(128) NOT NULL,
            title       VARCHAR(255) NOT NULL,
            description TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    # ---- dataset ---------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS dataset (
            id                          SERIAL PRIMARY KEY,
            key                         VARCHAR(128) NOT NULL,
            source_id                   INTEGER NOT NULL REFERENCES source(id),
            collection_id               INTEGER REFERENCES dataset_collection(id),
            product                     VARCHAR(255) NOT NULL,
            parameters                  JSON,
            spatial_coverage            VARCHAR(255),
            spatial_resolution          VARCHAR(128),
            temporal_resolution         VARCHAR(128),
            fmt                         VARCHAR(64),
            access_method               VARCHAR(128),
            auth_required               BOOLEAN NOT NULL DEFAULT FALSE,
            expected_update_interval_s  INTEGER,
            stale_multiplier            DOUBLE PRECISION,
            priority                    VARCHAR(32) NOT NULL DEFAULT 'normal_ingestion',
            retention_policy            VARCHAR(255),
            licensing_note              TEXT,
            status                      VARCHAR(32) NOT NULL DEFAULT 'disabled',
            consecutive_failures        INTEGER NOT NULL DEFAULT 0,
            last_success_at             TIMESTAMPTZ,
            last_failure_at             TIMESTAMPTZ,
            last_processed_at           TIMESTAMPTZ,
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_dataset_key ON dataset (key);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dataset_source_id ON dataset (source_id);")

    # ---- dataset_asset ---------------------------------------------------
    # FK ingestion_job_id references ingestion_job, created below; add the FK
    # after ingestion_job exists to avoid ordering issues.
    op.execute("""
        CREATE TABLE IF NOT EXISTS dataset_asset (
            id                SERIAL PRIMARY KEY,
            dataset_id        INTEGER NOT NULL REFERENCES dataset(id),
            role              VARCHAR(32) NOT NULL DEFAULT 'raw',
            storage_uri       VARCHAR(1024) NOT NULL,
            media_type        VARCHAR(128),
            checksum_sha256   VARCHAR(64),
            size_bytes        BIGINT,
            ingestion_job_id  INTEGER,
            retrieved_at      TIMESTAMPTZ,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_dataset_asset_uri UNIQUE (dataset_id, storage_uri)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_dataset_asset_dataset_id ON dataset_asset (dataset_id);")

    # --------------------------------------------------------------------- #
    # Environmental records
    # --------------------------------------------------------------------- #
    # ---- observation (hypertable on observed_at) -------------------------
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS observation (
            id            BIGSERIAL,
{_PROVENANCE_COLS},
            station_id    VARCHAR(128),
            station_type  VARCHAR(64),
            latitude      DOUBLE PRECISION,
            longitude     DOUBLE PRECISION,
            parameter     VARCHAR(64) NOT NULL,
            value         DOUBLE PRECISION,
            unit          VARCHAR(32),
            PRIMARY KEY (id, observed_at),
            CONSTRAINT uq_observation_idem UNIQUE (idempotency_key, observed_at)
        );
    """)
    op.execute(_hypertable("observation", "observed_at"))
    op.execute("CREATE INDEX IF NOT EXISTS ix_observation_provider ON observation (provider);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_observation_station_id ON observation (station_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_observation_parameter ON observation (parameter);")

    # ---- forecast (hypertable on forecast_time) --------------------------
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS forecast (
            id            BIGSERIAL,
{_PROVENANCE_COLS},
            model_name    VARCHAR(128),
            model_cycle   VARCHAR(32),
            forecast_hour INTEGER,
            latitude      DOUBLE PRECISION,
            longitude     DOUBLE PRECISION,
            parameter     VARCHAR(64) NOT NULL,
            value         DOUBLE PRECISION,
            unit          VARCHAR(32),
            resolution    VARCHAR(64),
            PRIMARY KEY (id, forecast_time),
            CONSTRAINT uq_forecast_idem UNIQUE (idempotency_key, forecast_time)
        );
    """)
    op.execute(_hypertable("forecast", "forecast_time"))
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_provider ON forecast (provider);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_forecast_parameter ON forecast (parameter);")

    # ---- alert -----------------------------------------------------------
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS alert (
            id               SERIAL PRIMARY KEY,
{_PROVENANCE_COLS},
            alert_uid        VARCHAR(255) NOT NULL,
            event_type       VARCHAR(64) NOT NULL,
            severity         VARCHAR(16) NOT NULL DEFAULT 'unknown',
            certainty        VARCHAR(16) NOT NULL DEFAULT 'unknown',
            urgency          VARCHAR(16) NOT NULL DEFAULT 'unknown',
            headline         TEXT,
            description      TEXT,
            area_description TEXT,
            geometry         geometry(Geometry, 4326),
            bbox_minx        DOUBLE PRECISION,
            bbox_miny        DOUBLE PRECISION,
            bbox_maxx        DOUBLE PRECISION,
            bbox_maxy        DOUBLE PRECISION,
            CONSTRAINT uq_alert_idem UNIQUE (idempotency_key)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_alert_provider ON alert (provider);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alert_source_dataset ON alert (source_dataset);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alert_idempotency_key ON alert (idempotency_key);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alert_alert_uid ON alert (alert_uid);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alert_event_type ON alert (event_type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alert_geometry ON alert USING GIST (geometry);")

    # ---- advisory --------------------------------------------------------
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS advisory (
            id                    SERIAL PRIMARY KEY,
{_PROVENANCE_COLS},
            advisory_uid          VARCHAR(255) NOT NULL,
            advisory_type         VARCHAR(64) NOT NULL,
            species_or_ecosystem  VARCHAR(128),
            region                VARCHAR(255),
            recommendation        TEXT,
            geometry              geometry(Geometry, 4326),
            CONSTRAINT uq_advisory_idem UNIQUE (idempotency_key)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_advisory_provider ON advisory (provider);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_advisory_advisory_uid ON advisory (advisory_uid);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_advisory_advisory_type ON advisory (advisory_type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_advisory_geometry ON advisory USING GIST (geometry);")

    # ---- pfz -------------------------------------------------------------
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS pfz (
            id                  SERIAL PRIMARY KEY,
{_PROVENANCE_COLS},
            pfz_uid             VARCHAR(255) NOT NULL,
            region              VARCHAR(255),
            advisory_text       TEXT,
            advisory_type       VARCHAR(64),
            sst_context         DOUBLE PRECISION,
            chlorophyll_context DOUBLE PRECISION,
            confidence          DOUBLE PRECISION,
            geometry            geometry(Geometry, 4326),
            centroid_lat        DOUBLE PRECISION,
            centroid_lon        DOUBLE PRECISION,
            CONSTRAINT uq_pfz_idem UNIQUE (idempotency_key)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pfz_provider ON pfz (provider);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pfz_source_dataset ON pfz (source_dataset);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pfz_idempotency_key ON pfz (idempotency_key);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pfz_pfz_uid ON pfz (pfz_uid);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pfz_validity ON pfz (valid_from, valid_until);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pfz_geometry ON pfz USING GIST (geometry);")

    # --------------------------------------------------------------------- #
    # Reference / geospatial entities
    # --------------------------------------------------------------------- #
    # ---- station ---------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS station (
            id           SERIAL PRIMARY KEY,
            station_uid  VARCHAR(128) NOT NULL,
            name         VARCHAR(255),
            station_type VARCHAR(64),
            latitude     DOUBLE PRECISION,
            longitude    DOUBLE PRECISION,
            provider     VARCHAR(64),
            source_url   VARCHAR(1024),
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_station_station_uid ON station (station_uid);")

    # ---- port ------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS port (
            id         SERIAL PRIMARY KEY,
            port_uid   VARCHAR(128) NOT NULL,
            name       VARCHAR(255) NOT NULL,
            latitude   DOUBLE PRECISION,
            longitude  DOUBLE PRECISION,
            country    VARCHAR(64),
            source     VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_port_port_uid ON port (port_uid);")

    # ---- marine_zone -----------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS marine_zone (
            id              SERIAL PRIMARY KEY,
            zone_uid        VARCHAR(128) NOT NULL,
            zone_type       VARCHAR(64) NOT NULL,
            name            VARCHAR(255) NOT NULL,
            status          VARCHAR(64),
            restriction     TEXT,
            authority       VARCHAR(255),
            geometry        geometry(Geometry, 4326),
            effective_from  TIMESTAMPTZ,
            effective_until TIMESTAMPTZ,
            source          VARCHAR(64),
            source_url      VARCHAR(1024),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_marine_zone_zone_type ON marine_zone (zone_type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_marine_zone_geometry ON marine_zone USING GIST (geometry);")

    # --------------------------------------------------------------------- #
    # Processing / lineage entities
    # --------------------------------------------------------------------- #
    # ---- ingestion_job ---------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_job (
            id              SERIAL PRIMARY KEY,
            job_uid         VARCHAR(64) NOT NULL,
            dataset_key     VARCHAR(128) NOT NULL,
            priority        VARCHAR(32) NOT NULL DEFAULT 'normal_ingestion',
            status          VARCHAR(32) NOT NULL DEFAULT 'queued',
            attempts        INTEGER NOT NULL DEFAULT 0,
            max_attempts    INTEGER NOT NULL DEFAULT 5,
            idempotency_key VARCHAR(255) NOT NULL,
            error_code      VARCHAR(128),
            error_detail    TEXT,
            bytes_fetched   BIGINT,
            queued_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at      TIMESTAMPTZ,
            finished_at     TIMESTAMPTZ
        );
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_ingestion_job_job_uid ON ingestion_job (job_uid);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_ingestion_job_idem ON ingestion_job (idempotency_key);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ingestion_job_status ON ingestion_job (status);")

    # Now that ingestion_job exists, wire the deferred FK from dataset_asset.
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE dataset_asset
                ADD CONSTRAINT fk_dataset_asset_ingestion_job
                FOREIGN KEY (ingestion_job_id) REFERENCES ingestion_job(id);
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    # ---- processing_job --------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS processing_job (
            id               SERIAL PRIMARY KEY,
            job_uid          VARCHAR(64) NOT NULL,
            dataset_key      VARCHAR(128) NOT NULL,
            job_type         VARCHAR(64) NOT NULL,
            priority         VARCHAR(32) NOT NULL DEFAULT 'normal_ingestion',
            status           VARCHAR(32) NOT NULL DEFAULT 'queued',
            attempts         INTEGER NOT NULL DEFAULT 0,
            max_attempts     INTEGER NOT NULL DEFAULT 5,
            idempotency_key  VARCHAR(255) NOT NULL,
            ingestion_job_id INTEGER REFERENCES ingestion_job(id),
            error_code       VARCHAR(128),
            error_detail     TEXT,
            queued_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at       TIMESTAMPTZ,
            finished_at      TIMESTAMPTZ
        );
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_processing_job_job_uid ON processing_job (job_uid);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_processing_job_job_type ON processing_job (job_type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_processing_job_status ON processing_job (status);")

    # ---- processing_run --------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS processing_run (
            id                  SERIAL PRIMARY KEY,
            run_uid             VARCHAR(64) NOT NULL,
            processing_job_id   INTEGER NOT NULL REFERENCES processing_job(id),
            attempt             INTEGER NOT NULL DEFAULT 1,
            status              VARCHAR(32) NOT NULL DEFAULT 'running',
            worker              VARCHAR(128),
            records_in          INTEGER NOT NULL DEFAULT 0,
            records_accepted    INTEGER NOT NULL DEFAULT 0,
            records_rejected    INTEGER NOT NULL DEFAULT 0,
            records_quarantined INTEGER NOT NULL DEFAULT 0,
            duration_ms         INTEGER,
            error_code          VARCHAR(128),
            error_detail        TEXT,
            started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at         TIMESTAMPTZ
        );
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_processing_run_run_uid ON processing_run (run_uid);")

    # ---- evidence --------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS evidence (
            id           SERIAL PRIMARY KEY,
            request_id   VARCHAR(64) NOT NULL,
            endpoint     VARCHAR(255) NOT NULL,
            query_params JSON,
            sources      JSON,
            record_refs  JSON,
            confidence   DOUBLE PRECISION,
            freshness    JSON,
            quality      JSON,
            warnings     JSON,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_evidence_request_id ON evidence (request_id);")

    # ---- data_quality_record --------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS data_quality_record (
            id                     SERIAL PRIMARY KEY,
            entity_type            VARCHAR(64) NOT NULL,
            entity_idempotency_key VARCHAR(255) NOT NULL,
            dataset_key            VARCHAR(128),
            quality_status         VARCHAR(16) NOT NULL DEFAULT 'unknown',
            quality_score          DOUBLE PRECISION,
            checks                 JSON,
            reason                 TEXT,
            processing_version     VARCHAR(32) NOT NULL DEFAULT '1.0.0',
            processing_run_id      INTEGER REFERENCES processing_run(id),
            created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)


def downgrade() -> None:
    # Drop in reverse dependency order.
    for table in [
        "data_quality_record",
        "evidence",
        "processing_run",
        "processing_job",
        "ingestion_job",
        "marine_zone",
        "port",
        "station",
        "pfz",
        "advisory",
        "alert",
        "forecast",
        "observation",
        "dataset_asset",
        "dataset",
        "dataset_collection",
        "source",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
