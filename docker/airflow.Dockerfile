# =============================================================================
# airflow.Dockerfile — Airflow runtime for source DAG orchestration.
# Built on the official pinned Airflow image (LocalExecutor is used in compose
# for a valid lightweight runtime: init + scheduler + webserver, no Celery).
# Adds the Postgres provider and light HTTP deps used by discovery/poll DAGs.
# Heavy scientific decoding stays in the dedicated Python workers, NOT here —
# Airflow only orchestrates/schedules and hands work to the worker queues.
# =============================================================================
FROM apache/airflow:2.10.4-python3.12

# Providers + light client libs for orchestration DAGs (HTTP polling, NATS/S3
# handoff triggers). Pinned to keep the constraint-managed image reproducible.
USER airflow
RUN pip install --no-cache-dir \
        "apache-airflow-providers-postgres==5.14.0" \
        "apache-airflow-providers-http==4.13.3" \
        "requests==2.32.3" \
        "nats-py==2.9.0"
