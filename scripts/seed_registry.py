#!/usr/bin/env python3
"""Seed the `dataset` registry from a JSON fixture.

Runs inside the API image (which has psycopg + DATABASE_URL).

The fixture uses the legacy registry field names, while the canonical
database schema uses:
    dataset.key
    dataset.source_id
    dataset.spatial_coverage
    dataset.fmt
    dataset.auth_required
    dataset.expected_update_interval_s
    dataset.licensing_note

This script maps the fixture fields to the canonical schema.

The operation is idempotent and safe to re-run.

Usage:
    seed_registry.py <path-to-json>
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

_CANONICAL_PROVIDER_CODES = {
    "imd": "IMD",
    "incois": "INCOIS",
    "mosdac": "MOSDAC",
    "marine regions": "Marine Regions",
}

# Map numeric priority strings from the legacy fixture to the documented
# canonical enum values.
_PRIORITY_MAP = {
    "0": "critical_alerts",
    "1": "realtime_observations",
    "2": "normal_ingestion",
    "3": "scientific",
    "4": "backfill_archive",
}


def map_priority(value: Any) -> str:
    """Translate a fixture priority into the canonical enum value.

    Falls back to ``normal_ingestion`` for unknown/missing values.
    """
    return _PRIORITY_MAP.get(str(value).strip(), "normal_ingestion")


def parse_update_interval(value: Any) -> int | None:
    """Extract an explicit polling interval and return seconds."""
    if not value:
        return None

    text = str(value).lower()

    match = re.search(
        r"(?:poll\s+)?(\d+)\s*"
        r"(seconds?|minutes?|hours?|days?|[smhd])\b",
        text,
    )
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)

    multipliers = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 24 * 60 * 60,
    }

    return amount * multipliers[unit[0]]


def authentication_required(value: Any) -> bool:
    """Convert fixture authentication text to the canonical boolean."""
    if value is None:
        return False

    text = str(value).strip().lower()

    if text in {
        "",
        "none",
        "no",
        "false",
        "not required",
    }:
        return False

    return True


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: seed_registry.py <fixture.json>", file=sys.stderr)
        return 2

    fixture_path = sys.argv[1]

    try:
        with open(fixture_path, encoding="utf-8") as fh:
            rows = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Unable to read fixture: {exc}", file=sys.stderr)
        return 1

    if not isinstance(rows, list):
        print("Fixture must contain a JSON array.", file=sys.stderr)
        return 1

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 1

    # psycopg.connect() expects a PostgreSQL URL without
    # SQLAlchemy's "+psycopg" dialect suffix.
    db_url = db_url.replace(
        "postgresql+psycopg://",
        "postgresql://",
    )

    try:
        import psycopg
    except ImportError:
        print("psycopg not available in this image", file=sys.stderr)
        return 2

    # Create or update the source/provider row first.
    source_upsert = """
        INSERT INTO source (
            code,
            name,
            organization,
            base_url,
            live_enabled,
            licensing_note
        )
        VALUES (
            %(code)s,
            %(name)s,
            %(organization)s,
            %(base_url)s,
            FALSE,
            %(licensing_note)s
        )
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            organization = EXCLUDED.organization,
            base_url = EXCLUDED.base_url,
            licensing_note = EXCLUDED.licensing_note
        RETURNING id;
    """

    # Insert/update the dataset using the canonical schema.
    dataset_upsert = """
        INSERT INTO dataset (
            key,
            source_id,
            product,
            parameters,
            spatial_coverage,
            spatial_resolution,
            temporal_resolution,
            fmt,
            access_method,
            auth_required,
            expected_update_interval_s,
            priority,
            status,
            last_result_state,
            status_detail,
            licensing_note
        )
        VALUES (
            %(key)s,
            %(source_id)s,
            %(product)s,
            %(parameters)s,
            %(spatial_coverage)s,
            %(spatial_resolution)s,
            %(temporal_resolution)s,
            %(fmt)s,
            %(access_method)s,
            %(auth_required)s,
            %(expected_update_interval_s)s,
            %(priority)s,
            %(status)s,
            %(last_result_state)s,
            %(status_detail)s,
            %(licensing_note)s
        )
        ON CONFLICT (key) DO UPDATE SET
            source_id = EXCLUDED.source_id,
            product = EXCLUDED.product,
            parameters = EXCLUDED.parameters,
            spatial_coverage = EXCLUDED.spatial_coverage,
            spatial_resolution = EXCLUDED.spatial_resolution,
            temporal_resolution = EXCLUDED.temporal_resolution,
            fmt = EXCLUDED.fmt,
            access_method = EXCLUDED.access_method,
            auth_required = EXCLUDED.auth_required,
            expected_update_interval_s = EXCLUDED.expected_update_interval_s,
            priority = EXCLUDED.priority,
            status = CASE
                WHEN dataset.last_checked_at IS NULL THEN EXCLUDED.status
                ELSE dataset.status
            END,
            last_result_state = CASE
                WHEN dataset.last_checked_at IS NULL THEN EXCLUDED.last_result_state
                ELSE dataset.last_result_state
            END,
            status_detail = CASE
                WHEN dataset.last_checked_at IS NULL THEN EXCLUDED.status_detail
                ELSE dataset.status_detail
            END,
            licensing_note = EXCLUDED.licensing_note,
            updated_at = now();
    """

    seeded = 0

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for row in rows:
                dataset_key = row.get("dataset_id")
                provider = row.get("provider")

                if not dataset_key:
                    print(
                        "Skipping row without dataset_id",
                        file=sys.stderr,
                    )
                    continue

                if not provider:
                    print(
                        f"Skipping {dataset_key}: provider is missing",
                        file=sys.stderr,
                    )
                    continue

                source_url = row.get("source_url")
                license_policy = row.get("license_policy")
                verification_status = row.get("verification_status")

                # Keep verification information because the canonical
                # dataset table does not have a separate verification column.
                licensing_note = license_policy

                if verification_status:
                    if licensing_note:
                        licensing_note = (
                            f"{licensing_note}; "
                            f"Verification: {verification_status}"
                        )
                    else:
                        licensing_note = (
                            f"Verification: {verification_status}"
                        )

                normalized_provider = str(provider).strip()
                source_code = _CANONICAL_PROVIDER_CODES.get(
                    normalized_provider.casefold(), normalized_provider
                )

                cur.execute(
                    source_upsert,
                    {
                        "code": source_code,
                        "name": str(provider),
                        "organization": str(provider),
                        "base_url": source_url,
                        "licensing_note": licensing_note,
                    },
                )

                source_row = cur.fetchone()
                if source_row is None:
                    raise RuntimeError(
                        f"Could not resolve source for provider: {provider}"
                    )

                source_id = source_row[0]

                parameters = row.get("parameters")

                # dataset.parameters is JSON.
                if parameters is not None:
                    parameters = json.dumps(parameters)

                priority = map_priority(row.get("priority", 2))

                status = str(
                    row.get("status", "DISABLED")
                ).lower()

                cur.execute(
                    dataset_upsert,
                    {
                        "key": str(dataset_key),
                        "source_id": source_id,
                        "product": row.get("product"),
                        "parameters": parameters,
                        "spatial_coverage": row.get("coverage"),
                        "spatial_resolution": row.get(
                            "spatial_resolution"
                        ),
                        "temporal_resolution": row.get(
                            "temporal_resolution"
                        ),
                        "fmt": row.get("format"),
                        "access_method": row.get("access_method"),
                        "auth_required": authentication_required(
                            row.get("authentication")
                        ),
                        "expected_update_interval_s": (
                            parse_update_interval(
                                row.get("update_frequency")
                            )
                        ),
                        "priority": priority,
                        "status": status,
                        "last_result_state": row.get("result_state", "not_run"),
                        "status_detail": row.get("status_detail"),
                        "licensing_note": licensing_note,
                    },
                )

                seeded += 1

        conn.commit()

    print(
        f"Seeded {seeded} dataset registry rows "
        f"from {fixture_path}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
