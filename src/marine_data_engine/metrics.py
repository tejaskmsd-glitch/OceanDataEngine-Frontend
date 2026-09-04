"""Prometheus metrics.

A single registry-backed set of metrics covering ingestion, processing,
queue depth, API latency, and data freshness/staleness.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# A dedicated registry keeps metrics isolated and testable.
REGISTRY = CollectorRegistry()

SOURCE_FETCH_TOTAL = Counter(
    "mde_source_fetch_total",
    "Source fetch attempts by source, dataset and outcome.",
    ["source", "dataset", "outcome"],
    registry=REGISTRY,
)

RECORDS_PROCESSED_TOTAL = Counter(
    "mde_records_processed_total",
    "Canonical records processed by dataset and QC outcome.",
    ["dataset", "qc_status"],
    registry=REGISTRY,
)

JOB_TOTAL = Counter(
    "mde_job_total",
    "Processing/ingestion jobs by type and terminal status.",
    ["job_type", "status"],
    registry=REGISTRY,
)

QUEUE_DEPTH = Gauge(
    "mde_queue_depth",
    "Current queue depth per priority subject.",
    ["priority"],
    registry=REGISTRY,
)

DLQ_DEPTH = Gauge(
    "mde_dlq_depth",
    "Dead-letter queue depth per priority subject.",
    ["priority"],
    registry=REGISTRY,
)

DATASET_AGE_SECONDS = Gauge(
    "mde_dataset_age_seconds",
    "Seconds since the last successful update per dataset.",
    ["dataset"],
    registry=REGISTRY,
)

DATASET_STALE = Gauge(
    "mde_dataset_stale",
    "1 if the dataset is stale, else 0.",
    ["dataset"],
    registry=REGISTRY,
)

PROCESSING_SECONDS = Histogram(
    "mde_processing_seconds",
    "Processing duration per job type.",
    ["job_type"],
    registry=REGISTRY,
)

API_REQUEST_SECONDS = Histogram(
    "mde_api_request_seconds",
    "API request latency by route and method.",
    ["route", "method", "status"],
    registry=REGISTRY,
)
