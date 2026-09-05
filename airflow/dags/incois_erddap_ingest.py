"""INCOIS ERDDAP open-data ingest DAG (P0 — catalog verified, open, WGS84,
standard formats; source_mapping §5.0 / §17.1.2).

Emits per-dataset ingest triggers onto `ingest.incois_erddap`. The worker first
runs ERDDAP-INFO (`/erddap/info/<id>/index.json`) to resolve variables/units/
axes (still UNKNOWN per source_mapping), then performs griddap/tabledap bbox+
time subsets. The connector MUST bundle the GlobalSign intermediate CA and must
never disable TLS verification (V3-TLS).
"""
from __future__ import annotations

import pendulum
from airflow.decorators import dag, task

from marine_common import publish_ingest_trigger

ERDDAP_BASE = "https://erddap.incois.gov.in/erddap"

# Exactly the 16 catalog-verified dataset IDs (source_mapping §5.0).
ERDDAP_DATASET_IDS = [
    "AMSRE_MONTHLY_GLOBAL",
    "ascat_daily_datasets",
    "ascat_mnt_datasets",
    "incois_argo_10day_McCreary",
    "incois_argo_10d_VAM",
    "incois_argo_mnt_McCreary",
    "incois_argo_mnt_VAM",
    "incois_argo_sst_weekly",
    "incois_oceansat2_datasets",
    "incois_quickscat_daily_datasets",
    "incois_quickscat_mnt_datasets",
    "incois_tmi_3day_datasets",
    "incois_valueadded_products_datasets",
    "Indian_ARGO_Floats",
    "IRS_chlorophyll_datasets",
    "NOAA_AVHRR_AMSR_datasets",
]


@dag(
    dag_id="incois_erddap_ingest",
    schedule="0 */6 * * *",  # every 6 hours (daily/composite products)
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    concurrency=4,
    dagrun_timeout=pendulum.duration(minutes=30),
    tags=["marine", "incois", "erddap", "P0"],
    default_args={
        "retries": 3, 
        "retry_delay": pendulum.duration(minutes=2),
        "execution_timeout": pendulum.duration(minutes=10),
    },
)
def incois_erddap_ingest():
    @task(task_id="trigger_erddap_ingest")
    def trigger(dataset_id: str) -> None:
        publish_ingest_trigger(
            subject="MARINE.work.scientific",
            payload={
                "type": "ingest.incois_erddap",
                "connector": "incois_erddap",
                "provider": "INCOIS",
                "erddap_base": ERDDAP_BASE,
                "dataset_id": dataset_id,
                # Worker resolves schema via ERDDAP-INFO before subsetting.
                "resolve_schema_first": True,
            },
        )

    trigger.expand(dataset_id=ERDDAP_DATASET_IDS)


incois_erddap_ingest()
