"""Idempotency helpers.

A stable idempotency key uniquely identifies a logical upstream record so that
repeated ingestion does not create duplicates. Keys are deterministic hashes of
the identifying tuple (provider, dataset, native id, and time semantics).
"""

from __future__ import annotations

import hashlib
from datetime import datetime


def _norm(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def make_idempotency_key(*parts: object) -> str:
    """Return a deterministic sha256 hex idempotency key for the given parts."""
    joined = "|".join(_norm(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
