"""realtime source provenance and explicit dataset outcomes

Adds the canonical fields required to distinguish a healthy empty source poll
from disabled, auth-blocked, contract-unavailable, license-gated, and failed
sources. It also preserves structured upstream metadata on environmental
records, station status/last-report time, and marine-zone provenance.

Revision ID: 0004_realtime_source_provenance
Revises: 0003_evidence_provenance
Create Date: 2026-09-05
"""
from __future__ import annotations

from alembic import op

revision = "0004_realtime_source_provenance"
down_revision = "0003_evidence_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dataset polling outcome. last_checked_at distinguishes never-run from a
    # source that was contacted and returned zero canonical records.
    op.execute("ALTER TABLE dataset ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ;")
    op.execute("ALTER TABLE dataset ADD COLUMN IF NOT EXISTS last_result_count INTEGER;")
    op.execute("ALTER TABLE dataset ADD COLUMN IF NOT EXISTS last_result_state VARCHAR(32);")
    op.execute("ALTER TABLE dataset ADD COLUMN IF NOT EXISTS status_detail TEXT;")

    # Structured source metadata is additive and defaults to a valid object.
    for table in ("observation", "forecast", "alert", "advisory", "pfz"):
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
            "source_metadata JSON NOT NULL DEFAULT '{}';"
        )

    op.execute("ALTER TABLE observation ADD COLUMN IF NOT EXISTS sensor_id VARCHAR(128);")

    op.execute("ALTER TABLE station ADD COLUMN IF NOT EXISTS source_dataset VARCHAR(128);")
    op.execute("ALTER TABLE station ADD COLUMN IF NOT EXISTS status VARCHAR(64);")
    op.execute("ALTER TABLE station ADD COLUMN IF NOT EXISTS last_reported_at TIMESTAMPTZ;")
    op.execute("ALTER TABLE station ADD COLUMN IF NOT EXISTS retrieved_at TIMESTAMPTZ;")
    op.execute(
        "ALTER TABLE station ADD COLUMN IF NOT EXISTS "
        "source_metadata JSON NOT NULL DEFAULT '{}';"
    )
    op.execute(
        "ALTER TABLE station ADD COLUMN IF NOT EXISTS "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now();"
    )

    op.execute("ALTER TABLE marine_zone ADD COLUMN IF NOT EXISTS source_dataset VARCHAR(128);")
    op.execute("ALTER TABLE marine_zone ADD COLUMN IF NOT EXISTS retrieved_at TIMESTAMPTZ;")
    op.execute(
        "ALTER TABLE marine_zone ADD COLUMN IF NOT EXISTS "
        "source_metadata JSON NOT NULL DEFAULT '{}';"
    )
    op.execute(
        "ALTER TABLE marine_zone ADD COLUMN IF NOT EXISTS "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now();"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_marine_zone_zone_uid "
        "ON marine_zone (zone_uid);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_marine_zone_zone_uid;")
    for column in ("updated_at", "source_metadata", "retrieved_at", "source_dataset"):
        op.execute(f"ALTER TABLE marine_zone DROP COLUMN IF EXISTS {column};")
    for column in (
        "updated_at",
        "source_metadata",
        "retrieved_at",
        "last_reported_at",
        "status",
        "source_dataset",
    ):
        op.execute(f"ALTER TABLE station DROP COLUMN IF EXISTS {column};")
    op.execute("ALTER TABLE observation DROP COLUMN IF EXISTS sensor_id;")
    for table in ("pfz", "advisory", "alert", "forecast", "observation"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS source_metadata;")
    for column in ("status_detail", "last_result_state", "last_result_count", "last_checked_at"):
        op.execute(f"ALTER TABLE dataset DROP COLUMN IF EXISTS {column};")
