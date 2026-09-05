"""Dataset freshness sweep DAG (requirements §13/§16).

Periodically triggers the freshness evaluator so each dataset's staleness class
(HEALTHY/STALE/DEGRADED/FAILED/DISABLED) and freshness_score are recomputed and
sampled into the `dataset_freshness` hypertable. Safety-critical datasets (CAP,
tsunami, surge) must never be served as fresh without an explicit age/status.
"""
from __future__ import annotations

import pendulum
from airflow.decorators import dag, task
from marine_common import publish_ingest_trigger


@dag(
    dag_id="dataset_freshness_sweep",
    schedule="*/5 * * * *",  # every 5 minutes
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    concurrency=2,
    dagrun_timeout=pendulum.duration(minutes=10),
    tags=["marine", "freshness", "health"],
    default_args={
        "retries": 2,
        "retry_delay": pendulum.duration(seconds=30),
        "execution_timeout": pendulum.duration(minutes=5),
    },
)
def dataset_freshness_sweep():
    @task(task_id="trigger_freshness_eval")
    def trigger() -> None:
        publish_ingest_trigger(
            subject="MARINE.work.normal_ingestion",
            payload={"type": "process.freshness_eval", "job_type": "freshness_eval"},
        )

    trigger()


dataset_freshness_sweep()
