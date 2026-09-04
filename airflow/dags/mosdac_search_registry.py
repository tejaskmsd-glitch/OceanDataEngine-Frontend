"""MOSDAC search -> dataset registry DAG (P0-support; source_mapping §17.1.3).

Populates the dataset registry / catalog candidates from the open, unauthenticated
MOSDAC OpenSearch API (`/apios/datasets.json`). Product-BYTE retrieval is
download-blocked until MOSDAC credentials are supplied (AUTH-A) — this DAG only
discovers/catalogs and marks products download-blocked. Gallery quicklooks are
VISUAL-ONLY and excluded from numeric ingest.
"""
from __future__ import annotations

import pendulum
from airflow.decorators import dag, task

from marine_common import publish_ingest_trigger

MOSDAC_SEARCH = "https://mosdac.gov.in/apios/datasets.json"


@dag(
    dag_id="mosdac_search_registry",
    schedule="0 */12 * * *",  # twice daily discovery
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["marine", "mosdac", "registry", "P0-support"],
    default_args={"retries": 3, "retry_delay": pendulum.duration(minutes=2)},
)
def mosdac_search_registry():
    @task(task_id="trigger_mosdac_search")
    def trigger() -> None:
        publish_ingest_trigger(
            subject="ingest.mosdac_search",
            payload={
                "connector": "mosdac_search",
                "provider": "MOSDAC",
                "search_url": MOSDAC_SEARCH,
                # No credentials -> discovery/catalog only, downloads blocked.
                "download_enabled": False,
            },
        )

    trigger()


mosdac_search_registry()
