# Marine Intelligence Data Layer — Master Build & Research Prompt

## Context

We are building the **data layer first** for an Agentic AI-powered Marine Intelligence Platform.

The conversational AI/agent application is **out of scope for the first phase**. The immediate objective is to build a reliable, source-agnostic marine data platform that continuously ingests, processes, normalizes, enriches, stores, and serves marine information through concrete APIs.

The future AI/agent layer will sit on top of these APIs and expose selected APIs as tools. Therefore, the data layer must be completely **AI-agnostic** and must provide deterministic, well-documented, evidence-backed capabilities.

Primary source families already investigated:

- MOSDAC / ISRO / SAC
- INCOIS / MoES
- IMD

The current source reconnaissance identified heterogeneous access mechanisms and formats, including NetCDF, HDF/HDF5, GRIB2, BUFR, ASCII/CSV, PNG/JPG quicklooks, RSS/XML/CAP, GeoJSON, and JavaScript-rendered/interactive portals. MOSDAC includes authenticated catalog access and open-data products; INCOIS includes OSF, PFZ, ecosystem services, buoy/tide/observation systems, LAS/ERDDAP/ESSDP; IMD includes marine observations, warnings/CAP, NWP products, marine forecasts, radar/satellite assets, and API access. Source access is subject to authentication, quotas, rate limits, licensing, and redistribution restrictions.

---

# 1. Core Objective

Build a **near-real-time Marine Data Engine** that can:

1. Discover and ingest authoritative marine, meteorological, satellite, oceanographic, advisory, and geospatial data.
2. Process data continuously using robust background workers.
3. Normalize heterogeneous datasets into a canonical marine data model.
4. Store immutable raw data plus processed/derived data in appropriate storage tiers.
5. Perform spatial, temporal, statistical, and domain-specific calculations.
6. Maintain freshness, data quality, provenance, and processing lineage.
7. Expose stable REST/geospatial/streaming APIs for applications and future agent tools.
8. Serve map layers and visual products for a lightweight React dashboard.
9. Provide a comprehensive operational dashboard showing ingestion and processed-data status, not a heavy business application.
10. Make it straightforward later to wrap each API capability as an AI tool.

The data layer must not depend on any LLM, agent framework, vector database, or conversational application.

---

# 2. Architectural Boundary

The intended separation is:

```text
                         FUTURE AGENTIC LAYER
              Planner / Marine Agent / Risk Agent / etc.
                                |
                           Tool Interface
                                |
                                v
                     +-------------------------+
                     |     MARINE DATA API     |
                     |-------------------------|
                     | Ocean Conditions        |
                     | Forecasts               |
                     | Weather                 |
                     | PFZ                     |
                     | Fishing Suitability     |
                     | Tides                   |
                     | Alerts                  |
                     | Geofencing              |
                     | Marine Risk             |
                     | Routing                 |
                     | Evidence / Provenance   |
                     | Tiles / Streams         |
                     +------------+------------+
                                  |
                           Canonical Model
                                  |
               +------------------+------------------+
               |                  |                  |
             MOSDAC             INCOIS              IMD
               |                  |                  |
          Satellite/Ocean     Ocean/PFZ           Weather/NWP
          SST/CHL/etc.        Buoys/Tides         Marine Obs/CAP
```

The data layer answers:

> What is happening, what was observed, what is forecast, what warnings are active, what zones exist, and what deterministic derived indicators can be computed for a location/time/context?

The future agent layer answers:

> Which capabilities should be called, in what order, and how should the results be explained to the user?

---

# 3. Processing Architecture

The core pipeline should be:

```text
SOURCE SYSTEMS
     |
     v
DISCOVERY / CATALOG
     |
     v
INGESTION WORKERS
     |
     +----> Raw Object Store (immutable)
     |
     v
VALIDATION + DECODING
     |
     v
NORMALIZATION
     |
     v
SPATIAL/TEMPORAL PROCESSING
     |
     v
QUALITY CONTROL
     |
     v
CANONICAL STORAGE
     |
     +-----------> DERIVED PRODUCTS
     |                    |
     |                    v
     |              Risk / Suitability /
     |              Geofence / Routing /
     |              Anomalies / etc.
     |
     v
API + TILES + EVENTS
     |
     +--------------------+
     |                    |
     v                    v
React Dashboard       Future Agent Tools
```

The architecture must support continuous/near-real-time processing. Do not build a system where ingestion only happens manually or through blocking API requests.

---

# 4. Real-Time and Background Processing Requirements

This is a critical requirement.

Heavy ingestion and processing must happen in **background workers**, never inside synchronous API requests.

Examples of jobs:

- Polling IMD CAP/warning feeds.
- Polling INCOIS high-wave/cyclone/tide/forecast updates.
- Polling MOSDAC catalogs/open-data sources.
- Downloading satellite products.
- Fetching GRIB2/NetCDF/HDF datasets.
- Decoding scientific formats.
- Regridding.
- Bounding-box subsetting.
- Unit conversion.
- QC and anomaly detection.
- Converting raster products to COG.
- Creating Zarr/Parquet datasets.
- Updating PostGIS/TimescaleDB.
- Generating derived indicators.
- Updating STAC metadata.
- Refreshing tiles/cache.
- Expiring old alerts/forecasts.
- Detecting stale upstream sources.

### Worker principles

1. Jobs must be asynchronous.
2. Jobs must be retryable.
3. Jobs must be idempotent where possible.
4. Jobs must have explicit status: queued/running/succeeded/failed/retrying/cancelled.
5. Failed jobs go to a dead-letter/error path after configured retries.
6. Workers must have backoff and jitter.
7. Workers must be independently scalable.
8. A failure of one source must not stop the entire engine.
9. Heavy scientific processing must run separately from API processes.
10. Critical alerts must receive priority over low-priority archival jobs.
11. Every processing job should have a traceable job ID.
12. Job execution metadata must be visible in the dashboard.

### Suggested execution model

Use:

- **Airflow** for scheduled/source DAG orchestration initially.
- **NATS JetStream** for event-driven work queues and live events initially.
- Python workers for ingestion and processing.

If scale/complexity later requires it, the system can evolve toward distributed workflow execution, Kubernetes, or Kafka without changing the API contract.

---

# 5. Recommended Technology Stack

## Core language

- Python 3.12+

## API

- FastAPI
- Pydantic v2
- OpenAPI 3.1

## Database

- PostgreSQL
- PostGIS
- TimescaleDB

Use PostgreSQL/PostGIS/TimescaleDB as the primary queryable relational/time-series system.

## Object storage

- S3 in production
- MinIO for local/self-hosted development

Use object storage for raw scientific files, large processed datasets, and generated artifacts.

## Scientific processing

- xarray
- NumPy
- SciPy
- pandas
- GeoPandas
- Shapely
- PyProj
- Rasterio
- GDAL
- Satpy
- pyresample
- cfgrib
- ecCodes

## Storage formats

- NetCDF/HDF/GRIB2: source/raw scientific formats
- Zarr: chunked multidimensional processed data
- Parquet: observation/tabular datasets
- COG GeoTIFF: raster/map-serving products
- GeoJSON: vector features and warnings
- CoverageJSON/NetCDF subsets where appropriate for API consumers

## Orchestration / jobs

- Airflow
- NATS JetStream
- Python workers

## Cache

- Redis

## Tiles

- TiTiler for COG/raster serving
- PostGIS vector tile serving as needed

## Catalog

- STAC / STAC-compatible catalog

## Monitoring

- Prometheus
- Grafana
- structured logs / OpenTelemetry

## Frontend dashboard

- React
- TypeScript
- Vite
- a lightweight map library such as MapLibre GL JS or Leaflet
- simple charting library such as Recharts or ECharts

The dashboard should be a **lightweight operational/observability dashboard**, not a complex application.

## Containers

- Docker
- Docker Compose initially
- k3s/Kubernetes later only when scale warrants it

---

# 6. Do Not Over-Engineer Initially

Do not introduce the following unless actual scale/requirements justify them:

- Spark
- Flink
- Kafka
- Kubernetes
- OpenSearch
- MongoDB
- vector databases
- GraphQL as a core dependency

Start with:

```text
FastAPI
Postgres + PostGIS + TimescaleDB
MinIO/S3
Redis
Airflow
NATS
Python workers
Zarr/Parquet/COG
React dashboard
```

The existing marine-data reconnaissance indicates that selective bbox/time ingestion and chunked scientific storage are preferable to indiscriminate full-disk ingestion because the raw data can quickly become multi-GB/TB scale. Keep this principle throughout the design.

---

# 7. Canonical Marine Data Model

The system must hide source-specific structures from consumers.

Core domain entities should include:

```text
Observation
Forecast
Alert
Advisory
Location
Region
MarineZone
FishingZone
Port
Station
Buoy
VesselContext
Route
RiskAssessment
Dataset
DatasetAsset
ProcessingJob
Evidence
```

Every environmental record should preserve relevant fields such as:

```text
source
provider
dataset_id
variable
value
unit
latitude
longitude
geometry
observed_at
issued_at
valid_from
valid_until
forecast_time
retrieved_at
processing_version
quality_status
quality_score
```

Do not conflate:

- observation time
- issue time
- forecast valid time
- ingestion time
- processing time

These must remain distinct.

---

# 8. Required Raw/Direct Parameters

The data engine should support the following families.

## Location

- latitude
- longitude
- timestamp
- bbox
- radius
- bearing

## Ocean

- sea surface temperature (SST)
- chlorophyll-a
- sea surface salinity
- surface current u/v
- current speed
- current direction
- significant wave height
- wave period
- wave direction
- swell height
- swell period
- swell direction
- wind-wave parameters where available
- sea level
- tide-gauge level
- subsurface temperature
- subsurface salinity
- subsurface currents
- ocean eddy features
- TCHP where available

## Weather / atmosphere

- wind speed
- wind direction
- wind u/v
- gust speed where available
- rainfall rate
- rainfall accumulation
- atmospheric/sea-level pressure
- humidity where available
- thunderstorm indicators where available
- lightning events/alerts

## Hazards / advisories

- cyclone center
- cyclone track
- forecast cone where available
- cyclone intensity
- central pressure
- maximum wind
- gust
- storm surge
- high-wave alert
- swell alert
- lightning alert
- thunderstorm warning
- heavy-rain warning
- tsunami warning
- marine/coastal warnings
- CAP warning properties

## Fisheries / ecosystem

- PFZ polygons
- PFZ validity
- fishery advisories
- species-specific advisory information where available
- HAB/algal bloom features
- jellyfish/ecological advisories where available
- coral/ecosystem advisories where available

## In-situ observations

- buoy observations
- drifting buoy observations
- moored buoy observations where permitted
- coastal station observations
- ship observations where available
- tide gauges
- wave rider observations

## Geospatial reference layers

- EEZ
- international maritime boundaries
- restricted zones
- marine protected areas
- ecologically sensitive zones
- operational/geofencing boundaries
- ports/harbours
- shipping lanes where legally/technically available
- bathymetry/depth

Important: MOSDAC/INCOIS/IMD are not assumed to cover every authoritative boundary, bathymetry, or fisheries-productivity dataset. Identify and add appropriate authoritative external sources where required.

---

# 9. Derived Parameters and Intelligence Products

The data layer must compute reusable deterministic products.

## Spatial

- nearest PFZ
- distance to PFZ
- nearest buoy/station
- distance to hazard
- distance to boundary
- point-in-restricted-zone
- route/zone intersection
- hazard coverage around a location

## Temporal

- forecast horizon
- time-to-high-tide
- time-to-low-tide
- changing conditions
- rate of change
- safe operating windows
- alert expiration
- forecast freshness

## Environmental anomalies

- SST anomaly
- chlorophyll anomaly
- current anomaly
- wave anomaly
- rainfall anomaly
- pressure anomaly
- climatological percentile
- change over previous day/week/month

## Marine state indicators

- current speed/direction
- combined sea state
- wave risk
- swell risk
- wind risk
- storm proximity
- hazard proximity

## Fisheries

- fishing suitability score
- fishing zone ranking
- productivity indicator
- PFZ distance/ranking
- favourable SST + chlorophyll regions

## Safety

- marine risk score
- hazard score
- safe operating window
- geofence status
- restricted-zone warning
- boundary proximity warning

## Routing

- route distance
- expected travel time
- segment risk
- weather penalty
- wave penalty
- current penalty
- hazard penalty
- geofence/restriction penalty
- route risk score
- safest candidate route

Derived products must be deterministic/configurable and must expose the factors that contributed to their result. Do not bury unexplained business logic inside the LLM layer.

---

# 10. Risk Engine

Implement a configurable marine-risk engine.

Inputs may include:

```text
wave height
wave period
swell
wind
wind gust
rainfall
pressure trend
lightning
cyclone
storm surge
tsunami
active warnings
current
vessel type
vessel constraints
```

Output should include:

```json
{
  "risk_score": 0,
  "risk_level": "LOW|MODERATE|HIGH|EXTREME",
  "factors": [],
  "warnings": [],
  "valid_from": "...",
  "valid_until": "...",
  "sources": []
}
```

Thresholds must be configurable by vessel/operational context. Do not assume one universal threshold applies to every type of vessel.

---

# 11. Fishing Suitability Engine

Create a configurable suitability engine.

Conceptually:

```text
suitability = f(
  SST,
  chlorophyll,
  SST anomaly,
  chlorophyll anomaly,
  currents,
  waves,
  wind,
  PFZ,
  ecological hazards,
  fishery advisories
)
```

Output must include:

- score
- classification
- spatial geometry/grid
- positive drivers
- negative drivers
- source evidence
- confidence/quality

Do not claim causality from correlation unless supported by domain methodology.

---

# 12. Safe Operating Window

Given:

```text
location
start_time
end_time/duration
vessel_type
```

compute windows such as:

```text
06:00–09:00   favourable
09:00–12:00   moderate
12:00–18:00   high risk
```

The calculation must inspect forecast conditions and active warnings throughout the requested interval, not merely evaluate the first timestamp.

---

# 13. Geofencing Service

Implement geospatial services for:

```text
check whether point is inside restricted zone
check whether point is inside MPA
check distance to EEZ/boundary
check route intersection with restricted area
check proximity to sensitive/ecological zones
```

Expose APIs such as:

```text
GET /v1/geofence/check
GET /v1/geofence/nearby
GET /v1/geofence/intersections
```

All boundary layers must retain:

```text
zone_id
name
zone_type
geometry
authority
source
status
effective_from
effective_until
restriction
```

---

# 14. Safe Routing Service

Build a deterministic route service.

Input:

```text
start
end
departure_time
vessel_type
vessel_speed
optional vessel constraints
```

Environmental/routing cost can incorporate:

```text
wave risk
wind risk
current penalty
weather risk
active hazards
restricted zones
geofencing constraints
```

Output:

```text
route geometry
distance
estimated duration
segment-level risk
avoided zones
major risk drivers
source evidence
```

Start with a practical geospatial cost/graph approach. Do not require an AI model for route optimization.

---

# 15. Provenance and Evidence

This is mandatory.

Every important API result must be traceable to its supporting data.

Minimum provenance:

```text
provider
source dataset
source URL/reference
issued_at
valid_from
valid_until
retrieved_at
processing_version
input datasets
```

Add:

```text
quality_status
quality_score
freshness
confidence
```

Example:

```json
{
  "source": "INCOIS",
  "dataset": "OSF",
  "issued_at": "...",
  "valid_from": "...",
  "valid_until": "...",
  "retrieved_at": "..."
}
```

Future agents must be able to explain recommendations using this evidence package.

---

# 16. Data Freshness / Health

Build first-class monitoring for source freshness.

For each dataset track:

```text
expected update interval
last successful fetch
last processed time
current latency
current status
consecutive failures
stale threshold
```

Expose:

```text
GET /v1/data-health
GET /v1/datasets
GET /v1/datasets/{id}/status
```

Example status:

```text
HEALTHY
STALE
DEGRADED
FAILED
DISABLED
```

The API should not silently return stale safety-critical data without indicating its age/status.

---

# 17. Dataset Registry

Create a dataset registry containing:

```text
dataset_id
provider
product
parameters
coverage
spatial_resolution
temporal_resolution
format
update_frequency
access_method
authentication
retention_policy
license/policy
priority
status
last_success
last_failure
```

This registry becomes the foundation for:

- ingestion scheduling
- monitoring
- STAC cataloging
- dashboard visibility
- future data-discovery agents

---

# 18. API Contract

The API should be semantic/capability-oriented rather than exposing upstream source mechanics.

Recommended initial endpoints:

```text
GET  /v1/health
GET  /v1/data-health
GET  /v1/datasets

GET  /v1/ocean/conditions
GET  /v1/ocean/forecast
GET  /v1/weather/conditions
GET  /v1/weather/forecast

GET  /v1/fishing/pfz
GET  /v1/fishing/advisories
GET  /v1/fishing/suitability

GET  /v1/tides
GET  /v1/alerts

GET  /v1/geofence/check
GET  /v1/geofence/nearby
GET  /v1/geofence/intersections

GET  /v1/risk/marine
POST /v1/routes/safe

GET  /v1/evidence/{request_id}
GET  /v1/tiles/{z}/{x}/{y}

WS   /v1/stream/alerts
```

A common response envelope is recommended:

```json
{
  "data": {},
  "meta": {
    "generated_at": "...",
    "valid_from": "...",
    "valid_until": "...",
    "freshness": "...",
    "confidence": 0.0
  },
  "sources": [],
  "quality": {},
  "warnings": []
}
```

Heavy collection APIs must support pagination/cursors where appropriate.

The API should support JSON/GeoJSON and selected scientific/coverage formats where useful.

---

# 19. Event/Alert Layer

Create an event-driven alert stream.

Examples:

```text
alert.created
alert.updated
alert.expired

cyclone.detected
cyclone.updated
high_wave.detected
lightning.detected
tsunami.detected

pfz.updated
forecast.updated
observation.updated
```

Critical event processing should be isolated from batch/backfill workloads.

Use NATS JetStream initially.

Provide:

```text
WS /v1/stream/alerts
```

and appropriate server-to-server event topics.

---

# 20. Storage Strategy

## Raw

Immutable object storage:

```text
s3://marine-raw/{provider}/{dataset}/{date}/...
```

Retain original files when licensing/policy allows.

Store:

- original file
- checksum
- source metadata
- retrieval metadata
- job ID

## Processed

Use the best representation for the data type:

```text
Zarr    → multidimensional scientific grids
Parquet → tabular/observation data
COG     → raster/map products
PostGIS → vector/geospatial features
TimescaleDB → time series/query layer
```

Do not force every dataset into a single storage format.

---

# 21. Regridding and Spatial Normalization

Sources may use different projections/resolutions.

Normalize where appropriate to:

- WGS84 lat/lon for API semantics
- consistent time in UTC
- configurable common resolutions rather than blindly forcing all products to one grid

Do not resample unnecessarily. Preserve native-resolution assets where scientifically important and create standardized derived products for querying/visualization.

Use:

- Satpy
- pyresample
- xarray
- pyproj
- GDAL/Rasterio

Every regridding operation should record the processing method/version.

---

# 22. Quality Control

Processing pipeline:

```text
fetch
  -> checksum
  -> schema validation
  -> decode
  -> physical-range validation
  -> temporal validation
  -> duplicate detection
  -> spatial validation
  -> spike/outlier checks where appropriate
  -> quality flag
  -> publish
```

Keep raw data immutable even when a processed record fails QC.

Never silently discard suspicious observations; record their QC status/reason.

---

# 23. Dashboard Requirement

Build a **simple React + TypeScript dashboard** after the processing/data APIs are working.

This dashboard is not the end-user marine application and not the future conversational UI.

Its purpose is to provide a comprehensive visual view of:

1. What sources are connected.
2. What data has been ingested.
3. What data is currently being processed.
4. What datasets succeeded/failed/stalled.
5. When each dataset was last updated.
6. What processed products exist.
7. Current alerts and warning events.
8. Spatial coverage of processed data.
9. Sample marine layers and derived products on a map.
10. Processing worker/job status.
11. Data freshness/latency.
12. Storage/volume trends.
13. API health.

### Suggested dashboard pages/sections

#### Overview

Show cards/charts for:

```text
sources online
healthy datasets
stale datasets
failed datasets
jobs running
jobs failed
jobs completed today
active alerts
last successful ingestion
```

#### Sources

For MOSDAC/INCOIS/IMD and future providers:

```text
source status
last fetch
last success
failure count
latency
rate/quota state
```

#### Dataset Catalog

Show:

```text
dataset
provider
parameter
resolution
coverage
last updated
status
format
```

#### Processing Jobs

Show:

```text
job ID
source
dataset
job type
queued at
started at
finished at
duration
status
error/retry state
worker
```

#### Map Explorer

Lightweight map with layers such as:

```text
SST
chlorophyll
wave height
wind
currents
PFZ
alerts
cyclones
buoys
ports
geofences
bathymetry
```

Provide date/time controls and layer toggles.

#### Data Products

Visually show what has been created:

```text
Zarr products
COGs
Parquet datasets
GeoJSON layers
PFZ products
risk grids
suitability grids
```

#### Alerts

Show active/recent:

```text
cyclone
high wave
lightning
heavy rain
storm surge
tsunami
marine warnings
```

#### System Health

Show:

```text
API latency
worker health
queue depth
failed jobs
DB health
object-store health
cache health
```

### Dashboard principle

Keep the dashboard read-heavy and lightweight.

It should primarily consume the same APIs/events that external applications will consume. Do not create a second hidden data-access implementation just for the dashboard.

---

# 24. Dashboard Real-Time Behavior

The dashboard should reflect near-real-time changes without excessive polling.

Use:

- REST for initial state and historical views.
- WebSocket/SSE for live processing/status/alert events.
- Reasonable polling only as a fallback.

Examples:

```text
new CAP warning arrives
        -> worker
        -> normalized alert
        -> DB
        -> NATS event
        -> dashboard updates
```

Likewise:

```text
PFZ processing completed
        -> derived product published
        -> dashboard dataset count/status changes
```

---

# 25. API / Agent Tool Readiness

Design every API with future agent consumption in mind.

For each capability define:

```text
name
purpose
inputs
validation
output schema
units
time semantics
spatial semantics
freshness guarantee
failure modes
provenance
```

Later, these can become tools such as:

```text
get_ocean_conditions(lat, lon, time)
get_marine_forecast(lat, lon, time)
find_nearest_pfz(lat, lon, time, radius)
get_active_alerts(lat, lon, radius)
get_tide_forecast(location, time)
check_geofence(lat, lon)
assess_marine_risk(location, time, vessel_type)
get_fishing_suitability(location/time/region)
find_safe_route(start, destination, departure_time, vessel_type)
```

The agent layer should call these capabilities and never need to understand source-specific MOSDAC/INCOIS/IMD quirks.

---

# 26. Source Adapter Principle

Create source-specific adapters/connectors such as:

```text
ingest/mosdac/
ingest/incois/
ingest/imd/
```

Each adapter is responsible for:

- discovery
- authentication
- fetching
- source-specific parsing
- source-specific rate limits
- source metadata
- retries
- policy restrictions

After ingestion, source-specific details must be converted into the canonical internal model.

Do not leak upstream API schemas into the public marine API unless necessary.

---

# 27. Research / Source-Mapping Work

A future `prompt.md`/research task should identify, for **every required parameter and derived capability**:

1. Exact authoritative provider.
2. Exact website/product/API/endpoint.
3. Authentication requirements.
4. Registration requirements.
5. Rate limit/quota.
6. Redistribution/license constraints.
7. Exact response/file format.
8. Example request.
9. Example response/file.
10. Update frequency.
11. Historical availability.
12. Spatial coverage.
13. Temporal resolution.
14. Spatial resolution.
15. Variables contained.
16. Extraction method.
17. Parser/library required.
18. Unit conversions.
19. Coordinate/projection handling.
20. Time semantics.
21. Quality metadata.
22. Whether the source is direct data or only a visualization/quicklook.
23. Fallback source.
24. Data-staleness behavior.

Do not infer an API merely because a web page visually displays a value. Confirm the actual underlying endpoint/file/service.

Where an endpoint is authenticated/blocked/uncertain, mark the uncertainty explicitly and document what must be verified with browser HAR/network inspection, registration, or provider contact.

---

# 28. Gaps That Must Be Explicitly Researched

The current MOSDAC/INCOIS/IMD reconnaissance does not by itself guarantee complete coverage of:

- authoritative bathymetry
- complete international maritime boundary geometry
- all restricted maritime zones
- all marine protected areas
- ecological/sensitive-zone polygons
- shipping lanes/navigation chart data
- actual fish catch/effort/productivity observations

These must be identified and sourced separately if required for final problem-statement coverage.

Do not fabricate or approximate authoritative boundary/navigation datasets merely to make the demo appear complete.

---

# 29. Security and Reliability

Implement:

- secrets via environment/secret manager
- no credentials committed to source control
- API authentication for internal/admin endpoints
- API keys/JWT where required
- source credential isolation
- rate limiting
- downstream quota protection
- input validation
- request IDs
- structured logging
- audit logs for critical processing/actions

Protect upstream sources from accidental request storms.

Use circuit breakers where appropriate.

---

# 30. Testing Strategy

Tests should exist at several levels.

## Unit tests

- parsers
- unit conversion
- coordinate transformations
- geospatial functions
- QC functions
- anomaly calculations
- risk calculations

## Contract tests

- every public API schema
- OpenAPI validation
- GeoJSON validity
- expected units

## Integration tests

- source adapter -> raw storage
- raw -> processing
- processing -> DB/object store
- derived -> API
- event -> dashboard/API

## End-to-end tests

At least these scenarios:

### PFZ

```text
source PFZ
 -> ingest
 -> normalize
 -> PostGIS
 -> nearest PFZ API
```

### Safety

```text
forecast + warnings + waves + wind
 -> risk engine
 -> marine risk API
```

### Alerts

```text
CAP/HWA input
 -> normalize
 -> store
 -> event
 -> WebSocket/SSE
```

### Routing

```text
start/end
 -> environmental layers
 -> hazard/geofence constraints
 -> safe route
```

---

# 31. Observability

Every pipeline stage must be observable.

Track:

```text
source fetch latency
source success/failure
records fetched
records accepted/rejected
bytes downloaded
processing time
queue depth
worker utilization
DB latency
API latency
cache hit/miss
stale datasets
active alerts
```

Use Prometheus metrics and Grafana dashboards.

Logs must include:

```text
request_id
job_id
source
dataset
processing_step
error code
```

---

# 32. Initial Build Sequence

Do not attempt to ingest the entire world on day one.

Recommended order:

### Phase 0 — Repository and contracts

- establish repository structure
- Docker Compose
- Postgres/PostGIS/Timescale
- MinIO
- Redis
- NATS
- Airflow
- FastAPI
- React dashboard skeleton
- OpenAPI base schemas
- dataset registry
- job model

### Phase 1 — One complete vertical slice

Implement:

```text
INCOIS PFZ
IMD CAP alerts
INCOIS/IMD basic marine conditions
basic geofencing
```

Prove:

```text
ingestion
 -> processing
 -> canonical data
 -> PostGIS
 -> API
 -> event
 -> dashboard
```

### Phase 2 — Heavy scientific data

Add:

```text
SST
chlorophyll
wave
wind
currents
GRIB2/NetCDF/HDF
Zarr/COG
```

### Phase 3 — Derived intelligence

Add:

```text
anomalies
fishing suitability
marine risk
safe operating window
hazard proximity
```

### Phase 4 — Routing + advanced geospatial

Add:

```text
bathymetry
navigation layers
full geofencing
route optimization
```

### Phase 5 — Scale and hardening

Add:

```text
retention policies
archival tiers
automatic recovery
higher worker concurrency
horizontal scaling
Kubernetes/k3s if actually needed
```

---

# 33. Definition of Done

The first meaningful version of the data layer is complete when a developer can call APIs such as:

```text
GET /v1/ocean/conditions?lat=...&lon=...&time=...
GET /v1/ocean/forecast?lat=...&lon=...&time=...
GET /v1/fishing/pfz?lat=...&lon=...&date=...
GET /v1/alerts?lat=...&lon=...&radius_km=...
GET /v1/tides?lat=...&lon=...&time=...
GET /v1/geofence/check?lat=...&lon=...
GET /v1/risk/marine?lat=...&lon=...&time=...&vessel_type=...
POST /v1/routes/safe
```

and receive:

1. correctly normalized data;
2. correct spatial/temporal semantics;
3. freshness information;
4. data quality information;
5. source provenance;
6. deterministic derived indicators where requested;
7. machine-readable geometry;
8. useful errors when sources are unavailable;
9. no dependence on an LLM.

The React dashboard must show what was ingested, processed, derived, failed, or become stale, and must update near-real-time operational state through the event layer.

---

# 34. Guiding Principle

The most important architectural rule is:

> **Build the Marine Data Engine as a reliable source-agnostic information substrate first. Build AI agents later as consumers of the substrate.**

Raw environmental data is not the final product.

The progression is:

```text
RAW DATA
   ↓
NORMALIZED DATA
   ↓
QUALITY-CHECKED DATA
   ↓
SPATIO-TEMPORAL DATA
   ↓
DERIVED MARINE INDICATORS
   ↓
DECISION-SUPPORT PRODUCTS
   ↓
STABLE APIs / EVENTS / TILES
   ↓
FUTURE AGENT TOOLS
```

The platform should make complex future user questions possible because the underlying marine capabilities already exist as deterministic, explainable, queryable services.
