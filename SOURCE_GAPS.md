# Marine Data Engine — Source Status and Remaining Gaps

This document is the current operational source-of-truth for live marine data
connectors. It supersedes the earlier HAR-A/HAR-C/HAR-D discovery notes in
`source_mapping.md` and older README text.

## Rules

- Production workers instantiate live adapters only. Fixtures are explicit,
  synthetic, test-only inputs and are never selected as fallback observations.
- Empty upstream responses remain empty. They are recorded as `empty` (healthy
  poll, zero records), never populated with inferred values.
- Unknown endpoints, authentication headers, station IDs, geometry, units,
  timestamps, licenses, or boundaries are never guessed.
- Dataset outcomes distinguish `not_run`, `empty`, `auth_blocked`,
  `contract_unavailable`, `license_gated`, `source_unavailable`,
  `contract_error`, and `processing_error`.

## Verified production connectors

| Dataset | Verified machine contract | Geometry/values retained | Polling |
|---|---|---|---|
| `imd_cap` | `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` and linked CAP 1.2 XML | Source CAP areas and fields; no XML-signature trust claim | 1 minute |
| `incois_pfz` | `https://gemini.incois.gov.in/api/ws/pfz` and `/pfzLines` | Native `Point` destination features and `LineString` advisory features; never polygonized | 3 hours |
| `incois_hwa` | `https://sarat.incois.gov.in/incoismobileappdata/rest/incois/hwassalatestdata` plus `https://samudra.incois.gov.in/incoismobileappdata/rest/incois/districtpolygons` | Double-decoded HWA/SSA records joined by normalized state + district; Polygon/MultiPolygon only; validity parsed in `Asia/Kolkata` | 15 minutes |
| `incois_tide` | `https://tsunami.incois.gov.in/itews/homexmls/TideStations.xml` and `https://tsunami.incois.gov.in/itews/JSONS/{UPPERCASE_DISPLAY_NAME}_1.json` | Dynamically enumerated station metadata and explicit latest `RAD`/`PRS`/`ENC` values only; malformed historical chart x-values are ignored | 10 minutes |
| `incois_buoy` | `https://incois.gov.in/OON/fetchMooredBuoyData.jsp`, bounded `backend_process.jsp`, and OON OMNI/MORED chart pages | Dynamically enumerated active stations; verified `hm0` and `wind_speed` tokens only; exact selected label/unit, UTC declaration, and freshness required | 30 minutes |
| `incois_erddap` | `https://erddap.incois.gov.in/erddap/info/index.json` and `/info/{dataset}/index.json` | Catalog/per-dataset metadata only in the current handler | 6 hours |
| `mosdac_search` | `https://mosdac.gov.in/apios/datasets.json` | Discovery catalog only; authenticated product downloads excluded | 12 hours |
| `imd_marine_bulletin` | `https://mausam.imd.gov.in/Forecast/coastal_bulletin_new.php?id={centre}` and `seaarea_bulletin_new.php?id={centre}` | Numeric wind range + gust (knots -> m/s by 1852/3600); sea state retained as a **WMO 3700 category**, never as a height; port-signal and storm-surge rows emitted as warnings; area-scoped, never a point forecast | 30 minutes |

### IMD marine bulletins — numeric wind, categorical sea state

IMD's authenticated `api.imd.gov.in` / `mausam.imd.gov.in/api/*.php` endpoints
return HTTP 401 and remain unusable (see below). The operational **Coastal
Weather Bulletin** and **Sea Area Bulletin** pages published by the Area/Cyclone
Warning Centres are open and unauthenticated, and they carry explicit numeric
wind with an explicit UTC validity window. They are ingested with these limits:

- Wind is genuinely numeric. The sustained range's **upper** bound is stored as
  the value, with both bounds and the verbatim source text in metadata.
- Sea state is published only as a word (`MODERATE`, `MODERATE TO ROUGH`). It is
  stored as `sea_state_category` with `value=None`. The adapter never converts a
  category to a wave height.
- The safety gate may map a category to its published WMO Code 3700 / Douglas
  band and use the **upper** bound, so a coarse term can only make a verdict
  more pessimistic. Such a decision is tagged `SEA_STATE_DERIVED_FROM_CATEGORY`
  and is capped at `CLEARED_WITH_CAUTION`: a word is not a measurement.
  Vocabulary outside the verified table counts as **missing evidence**.
- Bulletins are **area-scoped** (`South Maharashtra and Goa coast`, `East
  Central Arabian Sea`, ...). Latitude/longitude are `None` and nothing implies
  a value at a coordinate.
- Unverified issuing centres, area names, field labels, or wind units raise
  `SourceContractError`. A parse failure is never reported as "no data".
- Optional Redis provides lazy population and single-flight fetch coordination.
  It is **fail-open**: an absent or broken cache degrades to direct fetches and
  can never block ingestion.

Airflow emits thin NATS triggers; role-isolated workers own the live fetch,
raw archival, parsing, QC, persistence, freshness, and source-state update.
Verified real-time DAGs are unpaused by default. Operators can disable all live
fetches with `MDE_ENABLE_LIVE_SOURCES=false`; doing so records `disabled` and
does not activate fixtures.

## Explicitly blocked or unavailable

### IMD numeric marine NWP — `contract_unavailable`

No documented numeric machine endpoint/schema or credential/header contract has
been verified. Documented marine bulletin endpoints return HTTP 401, and no
basis exists for assuming bearer-token authentication. The former guessed
`/nwp/marine/forecast` path and bearer behavior have been removed. The
production adapter performs no outbound request and raises
`SourceContractUnavailableError`. Text bulletins and charts are not converted
into invented numeric grid points. No NWP DAG is scheduled.

This remains true and is **not** superseded by `imd_marine_bulletin`. That
source ingests the open bulletin pages, which carry a numeric wind range and a
*categorical* sea state — it does not provide a numeric wave/wind grid, point
forecasts, or any modelled field. A gridded numeric marine forecast is still
unavailable.

Reference: `https://api.imd.gov.in/public/api_reference.html`.

### India EEZ geometry — `license_gated`

Marine Regions WFS layer `MarineRegions:eez`, filtered by
`iso_sov1='IND' OR iso_sov2='IND'`, is the verified source for World EEZ v12
India sovereign geometry. Production fetch is blocked before network I/O until
an operator supplies the reviewed permission/attribution reference in
`MARINE_REGIONS_LICENSE_ACKNOWLEDGEMENT`. No schedule is installed while the
gate is closed.

Verified endpoint: `https://geo.vliz.be/geoserver/MarineRegions/wfs`.

### Zone categories with no loaded authoritative source

The following remain independently `not_loaded` and must not be inferred from
EEZ coverage:

- marine protected areas;
- restricted/no-fishing/exclusion areas;
- naval and firing-range areas.

MCP and geofence responses report each category separately. Loading an EEZ
feature never implies these categories are covered or clear.

### Other genuine gaps

- Tide **predictions** are not provided by the TEWS observation connector.
- Numeric ocean grids/current products are not claimed merely because ERDDAP
  metadata is catalogued; a dataset-specific validated parser is required.
- MOSDAC product downloads remain credential/license gated.
- Structured cyclone track/cone/intensity and machine-readable storm-surge
  products beyond the verified HWA/SSA contract remain unavailable.
- CAP XML signature trust-chain verification is not implemented; CAP parsing
  does not claim cryptographic authenticity.
- Bathymetry, shipping lanes, fisheries catch/effort, and other unsourced layers
  remain absent rather than inferred.

## Provenance and freshness

Every canonical environmental row retains provider, dataset, source URL,
retrieval time, processing version, quality status, and structured source
metadata. Station and marine-zone records retain their own authoritative
metadata. Query distance uses the nearest point on actual source geometry, and
point-on-boundary checks are inclusive.

A successful poll updates `last_checked_at`, `last_result_state`,
`last_result_count`, and status detail even when it emits no records. Blocked or
failed states are not overwritten by the freshness evaluator. API and MCP
responses derive provider attribution from returned canonical rows and persist
source states, capability status, versions, lineage, and warnings in evidence
records.

## Fixture policy

Files under `tests/fixtures/` represent synthetic contract shapes for offline
validation. They are labeled test-only and are not observations. Production
worker factories never import or select fixture adapters, regardless of the
live-source flag.

## TLS and credentials

- TLS verification must never be disabled. The engine augments system roots
  with its verified bundled GlobalSign RSA OV SSL CA 2018 intermediate for
  INCOIS hosts that omit it. `INCOIS_CA_BUNDLE` may add an operator-managed PEM
  bundle; it is not an insecure fallback.
- Blank credentials or missing approvals produce explicit blocked states.
- Project code, secrets, and upstream payloads are not sent to third-party
  services outside the configured authoritative source and storage endpoints.

## INCOIS WaveWatch III (`incois_ww3`) — numeric wave contract VERIFIED

Discovered from the Local Sea Forecast viewer's own catalogue reference and
verified live: INCOIS serves an operational WaveWatch III from a THREDDS Data
Server (OPeNDAP / DAP4 / WCS / WMS / NCSS), openly and unauthenticated.

- Catalogue: `https://incois.gov.in/thredds/catalog/osf/ww3/catalog.xml`
- Product consumed: `rsmc_coast_ww3_<init>.nc` (coastal RSMC)
- Domain 4.95–25.05 N, 64.95–95.05 E at 0.1 deg; 3-hourly, 56 steps (~7 days)
- NCSS point requests return CSV, so no HTML scraping and no NetCDF decoder

This closes the numeric wave-height gap: `significant_wave_height`,
`mean_wave_period`, `zero_crossing_wave_period`, `swell_height`,
`mean_wave_direction` and wind components are now real numeric forecasts. A
measured/forecast height takes precedence over the IMD bulletin's WMO category,
so the safety gate is no longer capped at `CLEARED_WITH_CAUTION` where WW3
covers the point.

Two upstream properties required explicit handling and must not be "tidied away":

1. **The CF `units` attribute is published empty** (`units=""`). The unit exists
   only in the human-readable `long_name` (`"Wave height (m)"`). Units are
   therefore resolved from the documented trailing `(unit)` group and then
   asserted against the unit the parameter requires
   (`domain/unit_labels.py`). A variable stating no unit is **refused, not
   assumed** — which is why `PWP` ("Peak Wave Period") is excluded despite being
   useful.
2. **Land is `NaN`, and `NaN` is not zero.** Panaji's own node (15.5 N, 73.8 E)
   is land-masked. `NaN` is treated as absence of evidence; the nearest wet node
   is resolved within a bounded radius (`MDE_WW3_SEARCH_RADIUS_KM`, default
   30 km) and the displacement is reported in `grid_distance_km` alongside
   `requested_point_land_masked`.

Node selection reports **both** `nearest_wet_node` (locality) and
`max_within_radius` (what a departure must be judged against), collapsing to a
single record tagged `nearest_wet_node+max_within_radius` when they coincide.
Off Panaji these differ materially — 0.47 m at 10.5 km versus 1.45 m at 26.4 km
— so collapsing them would have hidden either exposure or locality.

IMD numeric **gridded** NWP remains `contract_unavailable`; WW3 does not
supersede that entry, it is a different provider and product.

