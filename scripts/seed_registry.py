#!/usr/bin/env python3
"""Seed the `dataset` registry from a JSON fixture.

Runs inside the API image (which has psycopg + DATABASE_URL). It performs an
idempotent UPSERT so re-running is safe. This ONLY seeds dataset *registry rows*
(metadata: provider/product/access/verification/status) — it does NOT fabricate
any environmental data. Verification/access states mirror source_mapping.md.

Usage: seed_registry.py <path-to-json>
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: seed_registry.py <fixture.json>", file=sys.stderr)
        return 2

    fixture_path = sys.argv[1]
    with open(fixture_path, encoding="utf-8") as fh:
        rows = json.load(fh)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2

    try:
        import psycopg
    except ImportError:
        print("psycopg not available in this image", file=sys.stderr)
        return 2

    upsert = """
        INSERT INTO dataset (
            dataset_id, provider, product, parameters, coverage,
            spatial_resolution, temporal_resolution, format, update_frequency,
            access_method, authentication, license_policy, priority, status,
            source_url, verification_status
        ) VALUES (
            %(dataset_id)s, %(provider)s, %(product)s, %(parameters)s, %(coverage)s,
            %(spatial_resolution)s, %(temporal_resolution)s, %(format)s, %(update_frequency)s,
            %(access_method)s, %(authentication)s, %(license_policy)s, %(priority)s, %(status)s,
            %(source_url)s, %(verification_status)s
        )
        ON CONFLICT (dataset_id) DO UPDATE SET
            provider = EXCLUDED.provider,
            product = EXCLUDED.product,
            parameters = EXCLUDED.parameters,
            coverage = EXCLUDED.coverage,
            spatial_resolution = EXCLUDED.spatial_resolution,
            temporal_resolution = EXCLUDED.temporal_resolution,
            format = EXCLUDED.format,
            update_frequency = EXCLUDED.update_frequency,
            access_method = EXCLUDED.access_method,
            authentication = EXCLUDED.authentication,
            license_policy = EXCLUDED.license_policy,
            priority = EXCLUDED.priority,
            status = EXCLUDED.status,
            source_url = EXCLUDED.source_url,
            verification_status = EXCLUDED.verification_status,
            updated_at = now();
    """

    inserted = 0
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for row in rows:
                row.setdefault("product", None)
                row.setdefault("parameters", None)
                row.setdefault("coverage", None)
                row.setdefault("spatial_resolution", None)
                row.setdefault("temporal_resolution", None)
                row.setdefault("format", None)
                row.setdefault("update_frequency", None)
                row.setdefault("access_method", None)
                row.setdefault("authentication", None)
                row.setdefault("license_policy", None)
                row.setdefault("priority", 100)
                row.setdefault("status", "DISABLED")
                row.setdefault("source_url", None)
                row.setdefault("verification_status", None)
                cur.execute(upsert, row)
                inserted += 1
        conn.commit()

    print(f"Seeded {inserted} dataset registry rows from {fixture_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
