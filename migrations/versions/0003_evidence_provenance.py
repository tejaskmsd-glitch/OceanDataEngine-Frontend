"""evidence provenance columns (MCP readiness)

Adds MCP-readiness provenance fields to the ``evidence`` table so an API
response's evidence package can honestly record:

* ``capability_status`` — one of 'available', 'source_gap', 'blocked',
  'not_started', 'degraded' (VARCHAR(32), nullable; existing rows keep NULL).
* ``data_versions`` — JSON object mapping dataset key -> version/timestamp used
  to build the response, e.g. {"imd_cap": "2026-09-05T00:00Z"}.
* ``data_lineage`` — JSON array of structured processing steps, e.g.
  [{"step": "ingest", "source": "IMD CAP", "job_uid": "...", "at": "..."}].

The migration mirrors the backend ORM (``src/marine_data_engine/db/models.py``
``Evidence`` class) EXACTLY and is written as explicit SQL (it does not import
the ORM), matching the style of 0001_initial_canonical.

Design notes
------------
* All three columns are additive and nullable/defaulted so existing rows and
  existing writers keep working (``ADD COLUMN`` without NOT NULL).
* JSON columns get server defaults ('{}' / '[]') so rows inserted by paths that
  do not set them still hold well-formed, non-NULL JSON.

Revision ID: 0003_evidence_provenance
Revises: 0002_postgis_spatial_columns
Create Date: 2026-09-05T09:48Z
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_evidence_provenance"
down_revision = "0002_postgis_spatial_columns"
branch_labels = None
depends_on = None


# Allowed capability_status values (enforced in the application layer, matching
# the ORM contract which stores the plain string). Documented here for
# reference / optional CHECK use.
_CAPABILITY_STATUS = (
    "available",
    "source_gap",
    "blocked",
    "not_started",
    "degraded",
)


def upgrade() -> None:
    # ---- evidence: MCP-readiness provenance columns (additive, nullable) ---
    op.execute("""
        ALTER TABLE evidence
            ADD COLUMN IF NOT EXISTS capability_status VARCHAR(32);
    """)
    op.execute("""
        ALTER TABLE evidence
            ADD COLUMN IF NOT EXISTS data_versions JSON DEFAULT '{}';
    """)
    op.execute("""
        ALTER TABLE evidence
            ADD COLUMN IF NOT EXISTS data_lineage JSON DEFAULT '[]';
    """)


def downgrade() -> None:
    # Drop in reverse order of addition.
    op.execute("ALTER TABLE evidence DROP COLUMN IF EXISTS data_lineage;")
    op.execute("ALTER TABLE evidence DROP COLUMN IF EXISTS data_versions;")
    op.execute("ALTER TABLE evidence DROP COLUMN IF EXISTS capability_status;")
