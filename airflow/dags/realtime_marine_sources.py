"""Schedules for verified real-time INCOIS marine sources.

Each DAG emits only a thin NATS trigger. IMD numeric NWP has no DAG because its
auth/endpoint/schema contract is unavailable. Marine Regions EEZ has no
schedule until an operator supplies reviewed license/attribution terms.
"""
from __future__ import annotations

import os

import pendulum
from airflow.decorators import dag, task
from marine_common import publish_ingest_trigger

_DEFAULT_ARGS = {
    "retries": 3,
    "retry_delay": pendulum.duration(minutes=2),
    "execution_timeout": pendulum.duration(minutes=20),
}


@dag(
    dag_id="incois_hwa_swell_poll",
    schedule=os.environ.get("MDE_HWA_SCHEDULE", "*/15 * * * *"),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["marine", "incois", "high-wave", "swell", "realtime"],
    default_args=_DEFAULT_ARGS,
)
def incois_hwa_swell_poll():
    @task
    def trigger() -> None:
        publish_ingest_trigger(
            subject="MARINE.work.critical_alerts",
            payload={"type": "ingest.incois_hwa", "provider": "INCOIS"},
        )

    trigger()


@dag(
    dag_id="incois_pfz_poll",
    schedule=os.environ.get("MDE_PFZ_SCHEDULE", "17 */3 * * *"),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["marine", "incois", "pfz", "realtime"],
    default_args=_DEFAULT_ARGS,
)
def incois_pfz_poll():
    @task
    def trigger() -> None:
        publish_ingest_trigger(
            subject="MARINE.work.realtime_observations",
            payload={"type": "ingest.incois_pfz", "provider": "INCOIS"},
        )

    trigger()


@dag(
    dag_id="incois_tews_tide_poll",
    schedule=os.environ.get("MDE_TIDE_SCHEDULE", "*/10 * * * *"),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["marine", "incois", "tews", "tide", "realtime"],
    default_args=_DEFAULT_ARGS,
)
def incois_tews_tide_poll():
    @task
    def trigger() -> None:
        publish_ingest_trigger(
            subject="MARINE.work.realtime_observations",
            payload={"type": "ingest.incois_tide", "provider": "INCOIS"},
        )

    trigger()


@dag(
    dag_id="incois_oon_buoy_poll",
    schedule=os.environ.get("MDE_BUOY_SCHEDULE", "7,37 * * * *"),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["marine", "incois", "oon", "buoy", "realtime"],
    default_args=_DEFAULT_ARGS,
)
def incois_oon_buoy_poll():
    @task
    def trigger() -> None:
        publish_ingest_trigger(
            subject="MARINE.work.realtime_observations",
            payload={
                "type": "ingest.incois_buoy",
                "provider": "INCOIS",
                "parameter_tokens": ["hm0", "wind_speed"],
            },
        )

    trigger()


@dag(
    dag_id="incois_ww3_poll",
    # The model publishes one init per day; a 3-hourly poll keeps the newest
    # init and the nearest forecast steps fresh without hammering THREDDS. The
    # catalogue and dataset description are served from the Redis lazy cache, so
    # a poll normally costs only the per-point NCSS queries.
    schedule=os.environ.get("MDE_INCOIS_WW3_SCHEDULE", "0 */3 * * *"),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["marine", "incois", "ww3", "wave", "forecast", "realtime"],
    default_args=_DEFAULT_ARGS,
)
def incois_ww3_poll():
    @task
    def trigger() -> None:
        publish_ingest_trigger(
            subject="MARINE.work.realtime_observations",
            payload={
                "type": "ingest.incois_ww3",
                "dataset": "incois_ww3",
            },
        )

    trigger()


incois_ww3_poll()


@dag(
    dag_id="imd_marine_bulletin_poll",
    # Bulletins carry a 12 h validity and are issued roughly twice daily, so a
    # 30 minute poll is ample. The Redis cache collapses repeat reads inside a
    # bulletin's validity window so this is gentle on the upstream host.
    schedule=os.environ.get("MDE_IMD_BULLETIN_SCHEDULE", "*/30 * * * *"),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["marine", "imd", "bulletin", "wind", "sea-state", "realtime"],
    default_args=_DEFAULT_ARGS,
)
def imd_marine_bulletin_poll():
    @task
    def trigger() -> None:
        publish_ingest_trigger(
            subject="MARINE.work.realtime_observations",
            payload={
                "type": "ingest.imd_marine_bulletin",
                "provider": "IMD",
            },
        )

    trigger()


incois_hwa_swell_poll()
incois_pfz_poll()
incois_tews_tide_poll()
incois_oon_buoy_poll()
imd_marine_bulletin_poll()
