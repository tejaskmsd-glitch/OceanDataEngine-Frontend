"""Persist dataset freshness evaluations triggered by Airflow/worker events."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Dataset, DatasetFreshness
from ..domain.freshness import compute_freshness


def evaluate_dataset_freshness(
    session: Session, *, default_stale_multiplier: float = 3.0
) -> list[dict]:
    """Evaluate and upsert freshness for every registered dataset.

    Blocked/disabled/failed states are never overwritten by an age calculation.
    Only healthy/stale datasets transition between those two freshness states.
    """
    now = datetime.now(tz=UTC)
    results: list[dict] = []
    for dataset in session.execute(select(Dataset)).scalars():
        freshness = compute_freshness(
            dataset.last_success_at,
            now=now,
            expected_update_interval_s=dataset.expected_update_interval_s,
            stale_multiplier=dataset.stale_multiplier or default_stale_multiplier,
        )
        row = session.execute(
            select(DatasetFreshness).where(
                DatasetFreshness.dataset_key == dataset.key
            )
        ).scalar_one_or_none()
        if row is None:
            row = DatasetFreshness(dataset_key=dataset.key)
            session.add(row)
        row.last_data_at = freshness.reference_at
        row.expected_interval_s = freshness.expected_update_interval_s
        row.freshness_score = freshness.freshness_score
        row.is_stale = freshness.is_stale
        row.evaluated_at = now

        if dataset.status == "healthy" and freshness.is_stale:
            dataset.status = "stale"
        elif dataset.status == "stale" and not freshness.is_stale:
            dataset.status = "healthy"

        results.append(
            {
                "dataset": dataset.key,
                "status": dataset.status,
                **freshness.as_dict(),
            }
        )
    session.flush()
    return results
