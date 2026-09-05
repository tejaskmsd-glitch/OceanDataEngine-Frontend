# Marine Data Engine — Backend (Python)

Source-agnostic marine **data layer** backend: ingestion, immutable raw
storage, canonical normalization, quality control, freshness/provenance
tracking, priority-isolated work queue, background worker runtime, and a
**query-only** FastAPI. The backend is **AI-agnostic** — no LLM, agent
framework, or vector database is imported anywhere in the runtime path.

This package (`src/marine_data_engine/…`) is the backend workstream. It does
not modify `dashboard/`, compose files, Dockerfiles, `airflow/`, or monitoring
config.

## Layout

```
src/marine_data_engine/
├── config.py            env-driven settings (12-factor; secrets from env)
├── logging_config.py    structlog structured logging
├── metrics.py           Prometheus metrics (ingest/process/queue/DLQ/freshness)
├── db/
│   ├── base.py          declarative base + portable GeometryJSON/timestamp types
│   ├── enums.py         QC/job/priority/dataset/severity enums
│   ├── models.py        canonical SQLAlchemy models (all required entities)
│   └── session.py       engine/session/metadata helpers
├── domain/
│   ├── geo.py           haversine/bearing/centroid/point-in-polygon (WGS84)
│   ├── freshness.py     configurable staleness + freshness scoring
│   ├── qc.py            schema/range/temporal/spatial QC + scoring
│   └── idempotency.py   deterministic idempotency keys
├── storage/raw_store.py MinIO/S3 immutable raw storage (+ in-memory backend)
├── messaging/
│   ├── subjects.py      priority subjects, DLQ subjects, backoff+jitter
│   └── queue.py         priority queue (in-memory) + JetStream adapter
├── sources/
│   ├── base.py          adapter interfaces + parsed record dataclasses
│   ├── imd_cap.py       IMD CAP 1.2 parser (fixture + DISABLED live)
│   └── incois_pfz.py    INCOIS PFZ parser (fixture + DISABLED live)
├── services/
│   ├── registry.py      source/dataset registry seeding
│   ├── ingestion.py     parse→raw store→QC→canonical→lineage→events
│   └── queries.py       query-only repositories (processed data only)
├── api/
│   ├── schemas.py       explicit Pydantic v2 schemas + response envelope
│   ├── broker.py        in-process alert broker for WebSocket fan-out
│   └── app.py           FastAPI app + endpoints + WS
└── worker/runtime.py    priority-draining worker (retry/backoff/DLQ)
```

## Canonical model

All required entities are implemented in `db/models.py`: `Dataset`,
`DatasetCollection`, `DatasetAsset`, `Source`, `Observation`, `Forecast`,
`Alert`, `Advisory`, `PFZ`, `Station`, `Port`, `MarineZone`, `ProcessingJob`,
`IngestionJob`, `ProcessingRun`, `Evidence`, `DataQualityRecord`.

Environmental records preserve **distinct** timestamps — `observed_at`,
`issued_at`, `valid_from`, `valid_until`, `forecast_time`, `retrieved_at`,
`processed_at` — plus provenance (`provider`, `source_dataset`, `source_url`,
`processing_version`), QC fields (`quality_status`, `quality_score`,
`missing_flag`, `outlier_flag`, `interpolated_flag`), and an `idempotency_key`.

### Persistence portability

Production targets **PostgreSQL + PostGIS + TimescaleDB**. For deterministic,
dependency-light tests the ORM uses portable column types: geometry is stored
as canonical **GeoJSON (WGS84 / EPSG:4326)** via `GeometryJSON`, and timestamps
are timezone-aware UTC. The Python API and GeoJSON contract are identical to
the PostGIS target, so promoting geometry columns to `geometry(Geometry, 4326)`
with GIST indexes (in the platform-owned Alembic migrations) does not change
services or schemas. Spatial predicates used by the query layer
(haversine distance, point-in-polygon) map directly to
`ST_DWithin`/`ST_Distance`/`ST_Contains`.

## Queue priority isolation & reliability

Five isolated priority classes (`messaging/subjects.py`):
`critical_alerts` → `realtime_observations` → `normal_ingestion` →
`scientific` → `backfill_archive`. Critical alerts always drain first and can
never be blocked by backfill/archive work.

The queue provides idempotent enqueue, attempt tracking, **exponential backoff
with full jitter**, explicit job status, and **dead-letter** after
`max_attempts`. The worker (`worker/runtime.py`) dispatches by event type,
acks on success, and nacks (retry/DLQ) on failure, emitting Prometheus metrics.

## Source connectors

- **IMD CAP** parses the verified RSS-linked CAP 1.2 feed. Parsing does not
  claim XML-signature trust-chain verification.
- **INCOIS PFZ** fetches verified Gemini destination `Point` and advisory
  `LineString` FeatureCollections and preserves those types exactly.
- **INCOIS HWA/SSA** double-decodes live alert arrays, joins authoritative
  district polygons, and parses validity in `Asia/Kolkata`.
- **INCOIS TEWS tide** enumerates official stations and accepts only explicit
  latest `RAD`/`PRS`/`ENC` sensor timestamp/value fields.
- **INCOIS OON buoy** dynamically enumerates active stations and validates the
  selected parameter token, label, unit, UTC declaration, and freshness.
- **IMD numeric NWP** is deliberately `contract_unavailable`; it sends no
  guessed endpoint or authentication request.
- **Marine Regions India EEZ** is implemented but license-gated before network
  access. MPA/restricted/naval/firing geometry remains independently absent.

Workers always construct live adapters. `MDE_ENABLE_LIVE_SOURCES=false` records
an explicit disabled state; it never switches production ingestion to fixtures.
Fixtures are synthetic, explicit test inputs only.

## API (query-only)

All handlers read processed/canonical data only. Endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/health` | liveness + build/env info |
| GET | `/v1/datasets` | dataset registry |
| GET | `/v1/data-health` | per-dataset freshness/staleness |
| GET | `/v1/fishing/pfz` | nearest PFZ within radius (distance/validity) |
| GET | `/v1/alerts` | active/spatial alerts |
| GET | `/v1/evidence/{request_id}` | provenance/evidence for a prior response |
| WS  | `/v1/stream/alerts` | live alert event stream |

Every response uses the canonical envelope (`data`/`meta`/`sources`/`quality`/
`warnings`) and persists an `Evidence` row addressable by `request_id`.

## Configuration

Environment-driven (`config.py`); secrets are read from the environment and are
never committed. Key variables:

```
MDE_ENVIRONMENT, MDE_LOG_LEVEL, MDE_LOG_JSON, MDE_ENABLE_LIVE_SOURCES
MDE_DB_HOST/PORT/NAME/USER/PASSWORD  or  MDE_DB_URL_OVERRIDE
MDE_S3_ENDPOINT_URL/REGION/ACCESS_KEY/SECRET_KEY/RAW_BUCKET/IN_MEMORY
MDE_NATS_SERVERS/STREAM_PREFIX/MAX_DELIVER
```

## Install & test

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,storage]"
pytest
```

Tests are **deterministic and offline**: SQLite in-memory DB, in-process object
store, disabled live sources, fixture-only data, no network access.
