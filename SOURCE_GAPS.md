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
