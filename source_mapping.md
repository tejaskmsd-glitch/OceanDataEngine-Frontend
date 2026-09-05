# Marine Data Source Mapping

> **Runtime status update (2026-09-05):** This is a dated discovery artifact,
> not the current connector/status contract. [`SOURCE_GAPS.md`](./SOURCE_GAPS.md)
> supersedes all HAR-A/HAR-C/HAR-D and IMD-buoy claims below. Since this mapping
> was written, live PFZ Point/LineString, HWA/SSA, TEWS latest-observation, and
> INCOIS OON buoy contracts were verified and implemented. Numeric IMD NWP
> remains `contract_unavailable`. Marine Regions India EEZ was added as a
> separately approved candidate source but remains `license_gated`; it does not
> supply MPA/restricted/naval/firing zones. Historical notes are retained here
> solely to preserve the original research record.
>
> Scope note: This document maps **every** required raw parameter and derived capability from
> `marine_data_layer_requirements.md` (and the build directives in `prompt.md`) to concrete,
> evidence-backed data sources across the **three in-scope providers only** — **IMD, INCOIS, MOSDAC**.
> It is a research/mapping artifact. It **does not implement connectors**; it specifies them.
> No additional providers are proposed as solutions. Where the three providers do not cover a
> required parameter, the gap is stated explicitly and marked, never fabricated or substituted.
>
> **Licensing language rule:** Throughout this document we record the *observed provider policy*
> (copyright strings, registration/payment notices, redistribution statements as published). We
> **do not make a legal interpretation** of those policies. Legal/redistribution clearance is a
> separate action item flagged per source (§16).
>
> **Verification epistemics:** Cells are never left vague. Anything not directly confirmed against a
> live response in this session is written as `UNKNOWN — requires verification (ACTION-ID)` plus the
> exact verification action (HAR capture, registration, provider contact, or file inspection). We
> **never** record assumed access, auth, or format as fact.
>
> **Catalog-presence vs data/schema vs authenticated-retrieval:** These are three distinct verification
> levels and are kept distinct throughout:
> - **Catalog/page verified** — a listing or product page returned live and enumerated an item.
> - **Per-dataset data/schema verified** — the actual variable list / units / axes / geometry of a
>   specific dataset was fetched and inspected (mostly **NOT** done — marked per row).
> - **Authenticated file retrieval verified** — an actual data file was downloaded through auth
>   (**NOT** done — marked AUTH-A).

Document date: 2026-09-03 (IST). Verifier host: Linux, `curl`/`openssl`/`python3`.

---

## 1. Scope

### 1.1 In-scope providers (strictly three)

| Code | Provider | Role in this platform |
|---|---|---|
| IMD | India Meteorological Department | Weather/NWP, marine observations, CAP warnings, cyclone/RSMC bulletins, buoys, radar/GIS |
| INCOIS | Indian National Centre for Ocean Information Services (MoES) | Ocean state (OSF), PFZ, ecosystem advisories, buoys/tide gauges, ERDDAP/LAS/ESSDP catalog, TEWS, storm surge |
| MOSDAC | Meteorological & Oceanographic Satellite Data Archival Centre (SAC/ISRO) | Satellite-derived ocean/atmosphere products (SST, chlorophyll, currents, eddies, HRSSS = **High Resolution Sea Surface Salinity**, subsurface, rainfall) |

No external providers are proposed. Requirement-level gaps (bathymetry, authoritative maritime
boundaries/MPAs, ports, shipping lanes, fisheries catch/productivity) are documented as **gaps** in §15,
per the requirements' own "do not fabricate authoritative boundary/navigation datasets" rule
(requirements §16/§25, prompt §28). **No additional source is introduced as a solution anywhere in this document.**

### 1.2 Method

For each canonical parameter and derived capability we identify: exact provider, exact product/dataset,
exact URL, endpoint/API, access type, auth, format, update frequency, spatial coverage, spatial resolution,
temporal resolution, timestamp semantics, units, coordinate system, retrieval method, parser, normalization,
QC, fallback, licensing/redistribution (policy-observed), and status. Direct-data vs visualization-only is
separated explicitly (§14). We confirm underlying endpoints/files and do **not** infer an API from a web
page that merely displays a value (prompt §27 rule).

### 1.3 Direct-data vs visualization-only principle

A source counts as **direct data** only if it returns machine-readable numeric/geometry payloads
(NetCDF/HDF5/GRIB2/CSV/JSON/GeoJSON/CAP-XML). Products returning only PNG/GIF/JPG/PDF are marked
**VISUAL-ONLY** (§14) and are not treated as data sources for numeric parameters.

### 1.4 Verification-status vocabulary

| Status token | Meaning |
|---|---|
| `VERIFIED` | Live response inspected this session (see §19 verification log). |
| `CATALOG VERIFIED` | Listing/product page confirmed live; per-dataset schema **not** inspected. |
| `SEARCH VERIFIED` | Discovery/search API confirmed live; download **not** exercised. |
| `VERIFIED PATTERN` | URL pattern confirmed reachable; payload parsing fragile/unstructured. |
| `UNKNOWN — requires verification (ACTION-ID)` | Not confirmed; exact action named in §19.1. |
| `GAP` | No in-scope provider supplies it; do not fabricate (§15). |
| `READY (platform)` | Computed by platform; no external source needed. |

---

## 2. Source Overview

### 2.1 IMD — access profile

| Aspect | Detail | Status |
|---|---|---|
| CAP warnings (public) | `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` → linked CAP 1.2 XML files. Copyright string observed: `public domain`. | VERIFIED (V1/V2) |
| CAP transport | RSS 2.0 index (S3-hosted) enumerating dated CAP XML items; each item is a standalone, **digitally signed** CAP 1.2 document. | VERIFIED (V1/V2) |
| CAP event coverage | **Whatever IMD actually issues** into this feed. CAP 1.2 *can* represent cyclone/high_wave/strong_wind/heavy_rain/thunderstorm/lightning/storm_surge/tsunami/marine_hazard, but presence of any given event family is **not** implied by CAP's capability — event coverage must be measured by observing the live feed over time. | `UNKNOWN — requires verification (OBS-CAP)` for the full issued event set |
| Buoy observations | `https://mausam.imd.gov.in/imd_latest/contents/buoy_obs.php?id=<stationId>` — HTML/text page (pattern confirmed). Parsing is HTML/text scraping — brittle (§4.1, §13). | VERIFIED PATTERN |
| Authenticated API | `https://api.imd.gov.in` requires **registration/token**. Legacy `/api` endpoints returned **401/403**. Marine endpoint list unknown. | `UNKNOWN — requires verification (REG-A)` |
| DSP (Data Supply Portal) | Registration + payment + licensing constrained. Not usable without account/license. | `UNKNOWN — requires verification (REG-A)` |
| NWP / coastal forecast pages | Public renderings are mostly **PNG/PDF** → VISUAL-ONLY (§14). Numeric NWP requires GRIB2 via registered/authenticated access. | VISUAL-ONLY / REG-A |
| RSMC cyclone bulletins | Structured track/cone/intensity feed blocked/unverified in session. | `UNKNOWN — requires verification (REG-A/HAR)` |
| Radar / GIS | Radar imagery pages are image tiles; numeric/GIS service unverified. | VISUAL-ONLY / `UNKNOWN — requires verification (HAR-E)` |

### 2.2 INCOIS — access profile

| Aspect | Detail | Status |
|---|---|---|
| ERDDAP catalog | `https://erddap.incois.gov.in/erddap/info/index.json` — unauthenticated; supports pagination (`page`, `itemsPerPage`). | CATALOG VERIFIED (V3) |
| ERDDAP data protocols | **griddap** (gridded: `.nc`, `.csv`, `.json`), **tabledap** (tabular), **WMS** (map tiles) are real ERDDAP protocols. ERDDAP offers **no WFS** — do not claim WFS from ERDDAP. | Protocol facts (ERDDAP standard) |
| ERDDAP per-dataset schema | Variables/units/axes/coverage/resolution of any specific dataset **NOT** inspected this session. | `UNKNOWN — requires verification (ERDDAP-INFO)` per dataset |
| LAS (Live Access Server) | Separate INCOIS visualization/analysis UI. Underlying data protocol per product unverified. | `UNKNOWN — requires verification (HAR-F)` |
| ESSDP | INCOIS Earth System Science Data Portal — presence noted; machine endpoints/schema unverified. | `UNKNOWN — requires verification (HAR-F)` |
| TLS note | Server omits intermediate cert (V3-TLS). Connector must bundle GlobalSign intermediate; never disable verification in prod. | VERIFIED (V3-TLS) |
| PFZ advisory | Entry page (wire-verified): `https://incois.gov.in/MarineFisheries/PfzAdvisory`. Machine geometry/XHR endpoint unverified. | Entry page per verifier; geometry `UNKNOWN — requires verification (HAR-A)` |
| OSF currents / waves | Machine dataset/endpoint unverified. | `UNKNOWN — requires verification (HAR-B)` |
| HWA / storm surge / TEWS / TCHP | Machine feed/schema unverified. | `UNKNOWN — requires verification (HAR-C)` |
| Tide gauge obs / tide prediction | Obs endpoint and whether a *prediction* feed exists both unverified. | `UNKNOWN — requires verification (HAR-D)` |
| Pricing/policy | INCOIS bulk data **may be chargeable**; cite provider pricing/policy at access time. Policy observed, no legal conclusion drawn. | Policy observed |

### 2.3 MOSDAC — access profile

| Aspect | Detail | Status |
|---|---|---|
| Search/discovery API | `GET https://mosdac.gov.in/apios/datasets.json` — unauthenticated. Params: `datasetId, startTime, endTime, count, boundingBox, gId, startIndex`. OpenSearch envelope. | SEARCH VERIFIED (V4) |
| OpenSearch descriptor | `https://mosdac.gov.in/apios/osdd.xml` (advertised via `links.rel=search`). | Referenced by V4 envelope; descriptor fetch `UNKNOWN — requires verification (OSDD-A)` |
| Auth token | `POST https://mosdac.gov.in/download_api/gettoken` (JSON `username`/`password`). Client body/behavior per §6.2.1. | `UNKNOWN — requires verification (AUTH-A)` |
| Session/util endpoints | Official `mdapi.py` source verified: `GET check-internet` with JSON `{datasetId}`; `POST refresh-token` with JSON `{refresh_token}`; `POST logout` with JSON `{username}`. | SOURCE VERIFIED (V5); live authenticated responses not exercised (AUTH-A) |
| Download | Official client uses `GET /download_api/download?id=<record_id>` with `Authorization: Bearer <access_token>`, streaming bytes. **AUTH REQUIRED — not exercised.** | SOURCE VERIFIED / LIVE AUTH `UNKNOWN — requires verification (AUTH-A)` |
| Rate limits | **HTTP 429** with `minute_limit` / `daily_limit` messages reported. Connector must honor both. | Reported; enforce |
| Verified datasetId example | `3RIMG_L2B_SST` (INSAT-3R SST, HDF5 `.h5`). | SEARCH VERIFIED (V4) |
| Open-data product pages | Ocean current, HRSSS (**High Resolution Sea Surface Salinity**), eddies, subsurface NetCDF product pages. Page metadata verification is distinct from authenticated file retrieval. | Page metadata per §6.3; file retrieval `UNKNOWN — requires verification (AUTH-A)` |
| Gallery | PNG/GIF/JPG quicklooks are **VISUAL-ONLY** (§14) and must be separated from numeric NetCDF/HDF products. | VISUAL-ONLY |

### 2.4 Provider → parameter-family coverage summary

| Family | IMD | INCOIS | MOSDAC | Notes |
|---|---|---|---|---|
| CAP warnings / alerts | ✅ VERIFIED | (TEWS/HWA/surge unverified) | — | IMD CAP is the only fully verified machine-readable safety feed |
| Marine obs (buoy) | ✅ HTML pattern | ✅ ERDDAP ARGO | — | IMD buoy brittle HTML; INCOIS ARGO open |
| NWP numeric | REG-A | — | — | public IMD NWP is VISUAL-ONLY |
| SST | — | ✅ catalog | ✅ search (download AUTH-A) | fallback pair (§13) |
| Chlorophyll | — | ✅ catalog | search (datasetId TBD) | |
| Currents / waves / swell | — | HAR-B | search (datasetId TBD) | |
| Salinity (surface) HRSSS | — | — | ✅ page metadata (download AUTH-A) | HRSSS = High Resolution **Sea Surface Salinity** |
| Subsurface | — | ✅ ARGO catalog | ✅ page metadata (download AUTH-A) | |
| Eddies | — | — | ✅ page metadata (download AUTH-A) | |
| Tides | — | HAR-D | — | prediction may not exist as feed |
| Cyclone (structured) | REG-A/HAR | HAR-C | — | CAP gives partial (polygon only) |
| Tsunami | — | HAR-C (TEWS) | — | safety-critical |
| PFZ / advisories / ecosystem | — | HAR-A | — | PFZ page verified; geometry not |
| Geospatial reference (EEZ/MPA/ports/lanes/bathymetry) | — | — | — | **GAP (§15)** |
| Fisheries catch/productivity | — | — | — | **GAP (§15)** |

---

## 3. Master Parameter-to-Source Matrix

**Exact 23 columns (in order):** `1 Parameter/Capability` · `2 Required for` · `3 Source` · `4 Product/Dataset` · `5 Exact URL` · `6 Endpoint/API` · `7 Access Type` · `8 Auth` · `9 Format` · `10 Update Frequency` · `11 Spatial Coverage` · `12 Spatial Resolution` · `13 Temporal Resolution` · `14 Timestamp Semantics` · `15 Units` · `16 Coordinate System` · `17 Retrieval Method` · `18 Parser` · `19 Normalization` · `20 QC` · `21 Fallback` · `22 Licensing/Redistribution` · `23 Status`.

Notation: cells use footnote refs `[Fn]` (see §3.10) to stay readable, but **every row has all 23 cells with an explicit value or `UNKNOWN — requires verification (ACTION-ID)`**. **Fallback** cells: per scope (three providers only) cross-provider fallbacks are noted only where both are in-scope and verified; otherwise `None in-scope — gap (§15)`. Licensing = **policy observed only** (no legal interpretation). There is a **distinct row for every raw parameter and every derived capability**; nothing is aggregated away. Derived rows carry `Source = Platform (derived)` and their input dependency + readiness are detailed in §3.9.

### 3.1 Location & spatial-context (input/computed — no external source)

| 1 Parameter/Capability | 2 Required for | 3 Source | 4 Product/Dataset | 5 Exact URL | 6 Endpoint/API | 7 Access | 8 Auth | 9 Format | 10 Update Freq | 11 Coverage | 12 Spat.Res | 13 Temp.Res | 14 Timestamp Sem. | 15 Units | 16 CRS | 17 Retrieval | 18 Parser | 19 Normalization | 20 QC | 21 Fallback | 22 Licensing | 23 Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| latitude | all location queries | Platform input | n/a | n/a | Platform API | Input | n/a | float | per request | India focus | n/a | n/a | request-time | deg | WGS84 | API param | Pydantic | range check | −90..90 | n/a | n/a | READY (platform) |
| longitude | all location queries | Platform input | n/a | n/a | Platform API | Input | n/a | float | per request | India focus | n/a | n/a | request-time | deg | WGS84 | API param | Pydantic | 0..360→−180..180 [Fn1] | −180..180 | n/a | n/a | READY (platform) |
| timestamp | obs/fcst context | Platform input | n/a | n/a | Platform API | Input | n/a | ISO-8601 | per request | n/a | n/a | n/a | request-time→UTC | UTC | n/a | API param | dateutil | to UTC [Fn2] | parse/validate | n/a | n/a | READY (platform) |
| bbox | regional/map queries | Platform derived | n/a | n/a | Shapely | Computed | n/a | float[4] | per request | n/a | n/a | n/a | n/a | deg | WGS84 | geometry | Shapely | axis order per source | bounds | n/a | n/a | READY (platform) |
| radius_km | nearby search | Platform input | n/a | n/a | geodesic | Input | n/a | float | per request | n/a | n/a | n/a | n/a | km | WGS84 | API param | pyproj | geodesic basis | 0..2000 | n/a | n/a | READY (platform) |
| bearing | navigation/route | Platform derived | n/a | n/a | pyproj Geod | Computed | n/a | float | per request | n/a | n/a | n/a | n/a | deg true | WGS84 | forward azimuth | pyproj | 0..360 | range | n/a | n/a | READY (platform) |

### 3.2 Ocean — raw parameters

| 1 Parameter/Capability | 2 Required for | 3 Source | 4 Product/Dataset | 5 Exact URL | 6 Endpoint/API | 7 Access | 8 Auth | 9 Format | 10 Update Freq | 11 Coverage | 12 Spat.Res | 13 Temp.Res | 14 Timestamp Sem. | 15 Units | 16 CRS | 17 Retrieval | 18 Parser | 19 Normalization | 20 QC | 21 Fallback | 22 Licensing | 23 Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sea_surface_temperature (SST) | PFZ, suitability, anomalies, ocean cond. | MOSDAC | INSAT-3R L2B SST | `https://mosdac.gov.in/apios/datasets.json?datasetId=3RIMG_L2B_SST` | `GET /apios/datasets.json` (search) + download API | Search: Open; Download: Auth | Search none; Download token [Fn3] | HDF5 `.h5` | sub-daily slots (1615 UTC slot seen) | INSAT disk (Indian Ocean) | `UNKNOWN — requires verification (h5-attrs)` | per-slot | observed_at (`dcDate`/identifier time) | K or degC (read attrs) [Fn7] | sat grid→WGS84 | search then auth download | xarray/h5py [Fn4] | K→degC, regrid [Fn5][Fn7] | range −2..40, fill/scale [Fn6] | INCOIS AVHRR/AMSR & ARGO SST [Fn8] | MOSDAC: search open; download account-gated; policy observed | SEARCH VERIFIED / DOWNLOAD `UNKNOWN — requires verification (AUTH-A)` |
| sea_surface_temperature (SST) — in-scope fallback | same | INCOIS | NOAA AVHRR/AMSR SST; ARGO SST weekly | `https://erddap.incois.gov.in/erddap/info/index.json` | ERDDAP griddap/tabledap | Open | None (bundle intermediate) [Fn9] | NetCDF/CSV/JSON | dataset-dependent | Indian Ocean/global | `UNKNOWN — requires verification (ERDDAP-INFO)` | daily/weekly/monthly | observed_at | degC (read attrs) | WGS84 (ERDDAP) | griddap subset | xarray/erddapy | units/regrid [Fn5] | range/fill [Fn6] | MOSDAC SST | INCOIS bulk may be chargeable; policy observed [Fn10] | CATALOG VERIFIED; per-dataset schema `UNKNOWN — requires verification (ERDDAP-INFO)` |
| chlorophyll_a | PFZ, suitability, productivity | INCOIS | IRS chlorophyll (`IRS_chlorophyll_datasets`) | `https://erddap.incois.gov.in/erddap/info/index.json` | ERDDAP griddap | Open | None [Fn9] | NetCDF/CSV | dataset-dependent | Indian Ocean | `UNKNOWN — requires verification (ERDDAP-INFO)` | daily/composite | observed_at | mg/m³ | WGS84 | griddap subset | xarray/erddapy | log→linear if needed; regrid | range 0..100, fill | MOSDAC ocean-colour open-data [Fn11] | INCOIS policy; chargeable possible [Fn10] | CATALOG VERIFIED; schema `UNKNOWN — requires verification (ERDDAP-INFO)` |
| chlorophyll_a — alt | same | MOSDAC | Ocean colour (OCM, open-data) | `https://mosdac.gov.in/apios/datasets.json` (query OCM chlorophyll datasetId) | `GET /apios/datasets.json` | Search Open; Download Auth | Download token [Fn3] | NetCDF/HDF5 | product-dependent | INSAT/OceanSat disk | `UNKNOWN — requires verification (search+attrs)` | product-dependent | observed_at | mg/m³ | sat grid→WGS84 | search+download | xarray/h5py | units/regrid | range/fill | INCOIS IRS chlorophyll | MOSDAC policy observed | SEARCH VERIFIED; exact datasetId `UNKNOWN — requires verification (DSID-CHL)` |
| sea_surface_salinity | ecosystem, advanced fisheries (P2) | MOSDAC | **HRSSS = High Resolution Sea Surface Salinity** (open-data) | `https://mosdac.gov.in/apios/datasets.json` (query SSS datasetId) + open-data page | `GET /apios/datasets.json` | Search Open; Download Auth | Download token [Fn3] | NetCDF/HDF5 | six-month publication cadence [Fn28] | 10 km BoB [Fn28] | 10 km (BoB) [Fn28] | per publication | observed_at | PSU | sat grid→WGS84 | search+download | xarray/h5py | units/regrid | range 0..42 | None in-scope verified | MOSDAC policy observed | PAGE METADATA per §6.3; file retrieval `UNKNOWN — requires verification (AUTH-A)` |
| current_u | routing, travel-time, fishing, ocean cond. | INCOIS | OSF surface currents | `https://incois.gov.in/` OSF (data XHR/griddap) | OSF XHR or ERDDAP griddap | Open (assumed — unverified) | `UNKNOWN — requires verification (HAR-B)` | NetCDF/JSON `UNKNOWN` | daily/forecast cycles `UNKNOWN` | Indian Ocean | `UNKNOWN — requires verification (HAR-B)` | forecast cycles | valid_time | m/s | WGS84 | HAR then subset | xarray/erddapy | keep u/v [Fn12] | range −5..5 | MOSDAC ocean current open-data [Fn13] | INCOIS policy observed | `UNKNOWN — requires verification (HAR-B)` |
| current_v | routing, travel-time, fishing, ocean cond. | INCOIS | OSF surface currents | `https://incois.gov.in/` OSF (data XHR/griddap) | OSF XHR or ERDDAP griddap | Open (assumed — unverified) | `UNKNOWN — requires verification (HAR-B)` | NetCDF/JSON `UNKNOWN` | daily/forecast cycles `UNKNOWN` | Indian Ocean | `UNKNOWN — requires verification (HAR-B)` | forecast cycles | valid_time | m/s | WGS84 | HAR then subset | xarray/erddapy | keep u/v [Fn12] | range −5..5 | MOSDAC ocean current open-data [Fn13] | INCOIS policy observed | `UNKNOWN — requires verification (HAR-B)` |
| current_u/v — alt | same | MOSDAC | Ocean current (open-data NetCDF) | `https://mosdac.gov.in/apios/datasets.json` (query current datasetId) + open-data page | `GET /apios/datasets.json` | Search Open; Download Auth | Download token [Fn3] | NetCDF | 0.25° daily global [Fn28] | global [Fn28] | 0.25° [Fn28] | daily | valid_time | m/s | sat/model grid→WGS84 | search+download | xarray | keep u/v; regrid | range/fill | INCOIS OSF | MOSDAC policy observed | PAGE METADATA per §6.3; file retrieval `UNKNOWN — requires verification (AUTH-A)` |
| significant_wave_height | safety, windows, HWA, routing | INCOIS | OSF wave forecast | `https://incois.gov.in/` OSF (data XHR/griddap) | OSF XHR / ERDDAP griddap | Open (assumed — unverified) | `UNKNOWN — requires verification (HAR-B)` | NetCDF/JSON `UNKNOWN` | forecast cycles `UNKNOWN` | Indian Ocean | `UNKNOWN — requires verification (HAR-B)` | forecast steps | valid_time | m | WGS84 | HAR then subset | xarray | regrid | range 0..20 | None in-scope verified | INCOIS policy observed | `UNKNOWN — requires verification (HAR-B)` |
| wave_period | safety, windows, routing | INCOIS | OSF wave forecast | `https://incois.gov.in/` OSF | OSF XHR / griddap | Open (assumed — unverified) | `UNKNOWN — requires verification (HAR-B)` | NetCDF/JSON | forecast cycles | Indian Ocean | `UNKNOWN — requires verification (HAR-B)` | forecast steps | valid_time | s | WGS84 | HAR then subset | xarray | peak vs mean documented | range 0..30 | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-B)` |
| wave_direction | safety, windows, routing | INCOIS | OSF wave forecast | `https://incois.gov.in/` OSF | OSF XHR / griddap | Open (assumed — unverified) | `UNKNOWN — requires verification (HAR-B)` | NetCDF/JSON | forecast cycles | Indian Ocean | `UNKNOWN — requires verification (HAR-B)` | forecast steps | valid_time | deg | WGS84 | HAR then subset | xarray | to/from per source [Fn12] | range 0..360 | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-B)` |
| swell_height | safety, windows, routing | INCOIS | OSF swell | `https://incois.gov.in/` OSF | OSF XHR / griddap | Open (assumed — unverified) | `UNKNOWN — requires verification (HAR-B)` | NetCDF/JSON | forecast cycles | Indian Ocean | `UNKNOWN — requires verification (HAR-B)` | forecast steps | valid_time | m | WGS84 | HAR then subset | xarray | regrid | range 0..15 | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-B)` |
| swell_period | safety, windows, routing | INCOIS | OSF swell | `https://incois.gov.in/` OSF | OSF XHR / griddap | Open (assumed — unverified) | `UNKNOWN — requires verification (HAR-B)` | NetCDF/JSON | forecast cycles | Indian Ocean | `UNKNOWN — requires verification (HAR-B)` | forecast steps | valid_time | s | WGS84 | HAR then subset | xarray | peak vs mean | range 0..30 | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-B)` |
| swell_direction | safety, windows, routing | INCOIS | OSF swell | `https://incois.gov.in/` OSF | OSF XHR / griddap | Open (assumed — unverified) | `UNKNOWN — requires verification (HAR-B)` | NetCDF/JSON | forecast cycles | Indian Ocean | `UNKNOWN — requires verification (HAR-B)` | forecast steps | valid_time | deg | WGS84 | HAR then subset | xarray | to/from per source [Fn12] | range 0..360 | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-B)` |
| wind_wave_height | safety, windows, routing | INCOIS | OSF wind-wave | `https://incois.gov.in/` OSF | OSF XHR / griddap | Open (assumed — unverified) | `UNKNOWN — requires verification (HAR-B)` | NetCDF/JSON | forecast cycles | Indian Ocean | `UNKNOWN — requires verification (HAR-B)` | forecast steps | valid_time | m | WGS84 | HAR then subset | xarray | regrid | range 0..15 | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-B)` |
| wind_wave_period | safety, windows, routing | INCOIS | OSF wind-wave | `https://incois.gov.in/` OSF | OSF XHR / griddap | Open (assumed — unverified) | `UNKNOWN — requires verification (HAR-B)` | NetCDF/JSON | forecast cycles | Indian Ocean | `UNKNOWN — requires verification (HAR-B)` | forecast steps | valid_time | s | WGS84 | HAR then subset | xarray | peak vs mean | range 0..30 | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-B)` |
| sea_level (SSH) | coastal, surge context | INCOIS | ERDDAP value-added (`incois_valueadded_products_datasets`) | `https://erddap.incois.gov.in/erddap/info/index.json` | ERDDAP griddap/tabledap | Open | None [Fn9] | NetCDF/CSV | dataset-dependent | Indian Ocean | `UNKNOWN — requires verification (ERDDAP-INFO)` | dataset-dependent | observed_at | m | WGS84 | subset | xarray | datum noted | range −3..3 | None in-scope | INCOIS policy observed | CATALOG VERIFIED; dataset id `UNKNOWN — requires verification (ERDDAP-INFO)` |
| tide_gauge_level | tides, harbour ops | INCOIS | RT tide-gauge network | ERDDAP tabledap OR portal XHR | tabledap / portal | Open (assumed — unverified) | `UNKNOWN — requires verification (HAR-D)` | CSV/JSON/NetCDF | sub-hourly `UNKNOWN` | Indian coast stations | station points | sub-hourly `UNKNOWN` | observation_time | m | WGS84 (points) | tabledap query | pandas/erddapy | datum per station | range −6..6 | IMD coastal obs (HTML) | INCOIS policy observed | `UNKNOWN — requires verification (HAR-D)` |
| subsurface_temperature | advanced fisheries/oceanography (P2) | INCOIS | ARGO floats (`Indian_ARGO_Floats`, `incois_argo_*`) | `https://erddap.incois.gov.in/erddap/info/index.json` | ERDDAP tabledap/griddap | Open | None [Fn9] | NetCDF/CSV | 10-day/monthly (per dataset) | Indian Ocean | profile (z) | 10-day/monthly | observed_at | degC | WGS84 + depth | tabledap query | xarray/erddapy | depth axis kept | range/fill | MOSDAC subsurface NetCDF [Fn14] | INCOIS policy observed | CATALOG VERIFIED; schema `UNKNOWN — requires verification (ERDDAP-INFO)` |
| subsurface_salinity | advanced fisheries/oceanography (P2) | INCOIS | ARGO floats | `https://erddap.incois.gov.in/erddap/info/index.json` | ERDDAP tabledap | Open | None [Fn9] | NetCDF/CSV | 10-day/monthly | Indian Ocean | profile (z) | 10-day/monthly | observed_at | PSU | WGS84 + depth | tabledap query | xarray/erddapy | depth axis kept | range 0..42 | MOSDAC subsurface NetCDF [Fn14] | INCOIS policy observed | CATALOG VERIFIED; schema `UNKNOWN — requires verification (ERDDAP-INFO)` |
| subsurface_current | advanced oceanography (P2) | INCOIS | ARGO-derived (`incois_argo_*_McCreary/VAM`) | `https://erddap.incois.gov.in/erddap/info/index.json` | ERDDAP griddap/tabledap | Open | None [Fn9] | NetCDF/CSV | 10-day/monthly | Indian Ocean | profile (z) | 10-day/monthly | observed_at | m/s | WGS84 + depth | subset | xarray/erddapy | keep u/v; depth kept | range −5..5 | MOSDAC subsurface [Fn14] | INCOIS policy observed | CATALOG VERIFIED; schema `UNKNOWN — requires verification (ERDDAP-INFO)` |
| subsurface (alt) | same | MOSDAC | Subsurface (open-data NetCDF) | `https://mosdac.gov.in/apios/datasets.json` (query) + open-data page | `GET /apios/datasets.json` | Search Open; Download Auth | Download token [Fn3] | NetCDF | product-dependent | 25 km BoB, 10 m depth step [Fn28] | 25 km / 10 m [Fn28] | product-dependent | observed_at | degC/PSU | grid→WGS84 | search+download | xarray | depth kept | range/fill | INCOIS ARGO | MOSDAC policy observed | PAGE METADATA per §6.3; file retrieval `UNKNOWN — requires verification (AUTH-A)` |
| ocean_eddy | fisheries research, currents | MOSDAC | Oceanic eddy detection (open-data) | `https://mosdac.gov.in/apios/datasets.json` (query eddy datasetId) + open-data page | `GET /apios/datasets.json` | Search Open; Download Auth | Download token [Fn3] | NetCDF/vector `UNKNOWN` | weekly BoB [Fn28] | BoB [Fn28] | `UNKNOWN — requires verification (attrs)` | weekly | valid_time | radius km, amplitude cm | grid/vector→WGS84 | search+download | xarray/geopandas | keep polarity | topology/range | None in-scope | MOSDAC policy observed | PAGE METADATA per §6.3; file retrieval `UNKNOWN — requires verification (AUTH-A)` |
| tchp | cyclone/ocean-atmos analysis (P2) | INCOIS | TCHP service | INCOIS TCHP page | XHR / ERDDAP `UNKNOWN` | `UNKNOWN — requires verification (HAR-C)` | `UNKNOWN` | NetCDF/JSON `UNKNOWN` | daily `UNKNOWN` | Indian Ocean | `UNKNOWN — requires verification (HAR-C)` | daily | valid_time | kJ/cm² | WGS84 | HAR then subset | xarray | regrid | range 0..200 | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-C)` |

### 3.3 Weather / atmosphere — raw parameters

| 1 Parameter/Capability | 2 Required for | 3 Source | 4 Product/Dataset | 5 Exact URL | 6 Endpoint/API | 7 Access | 8 Auth | 9 Format | 10 Update Freq | 11 Coverage | 12 Spat.Res | 13 Temp.Res | 14 Timestamp Sem. | 15 Units | 16 CRS | 17 Retrieval | 18 Parser | 19 Normalization | 20 QC | 21 Fallback | 22 Licensing | 23 Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| wind_speed | safety, routing, waves, storms | IMD | Marine obs / NWP | `https://api.imd.gov.in` (marine) | REST (token) `UNKNOWN` | Registration/token | Token [Fn15] | JSON `UNKNOWN` / GRIB2 | hourly/cycles `UNKNOWN` | India + seas | `UNKNOWN — requires verification (REG-A)` | hourly/cycle | observed_at/valid_time | m/s | WGS84 | REST/GRIB2 | requests/cfgrib [Fn16] | knots→m/s [Fn12] | range 0..90 | INCOIS scatterometer [Fn17] | IMD DSP/API license; policy observed | `UNKNOWN — requires verification (REG-A)` |
| wind_direction | safety, routing, storms | IMD | Marine obs / NWP | `https://api.imd.gov.in` | REST (token) `UNKNOWN` | Registration/token | Token [Fn15] | JSON/GRIB2 | hourly/cycle | India + seas | `UNKNOWN — requires verification (REG-A)` | hourly/cycle | observed_at/valid_time | deg | WGS84 | REST/GRIB2 | requests/cfgrib | "from" per source [Fn12] | range 0..360 | INCOIS scatterometer [Fn17] | IMD license; policy observed | `UNKNOWN — requires verification (REG-A)` |
| wind_u | routing, waves | INCOIS | ASCAT/QuikSCAT/OceanSat scatterometer | `https://erddap.incois.gov.in/erddap/info/index.json` (`ascat_daily_datasets`,`incois_quickscat_daily_datasets`,`incois_oceansat2_datasets`) | ERDDAP griddap | Open | None [Fn9] | NetCDF/CSV | daily/monthly | ocean (Indian/global) | `UNKNOWN — requires verification (ERDDAP-INFO)` | daily/monthly | observed_at | m/s | WGS84 | griddap subset | xarray/erddapy | keep u/v [Fn12] | range −90..90 | IMD marine obs | INCOIS policy observed [Fn10] | CATALOG VERIFIED; schema `UNKNOWN — requires verification (ERDDAP-INFO)` |
| wind_v | routing, waves | INCOIS | ASCAT/QuikSCAT/OceanSat scatterometer | `https://erddap.incois.gov.in/erddap/info/index.json` | ERDDAP griddap | Open | None [Fn9] | NetCDF/CSV | daily/monthly | ocean | `UNKNOWN — requires verification (ERDDAP-INFO)` | daily/monthly | observed_at | m/s | WGS84 | griddap subset | xarray/erddapy | keep u/v [Fn12] | range −90..90 | IMD marine obs | INCOIS policy observed [Fn10] | CATALOG VERIFIED; schema `UNKNOWN — requires verification (ERDDAP-INFO)` |
| gust_speed | safety, storms | IMD | Marine obs / NWP | `https://api.imd.gov.in` | REST/GRIB2 `UNKNOWN` | Registration/token | Token [Fn15] | JSON/GRIB2 | hourly/cycle | India + seas | `UNKNOWN — requires verification (REG-A)` | hourly/cycle | valid_time | m/s | WGS84 | REST/GRIB2 | requests/cfgrib | knots→m/s | range 0..120 | None in-scope verified | IMD license; policy observed | `UNKNOWN — requires verification (REG-A)` |
| rainfall_rate | safety, heavy-rain hazard, routing | IMD | NWP rainfall / marine guidance | `https://api.imd.gov.in` (public NWP VISUAL-ONLY) | REST/GRIB2 `UNKNOWN` | Registration/token | Token [Fn15] | GRIB2/JSON | cycles/hourly | India + seas | `UNKNOWN — requires verification (REG-A)` | hourly | observed_at/valid_time | mm/h | WGS84 | GRIB2/REST | cfgrib [Fn16] | none | range 0..500 | MOSDAC INSAT rainfall [Fn18] | IMD license; policy observed | `UNKNOWN — requires verification (REG-A)` |
| rainfall_accumulation | safety, heavy-rain hazard | IMD | NWP rainfall | `https://api.imd.gov.in` | REST/GRIB2 `UNKNOWN` | Registration/token | Token [Fn15] | GRIB2/JSON | accum window | India + seas | `UNKNOWN — requires verification (REG-A)` | accum window | valid_from→valid_until | mm | WGS84 | GRIB2/REST | cfgrib | accum window kept | range 0..2000 | MOSDAC INSAT rainfall [Fn18] | IMD license; policy observed | `UNKNOWN — requires verification (REG-A)` |
| rainfall (satellite alt) | same | MOSDAC | INSAT rainfall (open-data) | `https://mosdac.gov.in/apios/datasets.json` (query rainfall datasetId) | `GET /apios/datasets.json` | Search Open; Download Auth | Download token [Fn3] | HDF5/NetCDF | sub-daily slots | INSAT disk | `UNKNOWN — requires verification (search+attrs)` | per-slot | observed_at | mm/h | sat grid→WGS84 | search+download | xarray/h5py | units/regrid | range/fill | INCOIS TMI (`incois_tmi_3day_datasets`) [Fn19] | MOSDAC policy observed | SEARCH VERIFIED; datasetId `UNKNOWN — requires verification (DSID-RAIN)` |
| sea_level_pressure | storm ID, cyclone, risk | IMD | Marine obs / NWP MSLP | `https://api.imd.gov.in` (public NWP VISUAL-ONLY) | REST/GRIB2 `UNKNOWN` | Registration/token | Token [Fn15] | GRIB2/JSON | hourly/cycle | India + seas | `UNKNOWN — requires verification (REG-A)` | hourly/cycle | observed_at/valid_time | hPa | WGS84 | REST/GRIB2 | cfgrib/requests | Pa→hPa ÷100 | range 850..1085 | None in-scope verified | IMD license; policy observed | `UNKNOWN — requires verification (REG-A)` |
| station_pressure | storm ID, risk | IMD | Marine/station obs | `https://api.imd.gov.in` | REST `UNKNOWN` | Registration/token | Token [Fn15] | JSON `UNKNOWN` | hourly | India stations | station | hourly | observed_at | hPa | WGS84 | REST | requests | none | range 500..1085 | None in-scope | IMD license; policy observed | `UNKNOWN — requires verification (REG-A)` |
| humidity | context (where available) | IMD | Marine obs / NWP | `https://api.imd.gov.in` | REST/GRIB2 `UNKNOWN` | Registration/token | Token [Fn15] | JSON/GRIB2 | hourly/cycle | India + seas | `UNKNOWN — requires verification (REG-A)` | hourly | observed_at | % | WGS84 | REST/GRIB2 | requests/cfgrib | none | range 0..100 | None in-scope | IMD license; policy observed | `UNKNOWN — requires verification (REG-A)` |
| thunderstorm_indicator | thunderstorm warning | IMD | CAP warnings (thunderstorm events **as issued**) | `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` → CAP items | RSS + CAP XML | Open | None | RSS 2.0 + CAP 1.2 | event-driven | India (polygon per alert) | polygon | event-driven | issued/effective/expires [Fn20] | categorical | WGS84 | poll RSS, fetch CAP | feedparser + lxml [Fn21] | to warning entity [Fn22] | signature check [Fn23] | None in-scope | **public domain** (RSS copyright) | VERIFIED (V1/V2); event presence `UNKNOWN — requires verification (OBS-CAP)` |
| lightning_event | lightning alerts | IMD | CAP (lightning events **as issued**) | `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` → CAP items | RSS + CAP XML | Open | None | CAP 1.2 | event-driven | India polygons | polygon | event-driven | issued/expires [Fn20] | categorical | WGS84 (`lat,lon` polygon) | poll+fetch | lxml [Fn21] | polygon→GeoJSON [Fn22] | signature [Fn23] | None in-scope | **public domain** | VERIFIED (V1/V2); event presence `UNKNOWN — requires verification (OBS-CAP)` |

### 3.4 Tides & coastal water level — raw parameters

| 1 Parameter/Capability | 2 Required for | 3 Source | 4 Product/Dataset | 5 Exact URL | 6 Endpoint/API | 7 Access | 8 Auth | 9 Format | 10 Update Freq | 11 Coverage | 12 Spat.Res | 13 Temp.Res | 14 Timestamp Sem. | 15 Units | 16 CRS | 17 Retrieval | 18 Parser | 19 Normalization | 20 QC | 21 Fallback | 22 Licensing | 23 Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tide_gauge_observation | tides, harbour ops | INCOIS | RT tide-gauge network | ERDDAP tabledap OR portal XHR | tabledap/portal | Open (assumed — unverified) | `UNKNOWN — requires verification (HAR-D)` | CSV/JSON/NetCDF | sub-hourly `UNKNOWN` | Indian coast | station points | sub-hourly `UNKNOWN` | observation_time | m | WGS84 | tabledap query | pandas | datum per station | range −6..6 | IMD coastal obs (HTML) | INCOIS policy observed | `UNKNOWN — requires verification (HAR-D)` |
| tide_prediction (future high/low) | time_to_high/low_tide, windows | INCOIS | Tidal prediction feed (existence unconfirmed) | `UNKNOWN — requires verification (HAR-D)` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN — requires verification (HAR-D)` | Indian coast | station | `UNKNOWN` | forecast valid_time | m | WGS84 | HAR then fetch | `UNKNOWN` | tide-state derivation [Fn24] | monotonic checks | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-D)` — **prediction may not exist as feed** |
| storm_surge / sea_level_surge | cyclone impact, coastal risk | INCOIS | Storm surge service | `UNKNOWN — requires verification (HAR-C)` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | NetCDF/JSON `UNKNOWN` | event/daily `UNKNOWN` | Indian coast | `UNKNOWN` | event/daily | valid_from→until | m | WGS84 | HAR then fetch | `UNKNOWN` | anomaly vs tide | range checks | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-C)` |

### 3.5 Hazards / alerts / advisories — raw parameters/entities

| 1 Parameter/Capability | 2 Required for | 3 Source | 4 Product/Dataset | 5 Exact URL | 6 Endpoint/API | 7 Access | 8 Auth | 9 Format | 10 Update Freq | 11 Coverage | 12 Spat.Res | 13 Temp.Res | 14 Timestamp Sem. | 15 Units | 16 CRS | 17 Retrieval | 18 Parser | 19 Normalization | 20 QC | 21 Fallback | 22 Licensing | 23 Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CAP marine/coastal warning (generic entity) | alerts, risk, events | IMD | CAP 1.2 (public) | `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` → dated CAP items e.g. `.../2026-09-03-07-21-21.xml` | RSS index + CAP XML | Open | None | RSS 2.0 + CAP 1.2 (signed) | event-driven; poll RSS | India (per-alert polygon) | polygon | event-driven | issued/effective/onset/expires [Fn20] | categorical (severity/urgency/certainty) | WGS84 (`lat,lon` polygon) | poll RSS → fetch CAP | feedparser + lxml [Fn21] | polygon→GeoJSON; enums normalized [Fn22] | XML signature verify [Fn23] | None in-scope | **public domain** | VERIFIED (V1/V2) |
| warning event coverage (which event families present) | alert taxonomy | IMD | CAP feed contents over time | same as above | RSS + CAP | Open | None | CAP 1.2 | event-driven | India | polygon | event-driven | per event | categorical | WGS84 | observe feed | lxml | count families **actually issued** (do not assume all present) | n/a | n/a | public domain | `UNKNOWN — requires verification (OBS-CAP)` — coverage = whatever IMD actually issues |
| high_wave_alert | safety, windows | INCOIS | HWA service | HWA JSON `UNKNOWN — requires verification (HAR-C)` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | JSON `UNKNOWN` | daily/event | Indian coast/seas | polygon | daily/event | valid_from→until | categorical + m | WGS84 | HAR then fetch | `UNKNOWN` | to warning entity | geometry validity | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-C)` |
| swell_alert | safety, windows | INCOIS | Swell surge/HWA service | `UNKNOWN — requires verification (HAR-C)` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | JSON `UNKNOWN` | daily/event | Indian coast | polygon | daily/event | valid_from→until | categorical + m | WGS84 | HAR then fetch | `UNKNOWN` | to warning entity | geometry validity | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-C)` |
| lightning_alert | lightning proximity | IMD | CAP thunderstorm/lightning (**as issued**) | `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` | RSS + CAP | Open | None | CAP 1.2 | event-driven | India polygons | polygon | event-driven | issued/expires | categorical | WGS84 | poll+fetch | lxml | to warning entity | signature | None in-scope | public domain | VERIFIED (V1/V2); presence `UNKNOWN — requires verification (OBS-CAP)` |
| thunderstorm_warning | safety | IMD | CAP thunderstorm (**as issued**) | `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` | RSS + CAP | Open | None | CAP 1.2 | event-driven | India polygons | polygon | event-driven | issued/expires | categorical | WGS84 | poll+fetch | lxml | to warning entity | signature | None in-scope | public domain | VERIFIED (V1/V2); presence `UNKNOWN — requires verification (OBS-CAP)` |
| heavy_rain_warning | safety | IMD | CAP heavy-rain (**as issued**; V2 saw `event=Extremely heavy`) | `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` | RSS + CAP | Open | None | CAP 1.2 | event-driven | India polygons | polygon | event-driven | issued/expires | categorical | WGS84 | poll+fetch | lxml | to warning entity | signature | None in-scope | public domain | VERIFIED (V1/V2) |
| marine/coastal warning (marine_hazard) | safety, alerts | IMD | CAP marine hazard (**as issued**) | `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` | RSS + CAP | Open | None | CAP 1.2 | event-driven | India polygons | polygon | event-driven | issued/expires | categorical | WGS84 | poll+fetch | lxml | to warning entity | signature | None in-scope | public domain | VERIFIED (V1/V2); presence `UNKNOWN — requires verification (OBS-CAP)` |
| CAP warning properties (severity/urgency/certainty) | risk weighting | IMD | CAP fields | `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` | RSS + CAP | Open | None | CAP 1.2 | event-driven | per alert | polygon | event-driven | per alert | categorical enums | WGS84 | poll+fetch | lxml | enum normalize [Fn22] | signature | n/a | public domain | VERIFIED (V2) |
| cyclone_center | cyclone entity, risk | IMD/RSMC | RSMC bulletins | RSMC page/feed (blocked in session) | `UNKNOWN` | `UNKNOWN` (likely restricted) | `UNKNOWN` | XML/PDF/shapefile `UNKNOWN` | 3–6 hourly during events | N Indian Ocean | point | 3–6 hourly | issue_time | deg | WGS84 | HAR/registration | `UNKNOWN` | to cyclone entity | geometry validity | INCOIS cyclone (also unverified) | IMD/RSMC policy observed | `UNKNOWN — requires verification (REG-A/HAR)` |
| cyclone_track | cyclone entity, routing | IMD/RSMC | RSMC bulletins | RSMC page/feed (blocked) | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | XML/shapefile `UNKNOWN` | 3–6 hourly | N Indian Ocean | track geometry | 3–6 hourly | issue/forecast_time | deg | WGS84 | HAR/registration | `UNKNOWN` | to cyclone entity | geometry validity | INCOIS cyclone (unverified) | IMD/RSMC policy observed | `UNKNOWN — requires verification (REG-A/HAR)` |
| forecast_cone | cyclone entity | IMD/RSMC | RSMC bulletins | RSMC page/feed (blocked) | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | shapefile/GeoJSON `UNKNOWN` | 3–6 hourly | N Indian Ocean | cone polygon | 3–6 hourly | forecast_time | deg | WGS84 | HAR/registration | `UNKNOWN` | to cyclone entity | geometry validity | None in-scope | IMD/RSMC policy observed | `UNKNOWN — requires verification (REG-A/HAR)` |
| cyclone_intensity / central_pressure / max_wind / gust | cyclone entity, risk | IMD/RSMC | RSMC bulletins | RSMC page/feed (blocked) | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | XML/PDF `UNKNOWN` | 3–6 hourly | N Indian Ocean | point attrs | 3–6 hourly | issue/forecast_time | hPa / m·s⁻¹ / deg | WGS84 | HAR/registration | `UNKNOWN` | to cyclone entity | range checks | None in-scope | IMD/RSMC policy observed | `UNKNOWN — requires verification (REG-A/HAR)` |
| cyclone (partial via CAP) | interim cyclone warning | IMD | CAP `cyclone` events (**if issued**) | `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` | RSS + CAP | Open | None | CAP 1.2 | event-driven | India polygons | polygon (no track) | event-driven | issued/expires | categorical | WGS84 | poll+fetch | lxml | to warning entity | signature | n/a | public domain | VERIFIED (partial — no track geometry); presence `UNKNOWN — requires verification (OBS-CAP)` |
| tsunami_warning | tsunami entity, safety-critical | INCOIS | TEWS bulletins | TEWS feed `UNKNOWN — requires verification (HAR-C)` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | XML/CAP/JSON `UNKNOWN` | event-driven | Indian Ocean rim | region geometry | event-driven | earthquake_time/issue | categorical | WGS84 | HAR then fetch | `UNKNOWN` | to tsunami entity; retain original provenance | signature/authenticity | None in-scope | INCOIS/TEWS policy observed | `UNKNOWN — requires verification (HAR-C)` |

### 3.6 Fisheries / ecosystem — raw parameters/entities

| 1 Parameter/Capability | 2 Required for | 3 Source | 4 Product/Dataset | 5 Exact URL | 6 Endpoint/API | 7 Access | 8 Auth | 9 Format | 10 Update Freq | 11 Coverage | 12 Spat.Res | 13 Temp.Res | 14 Timestamp Sem. | 15 Units | 16 CRS | 17 Retrieval | 18 Parser | 19 Normalization | 20 QC | 21 Fallback | 22 Licensing | 23 Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pfz_geometry (PFZ polygon) | nearest PFZ, suitability, fishing API | INCOIS | PFZ advisory service | `https://incois.gov.in/MarineFisheries/PfzAdvisory` (entry page, wire-verified) | machine geometry XHR/GeoJSON/WFS? `UNKNOWN` | Open (assumed — unverified) | `UNKNOWN — requires verification (HAR-A)` | GeoJSON/JSON/shapefile `UNKNOWN` | ~advisory days `UNKNOWN` | Indian coast sectors | polygon | daily/periodic | issue_time/valid_from/valid_until [Fn25] | — | WGS84 `UNKNOWN` | HAR then fetch | geopandas/shapely | to `pfz` entity | geometry+validity window | None in-scope | INCOIS policy observed | **`UNKNOWN — requires verification (HAR-A)` — P0 prerequisite** |
| pfz_validity | pfz_valid/pfz_age | INCOIS | PFZ advisory | `https://incois.gov.in/MarineFisheries/PfzAdvisory` | XHR `UNKNOWN` | Open (assumed) | `UNKNOWN — requires verification (HAR-A)` | JSON `UNKNOWN` | advisory days | Indian coast | polygon | daily | valid_from/valid_until | ISO-8601 | WGS84 | HAR then fetch | geopandas | validity window | window check | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-A)` |
| pfz_advisory_type (species/advisory) | advisory classification | INCOIS | PFZ advisory | `https://incois.gov.in/MarineFisheries/PfzAdvisory` | XHR `UNKNOWN` | Open (assumed) | `UNKNOWN — requires verification (HAR-A)` | JSON/text `UNKNOWN` | advisory days | Indian coast | polygon | daily | issued | categorical | WGS84 | HAR then fetch | geopandas | to `pfz.advisory_type` | enum check | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-A)` |
| fishery_advisory (Tuna) | suitability, advisories API | INCOIS | Ecosystem services (Tuna) | INCOIS ecosystem pages | machine feed `UNKNOWN` | `UNKNOWN — requires verification (HAR-A)` | `UNKNOWN` | JSON/GeoJSON `UNKNOWN` | periodic `UNKNOWN` | Indian coast | polygon | periodic | issued/valid_from/until | — | WGS84 | HAR then fetch | geopandas | to `fishery_advisory` | geometry validity | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-A)` |
| fishery_advisory (Hilsa) | suitability, advisories API | INCOIS | Ecosystem services (Hilsa) | INCOIS ecosystem pages | machine feed `UNKNOWN` | `UNKNOWN — requires verification (HAR-A)` | `UNKNOWN` | JSON/GeoJSON `UNKNOWN` | periodic | Indian coast | polygon | periodic | issued/valid | — | WGS84 | HAR then fetch | geopandas | to `fishery_advisory` | geometry validity | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-A)` |
| ecological_hazard (HAB / algal bloom) | ecological hazards, suitability | INCOIS | Ecosystem services (HAB) | INCOIS ecosystem pages | machine feed `UNKNOWN` | `UNKNOWN — requires verification (HAR-A)` | `UNKNOWN` | JSON/GeoJSON `UNKNOWN` | periodic | Indian coast | polygon | periodic | issued/valid | — | WGS84 | HAR then fetch | geopandas | to `ecological_hazard` | geometry validity | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-A)` |
| ecological_hazard (coral reef) | ecological hazards | INCOIS | Ecosystem services (Coral) | INCOIS ecosystem pages | machine feed `UNKNOWN` | `UNKNOWN — requires verification (HAR-A)` | `UNKNOWN` | JSON/GeoJSON `UNKNOWN` | periodic | Indian coast | polygon | periodic | issued/valid | — | WGS84 | HAR then fetch | geopandas | to `ecological_hazard` | geometry validity | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-A)` |
| ecological_hazard (jellyfish) | ecological hazards | INCOIS | Ecosystem services (Jellyfish) | INCOIS ecosystem pages | machine feed `UNKNOWN` | `UNKNOWN — requires verification (HAR-A)` | `UNKNOWN` | JSON/GeoJSON `UNKNOWN` | periodic | Indian coast | polygon | periodic | issued/valid | — | WGS84 | HAR then fetch | geopandas | to `ecological_hazard` | geometry validity | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (HAR-A)` |

### 3.7 In-situ observations — raw parameters/entities

| 1 Parameter/Capability | 2 Required for | 3 Source | 4 Product/Dataset | 5 Exact URL | 6 Endpoint/API | 7 Access | 8 Auth | 9 Format | 10 Update Freq | 11 Coverage | 12 Spat.Res | 13 Temp.Res | 14 Timestamp Sem. | 15 Units | 16 CRS | 17 Retrieval | 18 Parser | 19 Normalization | 20 QC | 21 Fallback | 22 Licensing | 23 Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| moored_buoy_observation | ground truth, ocean/weather cond. | IMD | Buoy obs page | `https://mausam.imd.gov.in/imd_latest/contents/buoy_obs.php?id=<stationId>` | HTTP GET (HTML page) | Open | None | **HTML/text** | ~hourly `UNKNOWN` (observe cadence) | Indian seas (points) | station | hourly `UNKNOWN` | observation_time | mixed (SI) | WGS84 (point) | GET + scrape | BeautifulSoup/regex [Fn26] | to `observation` entity | HTML brittle [Fn26] | INCOIS ARGO/buoy (ERDDAP) | IMD policy observed | VERIFIED PATTERN; cadence `UNKNOWN — requires verification (OBS-BUOY)` |
| coastal_station_observation | ground truth | IMD | Coastal station obs | `https://api.imd.gov.in` or coastal pages | REST/HTML `UNKNOWN` | Registration/Open `UNKNOWN` | `UNKNOWN — requires verification (REG-A)` | JSON/HTML | hourly `UNKNOWN` | Indian coast | point | hourly | observation_time | SI | WGS84 | REST/scrape | requests/bs4 | to `observation` | QC flags | INCOIS obs | IMD policy observed | `UNKNOWN — requires verification (REG-A)` |
| drifting_buoy_observation | ground truth | IMD/INCOIS | Marine obs | `UNKNOWN — requires verification (REG-A / HAR-B)` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | Indian seas | point | `UNKNOWN` | observation_time | SI | WGS84 | REG/HAR | `UNKNOWN` | to `observation` | QC flags | cross-provider (both in-scope) | policy observed | `UNKNOWN — requires verification (REG-A/HAR-B)` |
| ship_observation | ground truth | IMD | Ship obs (VOF) | `https://api.imd.gov.in` | REST `UNKNOWN` | Registration/token | Token [Fn15] | JSON `UNKNOWN` | as reported | Indian seas | point | irregular | observation_time | SI | WGS84 | REST | requests | to `observation` | QC flags | INCOIS obs | IMD policy observed | `UNKNOWN — requires verification (REG-A)` |
| tide_gauge_observation (in-situ family) | ground truth (water level) | INCOIS | RT tide-gauge network | ERDDAP tabledap OR portal XHR | tabledap/portal `UNKNOWN` | Open (assumed) | `UNKNOWN — requires verification (HAR-D)` | CSV/JSON/NetCDF | sub-hourly `UNKNOWN` | Indian coast | point | sub-hourly | observation_time | m | WGS84 | tabledap | pandas | datum per station | range checks | IMD coastal obs | INCOIS policy observed | `UNKNOWN — requires verification (HAR-D)` |
| argo_profile (T/S/current at depth) | subsurface, ground truth | INCOIS | ARGO datasets (`Indian_ARGO_Floats`,`incois_argo_*`) | `https://erddap.incois.gov.in/erddap/info/index.json` | ERDDAP tabledap | Open | None [Fn9] | NetCDF/CSV | 10-day/monthly | Indian Ocean | profile (z) | 10-day/monthly | observed_at | degC/PSU/(m/s) | WGS84 + depth | tabledap query | erddapy/pandas | to `observation` (profile) | ERDDAP QC flags kept [Fn27] | IMD buoy (surface only) | INCOIS policy observed [Fn10] | CATALOG VERIFIED; schema `UNKNOWN — requires verification (ERDDAP-INFO)` |
| wave_rider_observation | ground truth (waves) | INCOIS | Wave-rider buoys | `https://erddap.incois.gov.in/erddap/info/index.json` (confirm dataset) OR portal | tabledap `UNKNOWN` | Open (assumed) | `UNKNOWN — requires verification (ERDDAP-INFO/HAR-B)` | CSV/NetCDF | sub-hourly `UNKNOWN` | Indian coast | point | sub-hourly | observation_time | m/s | WGS84 | tabledap | pandas | to `observation` | QC flags | None in-scope | INCOIS policy observed | `UNKNOWN — requires verification (ERDDAP-INFO)` (dataset presence unconfirmed) |

### 3.8 Geospatial reference layers — raw parameters

| 1 Parameter/Capability | 2 Required for | 3 Source | 4 Product/Dataset | 5 Exact URL | 6 Endpoint/API | 7 Access | 8 Auth | 9 Format | 10 Update Freq | 11 Coverage | 12 Spat.Res | 13 Temp.Res | 14 Timestamp Sem. | 15 Units | 16 CRS | 17 Retrieval | 18 Parser | 19 Normalization | 20 QC | 21 Fallback | 22 Licensing | 23 Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EEZ / international maritime boundaries | geofence, routing | **None (IMD/INCOIS/MOSDAC do not supply)** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | None in-scope — gap (§15) | — | **GAP — do not fabricate** |
| restricted_zones | geofence, routing | **None** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | None in-scope — gap (§15) | — | **GAP — do not fabricate** |
| marine_protected_areas | geofence, routing | **None** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | None in-scope — gap (§15) | — | **GAP — do not fabricate** |
| ecologically_sensitive_zones | geofence, routing | **None** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | None in-scope — gap (§15) | — | **GAP — do not fabricate** |
| operational/geofence boundaries | geofence | Platform-defined (operator config) | operator config | n/a | Platform | Config | n/a | GeoJSON | on change | operator-defined | polygon | n/a | effective_from/until | — | WGS84 | config load | geopandas | to `zone` | topology valid | n/a | operator-owned | READY (operator-provided) |
| ports / harbours | context, routing | **None (not established in-scope)** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | None in-scope — gap (§15) | — | **GAP — do not fabricate** |
| shipping_lanes | routing | **None** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | None in-scope — gap (§15) | — | **GAP — do not fabricate** |
| bathymetry / depth | depth-aware routing, shallow-water | **None (IMD/INCOIS/MOSDAC do not supply)** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | None in-scope — gap (§15) | — | **GAP — do not infer depth** |

### 3.9 Derived capabilities (Level 3–4) — every capability a distinct row

All derived rows carry `Source = Platform (derived)`, `Access = Computed`, `Auth = n/a`, `CRS = WGS84`. Columns retained for uniformity; `Product/Dataset` = the deterministic method; `Fallback` = degraded method; `Status` = readiness gated by weakest input. No derived capability is aggregated away.

| 1 Parameter/Capability | 2 Required for | 3 Source | 4 Product/Dataset (method) | 5 Exact URL | 6 Endpoint/API | 7 Access | 8 Auth | 9 Format | 10 Update Freq | 11 Coverage | 12 Spat.Res | 13 Temp.Res | 14 Timestamp Sem. | 15 Units | 16 CRS | 17 Retrieval | 18 Parser | 19 Normalization | 20 QC | 21 Fallback | 22 Licensing | 23 Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| distance_to_feature | geofence/PFZ/hazard | Platform (derived) | PostGIS `ST_Distance` geography | n/a | Platform | Computed | n/a | float | per request | n/a | n/a | n/a | inherits input | km | WGS84 | PostGIS | Shapely | geodesic | consistency | n/a | inherits | READY (needs feature data) |
| inside_feature | geofence/restriction | Platform (derived) | PostGIS `ST_Contains`/`ST_Within` | n/a | Platform | Computed | n/a | bool | per request | n/a | n/a | n/a | inherits | — | WGS84 | PostGIS | Shapely | topology | valid | n/a | inherits | READY (needs zone data §15) |
| intersection_geometry | route/zone overlap | Platform (derived) | PostGIS `ST_Intersection` | n/a | Platform | Computed | n/a | GeoJSON | per request | n/a | n/a | n/a | inherits | — | WGS84 | PostGIS | Shapely | topology | valid | n/a | inherits | READY (needs zone data §15) |
| nearest_pfz / distance_to_pfz / pfz_area / pfz_age / pfz_valid | fishing API, suitability | Platform (derived) | PostGIS nearest + geodesic + validity window | n/a | Platform | Computed | n/a | mixed | per request | Indian coast | n/a | n/a | valid_from/until vs query | km/—/bool | WGS84 | PostGIS | geopandas | validity check [Fn25] | window/topology | n/a | inherits PFZ | **BLOCKED on HAR-A** |
| nearest_buoy_station + distance | ground-truth pairing | Platform (derived) | PostGIS nearest | n/a | Platform | Computed | n/a | mixed | per request | Indian seas | n/a | n/a | inherits | km | WGS84 | PostGIS | geopandas | geodesic | consistency | n/a | inherits | READY (once buoy/ARGO ingested) |
| distance_to_hazard | hazard proximity | Platform (derived) | PostGIS distance to hazard polygon | n/a | Platform | Computed | n/a | float | per request | India | n/a | n/a | inherits | km | WGS84 | PostGIS | Shapely | geodesic | consistency | CAP polygons ready | inherits | READY for CAP hazards |
| distance_to_boundary | boundary proximity | Platform (derived) | PostGIS distance to boundary | n/a | Platform | Computed | n/a | float | per request | n/a | n/a | n/a | inherits | km | WGS84 | PostGIS | Shapely | geodesic | consistency | none | n/a | **BLOCKED — boundary data GAP (§15)** |
| point_in_restricted_zone | geofence | Platform (derived) | PostGIS `ST_Contains` | n/a | Platform | Computed | n/a | bool | per request | n/a | n/a | n/a | inherits | — | WGS84 | PostGIS | Shapely | topology | valid | operator zones only | n/a | PARTIAL (operator zones only) |
| route/zone_intersection | routing safety | Platform (derived) | PostGIS `ST_Intersection` | n/a | Platform | Computed | n/a | GeoJSON | per request | n/a | n/a | n/a | inherits | — | WGS84 | PostGIS | Shapely | topology | valid | operator zones only | n/a | PARTIAL (operator zones only) |
| hazard_coverage_around_location | area alerting | Platform (derived) | PostGIS buffer∩polygon | n/a | Platform | Computed | n/a | GeoJSON | per request | India | n/a | n/a | inherits | — | WGS84 | PostGIS | Shapely | topology | valid | CAP ready | n/a | READY for CAP |
| forecast_horizon | forecast context | Platform (derived) | valid_time − issued_at | n/a | Platform | Computed | n/a | duration | per request | n/a | n/a | n/a | uses issued/valid | h | n/a | compute | Python | time arithmetic | consistency | n/a | inherits | READY once forecast source verified |
| forecast_freshness | freshness | Platform (derived) | now − retrieved_at vs expected interval (§12) | n/a | Platform | Computed | n/a | class | per request | n/a | n/a | n/a | uses retrieved_at | class | n/a | compute | Python | freshness fn [§12] | consistency | n/a | inherits | READY once forecast source verified |
| time_to_high_tide / time_to_low_tide / tide_state / rising_or_falling | tide windows | Platform (derived) | extrema/zero-crossing of tide **prediction** series | n/a | Platform | Computed | n/a | mixed | per request | Indian coast | n/a | n/a | prediction valid_time | h/enum | WGS84 | compute | Python | requires prediction [Fn24] | monotonic | none | n/a | **BLOCKED on HAR-D (prediction may not exist)** |
| changing_conditions / rate_of_change | trend | Platform (derived) | finite difference over consecutive obs/fcst | n/a | Platform | Computed | n/a | float | per request | inherits | n/a | n/a | inherits | per var/h | WGS84 | compute | NumPy | difference | consistency | n/a | inherits | READY once source verified |
| safe_operating_window | safety planning | Platform (derived) | scan interval; classify per configurable per-vessel thresholds | n/a | Platform | Computed | n/a | windows[] | per request | point/region | n/a | interval | scans valid_time range | class | WGS84 | compute | Python | scans whole interval (not first ts) | consistency | CAP-only interim | n/a | PARTIAL (CAP-only until env verified HAR-B/REG-A) |
| alert_expiration | alert lifecycle | Platform (derived) | compare CAP `expires` vs now | n/a | Platform | Computed | n/a | bool/ts | per request | India | n/a | n/a | uses expires | ts | WGS84 | compute | Python | to UTC | consistency | n/a | CAP | READY |
| sst_anomaly / sst_percentile / sst_gradient / sst_change | anomaly detection | Platform (derived) | current − retained seasonal baseline; percentile vs history | n/a | Platform | Computed | n/a | float | per request | grid | source res | source res | current vs baseline | degC | WGS84 | compute | xarray/NumPy | baseline from retained history | range | n/a | SST source | **BLOCKED until baseline accumulated** |
| chlorophyll_anomaly / chlorophyll_percentile / chlorophyll_gradient | anomaly, productivity | Platform (derived) | current − baseline | n/a | Platform | Computed | n/a | float | per request | grid | source res | source res | current vs baseline | mg/m³ | WGS84 | compute | xarray/NumPy | baseline required | range | n/a | CHL source | **BLOCKED until baseline** |
| current_anomaly | anomaly | Platform (derived) | current − baseline | n/a | Platform | Computed | n/a | float | per request | grid | source res | source res | current vs baseline | m/s | WGS84 | compute | xarray | baseline required | range | n/a | inherits | **BLOCKED (HAR-B + baseline)** |
| wave_anomaly | anomaly | Platform (derived) | current − baseline | n/a | Platform | Computed | n/a | float | per request | grid | source res | source res | current vs baseline | m | WGS84 | compute | xarray | baseline required | range | n/a | inherits | **BLOCKED (HAR-B + baseline)** |
| rainfall_anomaly | anomaly | Platform (derived) | current − baseline | n/a | Platform | Computed | n/a | float | per request | grid | source res | source res | current vs baseline | mm | WGS84 | compute | xarray | baseline required | range | n/a | inherits | **BLOCKED (REG-A/alt + baseline)** |
| pressure_anomaly / pressure_gradient / pressure_change_rate | storm ID | Platform (derived) | current − baseline; spatial/temporal gradient | n/a | Platform | Computed | n/a | float | per request | grid | source res | source res | current vs baseline | hPa | WGS84 | compute | xarray | baseline required | range | n/a | inherits | **BLOCKED (REG-A + baseline)** |
| climatological_percentile / change_over_day_week_month | anomaly context | Platform (derived) | percentile & delta vs retained history | n/a | Platform | Computed | n/a | float | per request | grid | source res | source res | vs history | mixed | WGS84 | compute | xarray | history required | range | n/a | inherits | **BLOCKED until history** |
| current_speed / current_direction | ocean cond., routing | Platform (derived) | √(u²+v²); dir from u/v when convention known [Fn12] | n/a | Platform | Computed | n/a | float | per request | grid | source res | source res | valid_time | m/s / deg | WGS84 | compute | NumPy | dir convention per source [Fn12] | consistency | n/a | inherits u/v | **BLOCKED (HAR-B)** |
| combined_sea_state | sea state | Platform (derived) | configurable combination of Hs/Tp/swell (no universal risk from Hs alone) | n/a | Platform | Computed | n/a | class | per request | grid | source res | source res | valid_time | class | WGS84 | compute | Python | configurable | consistency | n/a | inherits waves | **BLOCKED (HAR-B)** |
| wave_risk / swell_risk / wind_risk | safety | Platform (derived) | configurable per-vessel thresholds | n/a | Platform | Computed | n/a | class | per request | grid/point | source res | source res | valid_time | class | WGS84 | compute | Python | per-vessel config | consistency | n/a | inherits | **BLOCKED (HAR-B/REG-A)** |
| storm_proximity / hazard_proximity | safety | Platform (derived) | geodesic distance to feature/track | n/a | Platform | Computed | n/a | float | per request | India | n/a | n/a | inherits | km | WGS84 | PostGIS | Shapely | geodesic | consistency | CAP polygons | n/a | PARTIAL (CAP polygons; cyclone track unverified) |
| distance_to_cyclone / distance_to_forecast_track / track_intersection / estimated_arrival_time / cyclone_proximity_risk | cyclone safety | Platform (derived) | geodesic to center/track; kinematics | n/a | Platform | Computed | n/a | mixed | per request | N Indian Ocean | n/a | n/a | issue/forecast_time | km/h/class | WGS84 | PostGIS | Shapely | geodesic | consistency | CAP partial | n/a | **BLOCKED (cyclone structured feed REG-A/HAR)** |
| distance_to_source / tsunami ETA / tsunami_risk | tsunami safety | Platform (derived) | geodesic + kinematics from TEWS | n/a | Platform | Computed | n/a | mixed | per request | Indian Ocean rim | n/a | n/a | earthquake/issue | km/h/class | WGS84 | compute | Python | retain provenance | consistency | none | n/a | **BLOCKED (HAR-C)** |
| distance_to_lightning / lightning_risk / lightning_alert_active | lightning proximity | Platform (derived) | point-in / distance to CAP polygon | n/a | Platform | Computed | n/a | mixed | per request | India | n/a | n/a | issued/expires | km/class/bool | WGS84 | PostGIS | Shapely | geodesic | consistency | CAP ready | n/a | READY for CAP (presence OBS-CAP) |
| fishing_suitability_score | fishing API | Platform (derived) | configurable weighted f(SST,CHL,anomalies,currents,waves,wind,PFZ,advisories,hazards); expose drivers | n/a | Platform | Computed | n/a | score+drivers | per request | region/grid | source res | source res | inherits | score | WGS84 | compute | Python | no casual weights (§7 rule) | consistency | n/a | inherits | **BLOCKED (HAR-A + env + baselines)** |
| fishing_zone_ranking | fishing API | Platform (derived) | ranking function on CHL(+anomaly),SST | n/a | Platform | Computed | n/a | ranking | per request | region | source res | source res | inherits | rank | WGS84 | compute | Python | configurable | consistency | n/a | inherits | PARTIAL (baseline required) |
| productivity_indicator | fishing API | Platform (derived) | CHL-based indicator (no catch attribution) | n/a | Platform | Computed | n/a | index | per request | region | source res | source res | inherits | index | WGS84 | compute | Python | no productivity-decline claim (§15) | consistency | n/a | inherits | PARTIAL (env only; catch data GAP §15) |
| pfz_distance / pfz_ranking | fishing API | Platform (derived) | PostGIS distance + rank | n/a | Platform | Computed | n/a | mixed | per request | Indian coast | n/a | n/a | inherits | km/rank | WGS84 | PostGIS | geopandas | validity check | consistency | n/a | inherits PFZ | **BLOCKED (HAR-A)** |
| favourable_SST_plus_CHL_regions | fishing API | Platform (derived) | threshold intersection of SST & CHL | n/a | Platform | Computed | n/a | GeoJSON | per request | region | source res | source res | inherits | — | WGS84 | compute | xarray | configurable thresholds | consistency | n/a | inherits | READY once SST+CHL ingested |
| marine_risk_score / risk_level / risk_factors | risk API | Platform (derived) | configurable per-vessel weighted engine; expose factors, validity, sources | n/a | Platform | Computed | n/a | score+factors | per request | point/region | n/a | interval | valid_from/until | score/class | WGS84 | compute | Python | per-vessel config (§10 req) | consistency | CAP-driven interim | n/a | PARTIAL (warnings-driven until env verified) |
| hazard_score | risk API | Platform (derived) | aggregate hazard distances/severities | n/a | Platform | Computed | n/a | score | per request | point | n/a | n/a | inherits | score | WGS84 | compute | Python | configurable | consistency | CAP | n/a | PARTIAL (CAP) |
| geofence_status / restricted_zone_warning / boundary_proximity_warning | safety | Platform (derived) | PostGIS predicates | n/a | Platform | Computed | n/a | mixed | per request | n/a | n/a | n/a | inherits | class/km | WGS84 | PostGIS | Shapely | topology | valid | operator zones only | n/a | **BLOCKED (boundary GAP §15) except operator zones** |
| route_distance | routing | Platform (derived) | geodesic path length | n/a | Platform | Computed | n/a | float | per request | n/a | n/a | n/a | departure_time | km | WGS84 | pyproj/PostGIS | Shapely | geodesic | consistency | n/a | n/a | READY (distance only) |
| expected_travel_time | routing | Platform (derived) | distance / vessel_speed ± current adjustment | n/a | Platform | Computed | n/a | duration | per request | n/a | n/a | n/a | departure_time | h | WGS84 | compute | Python | current adj if available | consistency | n/a | inherits currents | PARTIAL (current penalty BLOCKED HAR-B) |
| segment_risk / weather_penalty / wave_penalty / current_penalty / hazard_penalty / geofence_penalty | routing cost | Platform (derived) | configurable cost graph per segment | n/a | Platform | Computed | n/a | cost | per request | route | n/a | segment | departure→valid | cost | WGS84 | compute | Python | configurable weights | consistency | n/a | inherits env/zones | **BLOCKED (env HAR-B + zones §15)** |
| route_risk_score / safest_candidate_route | routing API | Platform (derived) | deterministic cost optimization (no AI) | n/a | Platform | Computed | n/a | route+score | per request | route | n/a | segment | departure→valid | score | WGS84 | compute | Python/graph | deterministic (§17 req) | consistency | n/a | inherits | **BLOCKED until inputs verified** |
| fisheries_productivity_decline_attribution | fisheries analysis | Platform (derived) | correlation of env features vs catch history | n/a | Platform | Computed | n/a | analysis | per request | region | n/a | n/a | historical | — | WGS84 | compute | pandas | **no attribution claim without catch data** | n/a | none | n/a | **GAP — no in-scope catch/effort dataset (§15)** |

### 3.10 Detail footnotes for matrix cells

- **[Fn1]** Longitude normalization: if source uses 0..360, `lon' = ((lon + 180) mod 360) − 180`. Applied before storage; original retained in raw metadata.
- **[Fn2]** Timestamp normalization: parse to timezone-aware UTC; keep observed_at/issued_at/valid_from/valid_until/forecast_time/retrieved_at/processed_at separate (never conflate). See §8.
- **[Fn3]** MOSDAC download auth: token obtained via `POST /download_api/gettoken`, used on the download call; honor refresh/logout and HTTP 429 `minute_limit`/`daily_limit`. Exact request/response bodies are documented in §6.2.1 and remain **not exercised** (AUTH-A).
- **[Fn4]** MOSDAC SST files are HDF5 (`.h5`, e.g. `3RIMG_03SEP2026_1615_L2B_SST_V02R00.h5`). Read with `h5py`/`xarray` (engine `h5netcdf`); geolocation may require SAC-specific lat/lon datasets — confirm on first file.
- **[Fn5]** Regrid to a configurable common grid only for query/visualization layers; preserve native-resolution asset. Use pyresample/xarray; record processing_version.
- **[Fn6]** Apply CF `scale_factor`/`add_offset`; mask `_FillValue`/`missing_value`; do not silently drop — set QC flag. See §10/§11.
- **[Fn7]** SST unit: if stored in Kelvin, `degC = K − 273.15`; confirm from file attributes, do not assume.
- **[Fn8]** In-scope SST fallback chain: MOSDAC INSAT SST ↔ INCOIS AVHRR/AMSR & ARGO weekly SST. Both in-scope; select by freshness/coverage (§13 conflict policy).
- **[Fn9]** INCOIS ERDDAP TLS: server sends leaf only; supply GlobalSign RSA OV SSL CA 2018 intermediate in the connector trust store. Never use insecure/`-k` in production.
- **[Fn10]** INCOIS bulk data may be chargeable; check the published pricing/data-policy at access time. Policy observed only; no legal interpretation.
- **[Fn11]** MOSDAC ocean-colour chlorophyll (OceanSat OCM) is a candidate in-scope chlorophyll fallback to INCOIS IRS chlorophyll; confirm exact datasetId via search API.
- **[Fn12]** Direction convention: current uses oceanographic (toward) vs meteorological wind (from). **If the source convention is unclear, store the raw value and mark convention `UNKNOWN`; do not convert.** Compute `speed=√(u²+v²)`; direction from u/v only when convention is known. Wind knots→m/s ×0.514444 only after confirming source unit.
- **[Fn13]** MOSDAC ocean-current open-data NetCDF is the in-scope alternate to INCOIS OSF currents.
- **[Fn14]** MOSDAC subsurface NetCDF open-data is the in-scope alternate to INCOIS ARGO subsurface.
- **[Fn15]** IMD `api.imd.gov.in` requires registration/token; legacy `/api` returned 401/403. Auth flow + marine endpoint list `UNKNOWN — requires verification (REG-A)`.
- **[Fn16]** IMD NWP in GRIB2 → decode with `cfgrib`/`ecCodes`; REST JSON → `requests`+Pydantic.
- **[Fn17]** INCOIS scatterometer wind (ASCAT/QuikSCAT/OceanSat) is the in-scope observational alternate to IMD wind.
- **[Fn18]** MOSDAC INSAT rainfall is the in-scope satellite alternate to IMD rainfall guidance.
- **[Fn19]** INCOIS TMI 3-day product (`incois_tmi_3day_datasets`) is a candidate rainfall-related in-scope alternate; confirm variable set via ERDDAP info.
- **[Fn20]** CAP timestamps: `sent` (issued_at), `effective`/`onset` (effective_from), `expires` (expires_at). All parsed to UTC.
- **[Fn21]** RSS parsed with `feedparser`; CAP XML with `lxml` under `urn:oasis:names:tc:emergency:cap:1.2`.
- **[Fn22]** CAP polygon is **space-separated `lat,lon` pairs** (verified V2). Convert to GeoJSON `[lon,lat]` order (swap!) and close ring. Store both raw polygon string and GeoJSON. Enum-normalize severity/urgency/certainty/msgType/status.
- **[Fn23]** CAP documents carry `ds:Signature` (`xmldsig#`, verified V2). Verify signature (XML-DSig) against IMD/alert-hub key before trusting for safety-critical alerts; record verification result in provenance. Key retrieval procedure `UNKNOWN — requires verification (SIG-A)`.
- **[Fn24]** Tide-state derivation (rising/falling, time_to_high/low) requires a **prediction** series, not just observations. If only observations exist, mark prediction-derived fields unavailable (§15 gap / HAR-D).
- **[Fn25]** PFZ validity window is essential; `pfz_valid`/`pfz_age` derived from valid_from/valid_until vs query time.
- **[Fn26]** IMD buoy page is HTML/text; use resilient parsing (BeautifulSoup + labeled-field regex), snapshot raw HTML immutably, add a layout-change canary test. Numeric extraction is best-effort until a machine endpoint (REG-A) is confirmed.
- **[Fn27]** ERDDAP datasets expose QC/flag variables where present; retain as `quality_flag`. These are source/platform QC, propagated but re-validated by our pipeline.
- **[Fn28]** MOSDAC open-data **page metadata** (see §6.3): ocean current 0.25° daily global; HRSSS 10 km Bay of Bengal, six-month publication cadence, with a historical range; eddies weekly Bay of Bengal; subsurface 25 km horizontal / 10 m vertical Bay of Bengal. **Page-metadata verification only** — authenticated file retrieval is `UNKNOWN — requires verification (AUTH-A)`.

---

## 4. IMD

India Meteorological Department. One fully verified machine-readable interface (CAP), one verified-pattern
HTML interface (buoy), and several registration/blocked interfaces. HTTP contracts below are given for
**every verified interface**; unverified interfaces state the contract fields as `UNKNOWN — requires verification (ACTION-ID)`.

### 4.1 Marine Observations

**Buoy observations (VERIFIED PATTERN, HTML/text).**

HTTP contract:
- **Method:** `GET`
- **URL:** `https://mausam.imd.gov.in/imd_latest/contents/buoy_obs.php?id=<stationId>`
- **Params:** `id` = IMD buoy station identifier (enumeration procedure `UNKNOWN — requires verification (OBS-BUOY)`; scrape from IMD marine/coastal index pages).
- **Headers:** standard browser `User-Agent` advisable; no auth header.
- **Cookies:** none required (confirm none set on first fetch).
- **Auth:** none.
- **Request body:** none (GET).
- **Content type (response):** `text/html`.
- **Sample schema:** HTML page with a labeled table of observation fields (time, wind, pressure, temperature, wave where present). No JSON/structured payload — extraction is label/regex based.
- **Pagination:** none (single station page).
- **Rate limits:** not published; apply polite backoff + jitter; do not storm the host.
- **Failure behavior:** invalid/absent `id` returns an HTML error/empty page (not a structured error); connector must detect empty/canary-failed layout and flag, not silently parse garbage.

Limitations: brittle HTML; snapshot raw HTML immutably; add a canary test on layout; best-effort numeric extraction until a machine endpoint (REG-A) is confirmed [Fn26].

**Coastal / ship / drifting-buoy observations:** exposed (if at all) via `https://api.imd.gov.in` (token) — `UNKNOWN — requires verification (REG-A)`. Contract fields (method/params/headers/auth/body/content-type/schema/pagination/rate-limits/failure) are all `UNKNOWN — requires verification (REG-A)`.

### 4.2 Marine Forecast

IMD marine/coastal forecast **public web pages render PNG/PDF** → **VISUAL-ONLY (§14)**; not a numeric source.
Numeric marine forecast (if available) is behind `https://api.imd.gov.in` (token) or GRIB2 via DSP — `UNKNOWN — requires verification (REG-A)`. All HTTP-contract fields `UNKNOWN — requires verification (REG-A)`.

### 4.3 NWP

Numerical Weather Prediction products (wind/rain/pressure/humidity grids).
- Public NWP chart pages are **PNG/PDF → VISUAL-ONLY (§14)**.
- Numeric GRIB2 requires registered/authenticated access (DSP/API). HTTP contract `UNKNOWN — requires verification (REG-A)`; decode path once available: GRIB2 → `cfgrib`/`ecCodes` [Fn16].
- Do not infer numeric NWP values from rendered charts (prompt §27 rule).

### 4.4 Warnings / CAP

**IMD CAP alerts — the only fully verified, public-domain, machine-readable, signed safety feed.**

HTTP contract — RSS index:
- **Method:** `GET`
- **URL:** `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml`
- **Params:** none.
- **Headers:** none required (public S3). `Accept: application/xml` advisable.
- **Cookies:** none.
- **Auth:** none.
- **Request body:** none.
- **Content type (response):** `text/xml` (verified V1, 6915 B).
- **Sample schema (RSS 2.0):** `<rss><channel>` with `<title>`, `<lastBuildDate>` (drives refetch), `<copyright>public domain</copyright>`, repeated `<item>` each linking a dated CAP XML (e.g. `.../2026-09-03-07-21-21.xml`).
- **Pagination:** none — single rolling index; dedupe items by CAP `identifier`.
- **Rate limits:** none published; poll ~60 s with backoff+jitter; use `lastBuildDate`/ETag to avoid needless refetch.
- **Failure behavior:** S3 returns standard HTTP errors; on non-200 keep last good state and mark freshness (§12).

HTTP contract — CAP item:
- **Method:** `GET`
- **URL:** dated item URL from RSS, e.g. `https://cap-sources.s3.amazonaws.com/in-imd-en/2026-09-03-07-21-21.xml`
- **Params/Headers/Cookies/Auth/Body:** none / none / none / none / none.
- **Content type (response):** `application/xml` (verified V2, 4413 B).
- **Sample schema (CAP 1.2, namespace `urn:oasis:names:tc:emergency:cap:1.2`):** `identifier, sender, sent, status, msgType, scope, info{category, event, urgency, severity, certainty, effective/onset, expires, senderName, headline, description, area{areaDesc, polygon}}`, plus a `ds:Signature` (`xmldsig#`). Verified example: `event=Extremely heavy`, `areaDesc=ODISHA`; polygon = space-separated `lat,lon` pairs, first ring closed (`25.1254,80.2881 … 25.1254,80.2881`).
- **Pagination:** none.
- **Rate limits:** none published; fetch each new item once.
- **Failure behavior:** malformed/unsigned/expired documents must be flagged (do not drop expired — keep with status); verify `ds:Signature` before trusting for safety-critical use [Fn23].

**Event coverage caveat (required correction):** CAP 1.2 *can* encode cyclone/high_wave/strong_wind/heavy_rain/thunderstorm/lightning/storm_surge/tsunami/marine_hazard, but **the events actually available are only those IMD actually issues into this feed**. Do **not** claim a family is present merely because CAP can represent it. Measure real coverage by observing the feed over time → `UNKNOWN — requires verification (OBS-CAP)`.

### 4.5 Radar / GIS

IMD radar imagery pages are **image tiles → VISUAL-ONLY (§14)**. Any GIS/WMS numeric service is unverified;
all HTTP-contract fields `UNKNOWN — requires verification (HAR-E)`. Do not treat radar images as numeric precipitation data.

---

## 5. INCOIS

Indian National Centre for Ocean Information Services (MoES). One verified machine-readable interface
(ERDDAP **catalog**), plus PFZ/OSF/hazard/tide interfaces that are page-reachable but whose machine
endpoints/schemas are unverified. **Catalog presence is verified; per-dataset data/schema is not** — kept distinct throughout.

### 5.0 ERDDAP catalog — verified HTTP contract and the 16 dataset IDs

HTTP contract — ERDDAP catalog:
- **Method:** `GET`
- **URL:** `https://erddap.incois.gov.in/erddap/info/index.json?page=1&itemsPerPage=1000`
- **Params:** `page`, `itemsPerPage` (pagination); endpoint redirects to the paginated form.
- **Headers:** `Accept: application/json`. **TLS:** server sends leaf cert only (`CN=*.incois.gov.in`, issuer `GlobalSign RSA OV SSL CA 2018`); `openssl` reports code 21 (missing intermediate). Connector must **bundle the GlobalSign intermediate**; never disable verification [Fn9].
- **Cookies:** none required.
- **Auth:** none.
- **Request body:** none.
- **Content type (response):** `application/json;charset=UTF-8` (verified V3, 22076 B).
- **Sample schema:** ERDDAP `{"table":{"columnNames":[...],"rows":[...]}}` enumerating datasets with title/protocol columns.
- **Pagination:** `page` + `itemsPerPage`.
- **Rate limits:** not published; polite backoff.
- **Failure behavior:** standard HTTP; TLS chain failure if intermediate not bundled — do not fall back to insecure.

**Verified-present dataset IDs (exactly 16, catalog presence only — per-dataset schema `UNKNOWN — requires verification (ERDDAP-INFO)`):**

1. `AMSRE_MONTHLY_GLOBAL`
2. `ascat_daily_datasets`
3. `ascat_mnt_datasets`
4. `incois_argo_10day_McCreary`
5. `incois_argo_10d_VAM`
6. `incois_argo_mnt_McCreary`
7. `incois_argo_mnt_VAM`
8. `incois_argo_sst_weekly`
9. `incois_oceansat2_datasets`
10. `incois_quickscat_daily_datasets`
11. `incois_quickscat_mnt_datasets`
12. `incois_tmi_3day_datasets`
13. `incois_valueadded_products_datasets`
14. `Indian_ARGO_Floats`
15. `IRS_chlorophyll_datasets`
16. `NOAA_AVHRR_AMSR_datasets`

**ERDDAP query examples — labeled tested vs template:**

- **TESTED (this session):** `GET https://erddap.incois.gov.in/erddap/info/index.json?page=1&itemsPerPage=1000` → HTTP 200, JSON, dataset IDs enumerated (V3).
- **TEMPLATE (not yet executed — ERDDAP-INFO):** per-dataset metadata: `GET https://erddap.incois.gov.in/erddap/info/<datasetId>/index.json`
- **TEMPLATE (griddap subset, not executed):** `GET https://erddap.incois.gov.in/erddap/griddap/<datasetId>.nc?<var>[(time_start):(time_end)][(lat_min):(lat_max)][(lon_min):(lon_max)]`
- **TEMPLATE (tabledap subset, not executed):** `GET https://erddap.incois.gov.in/erddap/tabledap/<datasetId>.csv?<vars>&time>=<start>&time<=<end>&latitude>=<a>&latitude<=<b>&longitude>=<c>&longitude<=<d>`
- **TEMPLATE (WMS, not executed):** ERDDAP `griddap` WMS `.../griddap/<datasetId>/request?SERVICE=WMS&...`

> Reminder: ERDDAP provides **griddap/tabledap/WMS**, **not WFS**. Variable names, units, axes, coverage, and resolution for each dataset are **`UNKNOWN — requires verification (ERDDAP-INFO)`** until each `info/<id>/index.json` is fetched.

### 5.1 PFZ

Potential Fishing Zone advisory.
- **Entry page (wire-verified URL):** `https://incois.gov.in/MarineFisheries/PfzAdvisory` — use this exact URL. Do **not** retain guessed portal paths (e.g. `portal/osf/pfz.jsp`) that returned 404 / were never confirmed as entry pages.
- **Machine geometry endpoint:** `UNKNOWN — requires verification (HAR-A)`. HTTP contract (method/params/headers/cookies/auth/body/content-type/schema/pagination/rate-limits/failure) all `UNKNOWN — requires verification (HAR-A)`: capture the XHR/Fetch returning GeoJSON/JSON/WFS/NetCDF from the advisory page via DevTools → Network → export HAR; confirm exact geometry endpoint + response schema.
- Target entity: `pfz` (geometry, issue_time, valid_from/until, region, advisory_text, species/advisory_type, sst_context, chlorophyll_context, confidence, source_url).
- **P0 prerequisite:** PFZ cannot be advertised P0-ready until HAR-A confirms exact machine geometry (§18).

### 5.2 OSF

Ocean State Forecast (surface currents, waves, swell, wind-wave).
- Machine dataset/endpoint `UNKNOWN — requires verification (HAR-B)`: open the OSF page, capture the XHR/dataset URL serving current/wave/swell grids; confirm whether it is ERDDAP griddap or a separate service.
- HTTP contract fields all `UNKNOWN — requires verification (HAR-B)`.
- Provides on verification: current_u/v, Hs, Tp, wave_dir, swell_height/period/dir, wind_wave_height/period.

### 5.3 Tide

- **Tide-gauge observations:** RT tide-gauge network — endpoint `UNKNOWN — requires verification (HAR-D)` (ERDDAP tabledap vs portal XHR). Contract fields `UNKNOWN — requires verification (HAR-D)`.
- **Tide prediction (future high/low):** a tide-gauge **observation is not a future prediction** (requirements §7.1). Whether INCOIS exposes a machine **prediction** feed is `UNKNOWN — requires verification (HAR-D)` and **may not exist as a feed**. Until confirmed, `time_to_high_tide`/`time_to_low_tide`/`tide_state` are **unavailable** (mark, do not fabricate).

### 5.4 High Wave / Swell

- INCOIS High-Wave Alert (HWA) / swell alert service — machine JSON `UNKNOWN — requires verification (HAR-C)`.
- HTTP contract fields all `UNKNOWN — requires verification (HAR-C)`.
- Normalize to `warning` entity (severity, geometry, valid_from/until).

### 5.5 Cyclone / Storm Surge

- INCOIS storm-surge / sea-level-surge service — endpoint/schema `UNKNOWN — requires verification (HAR-C)`.
- Cyclone structured entity: authoritative structured track/cone from IMD/RSMC (§4.4/§3.5) is unverified; INCOIS cyclone/surge machine feed also `UNKNOWN — requires verification (HAR-C)`.
- HTTP contract fields all `UNKNOWN — requires verification (HAR-C)`.

### 5.6 Tsunami

- INCOIS TEWS (Tsunami Early Warning System) bulletins — the authoritative in-scope tsunami source.
- Feed URL/schema `UNKNOWN — requires verification (HAR-C)`. HTTP contract fields all `UNKNOWN — requires verification (HAR-C)`.
- Safety-critical: retain original advisory provenance verbatim; verify authenticity/signature where present.

### 5.7 Buoys / In-Situ

- **ARGO profiles** (`Indian_ARGO_Floats`, `incois_argo_10day_McCreary`, `incois_argo_10d_VAM`, `incois_argo_mnt_McCreary`, `incois_argo_mnt_VAM`, `incois_argo_sst_weekly`): via ERDDAP **tabledap** (catalog verified; per-dataset schema `UNKNOWN — requires verification (ERDDAP-INFO)`). Retain ERDDAP QC flags [Fn27].
- **Wave-rider buoys:** dataset presence in ERDDAP `UNKNOWN — requires verification (ERDDAP-INFO)`; may be portal-only (`UNKNOWN — requires verification (HAR-B)`).
- **Moored/drifting buoy** cross-provider with IMD buoy (§4.1).
- HTTP contract for ARGO retrieval follows the ERDDAP tabledap template (§5.0); **not executed** for any specific ARGO dataset yet.

### 5.8 Remote Sensing

INCOIS remote-sensing holdings surfaced through ERDDAP (catalog verified):
- **SST:** `NOAA_AVHRR_AMSR_datasets`, `incois_argo_sst_weekly`, `AMSRE_MONTHLY_GLOBAL`.
- **Chlorophyll:** `IRS_chlorophyll_datasets`.
- **Scatterometer wind:** `ascat_daily_datasets`, `ascat_mnt_datasets`, `incois_quickscat_daily_datasets`, `incois_quickscat_mnt_datasets`, `incois_oceansat2_datasets`.
- **Rainfall-related:** `incois_tmi_3day_datasets`.
- **Value-added (sea level etc.):** `incois_valueadded_products_datasets`.
- Access via ERDDAP griddap/tabledap (§5.0). **Per-dataset variables/units/axes/resolution `UNKNOWN — requires verification (ERDDAP-INFO)`.**

### 5.9 LAS / ERDDAP / ESSDP

- **ERDDAP:** verified machine-readable catalog (§5.0); the P0 numeric-data connector candidate.
- **LAS (Live Access Server):** separate INCOIS visualization/analysis UI; underlying per-product data protocol `UNKNOWN — requires verification (HAR-F)`. Do not assume LAS exposes the same datasets as ERDDAP.
- **ESSDP (Earth System Science Data Portal):** presence noted; machine endpoints/schema `UNKNOWN — requires verification (HAR-F)`. Rendered map views are **VISUAL-ONLY (§14)** until an XHR/data endpoint is captured.

---

## 6. MOSDAC

Meteorological & Oceanographic Satellite Data Archival Centre (SAC/ISRO). Discovery/search is verified
open (V4). Download is auth-gated and **not exercised** (AUTH-A). Open-data product **page metadata** is
recorded and kept distinct from **authenticated file retrieval**.

> **Official-client verification:** `https://www.mosdac.gov.in/software/mdapi.zip` was downloaded to a
> temporary verification directory and `mdapi.py` was inspected directly (V5). The exact client methods,
> payloads, headers, response-field handling, retries, and error branches are documented in §6.2.1. This
> verifies the client contract; authenticated live download remains unexercised without credentials (AUTH-A).

### 6.1 Satellite Products

Verified discovery example (V4): `datasetId=3RIMG_L2B_SST` (INSAT-3R L2B SST) →
- `totalResults=164696`, `totalSizeMB=2091369`, `author=MOSDAC,SAC-ISRO,India`
- sample entry `identifier=3RIMG_03SEP2026_1615_L2B_SST_V02R00.h5` (HDF5) with an SST summary.

Product files are HDF5 (`.h5`) / NetCDF; parse with `h5py`/`xarray` (`h5netcdf`) [Fn4]. Download requires auth (§6.2.1, AUTH-A). Gallery quicklooks (PNG/GIF/JPG) are **VISUAL-ONLY (§14)** and excluded from numeric use.

### 6.2 Catalog / mdapi

**Search/discovery HTTP contract (VERIFIED — V4):**
- **Method:** `GET`
- **URL:** `https://mosdac.gov.in/apios/datasets.json`
- **Params:** `datasetId`, `startTime`, `endTime`, `count`, `boundingBox`, `gId`, `startIndex`.
- **Headers:** `Accept: application/json`.
- **Cookies:** none required for search.
- **Auth:** none (search only).
- **Request body:** none (GET).
- **Content type (response):** `application/json` (verified V4, 1564 B for the sample).
- **Sample response schema (OpenSearch envelope):** `title, updated, author, links[], startIndex, itemsPerPage, totalResults, totalSizeMB, message, query, entries[]`. Each `entry`: `identifier, id, summary, updated, dcDate, enclosureLink, searchLink, boundbox`.
- **Pagination:** `startIndex` + `count` (OpenSearch-style); `totalResults` bounds iteration.
- **Rate limits:** **HTTP 429** carrying `minute_limit` / `daily_limit` messages — honor both.
- **Failure behavior:** non-200 / 429 with a `message` field; connector must back off on 429 and surface the `message`. **Tested search response** (V4) and **error schema (429 `minute_limit`/`daily_limit`)** are recorded here as the tested contract.

**OpenSearch descriptor:** `https://mosdac.gov.in/apios/osdd.xml` (advertised via `links.rel=search`); descriptor fetch itself `UNKNOWN — requires verification (OSDD-A)`.

#### 6.2.1 Download/session client behavior (mdapi) — official source verified

The official package `https://www.mosdac.gov.in/software/mdapi.zip` was downloaded and `mdapi.py` inspected
(V5). The table below is the exact client-side HTTP contract. **Authenticated success responses and product
bytes were not exercised without credentials (AUTH-A)**, so source-verified behavior and live-wire verification
remain distinct.

| Endpoint | Purpose | Exact client request | Headers | Parsed response / failure behavior | Verification |
|---|---|---|---|---|---|
| `/download_api/gettoken` | obtain bearer/session tokens | `POST`, JSON `{username, password}` | requests JSON content type | Parses `access_token`, `refresh_token`; handles 400/401 JSON `error`, 503 JSON `message` | SOURCE VERIFIED (V5); invalid credentials previously returned 400; success AUTH-A |
| `/download_api/check-internet` | determine whether dataset is released online | `GET`, JSON body `{datasetId}` | no Authorization header in official client | Parses nested array; `response[0][0] == 1` means product not released and client exits | SOURCE VERIFIED (V5); live success AUTH-A not required by source but not separately exercised |
| `/download_api/refresh-token` | refresh access token | `POST`, JSON `{refresh_token}` | requests JSON content type; no bearer header in official client | Returns JSON; 400 JSON `error` | SOURCE VERIFIED (V5); live success AUTH-A |
| `/download_api/logout` | end account session | `POST`, JSON `{username}`, timeout 5 s | requests JSON content type; no bearer header in official client | 400 JSON `error`; retries connection/timeouts at 5,10,20,30,40,50 s | SOURCE VERIFIED (V5); live success AUTH-A |
| `/download_api/download` | retrieve product file by search-entry record id | `GET`, query `id=<record_id>`, `stream=true`, timeout 5 s | `Authorization: Bearer <access_token>` | Streams product bytes; filename from search `identifier`; 400 `error`; 401 codes `NO_ACCESS_TOKEN`/`INVALID_TOKEN`; 404 `NOT_RELEASED`; 429 JSON `{message,type}` where type=`minute_limit` (sleep 20 s/retry) or `daily_limit` (logout/exit); network delays 10,20,30,60,90,120 s | SOURCE VERIFIED (V5); authenticated file bytes AUTH-A |

Search pagination is also source-verified: batches of 100, `startIndex` begins at 1 and advances after each
batch. Treat the unusual GET-with-JSON-body on `check-internet` as provider-client behavior; do not normalize
it into a query parameter unless MOSDAC documents an equivalent contract.

### 6.3 Open Data

MOSDAC open-data product **pages** advertise the following metadata. **This is page-metadata verification
only; authenticated file retrieval is `UNKNOWN — requires verification (AUTH-A)`.**

| Product | Page metadata (as published) | Verification level |
|---|---|---|
| Ocean surface current | **0.25° resolution, daily, global** | Page metadata verified; file retrieval `UNKNOWN — requires verification (AUTH-A)` |
| HRSSS — **High Resolution Sea Surface Salinity** | **10 km, Bay of Bengal; six-month publication cadence; with a historical range** | Page metadata verified; file retrieval `UNKNOWN — requires verification (AUTH-A)` |
| Oceanic eddies | **weekly, Bay of Bengal** | Page metadata verified; file retrieval `UNKNOWN — requires verification (AUTH-A)` |
| Ocean subsurface fields | **25 km horizontal, 10 m vertical step, Bay of Bengal** | Page metadata verified; file retrieval `UNKNOWN — requires verification (AUTH-A)` |

**Required correction applied:** HRSSS = **High Resolution Sea Surface Salinity** (a salinity product), **not** SST.

Exact `datasetId`s for these open-data products via the search API are `UNKNOWN — requires verification (DSID-*)` and must be resolved through `GET /apios/datasets.json`.

### 6.4 Gallery

MOSDAC gallery items are **PNG/GIF/JPG quicklooks → VISUAL-ONLY (§14)**. They are previews of products and
must **not** be treated as numeric NetCDF/HDF data. Use the corresponding `.h5`/`.nc` product (via search +
authenticated download) for numeric values.

---

## 7. Canonical Parameter Dictionary

Columns: **Canonical name** · **Aliases** (source terms) · **Datatype** · **Canonical unit** · **Candidate range** (platform QC bounds, *not source-authoritative*) · **Meaning** · **Obs/Forecast** · **Timestamp fields** · **Spatial form** · **Notes/conversion**.

> Candidate ranges are **platform sanity/QC bounds** for spike/outlier flagging only. They are **not**
> authoritative source-defined valid ranges. Never discard out-of-range values silently — flag with QC reason (§11).

### 7.1 Location & spatial-context

| Canonical | Aliases | Type | Unit | Candidate range | Meaning | O/F | Timestamps | Spatial | Conversion/notes |
|---|---|---|---|---|---|---|---|---|---|
| `latitude` | lat, y | float | deg | −90..90 | Latitude | input | — | point | WGS84 |
| `longitude` | lon, x | float | deg | −180..180 | Longitude | input | — | point | 0..360→−180..180 [Fn1] |
| `timestamp` | time, valid_time | datetime | ISO-8601 UTC | — | Query/context time | input | — | — | parse to UTC |
| `bbox` | boundingBox, extent | float[4] | deg | bounds | Region | input/derived | — | envelope | order per source |
| `radius_km` | radius, r | float | km | 0..2000 | Search radius | input | — | scalar | geodesic |
| `bearing` | heading, course | float | deg true | 0..360 | Travel direction | computed | — | scalar | forward azimuth |
| `distance_to_feature` | dist | float | km | ≥0 | Nearest feature distance | computed | — | scalar | PostGIS geodesic |
| `inside_feature` | in_zone | bool | — | — | Point-in-polygon | computed | — | bool | `ST_Contains` |
| `intersection_geometry` | overlap | geometry | GeoJSON | — | Route/zone overlap | computed | — | geometry | `ST_Intersection` |

### 7.2 Ocean

| Canonical | Aliases | Type | Unit | Candidate range | Meaning | O/F | Timestamps | Spatial | Conversion/notes |
|---|---|---|---|---|---|---|---|---|---|
| `sea_surface_temperature` | SST, sst | float | degC | −2..40 | Skin/bulk SST | obs (sat) | observed_at | grid/point | K→degC [Fn7] |
| `chlorophyll_a` | chlor_a, CHL | float | mg/m³ | 0..100 | Chlorophyll-a | obs (sat) | observed_at | grid/point | log→linear if needed |
| `sea_surface_salinity` | SSS, HRSSS | float | PSU | 0..42 | Surface salinity | obs | observed_at | grid | HRSSS=High Res Sea Surface Salinity |
| `current_u` | u, uo | float | m/s | −5..5 | Eastward current | obs/fcst | observed_at/valid_time | grid | keep u/v |
| `current_v` | v, vo | float | m/s | −5..5 | Northward current | obs/fcst | observed_at/valid_time | grid | keep u/v |
| `current_speed` | cur_speed | float | m/s | 0..7 | √(u²+v²) | computed | — | grid/point | derived |
| `current_direction` | cur_dir | float | deg | 0..360 | Current direction | computed | — | grid/point | convention per source [Fn12] |
| `significant_wave_height` | Hs, swh, VHM0 | float | m | 0..20 | Sig. wave height | fcst | valid_time | grid | — |
| `wave_period` | Tp, Tm, mwp | float | s | 0..30 | Wave period | fcst | valid_time | grid | peak vs mean |
| `wave_direction` | mwd | float | deg | 0..360 | Wave direction | fcst | valid_time | grid | to/from per source |
| `swell_height` | swell_Hs | float | m | 0..15 | Swell height | fcst | valid_time | grid | — |
| `swell_period` | swell_Tp | float | s | 0..30 | Swell period | fcst | valid_time | grid | — |
| `swell_direction` | swell_dir | float | deg | 0..360 | Swell direction | fcst | valid_time | grid | to/from per source |
| `wind_wave_height` | ww_Hs | float | m | 0..15 | Wind-sea height | fcst | valid_time | grid | where available |
| `wind_wave_period` | ww_Tp | float | s | 0..30 | Wind-sea period | fcst | valid_time | grid | where available |
| `sea_level` | ssh | float | m | −3..3 | Sea surface height | obs/fcst | observed_at | grid/point | datum documented |
| `tide_gauge_level` | water_level | float | m | −6..6 | Tide-gauge level | obs | observation_time | point | datum per station |
| `subsurface_temperature` | temp(z) | float | degC | −2..40 | Temp at depth | obs | observed_at | profile (z) | depth kept |
| `subsurface_salinity` | psal(z) | float | PSU | 0..42 | Salinity at depth | obs | observed_at | profile (z) | — |
| `subsurface_current` | u(z)/v(z) | float | m/s | −5..5 | Current at depth | obs/fcst | observed_at | profile (z) | u/v kept |
| `ocean_eddy` | eddy | entity | — | — | Eddy (center/radius/polarity/amplitude) | derived | valid_time | polygon+attrs | keep polarity |
| `tchp` | TCHP | float | kJ/cm² | 0..200 | Cyclone heat potential | derived | valid_time | grid | — |

### 7.3 Weather / atmosphere

| Canonical | Aliases | Type | Unit | Candidate range | Meaning | O/F | Timestamps | Spatial | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `wind_speed` | wspd | float | m/s | 0..90 | Wind speed | obs/fcst | observed_at/valid_time | grid/point | knots→m/s ×0.514444 |
| `wind_direction` | wdir | float | deg | 0..360 | Wind direction | obs/fcst | observed_at/valid_time | grid/point | "from" per source [Fn12] |
| `wind_u` | u10 | float | m/s | −90..90 | Eastward wind | obs/fcst | valid_time | grid | keep internally |
| `wind_v` | v10 | float | m/s | −90..90 | Northward wind | obs/fcst | valid_time | grid | keep internally |
| `gust_speed` | gust | float | m/s | 0..120 | Wind gust | obs/fcst | valid_time | grid/point | where available |
| `rainfall_rate` | rain_rate | float | mm/h | 0..500 | Rain rate | obs/fcst | observed_at/valid_time | grid | — |
| `rainfall_accumulation` | tp | float | mm | 0..2000 | Accumulated rain | obs/fcst | valid_from→valid_until | grid | window kept |
| `sea_level_pressure` | mslp | float | hPa | 850..1085 | MSLP | obs/fcst | observed_at/valid_time | grid/point | Pa→hPa ÷100 |
| `station_pressure` | pres | float | hPa | 500..1085 | Station pressure | obs | observed_at | point | — |
| `humidity` | rh | float | % | 0..100 | Relative humidity | obs/fcst | observed_at | grid/point | where available |
| `thunderstorm_indicator` | ts_flag | enum | — | — | Thunderstorm indicator | fcst/warn | valid_time | area | via CAP |
| `lightning_event` | lightning | entity | — | — | Lightning stroke/alert | obs/warn | lightning_time | point/polygon | via CAP |

### 7.4 Hazard / advisory entities (normalized)

| Entity | Key fields | Source family | Notes |
|---|---|---|---|
| `warning` (generic CAP) | warning_id, event_type, severity, certainty, urgency, headline, description, geometry, area_description, issued_at, effective_from, expires_at, source, source_url | IMD CAP (verified) | Direct from CAP 1.2; event coverage = as issued |
| `cyclone` | cyclone_id, name, center_lat/lon, issue_time, forecast_time, movement_dir/speed, central_pressure, max_sustained_wind, gust, track_geometry, forecast_cone, intensity_category | IMD/RSMC (unverified feed) | Structured feed `UNKNOWN — requires verification (REG-A/HAR)` |
| `tsunami` | event_id, earthquake_time, eq_lat/lon, magnitude, depth, tsunami_status, alert_level, affected_regions | INCOIS TEWS | `UNKNOWN — requires verification (HAR-C)` |
| `storm_surge` | sea_level, storm_surge_height, surge_anomaly, geometry, valid_from/until | INCOIS | `UNKNOWN — requires verification (HAR-C)` |
| `high_wave_alert` | severity, geometry, valid_from/until | INCOIS HWA | `UNKNOWN — requires verification (HAR-C)` |
| `lightning_alert` | location, time, severity, geometry, valid_from/until | IMD CAP | via CAP where issued |

### 7.5 Fisheries / ecosystem entities

| Entity | Key fields | Source | Notes |
|---|---|---|---|
| `pfz` | pfz_id, geometry, issue_time, valid_from/until, region, advisory_text, species/advisory_type, sst_context, chlorophyll_context, confidence, source, source_url | INCOIS PFZ | geometry `UNKNOWN — requires verification (HAR-A)` |
| `fishery_advisory` | advisory_id, advisory_type (Tuna/Hilsa/…), species_or_ecosystem, region, geometry, issued_at, valid_from/until, recommendation, source | INCOIS ecosystem | `UNKNOWN — requires verification (HAR-A)` |
| `ecological_hazard` | HAB/algal bloom, coral, jellyfish advisories | INCOIS | `UNKNOWN — requires verification (HAR-A)` |

### 7.6 In-situ & reference entities

| Entity | Key fields | Source | Notes |
|---|---|---|---|
| `observation` | station_id, station_type, latitude, longitude, observation_time, parameter, value, unit, quality_flag, source | IMD buoy (HTML), INCOIS ARGO/tide (ERDDAP) | IMD buoy=HTML; ARGO via ERDDAP |
| `zone` | zone_id, zone_type, name, geometry, status, restriction, authority, effective_from/until, source, source_url | **Not covered by three providers** | GAP §15; operator config only |
| `bathymetry` | bathymetry_depth, source, resolution, valid_area | **Not covered** | GAP §15; do not infer depth |

---

## 8. Timestamp Semantics

- Parse every source time to timezone-aware **UTC**. Keep distinct: `observed_at`, `issued_at`, `valid_from`, `valid_until`, `forecast_time`, `retrieved_at`, `processed_at`. Never conflate (requirements §7, rule 3).
- **CAP:** `sent`→issued_at, `effective`/`onset`→effective_from, `expires`→expires_at [Fn20].
- **MOSDAC:** entry `dcDate`/identifier-embedded time → observed_at; `updated`→retrieved metadata.
- **ERDDAP:** `time` axis → observed_at/valid_time per dataset semantics (confirm via ERDDAP-INFO).
- **Forecast records** additionally retain `model_name`, `model_cycle`, `forecast_hour` (requirements §12).
- Store the raw source timestamp string alongside the parsed UTC value for audit.

---

## 9. Spatial / CRS Semantics

- Canonical output CRS: **WGS84 (EPSG:4326)** lat/lon.
- ERDDAP is already WGS84. MOSDAC satellite grids may be sensor/geostationary projections → reproject with pyproj/GDAL; record `processing_version` and method.
- Longitude 0..360 → −180..180 via `lon' = ((lon + 180) mod 360) − 180`; keep original in raw metadata [Fn1].
- CAP polygon is space-separated `lat,lon` → GeoJSON `[lon,lat]` (swap), close ring, validate with Shapely; store raw + normalized [Fn22].
- bbox axis order is documented per source (MOSDAC `boundingBox` param; ERDDAP lat/lon subset syntax).
- Regrid only for query/visualization layers; preserve native-resolution assets [Fn5].

---

## 10. Units and Normalization

- Convert to canonical units (§7): K→degC (−273.15); Pa→hPa (÷100); knots→m/s (×0.514444).
- Confirm source units from file/API attributes before converting; if attributes absent, mark `unit=UNKNOWN` and defer conversion.
- Apply CF `scale_factor`+`add_offset`; mask `_FillValue`/`missing_value`; **never silently drop** — attach QC flag with reason [Fn6].
- **Direction:** wind meteorological "from", current oceanographic "toward"; if a source's convention is unclear, DO NOT convert — store raw value + `direction_convention=UNKNOWN` [Fn12].
- Keep u/v internally even when the public API exposes speed/direction.

---

## 11. Quality Control

Pipeline (requirements §14/§22): `fetch → checksum → schema validation → decode → physical-range validation → temporal validation → duplicate detection → spatial validation → spike/outlier checks → quality flag → publish`.

- Keep raw data immutable even when a processed record fails QC.
- Never silently discard suspicious observations; record QC status/reason (`missing_flag`, `outlier_flag`, `interpolated_flag`, `quality_status`, `quality_score`).
- Candidate ranges in §7 are platform QC bounds, **not** source-authoritative.
- Retain source/ERDDAP QC flags as `quality_flag`; re-validate in-pipeline [Fn27].
- CAP: verify `ds:Signature` before trusting for safety-critical use; record result in provenance [Fn23].

---

## 12. Freshness / Staleness

Per dataset track: expected update interval, last successful fetch, last processed time, current latency, current status, consecutive failures, stale threshold (requirements §13/§16).

`freshness_score = f(now − source_timestamp, expected_update_interval)` (configurable per dataset).

| Class | Rule (example, configurable) |
|---|---|
| HEALTHY | age ≤ expected_interval |
| STALE | expected_interval < age ≤ stale_threshold |
| DEGRADED | partial data / elevated latency / consecutive_failures ≥ N |
| FAILED | last fetch failed and age > stale_threshold |
| DISABLED | connector disabled (auth/HAR blocker) |

Safety-critical data (CAP, tsunami, surge) must **never** be served as fresh without an explicit age/status flag.

---

## 13. Source Priority / Conflict Resolution

When two in-scope sources provide the same parameter, resolve deterministically (configurable):

1. **Verification status** — a verified machine-readable source beats an unverified/HTML/scraped one.
2. **Freshness** — HEALTHY beats STALE (§12).
3. **QC quality_score** — higher wins.
4. **Modality priority for the use case** — e.g., in-situ obs as ground truth vs satellite estimate; **expose both** in evidence rather than discarding.
5. **Spatial/temporal proximity** — nearer in space/time to query wins.

Record the chosen source and alternatives in the evidence/provenance package; never hide the conflict.
Example in-scope conflict: SST from MOSDAC INSAT vs INCOIS AVHRR/AMSR — apply order above; surface both in `sources[]` [Fn8].

---

## 14. Visualization-only Data

Products returning only images/tiles/PDF, with **no numeric/machine-readable payload**, are excluded as
numeric data sources. Table columns are **exactly**: `Dataset` · `Page` · `Numeric data available?` ·
`Machine-readable endpoint?` · `Image/tile only?` · `Can safely ingest?` · `Notes`.

| Dataset | Page | Numeric data available? | Machine-readable endpoint? | Image/tile only? | Can safely ingest? | Notes |
|---|---|---|---|---|---|---|
| IMD NWP / coastal-forecast charts | IMD NWP/coastal forecast web pages | No (rendered) | No (numeric GRIB2 behind REG-A) | Yes (PNG/PDF) | No | Use registered GRIB2 (`UNKNOWN — requires verification (REG-A)`) for numeric NWP; do not OCR charts |
| IMD radar imagery | IMD radar pages | No | No (GIS service `UNKNOWN — requires verification (HAR-E)`) | Yes (image tiles) | No | Radar images are not numeric precipitation data |
| MOSDAC gallery quicklooks | `mosdac.gov.in` gallery | No | No (numeric = `.h5`/`.nc` via search+download) | Yes (PNG/GIF/JPG) | No | Use the corresponding product file (§6.1) for numeric values |
| INCOIS portal map renderings (non-XHR) | INCOIS OSF/PFZ/portal map views | No (rendered) | Underlying XHR/ERDDAP where present | Yes (rendered map) | No | Capture underlying XHR (HAR-A/B) or use ERDDAP (§5.0) instead |
| INCOIS LAS map/plot output | INCOIS LAS UI | No (rendered) | Per-product data protocol `UNKNOWN — requires verification (HAR-F)` | Yes (rendered) | No | Do not assume LAS renders = ERDDAP data |
| INCOIS ESSDP map views | INCOIS ESSDP | No (rendered) | `UNKNOWN — requires verification (HAR-F)` | Yes (rendered) | No | Confirm an XHR/data endpoint before any ingest |

---

## 15. Source Gaps

Per prompt scope (three providers only) and requirements §25/§28: gaps are **marked**, not filled with
external providers or fabricated data. **No additional source is introduced as a solution.**

| Gap | Requirement driver | In-scope status | Verification/HAR action | Disposition |
|---|---|---|---|---|
| PFZ machine geometry/XHR | §9 PFZ, suitability | INCOIS page `PfzAdvisory` reachable; endpoint unverified | **HAR-A** | **P0 prerequisite**; not P0-ready until confirmed |
| OSF surface currents dataset | currents, routing | Unverified | HAR-B | P1 blocker for currents/routing |
| OSF wave/swell/wind-wave dataset | waves, windows, routing | Unverified | HAR-B | P1 blocker for wave-based products |
| INCOIS HWA / swell alert JSON | high-wave/swell alert | Unverified | HAR-C | P1 |
| INCOIS storm surge feed | surge | Unverified | HAR-C | P1 |
| INCOIS TEWS tsunami feed | tsunami | Unverified | HAR-C | P1 (safety-critical) |
| INCOIS tide **prediction** feed | tides, windows | Unverified; may not exist as feed | HAR-D | P1; tide-state fields unavailable meanwhile |
| INCOIS TCHP | TCHP | Unverified | HAR-C | P2 |
| INCOIS LAS/ESSDP data protocols | remote sensing/analysis | Unverified | HAR-F | P2 |
| IMD structured cyclone (track/cone/intensity) | cyclone | Blocked/unverified (RSMC) | REG-A/HAR | P1 (CAP partial interim) |
| IMD numeric NWP (wind/rain/pressure/humidity) | weather | Token-gated; public pages VISUAL-ONLY | REG-A | P1 |
| IMD authenticated API marine endpoints | weather, obs | 401/403 on legacy; token required | REG-A | P1 |
| IMD radar/GIS numeric service | radar | Image tiles only | HAR-E | P2 |
| MOSDAC authenticated download (all products) | ocean/atmos numeric | Search open; download not exercised | AUTH-A | P1 |
| MOSDAC official `mdapi.py` client contract | download/session behavior | Official package inspected; exact methods/payloads verified (V5) | AUTH-A only for live success | Source contract complete; authenticated end-to-end test remains P1 |
| CAP issued-event coverage | alert taxonomy | Only measured, not assumed | OBS-CAP | P1 (observe feed over time) |
| Anomaly baselines (SST/CHL/etc.) | anomalies | Not a source; must retain history | build over time | Build dependency (not a provider gap) |
| **EEZ / international maritime boundaries** | geofence | **No in-scope provider** | none in-scope | **GAP — external authoritative GIS required later; do not fabricate** |
| **Restricted zones / MPAs / sensitive zones** | geofence | **No in-scope provider** | none in-scope | **GAP — do not fabricate** |
| **Ports / harbours** | reference | **Not established in-scope** | none in-scope | **GAP** |
| **Shipping lanes** | routing | **No in-scope provider** | none in-scope | **GAP** |
| **Bathymetry / depth** | routing | **No in-scope provider** | none in-scope | **GAP — do not infer depth** |
| **Fisheries catch/effort/productivity** | fisheries analysis | **No in-scope provider** | none in-scope | **GAP — no productivity attribution claims** |

---

## 16. Licensing / Redistribution Constraints

This document records the **observed provider policy** only (published copyright/registration/payment/redistribution
notices). It makes **no legal interpretation**. Redistribution/commercial-use clearance is a separate
legal/procurement action to be completed before production redistribution.

| Provider | Observed policy | Evidence URL | Cautious note |
|---|---|---|---|
| IMD CAP | RSS `<copyright>public domain</copyright>` (verified V1) | `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` | "public domain" string observed in-feed; confirm scope covers derived redistribution before relying on it commercially |
| IMD API / DSP | Registration + possible payment + license terms | `https://api.imd.gov.in` ; IMD Data Supply Portal (registration) | Terms `UNKNOWN — requires verification (REG-A)`; do not redistribute without confirming license |
| IMD buoy page | No explicit license string observed on the HTML page | `https://mausam.imd.gov.in/imd_latest/contents/buoy_obs.php?id=<stationId>` | Absence of a license notice is **not** a grant; treat as restricted until confirmed |
| INCOIS ERDDAP / data | INCOIS data policy; bulk data **may be chargeable** | `https://erddap.incois.gov.in/erddap/` ; INCOIS data-policy page | Cite published pricing/policy at access time; chargeable/redistribution terms `UNKNOWN — requires verification` |
| INCOIS PFZ / advisories | INCOIS advisory policy | `https://incois.gov.in/MarineFisheries/PfzAdvisory` | Advisory reuse terms `UNKNOWN — requires verification (HAR-A)` |
| MOSDAC search | Search open; `author=MOSDAC,SAC-ISRO,India` on results (V4) | `https://mosdac.gov.in/apios/datasets.json` | Search-open ≠ redistribution grant |
| MOSDAC download / open-data | Account-gated download; product/open-data terms per MOSDAC policy | `https://mosdac.gov.in/` (open-data product pages) | Download license `UNKNOWN — requires verification (AUTH-A)`; do not redistribute files without confirming terms |

Cautious language rule: everywhere above, "policy observed" means the literal published notice; any statement
about permissibility of redistribution/commercial use is deferred to a legal/procurement action, not asserted here.

---

## 17. Connector Specifications

Declarative specs, not implementations (connectors are **not** implemented here). **Enabled** connectors have
a verified, machine-readable, usable access path today and get **individual** specs. **Disabled** candidates
may be grouped only when **every blocker is explicit**.

### 17.1 ENABLED — individual specs per verified usable interface/product

#### 17.1.1 IMD CAP alerts (VERIFIED — public domain)

```yaml
connector: imd_cap_alerts
enabled: true
provider: IMD
verification: V1_V2_2026-09-03
kind: alert_feed
discovery:
  rss_index: "https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml"
  item_pattern: "linked CAP 1.2 XML per <item> (e.g. .../2026-09-03-07-21-21.xml)"
http_contract:
  rss:  { method: GET, params: none, headers: {Accept: application/xml}, auth: none, body: none, content_type: text/xml }
  item: { method: GET, params: none, headers: none, auth: none, body: none, content_type: application/xml }
access: { type: open, auth: none, method: poll_rss_then_fetch_cap }
schedule: { poll_interval: 60s, backoff: exponential_with_jitter, dedupe_by: cap_identifier }
format: { index: rss_2.0, item: cap_1.2_xml, namespace: "urn:oasis:names:tc:emergency:cap:1.2", signed: true }
parse:
  rss: feedparser
  cap: lxml
  fields: [identifier, sender, sent, status, msgType, scope, category, event, urgency, severity,
           certainty, effective, onset, expires, senderName, headline, description, areaDesc, polygon]
geometry: { source_form: "space-separated lat,lon pairs (verified V2)", normalize_to: geojson_polygon_swap_close }
crs: EPSG:4326
timestamps: { issued_at: sent, effective_from: "effective|onset", expires_at: expires, all_to: UTC }
event_coverage: "only families IMD actually issues; do NOT assume all CAP-representable families present (OBS-CAP)"
normalization: { map_to_entity: warning, enum_normalize: [severity, urgency, certainty, msgType, status] }
qc: { verify_signature: true, signature_key_retrieval: "UNKNOWN — requires verification (SIG-A)", require_polygon_or_areaDesc: true, drop_expired: false }
freshness: { expected_update: event_driven, stale_threshold: 3h }
rate_limits: none_published
failure_behavior: "keep last good state on non-200; flag freshness"
licensing: { policy_observed: "RSS <copyright>public domain</copyright>", evidence_url: "https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml", legal_interpretation: none }
outputs: [alerts, alert_events(NATS), lightning_alert, thunderstorm_warning, heavy_rain_warning, partial_cyclone_warning]
priority: P0
```

#### 17.1.2 INCOIS ERDDAP — open catalog + gridded/tabular (VERIFIED CATALOG)

```yaml
connector: incois_erddap
enabled: true
provider: INCOIS
verification: V3_2026-09-03  # CATALOG presence only; per-dataset schema NOT verified
kind: erddap
catalog:
  info_json: "https://erddap.incois.gov.in/erddap/info/index.json"
  http_contract: { method: GET, params: [page, itemsPerPage], headers: {Accept: application/json}, auth: none, body: none, content_type: "application/json;charset=UTF-8" }
tls: { note: "server omits intermediate; bundle GlobalSign RSA OV SSL CA 2018", insecure_allowed: false }
access: { type: open, auth: none, protocols: [griddap, tabledap, wms] }   # NO wfs from ERDDAP
datasets_verified_present:   # 16 IDs; catalog presence only
  - AMSRE_MONTHLY_GLOBAL
  - ascat_daily_datasets
  - ascat_mnt_datasets
  - incois_argo_10day_McCreary
  - incois_argo_10d_VAM
  - incois_argo_mnt_McCreary
  - incois_argo_mnt_VAM
  - incois_argo_sst_weekly
  - incois_oceansat2_datasets
  - incois_quickscat_daily_datasets
  - incois_quickscat_mnt_datasets
  - incois_tmi_3day_datasets
  - incois_valueadded_products_datasets
  - Indian_ARGO_Floats
  - IRS_chlorophyll_datasets
  - NOAA_AVHRR_AMSR_datasets
per_dataset_schema: "UNKNOWN — requires verification (ERDDAP-INFO): GET /erddap/info/<id>/index.json"
query_examples:
  tested:   "GET /erddap/info/index.json?page=1&itemsPerPage=1000  # V3, HTTP 200"
  template_info: "GET /erddap/info/<datasetId>/index.json"
  template_griddap: "GET /erddap/griddap/<datasetId>.nc?<var>[(t0):(t1)][(lat0):(lat1)][(lon0):(lon1)]"
  template_tabledap: "GET /erddap/tabledap/<datasetId>.csv?<vars>&time>=<t0>&time<=<t1>&latitude>=<a>&latitude<=<b>&longitude>=<c>&longitude<=<d>"
format: [nc, csv, json]
parse: [xarray, erddapy, pandas]
crs: EPSG:4326
normalization: { units: per_variable_attrs_confirm_first, scale_offset_fill: apply_never_drop, keep_uv: true }
qc: { retain_source_flags: true }
freshness: { expected_update: per_dataset }
rate_limits: none_published_polite_backoff
failure_behavior: "TLS chain failure if intermediate not bundled — do not fall back to insecure"
licensing: { policy_observed: "INCOIS data policy; bulk data may be chargeable — check at access", evidence_url: "https://erddap.incois.gov.in/erddap/", legal_interpretation: none }
provides:
  - chlorophyll_a            # IRS_chlorophyll_datasets
  - sea_surface_temperature  # NOAA_AVHRR_AMSR_datasets, incois_argo_sst_weekly, AMSRE_MONTHLY_GLOBAL
  - wind_uv                  # ascat_*, incois_quickscat_*, incois_oceansat2_*
  - subsurface_profiles      # Indian_ARGO_Floats, incois_argo_*
  - sea_level                # incois_valueadded_products_datasets (confirm var via ERDDAP-INFO)
priority: P0   # the verified machine-readable numeric-data connector; needs ERDDAP-INFO per dataset before ingest
```

#### 17.1.3 MOSDAC search/discovery (VERIFIED — discovery only)

```yaml
connector: mosdac_search
enabled: true            # discovery only; DOWNLOAD is separate & disabled (see 17.2.3)
provider: MOSDAC
verification: V4_2026-09-03
kind: opensearch_discovery
endpoint:
  search: "https://mosdac.gov.in/apios/datasets.json"
  osdd:   "https://mosdac.gov.in/apios/osdd.xml"   # fetch UNKNOWN — requires verification (OSDD-A)
http_contract: { method: GET, params: [datasetId, startTime, endTime, count, boundingBox, gId, startIndex], headers: {Accept: application/json}, auth: none, body: none, content_type: application/json }
response_envelope: [title, updated, author, links, startIndex, itemsPerPage, totalResults, totalSizeMB, message, query, entries]
entry_fields: [identifier, id, summary, updated, dcDate, enclosureLink, searchLink, boundbox]
tested_response:
  request: "GET /apios/datasets.json?datasetId=3RIMG_L2B_SST&count=1"
  result: { totalResults: 164696, totalSizeMB: 2091369, author: "MOSDAC,SAC-ISRO,India", sample_identifier: "3RIMG_03SEP2026_1615_L2B_SST_V02R00.h5" }
error_schema: { http_429: { fields: [minute_limit, daily_limit], carries: message } }
pagination: { startIndex: startIndex, page_size: count, bound: totalResults }
gallery_exclusion: "PNG/GIF/JPG quicklooks are VISUAL-ONLY (§14)"
licensing: { policy_observed: "search open; product download account-gated", evidence_url: "https://mosdac.gov.in/apios/datasets.json", legal_interpretation: none }
provides: [dataset_discovery, catalog_metadata, boundbox_for_bbox_queries]
priority: P0-support   # powers registry/catalog; numeric ingest needs 17.2.3
```

#### 17.1.4 IMD buoy HTML (ENABLEABLE but FRAGILE — individual spec, gated by canary)

```yaml
connector: imd_buoy_html
enabled: false            # usable pattern but brittle; enable only with canary tests
provider: IMD
verification: "endpoint pattern confirmed reachable in session"
kind: in_situ_html
http_contract: { method: GET, url: "https://mausam.imd.gov.in/imd_latest/contents/buoy_obs.php?id=<stationId>", params: {id: stationId}, headers: {User-Agent: browser}, cookies: none, auth: none, body: none, content_type: text/html }
station_id_discovery: "UNKNOWN — requires verification (OBS-BUOY): enumerate from IMD marine/coastal pages"
parse: [beautifulsoup, regex]
normalization: { map_to_entity: observation }
limitations: "HTML layout-change risk; snapshot raw HTML; canary test; best-effort numeric extraction"
freshness: { expected_update: "UNKNOWN — requires verification (OBS-BUOY)" }
failure_behavior: "detect empty/canary-failed layout and flag; do not parse garbage"
licensing: { policy_observed: "no explicit license string on page", evidence_url: "https://mausam.imd.gov.in/imd_latest/contents/buoy_obs.php", legal_interpretation: none }
priority: P1
```

### 17.2 DISABLED — grouped only where every blocker is explicit

#### 17.2.1 INCOIS PFZ (DISABLED — HAR-A; P0 prerequisite)

```yaml
connector: incois_pfz
enabled: false
disabled_reason: "machine geometry/XHR endpoint unverified"
blocker: { id: HAR-A, action: "capture XHR returning GeoJSON/JSON/WFS/NetCDF from PfzAdvisory page; export HAR; confirm endpoint+schema" }
provider: INCOIS
kind: fisheries_advisory
entry_page: "https://incois.gov.in/MarineFisheries/PfzAdvisory"   # wire-verified URL; do not use guessed 404 paths
unknowns:
  endpoint: "UNKNOWN — requires verification (HAR-A)"
  http_contract: "method/params/headers/cookies/auth/body/content_type/schema/pagination/rate_limits/failure ALL UNKNOWN — requires verification (HAR-A)"
target_entity: pfz
required_fields: [pfz_id, geometry, issue_time, valid_from, valid_until, region, advisory_text, species, sst_context, chlorophyll_context, source_url]
priority_note: "PFZ CANNOT be P0-ready until HAR-A confirms exact machine geometry; HAR-A is a P0 prerequisite"
```

#### 17.2.2 INCOIS OSF / HWA / storm-surge / TEWS / tide / TCHP / LAS / ESSDP (DISABLED — HAR-B/C/D/F)

```yaml
connector: incois_osf_and_hazards
enabled: false
provider: INCOIS
disabled_reason: "machine endpoints/schemas unverified per component"
components:   # every blocker explicit
  osf_currents:    { enabled: false, blocker: HAR-B, provides: [current_uv], http_contract: "UNKNOWN — requires verification (HAR-B)" }
  osf_waves:       { enabled: false, blocker: HAR-B, provides: [Hs, Tp, wave_dir, swell_h, swell_p, swell_dir, ww_h, ww_p], http_contract: "UNKNOWN — requires verification (HAR-B)" }
  high_wave_alert: { enabled: false, blocker: HAR-C, provides: [high_wave_alert, swell_alert], http_contract: "UNKNOWN — requires verification (HAR-C)" }
  storm_surge:     { enabled: false, blocker: HAR-C, provides: [storm_surge], http_contract: "UNKNOWN — requires verification (HAR-C)" }
  tews_tsunami:    { enabled: false, blocker: HAR-C, provides: [tsunami], safety_critical: true, http_contract: "UNKNOWN — requires verification (HAR-C)" }
  tide_obs:        { enabled: false, blocker: HAR-D, provides: [tide_gauge_level], http_contract: "UNKNOWN — requires verification (HAR-D)" }
  tide_prediction: { enabled: false, blocker: HAR-D, provides: [tide_prediction], note: "may not exist as feed", http_contract: "UNKNOWN — requires verification (HAR-D)" }
  tchp:            { enabled: false, blocker: HAR-C, provides: [tchp], priority: P2, http_contract: "UNKNOWN — requires verification (HAR-C)" }
  las_essdp:       { enabled: false, blocker: HAR-F, note: "LAS/ESSDP per-product data protocol unknown; renders are VISUAL-ONLY until XHR captured" }
auth: "UNKNOWN — requires verification (per component)"
licensing: { policy_observed: "INCOIS policy; chargeable possible", evidence_url: "https://incois.gov.in/", legal_interpretation: none }
```

#### 17.2.3 MOSDAC authenticated download / session (DISABLED — AUTH-A)

```yaml
connector: mosdac_download
enabled: false
disabled_reason: "official client contract verified; live authenticated download not exercised"
blockers:
  - { id: AUTH-A, action: "exercise gettoken→download with issued credentials; verify success payloads and product bytes end-to-end" }
provider: MOSDAC
client_source:
  package: "https://www.mosdac.gov.in/software/mdapi.zip"
  verification: "V5 — mdapi.py inspected directly"
auth_flow:
  gettoken:       { method: POST, url: "https://mosdac.gov.in/download_api/gettoken", json: {username: "<secret>", password: "<secret>"}, response_fields: [access_token, refresh_token] }
  check_internet: { method: GET, url: "https://mosdac.gov.in/download_api/check-internet", json: {datasetId: "<datasetId>"}, released_test: "response[0][0] != 1" }
  download:       { method: GET, url: "https://mosdac.gov.in/download_api/download", query: {id: "<record_id>"}, headers: {Authorization: "Bearer <access_token>"}, stream: true }
  refresh_token:  { method: POST, url: "https://mosdac.gov.in/download_api/refresh-token", json: {refresh_token: "<refresh_token>"} }
  logout:         { method: POST, url: "https://mosdac.gov.in/download_api/logout", json: {username: "<username>"} }
failures:
  token: {400: "JSON error", 401: "JSON error", 503: "JSON message"}
  download: {400: "error", 401: [NO_ACCESS_TOKEN, INVALID_TOKEN], 404: NOT_RELEASED, 429: [minute_limit, daily_limit]}
retry:
  minute_limit: "sleep 20s then retry"
  daily_limit: "logout and stop"
  network_seconds: [10, 20, 30, 60, 90, 120]
provides_on_enable:
  - sea_surface_temperature   # 3RIMG_L2B_SST (h5)
  - chlorophyll_a             # ocean-colour OCM (datasetId UNKNOWN — requires verification (DSID-CHL))
  - surface_current           # 0.25° daily global (datasetId UNKNOWN — requires verification (DSID-CUR))
  - sea_surface_salinity      # HRSSS 10km BoB, six-month cadence (datasetId UNKNOWN — requires verification (DSID-SSS))
  - subsurface_profiles       # 25km/10m BoB (datasetId UNKNOWN — requires verification (DSID-SUB))
  - ocean_eddies              # weekly BoB (datasetId UNKNOWN — requires verification (DSID-EDDY))
  - rainfall                  # INSAT rainfall (datasetId UNKNOWN — requires verification (DSID-RAIN))
parse: [h5py, xarray]
open_data_page_metadata: "verified per §6.3; file retrieval still AUTH-A"
licensing: { policy_observed: "account-gated download", evidence_url: "https://mosdac.gov.in/data-access-policy", legal_interpretation: none }
```

#### 17.2.4 IMD authenticated API / NWP / RSMC / radar (DISABLED — REG-A, HAR-E)

```yaml
connector: imd_api_nwp
enabled: false
disabled_reason: "registration/token required; legacy /api returned 401/403; public NWP is VISUAL-ONLY; radar image-only"
blockers:
  - { id: REG-A, action: "register for api.imd.gov.in token; document auth flow and marine/NWP endpoint list" }
  - { id: HAR-E, action: "capture any IMD radar/GIS numeric service; else remains VISUAL-ONLY" }
provider: IMD
endpoints:
  api_base: "https://api.imd.gov.in"   # marine endpoint list UNKNOWN — requires verification (REG-A)
  legacy_api: "returns 401/403"
http_contract: "UNKNOWN — requires verification (REG-A)"
provides_on_enable: [wind, gust, rainfall_rate, rainfall_accumulation, sea_level_pressure, station_pressure, humidity, cyclone_structured]
format: [json?, grib2]
parse: [requests, cfgrib, ecCodes]
visual_only_excluded: [nwp_charts_png_pdf, radar_imagery, coastal_forecast_pdf]
licensing: { policy_observed: "IMD API/DSP license & possible payment", evidence_url: "https://api.imd.gov.in", legal_interpretation: none }
```

---

## 18. Implementation Priority

| Priority | Connector / capability | Rationale |
|---|---|---|
| **P0** | **IMD CAP alerts** (§17.1.1) | Only fully verified, public-domain, machine-readable, signed safety feed. Backbone of alerts/events. |
| **P0** | **INCOIS ERDDAP open data** (§17.1.2) | Verified machine-readable catalog: open, WGS84, standard formats. Delivers first real numeric params (chlorophyll, SST, ARGO, scatterometer wind) — after per-dataset ERDDAP-INFO. |
| **P0-support** | **MOSDAC search** (§17.1.3) | Verified open discovery → powers dataset registry/catalog; no numeric ingest until AUTH-A. |
| **P0-prerequisite** | **INCOIS PFZ HAR-A** (§17.2.1) | PFZ required and high-value but **NOT P0-ready** until exact machine geometry verified. HAR-A is a gating task, not a shippable connector. |
| **P1** | MOSDAC authenticated end-to-end download (AUTH-A), IMD API/NWP (REG-A), INCOIS OSF/HWA/surge/TEWS/tide (HAR-B/C/D), IMD buoy HTML, CAP event coverage (OBS-CAP) | Unlock currents, waves, satellite SST/CHL/current/salinity/eddies numeric ingest, structured hazards. |
| **P2** | TCHP, sea-surface salinity analytics, subsurface analytics, eddies analytics, IMD radar/GIS (HAR-E), INCOIS LAS/ESSDP (HAR-F) | Advanced/oceanographic; depend on P1 access. |
| **Build-dependency** | Anomaly baselines | Accumulate retained history before anomaly/percentile products. |
| **GAP (out of in-scope providers)** | EEZ/boundaries/MPAs/ports/shipping-lanes/bathymetry/fisheries-catch | Cannot be delivered by IMD/INCOIS/MOSDAC; do not fabricate. |

Concrete next-build sequence is in §21.

---

## 19. Verification Status

### 19.1 Verification log (date / method / result)

All checks performed 2026-09-03 from a Linux host using `curl`, `openssl s_client`, `python3`.

| # | Target | Method | Result |
|---|---|---|---|
| V1 | `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` | `curl -sS` | **HTTP 200**, `text/xml`, 6915 B. RSS 2.0, `<copyright>public domain</copyright>`, live `<item>` alerts, `lastBuildDate` current. |
| V2 | CAP item `https://cap-sources.s3.amazonaws.com/in-imd-en/2026-09-03-07-21-21.xml` | `curl -sS` + `python3` regex | **HTTP 200**, `application/xml`, 4413 B. Namespace `urn:oasis:names:tc:emergency:cap:1.2`. Fields incl. `identifier,sender,sent,status,msgType,scope,info,category,event,urgency,severity,certainty,effective/onset,expires,senderName,headline,area,areaDesc,polygon`. **`ds:Signature` present** (`xmldsig#`). Polygon = space-separated `lat,lon` pairs, ring closed (`25.1254,80.2881 … 25.1254,80.2881`). `event=Extremely heavy`, `areaDesc=ODISHA`. |
| V3 | `https://erddap.incois.gov.in/erddap/info/index.json?page=1&itemsPerPage=1000` | `curl -sSLk` | **HTTP 200**, `application/json;charset=UTF-8`, 22076 B. 16 dataset IDs enumerated (see §5.0). **Catalog presence only — per-dataset schema NOT inspected.** |
| V3-TLS | `erddap.incois.gov.in:443` | `openssl s_client` | Leaf `CN=*.incois.gov.in`, issuer `GlobalSign RSA OV SSL CA 2018`. Code 21 (missing intermediate) → server omits intermediate; bundle it, never disable verification. |
| V4 | `https://mosdac.gov.in/apios/datasets.json?datasetId=3RIMG_L2B_SST&count=1` | `curl -sS` | **HTTP 200**, `application/json`, 1564 B. `totalResults=164696`, `totalSizeMB=2091369`, `author=MOSDAC,SAC-ISRO,India`, entry `3RIMG_03SEP2026_1615_L2B_SST_V02R00.h5` (HDF5). Search/discovery works unauthenticated; **download not exercised**. |
| V5 | `https://www.mosdac.gov.in/software/mdapi.zip` (`mdapi.py`) | `curl`, `unzip`, source inspection | **HTTP 200 package; official client inspected.** Verified exact methods/payloads: token POST JSON credentials; search GET query params; check-internet GET JSON `{datasetId}`; download GET query `id` + Bearer; refresh POST JSON refresh token; logout POST JSON username; error/retry behavior in §6.2.1. Authenticated success/file bytes remain AUTH-A. |

### 19.2 Verification-level summary

| Interface | Catalog/page | Data/schema | Auth retrieval | Overall |
|---|---|---|---|---|
| IMD CAP RSS + item | ✅ V1 | ✅ V2 (fields+polygon+signature) | n/a (open) | VERIFIED |
| IMD buoy HTML | ✅ pattern | ⚠ unstructured HTML | n/a | VERIFIED PATTERN |
| IMD API/NWP/RSMC/radar | ✗ | ✗ | ✗ | REG-A/HAR-E |
| INCOIS ERDDAP | ✅ V3 (16 IDs) | ✗ per-dataset (ERDDAP-INFO) | n/a (open) | CATALOG VERIFIED |
| INCOIS PFZ | ✅ page (`PfzAdvisory`) | ✗ geometry (HAR-A) | ✗ | ENTRY PAGE ONLY |
| INCOIS OSF/HWA/surge/TEWS/tide/TCHP | ✗ | ✗ | ✗ | HAR-B/C/D |
| INCOIS LAS/ESSDP | ⚠ present | ✗ | ✗ | HAR-F |
| MOSDAC search | ✅ V4 | ✅ envelope+error schema | n/a (open) | SEARCH VERIFIED |
| MOSDAC open-data pages | ✅ page metadata (§6.3) | ⚠ page only | ✗ (AUTH-A) | PAGE METADATA |
| MOSDAC download/mdapi | ✅ official client source (V5) | ✅ request/error contract from source | ✗ live success/file bytes (AUTH-A) | SOURCE VERIFIED / AUTH REQUIRED |

### 19.3 Outstanding verification actions (exact)

- **HAR-A (INCOIS PFZ):** From `https://incois.gov.in/MarineFisheries/PfzAdvisory`, DevTools → Network → XHR/Fetch → record every JSON/GeoJSON/WFS/NetCDF request; export HAR; confirm geometry endpoint + schema. **P0 prerequisite.**
- **HAR-B (INCOIS OSF):** Capture the XHR/dataset URL serving current/wave/swell/wind-wave grids; confirm ERDDAP griddap vs separate service.
- **HAR-C (INCOIS HWA / storm surge / TEWS / TCHP):** Capture HWA/swell JSON, storm-surge product, TEWS bulletin, TCHP feed URLs + schemas.
- **HAR-D (INCOIS tide):** Confirm tide-gauge **observation** endpoint and whether a **prediction** feed exists.
- **HAR-E (IMD radar/GIS):** Capture any numeric radar/GIS service; else remains VISUAL-ONLY.
- **HAR-F (INCOIS LAS/ESSDP):** Capture per-product data protocol behind LAS/ESSDP UIs.
- **ERDDAP-INFO (INCOIS):** For each needed dataset, `GET /erddap/info/<id>/index.json` to resolve variables/units/axes/coverage/resolution.
- **REG-A (IMD):** Register for `api.imd.gov.in` token; document auth flow and marine/NWP endpoint list.
- **AUTH-A (MOSDAC):** Exercise `gettoken`→`download` with issued credentials in a controlled test; confirm token + record-id contract end-to-end.
- **OBS-CAP (IMD):** Observe the CAP feed over time to enumerate the event families IMD actually issues.
- **OBS-BUOY (IMD):** Observe successive buoy-page fetches to derive update cadence and enumerate station IDs.
- **OSDD-A (MOSDAC):** Fetch `https://mosdac.gov.in/apios/osdd.xml` to confirm descriptor contents.
- **SIG-A (IMD CAP):** Determine CAP `ds:Signature` key retrieval/verification procedure.
- **DSID-\* (MOSDAC):** Resolve exact `datasetId`s for chlorophyll/current/SSS/subsurface/eddies/rainfall via search API.

---

## 20. Open Questions

1. **CAP signature trust chain (SIG-A):** Which key/certificate verifies IMD CAP `ds:Signature`, and how is it retrieved/rotated? Required before CAP is trusted for safety-critical automation.
2. **CAP event coverage (OBS-CAP):** Which event families does IMD actually issue into `in-imd-en`? (Do not assume all CAP-representable families appear.)
3. **ERDDAP per-dataset schema (ERDDAP-INFO):** Exact variable names, units, axes, coverage, resolution, and QC-flag variables for each of the 16 datasets?
4. **PFZ machine geometry (HAR-A):** Exact endpoint, format (GeoJSON/WFS/shapefile/NetCDF), auth, and update cadence?
5. **OSF data protocol (HAR-B):** Is OSF served via ERDDAP griddap or a bespoke service? What are variable names/units/step?
6. **Tide prediction (HAR-D):** Does INCOIS expose a machine **prediction** feed at all, or only observations?
7. **TEWS/HWA/surge schemas (HAR-C):** Exact feed formats and authenticity/signature mechanisms (safety-critical)?
8. **MOSDAC download contract (AUTH-A):** End-to-end token → record-id → file bytes behavior and 429 handling under real credentials?
9. **MOSDAC open-data datasetIds (DSID-\*):** Which `datasetId`s correspond to the 0.25° current / HRSSS / eddies / subsurface open-data products?
10. **IMD numeric NWP (REG-A):** After registration, what marine endpoints exist and in what format (JSON vs GRIB2)?
11. **Licensing/redistribution:** For each provider, does the observed policy permit derived redistribution/commercial use? (Legal/procurement action, not asserted here.)
12. **GAP sourcing (out of scope now):** For EEZ/boundaries/MPAs/ports/shipping-lanes/bathymetry/fisheries-catch, which authoritative external datasets will be adopted later? (No in-scope provider supplies them.)

---

## 21. Recommended Next Build Step

**Immediate next step:** Stand up the **registry + normalization core**, then implement the **IMD CAP connector (§17.1.1)** as the first end-to-end vertical slice, because it is the only fully verified, public-domain, machine-readable, signed feed.

Sequence:

1. **Registry + normalization core.** Dataset registry (requirements §17) + canonical dictionary (§7) with timestamp/CRS/longitude/direction/scale-offset-fill utilities (§8–§10). No source-specific logic leaks into the public model.
2. **P0-A — IMD CAP connector (§17.1.1).** Poll RSS → fetch CAP 1.2 → verify `ds:Signature` (resolve SIG-A) → parse fields → polygon `lat,lon`→GeoJSON (swap+close) → `warning` entity → PostGIS + NATS `alert.*` events. Proves ingest→normalize→store→event→dashboard. Enumerate real event coverage (OBS-CAP) rather than assuming families.
3. **P0-B — INCOIS ERDDAP connector (§17.1.2).** Run ERDDAP-INFO per needed dataset to resolve variables/units/axes, then griddap/tabledap bbox+time subsets. Deliver first numeric params: chlorophyll (`IRS_chlorophyll_datasets`), SST (`NOAA_AVHRR_AMSR_datasets`, `incois_argo_sst_weekly`), ARGO (`Indian_ARGO_Floats`), scatterometer wind (`ascat_daily_datasets`). Bundle the GlobalSign intermediate; never disable TLS.
4. **P0-C — MOSDAC search → registry (§17.1.3).** Populate catalog/registry and bbox candidates from `datasets.json`; mark all product-byte retrieval download-blocked (AUTH-A); client contract is verified (V5). Separate gallery quicklooks (VISUAL-ONLY).
5. **P0-prereq — Execute HAR-A (PFZ).** Capture PFZ machine geometry endpoint/schema. Only after success implement `incois_pfz` and promote nearest-PFZ/suitability inputs.
6. **P1 verification wave.** HAR-B (OSF), HAR-C (HWA/surge/TEWS/TCHP), HAR-D (tide), REG-A (IMD), AUTH-A (MOSDAC live authenticated download). Enable connectors as each is confirmed.
7. **Derived products, gated by inputs (§3.9).** Turn on alert-expiration & hazard-proximity (CAP, ready); favourable SST+CHL regions (once both ingested); currents speed/dir and sea-state (after HAR-B); anomalies (after baseline accumulation); marine-risk/suitability/safe-window as inputs verify — always exposing factors and provenance.
8. **Gap handling.** Keep geofence/routing/bathymetry/fisheries schemas ready but **empty of fabricated data**; authoritative external sourcing is out of current three-provider scope (§15).

### 21.1 P0 exit criteria
- IMD CAP alerts flowing to PostGIS + NATS with signature verification, correct GeoJSON geometry, UTC time semantics, and measured (not assumed) event coverage.
- ≥1 INCOIS ERDDAP dataset ingested with resolved variable schema (ERDDAP-INFO), units normalized, QC flags retained, freshness classified.
- MOSDAC catalog reflected in the registry with download items marked auth-blocked (AUTH-A), with source-verified client contracts (V5).
- HAR-A completed or explicitly tracked as the gating item before any PFZ capability is advertised as ready.

---

### Appendix A — Evidence URLs (official)

- IMD CAP RSS (public domain): `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml`
- IMD CAP item (example, signed CAP 1.2): `https://cap-sources.s3.amazonaws.com/in-imd-en/2026-09-03-07-21-21.xml`
- IMD buoy obs (HTML): `https://mausam.imd.gov.in/imd_latest/contents/buoy_obs.php?id=<stationId>`
- IMD API (registration/token): `https://api.imd.gov.in`
- INCOIS ERDDAP catalog: `https://erddap.incois.gov.in/erddap/info/index.json`
- INCOIS per-dataset info (template): `https://erddap.incois.gov.in/erddap/info/<datasetId>/index.json`
- INCOIS PFZ advisory (wire-verified entry page): `https://incois.gov.in/MarineFisheries/PfzAdvisory`
- MOSDAC search: `https://mosdac.gov.in/apios/datasets.json`
- MOSDAC OpenSearch descriptor: `https://mosdac.gov.in/apios/osdd.xml`
- MOSDAC official client package: `https://www.mosdac.gov.in/software/mdapi.zip`
- MOSDAC token/download: `https://mosdac.gov.in/download_api/{gettoken,check-internet,download,refresh-token,logout}`

### Appendix B — Licensing posture statement
For every source above, this document records the **observed provider policy** (published copyright,
registration, payment, or redistribution notices). It makes **no legal interpretation**. Redistribution/commercial-use
clearance for IMD DSP/API, INCOIS (possibly chargeable bulk data), and MOSDAC (account-gated downloads) is a
separate legal/procurement action to be completed before production redistribution.

### Appendix C — Corrections applied in this revision
1. **HRSSS** corrected to **High Resolution Sea Surface Salinity** (was mislabeled "High Resolution SST").
2. **MOSDAC official client** re-downloaded and inspected (V5): `check-internet` is `GET` with JSON `{datasetId}`, download is `GET?id=<record_id>` with Bearer auth, and refresh/logout payloads and error/retry behavior are documented exactly; only live authenticated success remains AUTH-A.
3. **ERDDAP** catalog presence explicitly distinguished from per-dataset data/schema verification throughout.
4. **CAP event coverage** stated as *whatever IMD actually issues* (OBS-CAP), not "all families present because CAP can represent them".
5. **PFZ entry page** set to the wire-verified `https://incois.gov.in/MarineFisheries/PfzAdvisory`; guessed 404 portal paths removed.
6. **Visualization-only table** uses exactly the seven required columns.
7. **HTTP contracts** added per provider for every verified interface (§4, §5.0, §6.2/§6.2.1).
8. **Individual connector YAML** provided for each usable verified interface/product; disabled candidates grouped only with explicit per-component blockers.
9. **MOSDAC open-data page metadata** included (0.25° daily global current; HRSSS 10 km BoB / six-month cadence / historical range; eddies weekly BoB; subsurface 25 km/10 m BoB), distinguished from authenticated file retrieval.
10. **Exact mdapi search response + 429 error schema** and the **16 INCOIS dataset IDs** with tested-vs-template query examples included.
11. **No additional source introduced as a solution**; all gaps remain marked (§15).

*End of source_mapping.md*


---

## Source Expansion — Geospatial and Fisheries

> Added 2026-09-04. Research to resolve SOURCE_GAP items identified in IMPLEMENTATION_STATUS.md.
> Full details in `SOURCE_EXPANSION_REPORT.md`.

### EEZ / Maritime Boundaries

| Status | Current | Candidate | Verified | Recommended |
|---|---|---|---|---|
| Previous | SOURCE_GAP | — | — | — |
| **New** | PARTIALLY_RESOLVED | Marine Regions / VLIZ v12 | YES (GeoPackage/SHP, CC-BY, India EEZ MRGID 8920) | USE as SCIENTIFIC_REFERENCE; NOT legal/authoritative |

- **Machine-readable:** YES — GeoPackage + Shapefile download, no auth
- **Authority:** SCIENTIFIC_REFERENCE (VLIZ/Flanders Marine Institute), NOT Government of India
- **GoI official boundary:** NOT publicly downloadable as GIS data (INHD controls ENC)
- **Remaining limitation:** System must carry warning for legal/safety-critical use

### Restricted Zones / MPAs

| Status | Current | Candidate | Verified | Recommended |
|---|---|---|---|---|
| Previous | SOURCE_GAP | — | — | — |
| **New** | PARTIALLY_RESOLVED | WDPA (Protected Planet) | YES (India: 672 PAs, 68 marine, polygon+point) | USE as OFFICIAL_REFERENCE; non-commercial license |

- **Machine-readable:** YES — Shapefile/GDB/CSV download from protectedplanet.net
- **Authority:** OFFICIAL_REFERENCE (UNEP-WCMC/IUCN, compiled from government submissions including MoEFCC)
- **License:** Non-commercial free; commercial requires IBAT
- **Remaining limitation:** Some MPAs are point-only (no polygon boundary)

### Ports / Harbours

| Status | Current | Candidate | Verified | Recommended |
|---|---|---|---|---|
| Previous | SOURCE_GAP | — | — | — |
| **New** | **RESOLVED** | NGA World Port Index Pub 150 | YES (CSV/JSON, public domain, ~3800 ports, India covered) | USE — public domain, comprehensive |

- **Machine-readable:** YES — CSV with lat/lon, 110+ attributes per port
- **Authority:** OFFICIAL_REFERENCE (US Government NGA publication)
- **License:** Public domain (US Government work)
- **India coverage:** All 13 major ports + minor ports

### Shipping Lanes

| Status | Current | Candidate | Verified | Recommended |
|---|---|---|---|---|
| Previous | SOURCE_GAP | — | — | — |
| **New** | EXTERNAL_SOURCE_REQUIRED | INHD ENC (S-57) | NOT publicly downloadable | KEEP GAP — navigation-grade data requires INHD access |

- **No public machine-readable source** for Indian shipping lanes / TSS
- DG Shipping publishes TSS regulations as PDF circulars, not GIS
- INHD ENC is the only authoritative source (controlled distribution)

### Bathymetry

| Status | Current | Candidate | Verified | Recommended |
|---|---|---|---|---|
| Previous | SOURCE_GAP | — | — | — |
| **New** | PARTIALLY_RESOLVED | GEBCO 2026 Grid | YES (NetCDF/GeoTIFF, 15 arc-sec, public domain) | USE for analytics/planning; NOT navigation-grade |

- **Machine-readable:** YES — NetCDF global + GeoTIFF tiles
- **Authority:** SCIENTIFIC_REFERENCE (IHO/IOC joint project)
- **Resolution:** 15 arc-second (~450m)
- **NOT for navigation** — GEBCO explicitly states this
- **Suitable for:** route-cost estimation, depth visualization, shallow-water flagging (approximate)

### Fisheries Catch / Productivity

| Status | Current | Candidate | Verified | Recommended |
|---|---|---|---|---|
| Previous | SOURCE_GAP | — | — | — |
| **New** | PARTIALLY_RESOLVED | CMFRI annual publications | YES (PDF download, 2015-2025) | DIGITIZE PDF tables or request NMFDC access |

- **Machine-readable:** NO — PDF publication only
- **Authority:** AUTHORITATIVE (ICAR-CMFRI is India's official marine fisheries research institute)
- **Content:** Species × state × gear × landing (tonnes), annual 2015-2025
- **Action required:** Extract tables from PDF to CSV, or contact CMFRI for NMFDC structured data

### TiTiler

| Status | Current | Candidate | Verified | Recommended |
|---|---|---|---|---|
| Previous | BLOCKED_ON_PREREQ | — | — | — |
| **New** | IMPLEMENTATION_DEPENDENCY | N/A (internal) | N/A | Add TiTiler to compose.yaml + generate COGs from ingested rasters |

- **Not a source gap** — infrastructure dependency
- COG writer: implemented (`storage/writers.py`)
- TiTiler image: `ghcr.io/developmentseed/titiler:0.18.4`
