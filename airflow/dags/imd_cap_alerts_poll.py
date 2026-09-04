"""IMD CAP alerts polling DAG (P0 — the only fully verified, public-domain,
machine-readable, signed safety feed; source_mapping §17.1.1).

This DAG only *schedules* a poll and emits an ingest trigger onto NATS subject
`ingest.imd_cap`. The `worker-alerts` role consumes it, fetches the RSS index +
CAP 1.2 items, verifies the signature, normalizes to the `warning` entity, and
publishes `alert.*` events. Heavy work is NOT done here.
"""
from __future__ import annotations

import pendulum
from airflow.decorators import dag, task

from marine_common import publish_ingest_trigger

RSS_INDEX = "https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml"


@dag(
    dag_id="imd_cap_alerts_poll",
    schedule="* * * * *",  # every minute (event-driven safety feed)
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["marine", "imd", "alerts", "P0"],
    default_args={"retries": 3, "retry_delay": pendulum.duration(seconds=15)},
)
def imd_cap_alerts_poll():
    @task(task_id="trigger_cap_ingest")
    def trigger() -> None:
        publish_ingest_trigger(
            subject="ingest.imd_cap",
            payload={
                "connector": "imd_cap_alerts",
                "provider": "IMD",
                "rss_index": RSS_INDEX,
                "priority": "high",
            },
        )

    trigger()


imd_cap_alerts_poll()
