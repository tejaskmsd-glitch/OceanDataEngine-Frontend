"""Deterministic domain logic: geo, freshness, provenance, QC, idempotency.

Also exposes pure unit conversions (:mod:`units`) and domain event factories
(:mod:`events`).
"""

from __future__ import annotations

from . import events, units

__all__ = ["events", "units"]
