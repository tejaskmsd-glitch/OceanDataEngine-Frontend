# Marine Intelligence Data Layer — Requirements & Parameter Design

## 1. Purpose

This document defines the data-layer scope for the Agentic AI Marine Intelligence Platform described in the problem statement.

The immediate goal is **not** to build the conversational/agentic application. The immediate goal is to build a clean, reliable, source-agnostic **Marine Data Layer** that:

1. ingests data from MOSDAC, INCOIS, IMD, and later additional authoritative sources;
2. normalizes heterogeneous marine, meteorological, satellite, advisory, and geospatial data;
3. stores raw and processed data;
4. computes reusable derived marine-intelligence products;
5. exposes deterministic APIs that applications and future AI agents can consume;
6. preserves freshness, quality, provenance, and evidence for every important result.

The future agent layer should treat this service as a black box of reliable marine capabilities. It should not need to know whether a value came from NetCDF, HDF, GRIB2, RSS, a JSP page, a GIS service, or an upstream API.

---

## 2. Architectural Principle

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
              | Conditions              |
              | Forecasts               |
              | PFZ                     |
              | Alerts                  |
              | Tides                   |
              | Geofencing              |
              | Risk                    |
              | Fishing Suitability     |
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
 Satellite products     Ocean/PFZ          Weather/NWP
 SST / CHL / Current    Buoys / Tide       Marine Obs
 etc.                   OSF / Alerts       CAP / Warnings
```

### Hard boundary

The data layer must be **AI-agnostic**.

The data layer answers:

> What is happening, what was observed, what is forecast, what warnings are active, what zones exist, and what deterministic derived indicators can be calculated for a location/time/context?

The agent layer answers:

> Which capabilities should I invoke, in what order, and how should I explain the result to the user?

---

## 3. Four Levels of Data

### Level 1 — Raw / directly fetched

Examples:

- SST
- chlorophyll-a
- wind speed/direction
- wave height/period/direction
- swell
- surface currents
- rainfall
- pressure
- tide-gauge observations
- PFZ polygons
- marine warnings
- cyclone bulletins
- lightning alerts
- buoy observations
- satellite imagery/products
- marine advisories

### Level 2 — Normalized

Convert source-specific information into common representations:

- common variable names
- common units
- UTC timestamps
- WGS84 geographic coordinates
- common geometry formats
- consistent forecast/observation semantics
- quality flags
- source/provenance metadata

### Level 3 — Derived geospatial/temporal indicators

Examples:

- nearest PFZ
- distance to PFZ
- distance to hazard
- distance to boundary
- SST anomaly
- chlorophyll anomaly
- current speed/direction
- storm proximity
- safe operating window
- hazard intersection
- route-segment risk

### Level 4 — Decision indicators

Examples:

- marine risk score
- fishing suitability score
- route risk score
- safe-route recommendation
- zone avoidance recommendation
- contextual evidence package

Levels 3 and 4 are **products computed by our data layer**, not raw observations.

---

# 4. Required Parameter Inventory

## 4.1 Location and Spatial Context

| Parameter | Why it is needed | How obtained/computed |
|---|---|---|
| latitude | Core spatial reference for all location-based queries | User/device/API |
| longitude | Core spatial reference for all location-based queries | User/device/API |
| timestamp | Determines observation/forecast context | User/system |
| bounding box | Regional/map queries | Derived from query geometry |
| radius_km | Nearby searches | Input/default |
| bearing | Navigation/route calculations | Computed geodesically |
| distance_to_feature | Nearest PFZ/hazard/boundary | PostGIS geospatial calculation |
| inside_feature | Geofence/restriction checks | PostGIS spatial predicate |
| intersection_geometry | Route/hazard/zone overlap | PostGIS intersection |

Spatial operations should be first-class capabilities, not left to the future agent.

---

# 5. Oceanographic Parameters

## 5.1 Sea Surface Temperature (SST)

### Raw

```text
sea_surface_temperature
unit: degC
```

### Why needed

SST is a primary ocean/environmental variable for:

- PFZ analysis
- fishing suitability
- fish-habitat reasoning
- productivity analysis
- ocean-condition summaries
- correlation with chlorophyll
- identifying anomalous marine conditions

### How obtained

Satellite/ocean products from MOSDAC and INCOIS are relevant sources. The source reconnaissance identifies MOSDAC ocean/open-data products and INCOIS remote-sensing/SST holdings.

### Derived

```text
sst_anomaly
sst_gradient
sst_change
sst_percentile
```

Basic anomaly concept:

```text
SST anomaly = current SST - climatological/seasonal baseline SST
```

The baseline must come from a retained historical dataset.

---

## 5.2 Chlorophyll-a

### Raw

```text
chlorophyll_a
unit: mg/m3
```

### Why needed

Core biological-productivity indicator for:

- PFZ reasoning
- productive-region detection
- fishing suitability
- productivity-change analysis
- ecosystem analysis

INCOIS PFZ services are explicitly based on SST + chlorophyll fusion.

### Derived

```text
chlorophyll_anomaly
chlorophyll_percentile
chlorophyll_gradient
productivity_indicator
```

Basic anomaly:

```text
chlorophyll anomaly = current chlorophyll - seasonal baseline
```

---

## 5.3 Surface Current

### Raw

Prefer vector form:

```text
current_u
current_v
```

And expose derived forms:

```text
current_speed
current_direction
```

### Why needed

- vessel route optimization
- travel-time estimation
- fuel/operational efficiency
- fishing conditions
- oceanographic interpretation

### Compute

```text
speed = sqrt(u^2 + v^2)
```

Direction is calculated from the vector components using the appropriate oceanographic/geospatial convention.

Keep `u` and `v` internally even if the public API exposes speed and direction.

---

## 5.4 Waves

### Minimum

```text
significant_wave_height
wave_period
wave_direction
```

### Better

```text
swell_height
swell_period
swell_direction
wind_wave_height
wind_wave_period
```

### Why needed

Essential for:

- sea-safety decisions
- vessel suitability
- fishing operations
- route planning
- high-wave alerts
- safe operating windows

INCOIS OSF exposes wave/swell forecast information; INCOIS also provides high-wave/swell warning services.

### Derived

```text
sea_state
wave_risk
swell_risk
wave_change_rate
```

Risk thresholds must be configurable by vessel type/operational context rather than hard-coded globally.

---

## 5.5 Sea Surface Salinity

### Raw

```text
sea_surface_salinity
```

### Why needed

Primarily useful for:

- scientific/oceanographic reasoning
- ecosystem analysis
- coastal freshwater influence
- advanced fisheries analysis

### Priority

Phase 2 unless required for a specific pilot.

MOSDAC reconnaissance identified high-resolution sea-surface-salinity ocean data.

---

## 5.6 Subsurface Ocean Parameters

Potential variables:

```text
temperature(depth)
salinity(depth)
current(depth)
```

### Why

Useful for:

- advanced fish-habitat analysis
- oceanographic research
- productivity studies
- understanding vertical structure

### Priority

Phase 2/Research.

INCOIS reconnaissance identified ocean subsurface holdings and observations.

---

## 5.7 Ocean Eddies

Potential entity fields:

```text
eddy_id
center_lat
center_lon
radius
polarity
amplitude
geometry
valid_time
```

### Why

Useful for:

- fisheries research
- productivity analysis
- current structure
- explaining localized biological productivity

MOSDAC reconnaissance identified oceanic eddy detection products.

---

## 5.8 Tropical Cyclone Heat Potential (TCHP)

```text
tchp
```

### Why

Primarily useful for:

- cyclone intensity/environmental analysis
- ocean-atmosphere interaction
- research models

### Priority

Advanced / Phase 2.

INCOIS reconnaissance identified TCHP services.

---

# 6. Meteorological Parameters

## 6.1 Wind

### Raw

```text
wind_speed
wind_direction
wind_u
wind_v
```

Potentially:

```text
gust_speed
```

### Why

- vessel safety
- route optimization
- wave generation/context
- fishing operations
- storm analysis

IMD marine observations and NWP products provide wind information.

### Derived

```text
wind_change
wind_gust_risk
headwind_component
crosswind_component
```

The components relative to route direction become useful for route optimization.

---

## 6.2 Atmospheric Pressure

```text
sea_level_pressure
station_pressure
```

### Why

- storm identification
- cyclone analysis
- rapidly changing weather
- contextual marine-risk explanation

### Derived

```text
pressure_anomaly
pressure_gradient
pressure_change_rate
```

---

## 6.3 Rainfall

### Raw

```text
rainfall_rate
rainfall_accumulation
forecast_rainfall
```

### Why

- fishing safety
- operational planning
- heavy-rain hazards
- route risk
- storm context

IMD and MOSDAC reconnaissance identify rainfall products; IMD NWP includes marine rainfall guidance.

### Derived

```text
rainfall_1h
rainfall_3h
rainfall_24h
heavy_rain_flag
```

---

# 7. Tide and Coastal Water Level

## 7.1 Tide Gauge Observations

Potential fields:

```text
station_id
latitude
longitude
water_level
observation_time
```

### Why needed

- fishing/port operations
- harbour entry/exit
- shallow-water safety
- coastal planning
- contextual marine conditions

INCOIS reconnaissance identified its Tide Gauge real-time network.

### Derived

```text
tide_state
rising_or_falling
time_to_high_tide
time_to_low_tide
tide_height
```

Important distinction: a tide-gauge observation is not automatically a future tide prediction. Future predictions require a suitable tidal-prediction dataset/model.

---

## 7.2 Sea Level / Storm Surge

Potential fields:

```text
sea_level
storm_surge_height
surge_anomaly
```

### Why

- cyclone impact
- coastal flooding
- disaster management
- harbour safety
- coastal-route avoidance

INCOIS reconnaissance identifies storm-surge services.

---

# 8. Alerts and Hazards

## 8.1 Generic Warning Entity

Every warning should normalize to a common structure:

```text
warning_id
event_type
severity
certainty
urgency
headline
description
geometry
area_description
issued_at
effective_from
expires_at
source
source_url
```

### Event types

```text
cyclone
high_wave
strong_wind
heavy_rain
thunderstorm
lightning
storm_surge
tsunami
marine_hazard
```

IMD CAP/RSS and warning systems are important sources for this layer.

---

## 8.2 Lightning

Fields:

```text
lightning_location
lightning_time
severity
alert_geometry
valid_from
valid_until
```

### Why

Directly supports:

> Are there any lightning alerts in my area?

### Derived

```text
distance_to_lightning
lightning_risk
lightning_alert_active
```

Spatial intersection with warning polygons is the primary mechanism for area-based alerts.

---

## 8.3 Cyclone

Treat cyclone as a structured entity rather than merely a generic alert.

Fields:

```text
cyclone_id
cyclone_name
center_lat
center_lon
issue_time
forecast_time
movement_direction
movement_speed
central_pressure
maximum_sustained_wind
gust
track_geometry
forecast_cone
intensity_category
```

### Derived

```text
distance_to_cyclone
distance_to_forecast_track
track_intersection
estimated_arrival_time
cyclone_proximity_risk
```

IMD/RSMC and INCOIS cyclone/storm-surge systems should be normalized into this model.

---

## 8.4 Tsunami

Potential fields:

```text
event_id
earthquake_time
earthquake_lat
earthquake_lon
magnitude
depth
tsunami_status
alert_level
affected_regions
```

Derived:

```text
distance_to_source
estimated_arrival_time
tsunami_risk
```

INCOIS TEWS is the relevant authoritative source identified in the reconnaissance.

This capability is safety-critical and must retain original advisory provenance.

---

# 9. Potential Fishing Zone (PFZ)

PFZ is one of the most important domain entities.

### Raw/entity fields

```text
pfz_id
geometry
issue_time
valid_from
valid_until
region
advisory_text
source
source_url
```

Potential additional attributes:

```text
species/advisory_type
sst_context
chlorophyll_context
confidence
```

INCOIS explicitly provides PFZ ecosystem services based on SST/chlorophyll fusion.

### Derived

```text
nearest_pfz
distance_to_pfz
pfz_area
pfz_age
pfz_valid
```

Core API example:

```http
GET /v1/fishing/pfz?lat=<lat>&lon=<lon>&radius_km=<r>
```

---

# 10. Fisheries / Ecosystem Advisories

INCOIS reconnaissance identifies ecosystem services such as:

```text
Tuna
Hilsa
HAB / Algal Bloom
Coral Reef
Jellyfish
```

Normalize advisories into:

```text
advisory_id
advisory_type
species_or_ecosystem
region
geometry
issued_at
valid_from
valid_until
recommendation
source
```

### Why

This allows future tools to distinguish between:

- a general PFZ;
- species-specific guidance;
- ecological hazards.

---

# 11. Buoy, Ship, Coastal Station, and Other In-Situ Observations

Generic observation entity:

```text
station_id
station_type
latitude
longitude
observation_time
parameter
value
unit
quality_flag
source
```

Potential parameters:

```text
temperature
pressure
humidity
wind
current
wave
rainfall
salinity
```

Sources identified include INCOIS drifting/moored buoys and IMD ship/coastal/buoy observations.

### Why

In-situ observations provide ground truth and help compare model/satellite estimates with actual conditions.

A future evidence response could say:

> Satellite/model guidance indicates X, while the nearest buoy observed Y.

That is materially better than relying on a single data modality.

---

# 12. Forecast Semantics

A forecast value is not just a value.

Every forecast record should preserve:

```text
model_name
model_cycle
issued_at
forecast_hour
valid_time
parameter
value
unit
location/grid
resolution
source
```

Example:

```text
model = GFS
cycle = 00Z
forecast_hour = +18h
valid_time = ...
```

This prevents the system from confusing:

- when a forecast was generated;
- what time it predicts;
- when it expires;
- whether it is newer than another model run.

IMD reconnaissance identifies multiple NWP systems/cycles and marine parameters.

---

# 13. Data Freshness

Every important observation, forecast, warning, and advisory must preserve:

```text
observed_at
issued_at
valid_from
valid_until
retrieved_at
processed_at
```

Derived:

```text
age_minutes
is_stale
freshness_score
```

Example:

```text
freshness_score = f(current_time - source_timestamp,
                    expected_update_interval)
```

The exact scoring formula should be configurable per dataset.

The existing reconnaissance already identifies stale-data detection as an important reliability mechanism.

---

# 14. Data Quality

Each observation/forecast/product should support:

```text
quality_status
quality_score
missing_flag
outlier_flag
interpolated_flag
source_status
processing_version
```

Recommended processing pipeline:

```text
raw
  |
schema validation
  |
physical range validation
  |
temporal consistency
  |
spatial consistency
  |
duplicate detection
  |
quality scoring
  |
accepted/rejected/quarantined
```

---

# 15. Derived Marine Intelligence

These are the main products that should be computed by the data layer.

## 15.1 SST Anomaly

```text
current_sst - historical/seasonal baseline
```

Useful for identifying abnormal ocean conditions.

---

## 15.2 Chlorophyll Anomaly

```text
current_chlorophyll - historical/seasonal baseline
```

Useful for identifying unusually productive or unproductive periods.

---

## 15.3 Current Speed and Direction

Derived from vector components.

---

## 15.4 Combined Sea State

Combine wave/swell characteristics into a standardized representation.

Do not initially claim a universal risk score from wave height alone; keep domain thresholds configurable.

---

## 15.5 Hazard Proximity

For each hazard:

```text
distance_to_hazard
hazard_type
severity
validity
```

Compute using PostGIS/geodesic calculations.

---

## 15.6 Marine Risk Score

Input factors can include:

```text
wave_height
wave_period
swell
wind
wind_gust
rainfall
lightning
cyclone
storm_surge
tsunami
active_marine_warnings
vessel_type
```

Output:

```text
risk_score
risk_level
risk_factors
```

Suggested conceptual levels:

```text
LOW
MODERATE
HIGH
EXTREME
```

The actual thresholds must be configurable by vessel/operational context and validated by domain experts.

---

## 15.7 Fishing Suitability Score

Candidate inputs:

```text
SST
chlorophyll
SST anomaly
chlorophyll anomaly
current
wave
wind
PFZ
fishery advisories
ecological hazards
```

Conceptually:

```text
fishing_suitability = f(environmental_conditions,
                        fishing_advisories,
                        hazards,
                        context)
```

Output:

```text
score
classification
drivers
constraints
validity
```

Important: weights should not be invented casually. Make them configurable and calibrate them using fisheries/domain knowledge.

---

## 15.8 Safe Operating Window

Input:

```text
location
start_time
end_time/duration
vessel_type
```

Output:

```text
safe_windows[]
condition_summary[]
risk_changes[]
```

Conceptual example:

```text
06:00-09:00 -> favourable
09:00-12:00 -> moderate
12:00-18:00 -> high risk
```

This supports the query:

> Is it safe to venture into the sea tomorrow morning?

---

# 16. Geofencing and Maritime Zones

The problem statement requires support for:

- international maritime boundaries;
- restricted waters;
- marine protected areas;
- ecologically sensitive zones;
- predefined operational boundaries.

These need a normalized zone model:

```text
zone_id
zone_type
name
geometry
status
restriction
authority
effective_from
effective_until
source
source_url
```

Core spatial operations:

```text
check point inside zone
find nearby zones
find route/zone intersection
distance to zone boundary
```

Example APIs:

```http
GET /v1/geofence/check?lat=<lat>&lon=<lon>
GET /v1/geofence/nearby?lat=<lat>&lon=<lon>&radius_km=<r>
```

### Important source gap

MOSDAC + INCOIS + IMD are not sufficient, based on the present reconnaissance, to guarantee a complete authoritative database of every required maritime boundary/restricted/MPA/operational polygon.

Therefore the data layer **can and should support these capabilities**, but it must later ingest additional authoritative GIS datasets where required.

Do not silently fabricate or infer legal boundaries from environmental datasets.

---

# 17. Safe Vessel Routing

A route engine should eventually accept:

```text
start_lat
start_lon
destination_lat
destination_lon
departure_time
vessel_type
vessel_speed
draft/operational constraints where available
```

Environmental route cost inputs:

```text
wave_height
wave_period
wind
current
rainfall
hazards
restricted_zones
```

For each candidate route segment, derive:

```text
segment_distance
estimated_travel_time
wave_risk
wind_risk
current_penalty
hazard_penalty
geofence_penalty
overall_segment_cost
```

Conceptually:

```text
route_cost =
    distance_cost
  + weather_penalty
  + wave_penalty
  + current_penalty
  + hazard_penalty
  + restriction_penalty
```

This should start as a deterministic geospatial optimization service. AI can later choose when to invoke it and explain its result.

---

# 18. Fisheries Productivity Decline

The problem statement includes questions such as:

> Why has fish productivity declined in a particular coastal region?

This is an important capability but requires a dataset beyond MOSDAC/INCOIS/IMD if the system is expected to measure actual fishing productivity.

### Required fishery-side observations

Ideally:

```text
catch_volume
catch_per_unit_effort
species_abundance
landing_data
fishing_effort
```

### Environmental explanatory features

Can include:

```text
SST anomaly
chlorophyll anomaly
current anomaly
eddy activity
salinity
rainfall
wave regime
HAB
```

### Analysis

```text
historical fisheries outcome
            +
historical environmental conditions
            ->
correlation / attribution analysis
```

### Important source gap

The current reconnaissance does **not establish a complete authoritative fisheries catch/productivity dataset** among MOSDAC, INCOIS, and IMD.

Therefore the data layer should expose the structure for this capability, but actual fish productivity conclusions should not be claimed until appropriate fisheries observations are sourced.

---

# 19. Data Provenance and Evidence

Every meaningful API response should be able to explain where the result came from.

Recommended provenance object:

```json
{
  "source": "INCOIS",
  "dataset": "OSF",
  "issued_at": "...",
  "valid_from": "...",
  "valid_until": "...",
  "retrieved_at": "...",
  "source_url": "...",
  "processing_version": "..."
}
```

Response-level metadata should also include:

```text
confidence
quality
freshness
source_priority
warnings
```

This is what enables a later agent to produce evidence-based answers rather than unsupported statements.

---

# 20. Canonical API Response Envelope

A common response contract should be used across APIs.

Example:

```json
{
  "data": {},
  "meta": {
    "generated_at": "...",
    "valid_from": "...",
    "valid_until": "...",
    "freshness": {},
    "confidence": 0.93
  },
  "sources": [],
  "quality": {},
  "warnings": []
}
```

This is intentionally independent of any future AI framework.

---

# 21. Recommended Data-Layer Capability APIs

Do not expose a huge number of source-specific APIs to the future agent.

Group the normalized capabilities into a compact domain API.

```text
GET  /v1/location/resolve

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

GET  /v1/risk/marine

POST /v1/routes/safe

GET  /v1/datasets
GET  /v1/datasets/{dataset_id}/status
GET  /v1/data-health

GET  /v1/evidence/{request_id}

GET  /v1/tiles/{z}/{x}/{y}

WS   /v1/stream/alerts
```

These are capability APIs, not source mirrors.

---

# 22. Examples of Capability Responses

## Ocean conditions

```http
GET /v1/ocean/conditions?lat=15.2&lon=73.8&time=...
```

Potential output:

```text
SST
chlorophyll
wave
swell
current
salinity (when available)
sea-state summary
```

## Nearby PFZ

```http
GET /v1/fishing/pfz?lat=15.2&lon=73.8&radius_km=100
```

Potential output:

```text
PFZ geometry
distance
validity
advisory
source
```

## Marine risk

```http
GET /v1/risk/marine?lat=15.2&lon=73.8&time=...&vessel_type=small_fishing_boat
```

Potential output:

```text
risk score
risk level
individual contributing factors
evidence/provenance
validity
```

---

# 23. Minimum Viable Parameter Set

Do not build every possible parameter on day one.

The strongest MVP should support:

## Location

```text
latitude
longitude
timestamp
```

## Ocean

```text
SST
chlorophyll
wave height
wave period
swell
surface current
tide
```

## Weather

```text
wind speed
wind direction
rainfall
pressure
lightning
```

## Hazards

```text
cyclone
high wave
storm surge
tsunami
marine warnings
```

## Fishing

```text
PFZ
fishery advisories
```

## Geospatial

```text
EEZ
restricted zones
MPAs
operational boundaries
ports
```

## Metadata

```text
source
dataset
issued_at
valid_from
valid_until
retrieved_at
quality
confidence
```

---

# 24. Derived MVP Products

The initial data layer should compute:

```text
nearest_pfz
distance_to_pfz
sst_anomaly
chlorophyll_anomaly
current_speed
current_direction
combined_sea_state
storm_distance
hazard_distance
marine_risk_score
fishing_suitability_score
safe_operating_window
geofence_status
route_risk
```

---

# 25. Important Data Gaps

The current source reconnaissance is strong for environmental, satellite, ocean, weather, forecast, and warning information, but three important categories need special treatment.

## 25.1 Bathymetry / Navigation Data

Needed for:

- depth-aware route planning
- shallow-water detection
- coastal navigation context
- safer harbour/nearshore route decisions

The current MOSDAC/INCOIS/IMD reconnaissance does not establish complete authoritative navigation/bathymetry coverage for the whole intended use case.

### Data-layer decision

Support bathymetry as a first-class canonical dataset:

```text
bathymetry_depth
bathymetry_source
resolution
valid_area
```

Later map an authoritative external source into it.

Do not invent depth from other parameters.

---

## 25.2 Authoritative Maritime Restrictions / Boundaries

Needed for:

- international boundary awareness
- restricted waters
- MPA avoidance
- ecologically sensitive zones
- operational geofencing

### Data-layer decision

Build the geofence service now, but allow additional authoritative GIS sources to be plugged into the zone registry later.

---

## 25.3 Fisheries Catch / Productivity Data

Needed for robust answers about actual fish-productivity changes.

### Data-layer decision

Build the fisheries schema and analytics interface, but don't claim a productivity decline/attribution capability until actual fisheries observations are available.

Environmental factors can still be analyzed independently.

---

# 26. Source-to-Canonical Mapping Philosophy

Later, a separate source-mapping document/prompt should answer:

```text
What exact source provides this parameter?
What endpoint/product contains it?
How frequently does it update?
What authentication is required?
What format is it in?
What geographic coverage does it have?
What preprocessing is required?
How is it mapped into the canonical schema?
What fallback source exists?
What license/redistribution constraint applies?
```

For example:

```text
CANONICAL PARAMETER
       |
       +--> MOSDAC product
       +--> INCOIS product
       +--> IMD product
       +--> external authoritative source
       |
       v
NORMALIZATION RULE
       |
       v
CANONICAL STORAGE
       |
       v
PUBLIC DATA API
```

This document deliberately defines **what the platform needs**. The later source-mapping prompt should define **exactly where to obtain each required field and how to ingest it**.

---

# 27. Data-Layer Design Rules

1. **Never expose raw source semantics directly to agents.**
2. **Always preserve source provenance.**
3. **Always preserve forecast issuance and validity times.**
4. **Do not discard raw files; keep them immutable for reprocessing.**
5. **Normalize units and coordinate systems centrally.**
6. **Treat observations, forecasts, advisories, alerts, and derived products as different entity types.**
7. **Make spatial and temporal queries first-class.**
8. **Keep quality/freshness metadata attached to results.**
9. **Make risk thresholds configurable.**
10. **Do not use the LLM to perform deterministic geospatial calculations that the backend can perform reliably.**
11. **Do not infer legal/restricted zones from environmental data.**
12. **Do not claim actual fish-productivity changes without an appropriate fisheries dataset.**
13. **Design every capability so that it can later become an agent tool without rewriting the underlying data service.**

---

# 28. Relationship to Future Agent Tools

The future agent layer should be able to wrap these APIs as tools such as:

```text
get_ocean_conditions()
get_weather_forecast()
get_marine_alerts()
find_nearest_pfz()
get_tide_conditions()
check_geofence()
calculate_marine_risk()
calculate_fishing_suitability()
find_safe_route()
get_evidence()
```

The agent should never need to know:

```text
which NetCDF file
which upstream JSP
which satellite product code
which source authentication mechanism
which database table
```

Those remain inside the data platform.

---

# 29. Target End State

The target architecture is:

```text
SOURCE SYSTEMS
    |
    +-- MOSDAC
    +-- INCOIS
    +-- IMD
    +-- Future authoritative GIS/fisheries sources
    |
    v
INGESTION
    |
    v
RAW OBJECT STORE
    |
    v
PROCESSING / NORMALIZATION / QC
    |
    v
CANONICAL MARINE DATA MODEL
    |
    +-------------------------------+
    |                               |
    v                               v
FACTUAL DATA                   DERIVED PRODUCTS
    |                               |
    |                          PFZ / Risk /
    |                          Suitability /
    |                          Geofence /
    |                          Routing /
    |                               |
    +---------------+---------------+
                    |
                    v
              MARINE DATA API
                    |
             +------+------+
             |             |
          Applications   Future AI Tools
```

The core success criterion is:

> Given a location, time, and operational context, the data layer must be able to return the relevant marine facts, forecasts, hazards, geometries, derived indicators, freshness, quality, and provenance in a deterministic and machine-readable form.

Once that contract is stable, the agentic platform becomes a separate orchestration/explanation layer built on top of these capabilities.
