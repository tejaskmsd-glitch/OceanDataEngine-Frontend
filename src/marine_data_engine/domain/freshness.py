"""Data freshness and staleness computation.

Freshness is derived from the age of the most recent authoritative timestamp
relative to the dataset's expected update interval. The scoring is configurable
per dataset (``expected_update_interval_s`` and ``stale_multiplier``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Freshness:
    """Computed freshness result."""

    reference_at: datetime | None
    age_seconds: float | None
    age_minutes: float | None
    is_stale: bool
    freshness_score: float  # 1.0 = fresh, 0.0 = fully stale/unknown
    expected_update_interval_s: int | None
    stale_threshold_s: float | None

    def as_dict(self) -> dict:
        return {
            "reference_at": self.reference_at.isoformat() if self.reference_at else None,
            "age_seconds": self.age_seconds,
            "age_minutes": self.age_minutes,
            "is_stale": self.is_stale,
            "freshness_score": self.freshness_score,
            "expected_update_interval_s": self.expected_update_interval_s,
            "stale_threshold_s": self.stale_threshold_s,
        }


def compute_freshness(
    reference_at: datetime | None,
    *,
    now: datetime | None = None,
    expected_update_interval_s: int | None = None,
    stale_multiplier: float = 3.0,
) -> Freshness:
    """Compute freshness for a reference timestamp.

    ``reference_at`` should be the most authoritative "as of" time (e.g.
    ``valid_until`` for a warning, ``observed_at`` for an observation, or the
    dataset's ``last_success_at``).
    """
    now = now or datetime.now(tz=UTC)
    if reference_at is None:
        return Freshness(
            reference_at=None,
            age_seconds=None,
            age_minutes=None,
            is_stale=True,
            freshness_score=0.0,
            expected_update_interval_s=expected_update_interval_s,
            stale_threshold_s=None,
        )

    if reference_at.tzinfo is None:
        reference_at = reference_at.replace(tzinfo=UTC)

    age_s = max(0.0, (now - reference_at).total_seconds())

    if expected_update_interval_s and expected_update_interval_s > 0:
        threshold = expected_update_interval_s * stale_multiplier
        is_stale = age_s > threshold
        # Linear decay to 0 at the stale threshold.
        score = max(0.0, 1.0 - (age_s / threshold)) if threshold > 0 else 0.0
    else:
        # No cadence known: report age but do not assert staleness score decay.
        threshold = None
        is_stale = False
        score = 1.0

    return Freshness(
        reference_at=reference_at,
        age_seconds=age_s,
        age_minutes=age_s / 60.0,
        is_stale=is_stale,
        freshness_score=round(score, 4),
        expected_update_interval_s=expected_update_interval_s,
        stale_threshold_s=threshold,
    )
