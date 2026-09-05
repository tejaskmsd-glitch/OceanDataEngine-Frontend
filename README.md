# Marine Data Layer — Local Platform / Operations

This directory contains the **platform & operations** layer for the Marine
Intelligence Data Layer: Docker Compose stack, Dockerfiles, database init +
Alembic migrations, Airflow DAGs, observability (Prometheus / Grafana /
OpenTelemetry), and bootstrap/fixture tooling.

It stands up the Phase-0 substrate described in `prompt.md` §32 and
`marine_data_layer_requirements.md`, and is deliberately **AI-agnostic**.

> Backend Python source (`src/marine_data_engine/…`), `pyproject.toml`, and the
> React `dashboard/` source are owned by other workstreams. This layer builds,
> runs, migrates, and observes them — it does **not** modify their source.

---

## What the stack runs

| Service | Purpose | Host port |
|---|---|---|
| `postgres` | PostgreSQL **+ PostGIS + TimescaleDB** (canonical + time-series) | 5432 |
| `minio` | S3-compatible object store (raw immutable + processed) | 19000 / 19001 |
| `minio-init` | one-shot: creates `marine-raw`, `marine-processed`, `marine-artifacts` | — |
| `redis` | cache / rate-limit / light broker | 6379 |
| `nats` | **NATS JetStream** work queues + live alert events | 14222 / 18222 |
| `otel-collector` | OpenTelemetry traces/metrics fan-in | 14317 / 14318 / 18889 |
| `api` | FastAPI application (query-only) | 8000 |
| `worker-ingest` | source fetch → raw object store | — |
| `worker-process` | decode / normalize / QC / derived products (heavy) | — |
| `worker-alerts` | priority CAP/hazard events (isolated) | — |
| `airflow-init` | one-shot Airflow DB migrate + admin user | — |
| `airflow-scheduler` | source DAG scheduling (LocalExecutor) | — |
| `airflow-webserver` | Airflow UI | 8080 |
| `prometheus` | metrics scraping | 19090 |
| `grafana` | dashboards (provisioned) | 13000 |
| `dashboard` | React ops dashboard (static via nginx) | 5173 |

Every long-running service declares a healthcheck and dependency ordering.
All image versions are pinned. No secrets are committed.

---

## Prerequisites

- Docker Engine + Docker Compose v2 (`docker compose version`)
- ~8 GB free RAM recommended (Airflow + Postgres + scientific images)

---

## Quick start (exact commands)

```bash
# 1. Create your local env file (never committed; edit passwords before sharing)
make env            # copies .env.example -> .env if absent

# 2. One-command bring-up: build -> up -> wait for DB -> migrate -> seed registry
make bootstrap
```

`make bootstrap` prints the URLs when done:

```
API:        http://localhost:8000        (OpenAPI docs at /docs)
Dashboard:  http://localhost:5173
Grafana:    http://localhost:13000       (user/pass from .env)
Airflow:    http://localhost:8080        (user/pass from .env)
Prometheus: http://localhost:19090
MinIO:      http://localhost:19001       (console; user/pass from .env)
```

### Step-by-step (equivalent to bootstrap)

```bash
make env                 # .env from .env.example
make build               # build all images
make up                  # start the stack (detached)
make migrate             # apply Alembic canonical schema
make seed-registry       # seed dataset registry fixtures (verified sources)
make ps                  # check service/health status
make logs                # tail logs
```

### Common operations

```bash
make down                # stop stack, keep volumes
make restart             # down + up
make migrate-down        # roll back one migration
make validate            # validate compose config
make validate-dockerfiles# lint Dockerfiles (hadolint if available)
make nuke                # DESTRUCTIVE: down + delete all volumes
```

---

## Database migrations (Alembic)

Migrations create the **canonical marine schema** (requirements §7, §17;
source_mapping §7): dataset registry, processing jobs, `observation` /
`forecast` (TimescaleDB hypertables), `warning` / `cyclone` / `tsunami_event`,
`pfz`, `fishery_advisory`, `station`, `zone` (geofence), `bathymetry` (table planned, currently pending source data),
`evidence`, and `dataset_freshness`.

- Geometry columns currently use **TEXT (GeoJSON)** (native PostGIS integration is in progress).
- Hypertable creation is guarded, so migrations also succeed on a PostGIS-only DB.
- **TimescaleDB requirement**: Hypertables (e.g. `observation`, `forecast`) use a composite primary key (`id`, `[time_column]`) because the partition column must be part of any unique/primary index.
- Migrations are **explicit SQL** and do **not** import backend SQLAlchemy models
  — they coordinate with the backend by matching the documented canonical fields.
  If the backend later manages its own metadata, run migrations against the
  canonical tables only and reconcile ownership before enabling autogenerate.

```bash
make migrate       # alembic upgrade head
make migrate-down  # alembic downgrade -1
```

---

## Object storage

`minio-init` creates the buckets on first boot and enables **versioning on the
raw bucket** (`marine-raw`) so raw scientific files are not silently overwritten
(prompt §20 "immutable raw"). Buckets: `marine-raw`, `marine-processed`,
`marine-artifacts` (overridable via `.env`).

---

## Events (NATS JetStream)

JetStream is enabled (`nats -js`). Logical subjects (documented contract):

- `ingest.*`   — ingest triggers (Airflow → workers)
- `process.*`  — processing/derived jobs
- `alert.*`    — normalized alert events (workers → API/dashboard stream)
- `events.*`   — general domain events

Airflow DAGs publish thin ingest triggers; the dedicated workers do the heavy
fetch/decode/normalize/QC so no heavy work runs in the orchestrator or in
synchronous API requests (prompt §4).

---

## Airflow DAGs

| DAG | Schedule | Purpose | Verification |
|---|---|---|---|
| `imd_cap_alerts_poll` | every 1 min | Trigger IMD CAP alert ingest | endpoint/parser verified |
| `incois_hwa_swell_poll` | every 15 min | Trigger INCOIS HWA/SSA + district geometry ingest | live contract verified |
| `incois_pfz_poll` | every 3 h | Trigger native PFZ Point + LineString ingest | live contract verified |
| `incois_tews_tide_poll` | every 10 min | Enumerate TEWS stations and ingest explicit latest sensor values | live contract verified |
| `incois_oon_buoy_poll` | twice hourly | Enumerate active OON stations and ingest strict wave/wind chart values | live contract verified |
| `incois_ww3_poll` | every 3 h | Trigger INCOIS WaveWatch III numeric wave/period/swell/wind point forecasts | live contract verified |
| `incois_erddap_ingest` | every 6 h | Trigger per-dataset ERDDAP metadata ingest | catalog verified |
| `mosdac_search_registry` | every 12 h | Discovery → registry (downloads excluded) | search verified |
| `dataset_freshness_sweep` | every 5 min | Recompute dataset freshness/staleness | platform |

Verified live DAGs are unpaused at creation by default. Set
`AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=true` or
`MDE_ENABLE_LIVE_SOURCES=false` for a deliberately disabled deployment. IMD
numeric NWP has no schedule because its numeric endpoint/auth/schema contract is
unavailable. Marine Regions EEZ has no schedule while license approval is gated.

---

## Observability

- **Prometheus** scrapes `api`, workers (`:9100/metrics`), `nats`, and the OTel
  collector. Config: `observability/prometheus/prometheus.yml`.
- **Grafana** auto-provisions the Prometheus datasource and the
  *Marine Data Layer — Operations* dashboard.
- **OpenTelemetry**: services export OTLP to `otel-collector:4317`
  (`OTEL_EXPORTER_OTLP_ENDPOINT`). The collector re-exports metrics on `:8889`
  and logs traces locally (swap for Tempo/Jaeger later).

---

## Configuration & secrets

All configuration lives in `.env` (copied from `.env.example`, git-ignored).
**No real credentials are committed.** Source connector credentials
(`MOSDAC_*`, `IMD_API_TOKEN`) are intentionally blank locally, which keeps the
corresponding connectors disabled until verified access is obtained — see
[`SOURCE_GAPS.md`](./SOURCE_GAPS.md).

INCOIS hosts that omit their intermediate certificate are handled by augmenting
the platform trust store with the bundled **GlobalSign RSA OV SSL CA 2018**
intermediate. `INCOIS_CA_BUNDLE` can add an operator-managed PEM bundle;
hostname and certificate verification are never disabled (source_mapping
V3-TLS).

---

## Validation performed

- `docker compose config` — **passes** (stack resolves).
- Alembic migration, DAGs, and seed script — **`py_compile` clean**.
- Prometheus / OTel / Grafana YAML and dashboard/fixture JSON — **parse clean**.
- Dockerfiles — hadolint reports only style-level warnings (versions are pinned
  via pinned base images + `pyproject.toml`; `sh -c` CMDs are intentional for
  runtime env-var expansion).

---

## Source limitations

Live PFZ, HWA/SSA, TEWS tide observations, and dynamically enumerated INCOIS OON
buoy wave/wind observations have verified production adapters and schedules.
Production never falls back to fixtures, and healthy empty polls remain empty.

Two deliberate gates remain: IMD numeric marine NWP is
`contract_unavailable` (no verified numeric endpoint/schema/auth-header
contract), and Marine Regions India EEZ ingestion is `license_gated` pending an
operator-reviewed permission/attribution reference. Marine protected,
restricted, naval, and firing-range geometry remains independently unavailable;
EEZ coverage never implies those categories are loaded. See
[`SOURCE_GAPS.md`](./SOURCE_GAPS.md) for exact endpoint, provenance, and state
semantics.
