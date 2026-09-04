# Marine Data Engine — Source Expansion Report

> **Date:** 2026-09-04 · **Purpose:** Resolve SOURCE_GAP items through authoritative source identification
> **Method:** Web research + endpoint verification + documentation review

---

## Executive Summary

Of the 7 items classified as SOURCE_GAP or BLOCKED_ON_PREREQ:

| # | Capability | Previous Status | **New Status** | Source Found | Action |
|---|---|---|---|---|---|
| 1 | EEZ / maritime boundaries | SOURCE_GAP | **PARTIALLY_RESOLVED** | Marine Regions / VLIZ (CC-BY) | BUILD AFTER SOURCE VERIFICATION |
| 2 | Restricted zones / MPAs | SOURCE_GAP | **PARTIALLY_RESOLVED** | WDPA / Protected Planet (non-commercial) | BUILD AFTER SOURCE VERIFICATION |
| 3 | Ports / harbours | SOURCE_GAP | **RESOLVED** | NGA World Port Index (public domain) | BUILD NOW |
| 4 | Shipping lanes | SOURCE_GAP | **EXTERNAL_SOURCE_REQUIRED** | INHD ENC (restricted) | KEEP SOURCE GAP (navigation-grade) |
| 5 | Bathymetry | SOURCE_GAP | **PARTIALLY_RESOLVED** | GEBCO 2026 (analytics-grade) | BUILD NOW (analytics layer) |
| 6 | Fisheries catch/productivity | SOURCE_GAP | **PARTIALLY_RESOLVED** | CMFRI annual publications (PDF) | BUILD AFTER SOURCE VERIFICATION |
| 7 | TiTiler raster tiles | BLOCKED_ON_PREREQ | **IMPLEMENTATION_DEPENDENCY** | N/A (internal) | INTERNAL IMPLEMENTATION TASK |

**4 of 7 items can be actioned now.** 2 require further source verification. 1 remains a genuine gap for navigation-grade data.

---

## 1. EEZ / Maritime Boundaries

### Current status: SOURCE_GAP
### New status: PARTIALLY_RESOLVED

### Candidate sources investigated

#### A. Flanders Marine Institute — Marine Regions (VLIZ)

```yaml
capability: EEZ / maritime boundaries
authority: Flanders Marine Institute (VLIZ)
dataset: Maritime Boundaries Geodatabase v12
url: https://www.marineregions.org/downloads.php
endpoint: Direct download (GeoPackage, Shapefile, KML)
access_method: HTTP download (no auth required)
auth: None
format: GeoPackage, Shapefile, KML
geometry: Polygon (EEZ, Territorial Sea, Contiguous Zone, Internal Waters, Archipelagic Waters)
crs: EPSG:4326 (WGS84) and 0-360 degree variant
coverage: Global (includes India EEZ, TS, CZ)
resolution: High (detailed coastline-derived boundaries)
temporal_resolution: Versioned releases (~annual)
update_frequency: ~annual (v12 released 2023-10-25)
license: CC-BY 4.0
redistribution: Yes, with attribution
authority_level: SCIENTIFIC_REFERENCE
navigation_suitable: NO — derived from UNCLOS provisions and coastline proxy, not official hydrographic survey. Disclaimer on site.
analytics_suitable: YES — widely used in marine science, fisheries management, biogeography. Cited by FAO, ICES, and scientific literature.
verification_status: VERIFIED (download page confirmed, formats confirmed, India coverage confirmed)
notes: |
  Includes EEZ, TS (12nm), CZ (24nm), Internal Waters, Archipelagic Waters.
  India's EEZ polygon is present (MRGID 8920, ~2.02M km²).
  NOT an official Government of India legal boundary.
  Government of India maritime boundary shapefiles not found as public download.
```

#### B. Government of India — Survey of India / National Hydrographic Office

```yaml
capability: EEZ / maritime boundaries
authority: Indian Naval Hydrographic Department (INHD)
dataset: Official EEZ / maritime boundaries
url: https://hydrobharat.gov.in/
endpoint: UNKNOWN — no public GIS download found
access_method: NOT MACHINE READABLE (website only)
auth: N/A
format: N/A (official charts are restricted/controlled)
verification_status: DISCOVERED (website exists; no public polygon download)
authority_level: AUTHORITATIVE (Government of India)
navigation_suitable: Would be authoritative if available
analytics_suitable: N/A — not downloadable
notes: |
  INHD is the nodal agency for hydrographic surveys and nautical charting.
  Official maritime boundary geometry is NOT publicly downloadable as GIS data.
  ENC (Electronic Navigation Charts) are controlled products.
  For LEGAL boundary disputes, only official GoI sources are authoritative.
```

### Recommendation

**BUILD AFTER SOURCE VERIFICATION** using Marine Regions/VLIZ data as an **analytical/reference** layer. Clearly label as `authority_level: SCIENTIFIC_REFERENCE` — NOT legal/authoritative. The system must distinguish this from an official GoI boundary.

### Remaining limitation
No official Government of India maritime boundary GIS download exists publicly. For legal/safety-critical geofencing, the Marine Regions layer should carry a warning: "Reference boundary — not an official Government of India legal boundary."

---

## 2. Restricted Zones / MPAs / Ecologically Sensitive Areas

### Current status: SOURCE_GAP
### New status: PARTIALLY_RESOLVED

### Candidate sources investigated

#### A. WDPA — World Database on Protected Areas (Protected Planet / UNEP-WCMC)

```yaml
capability: Marine Protected Areas / restricted zones
authority: UNEP-WCMC & IUCN
dataset: World Database on Protected Areas (WDPA)
url: https://www.protectedplanet.net/
endpoint: Country download (India) + API (v4)
access_method: HTTP download (Shapefile, GDB, CSV) + REST API
auth: API requires token (free for non-commercial); bulk download requires acceptance of terms
format: Shapefile, File Geodatabase, CSV (polygon + point)
geometry: Polygon (where boundaries reported) + Point (centroid where polygon unavailable)
crs: EPSG:4326
coverage: India — 672+ protected areas, 68 with marine component (as of 2021 factsheet)
resolution: Varies by source (some detailed polygons, some point-only)
update_frequency: Monthly
license: Non-commercial use free. Commercial use requires IBAT license.
redistribution: Non-commercial only; check terms for derivative works.
authority_level: OFFICIAL_REFERENCE (compiled from government submissions worldwide)
navigation_suitable: NO — PA boundaries are management boundaries, not navigation charts
analytics_suitable: YES — standard reference for MPA analysis globally
verification_status: VERIFIED (India factsheet confirmed, download page confirmed)
notes: |
  WDPA India data: 672 PAs, 68 marine. Includes National Parks (Gulf of Mannar,
  Mahatma Gandhi Marine National Park), Wildlife Sanctuaries (Gahirmatha,
  Malvan, Bhitarkanika), Biosphere Reserves.
  Some areas have detailed polygon geometry; some are point-only.
  MoEFCC is the Indian government source that submits data to WDPA.
  No direct MoEFCC GIS download portal found.
  API is non-commercial only.
```

#### B. WCS India — BlueMAP-India

```yaml
capability: Marine Protected Areas
authority: Wildlife Conservation Society India
dataset: BlueMAP-India
url: https://india.wcs.org/Resources/BlueMAP-India
verification_status: DISCOVERED (website exists; machine-readable download not confirmed)
notes: Maps and analyses of India MPAs. May provide useful supplementary information.
```

### Recommendation

**BUILD AFTER SOURCE VERIFICATION** using WDPA data. Download India-filtered dataset. Ingest polygons into `marine_zone` table with `zone_type='mpa'`. Non-commercial license limits redistribution — document this.

### Remaining limitation
Some India MPAs in WDPA are point-only (no polygon boundary). No direct MoEFCC GIS portal found. Legal establishment boundaries require gazette notifications, not a GIS download.

---

## 3. Ports / Harbours

### Current status: SOURCE_GAP
### New status: RESOLVED

### Candidate sources investigated

#### A. NGA World Port Index (Pub 150)

```yaml
capability: Ports / harbours
authority: US National Geospatial-Intelligence Agency (NGA)
dataset: World Port Index, Publication 150
url: https://msi.nga.mil/Publications/WPI
endpoint: CSV/shapefile download + ArcGIS Online
access_method: HTTP download (no auth)
auth: None
format: CSV (with lat/lon), Shapefile on ArcGIS Online
geometry: Point (lat/lon per port)
crs: EPSG:4326
coverage: ~3,800 ports worldwide. India: 13 major ports + many minor ports included.
resolution: Port-level point locations
update_frequency: Periodic (maintained by NGA)
license: US Government public domain (no copyright)
redistribution: Yes (public domain)
authority_level: OFFICIAL_REFERENCE (US Government publication, used by IMO/IHO)
navigation_suitable: YES for port identification and location. NOT a substitute for approach charts.
analytics_suitable: YES — standard maritime reference, 110+ attributes per port.
verification_status: VERIFIED (GitHub mirror confirmed with 5,410 ports JSON; NGA official download page exists)
notes: |
  Each port record includes: name, country, coordinates, harbor size/type,
  max vessel size, depth, shelter, tide info, pilotage, facilities, ISPS status.
  India ports included: Mumbai, JNPT, Chennai, Kolkata, Cochin, Visakhapatnam,
  Tuticorin, Kandla, Mormugao, Paradip, New Mangalore, Ennore, etc.
  GitHub mirror: https://github.com/tayljordan/ports (5,410 ports JSON, 2019 edition)
```

#### B. Ministry of Ports, Shipping and Waterways — Basic Port Statistics

```yaml
capability: Ports / harbours
authority: Ministry of Ports, Shipping and Waterways, Government of India
dataset: Basic Port Statistics (BPS)
url: https://shipmin.gov.in/division/transport-research
format: PDF (annual publication)
verification_status: VERIFIED (BPS 2024-25 PDF available)
machine_readable: NO (PDF tables, not GIS data)
notes: |
  Lists all major (13) and non-major (200+) ports.
  Contains port names, locations (state-level), cargo volumes, infrastructure.
  NOT machine-readable GIS data. Would require manual extraction or OCR.
```

### Recommendation

**BUILD NOW** using NGA World Port Index. Public domain, machine-readable (CSV with coordinates), comprehensive India coverage. Ingest into `port` table. Supplement with fishing harbour coordinates from CMFRI if available.

---

## 4. Shipping Lanes / Navigation Constraints

### Current status: SOURCE_GAP
### New status: EXTERNAL_SOURCE_REQUIRED

### Candidate sources investigated

#### A. Indian Naval Hydrographic Department (INHD) — ENC / Nautical Charts

```yaml
capability: Shipping lanes / Traffic Separation Schemes
authority: INHD (Chief Hydrographer to Government of India)
url: https://hydrobharat.gov.in/
format: S-57 ENC (IHO standard)
access_method: Controlled distribution (not public download)
auth: Required (official channel)
verification_status: DISCOVERED (website confirmed; no public GIS download)
notes: |
  Official TSS (Traffic Separation Schemes) are gazetted by DG Shipping.
  Gulf of Kutch TSS documented in MS Notice circulars (PDF).
  S-57 ENC data contains TSS, shipping lanes, anchorage areas, fairways.
  This data is NOT freely downloadable — it's controlled navigation data.
  This is the ONLY authoritative source for navigation-grade shipping lanes in Indian waters.
```

#### B. OpenStreetMap (rejected for navigation)

```yaml
capability: Shipping lanes
authority: Community-sourced
authority_level: COMMUNITY_REFERENCE
navigation_suitable: NO — explicitly NOT suitable for navigation.
analytics_suitable: LIMITED — may show approximate routes but not authoritative.
verification_status: N/A (rejected for this use case)
```

### Recommendation

**KEEP SOURCE GAP** for navigation-grade shipping lane data. INHD ENC data is the only authoritative source and is not publicly downloadable. The system should clearly state: "Navigation-grade shipping lane data requires Indian Naval Hydrographic Department ENC products."

---

## 5. Bathymetry

### Current status: SOURCE_GAP
### New status: PARTIALLY_RESOLVED

### Candidate sources investigated

#### A. GEBCO — General Bathymetric Chart of the Oceans

```yaml
capability: Bathymetry
authority: IHO/IOC (via Nippon Foundation-GEBCO Seabed 2030)
dataset: GEBCO_2026 Grid
url: https://www.gebco.net/data_and_products/gridded_bathymetry_data/
endpoint: HTTP download (NetCDF, GeoTIFF, Esri ASCII)
access_method: Direct download (no auth)
auth: None
format: NetCDF (global), GeoTIFF (tiles)
geometry: Raster grid
crs: EPSG:4326
coverage: Global (Indian Ocean fully covered)
resolution: 15 arc-second (~450m at equator)
temporal_resolution: Annual grid releases
update_frequency: Annual (GEBCO_2026 latest)
license: Public domain / open (terms on gebco.net)
redistribution: Yes
authority_level: SCIENTIFIC_REFERENCE (IHO/IOC authoritative scientific dataset)
navigation_suitable: NO — explicitly stated. "GEBCO data should NOT be used for navigation." Scientific/reference only.
analytics_suitable: YES — standard for ocean science, route-cost estimation, depth-aware planning, visualization.
verification_status: VERIFIED (download confirmed via NOAA repository and gebco.net)
notes: |
  15 arc-second = ~450m resolution. Not navigation-grade.
  Suitable for: planning, analysis, visualization, route-cost estimation,
  shallow-water area identification (approximate), scientific research.
  NOT suitable for: vessel draft clearance, harbour approach, chart-replacement.
  Can be processed to COG for TiTiler serving.
```

#### B. INHD — Official nautical chart bathymetry

```yaml
capability: Navigation-grade bathymetry
authority: Indian Naval Hydrographic Department
verification_status: DISCOVERED (not publicly downloadable)
notes: Official survey data. Controlled distribution through ENC/paper charts.
```

### Recommendation

**BUILD NOW** for the analytics/reference layer using GEBCO. Download the Indian Ocean tile (NetCDF/GeoTIFF), ingest into `bathymetry` table, process to COG for tile serving. Clearly label as "SCIENTIFIC_REFERENCE — not for navigation." The route service can use this for cost estimation, but must carry a warning.

---

## 6. Fisheries Catch / Productivity

### Current status: SOURCE_GAP
### New status: PARTIALLY_RESOLVED

### Candidate sources investigated

#### A. ICAR-CMFRI — Marine Fish Landings in India (annual publication)

```yaml
capability: Fisheries catch / landings / CPUE
authority: ICAR-Central Marine Fisheries Research Institute
dataset: Marine Fish Landings in India (annual series: 2015-2025)
url: https://eprints.cmfri.org.in/ (search "Marine Fish Landings")
endpoint: PDF download (no API)
access_method: HTTP download of PDF publications
auth: None
format: PDF (tables with species × state × gear × landing data)
geometry: State-level / zone-level aggregation (not spatial points)
crs: N/A (tabular, not GIS)
coverage: All India maritime states (9 states + 2 UTs)
resolution: Species-level, state-level, gear-level, annual/quarterly
update_frequency: Annual (consistently published 2015-2025)
license: ICAR research data — "reused with due citation credentials"
redistribution: With citation
authority_level: AUTHORITATIVE (CMFRI is the official national marine fisheries research institute)
machine_readable: NO — PDF tables. Would require manual digitization or PDF extraction.
verification_status: VERIFIED (PDFs for 2022-2025 confirmed downloadable from eprints.cmfri.org.in)
notes: |
  CMFRI data is THE authoritative source for India marine fisheries statistics.
  Collected through stratified multi-stage random sampling across all coastline.
  Covers: landings (tonnes) by species, state, quarter, gear, craft type.
  Data for 2024: 42-page booklet with detailed tables.
  Data for 2025: 47-page booklet published.
  CMFRI also maintains NMFDC (National Marine Fisheries Data Centre).
  No public API or machine-readable download found — only PDF publications.
  A structured dataset would need to be extracted from these PDFs.
```

#### B. FAO Fisheries Statistics (global)

```yaml
capability: Global fisheries statistics
authority: FAO (Food and Agriculture Organization)
dataset: FAO Global Capture Production
url: https://www.fao.org/fishery/statistics-query/en/capture
access_method: Web query + CSV download
format: CSV
coverage: India (country-level aggregation)
verification_status: DISCOVERED (query interface exists)
authority_level: OFFICIAL_REFERENCE (international)
notes: Country-level only; less granular than CMFRI state/species data.
```

### Recommendation

**BUILD AFTER SOURCE VERIFICATION.** CMFRI is the authoritative source but data is PDF-only. Two paths:

1. **Manual digitization** — extract tables from the annual PDFs into structured CSV/JSON for ingestion. This is a one-time effort per year.
2. **Contact CMFRI** — request machine-readable access to the NMFDC (National Marine Fisheries Data Centre). CMFRI may provide structured data on request.

Until structured data is available, the system can:
- Store the schema and service layer (already built)
- Document CMFRI as the authoritative source
- NOT claim causal attribution from environmental data alone

---

## 7. TiTiler Raster Tiles

### Current status: BLOCKED_ON_PREREQ
### New status: IMPLEMENTATION_DEPENDENCY

This is NOT a source gap. The prerequisite chain is:

```text
Source raster (MOSDAC SST HDF5, GEBCO NetCDF, etc.)
  → Scientific processing (xarray/rasterio)
  → COG generation (write_cog in storage/writers.py — IMPLEMENTED)
  → Upload to MinIO (raw_store — IMPLEMENTED)
  → TiTiler deployment (Docker container pointing at MinIO)
  → GET /v1/tiles/{layer}/{z}/{x}/{y}
```

Current state:
- COG writer: **IMPLEMENTED** (`storage/writers.py`)
- MinIO: **IMPLEMENTED** (compose.yaml, raw_store)
- Tile endpoint: **IMPLEMENTED** (HTTP 501 placeholder)
- TiTiler container: **NOT CONFIGURED** in compose.yaml
- COG products: **NOT GENERATED** (no source raster ingested yet)

### Recommendation

**INTERNAL IMPLEMENTATION TASK.** Add TiTiler to compose.yaml pointing at the MinIO buckets. When any source raster is ingested and converted to COG (e.g., GEBCO bathymetry), the tile endpoint can serve it. No external source needed.

```yaml
# compose.yaml addition
titiler:
  image: ghcr.io/developmentseed/titiler:0.18.4
  environment:
    AWS_ACCESS_KEY_ID: ${S3_ACCESS_KEY_ID}
    AWS_SECRET_ACCESS_KEY: ${S3_SECRET_ACCESS_KEY}
    AWS_S3_ENDPOINT: ${S3_ENDPOINT_URL}
    AWS_HTTPS: "NO"
    AWS_VIRTUAL_HOSTING: "FALSE"
  ports:
    - "8888:8000"
  depends_on:
    minio-init:
      condition: service_completed_successfully
```

---

## Source Quality Classification Summary

| Source | Authority Level | Navigation Suitable | Analytics Suitable |
|---|---|---|---|
| Marine Regions / VLIZ (EEZ v12) | SCIENTIFIC_REFERENCE | NO | YES |
| WDPA / Protected Planet (MPAs) | OFFICIAL_REFERENCE | NO | YES |
| NGA World Port Index (Pub 150) | OFFICIAL_REFERENCE | YES (port ID) | YES |
| INHD ENC (shipping lanes) | AUTHORITATIVE | YES | YES |
| GEBCO 2026 (bathymetry) | SCIENTIFIC_REFERENCE | NO (explicitly) | YES |
| CMFRI landings (fisheries) | AUTHORITATIVE | N/A | YES |
| FAO fisheries statistics | OFFICIAL_REFERENCE | N/A | YES |

---

## Final Reclassification Table

| Capability | Previous Status | New Status | Source | Authority | Machine Readable | Suitable For | Remaining Blocker |
|---|---|---|---|---|---|---|---|
| EEZ / maritime boundaries | SOURCE_GAP | **PARTIALLY_RESOLVED** | Marine Regions v12 | SCIENTIFIC_REFERENCE | YES (GeoPackage/SHP) | Analytics, reference, visualization | GoI legal boundary not publicly downloadable |
| Restricted zones / MPAs | SOURCE_GAP | **PARTIALLY_RESOLVED** | WDPA | OFFICIAL_REFERENCE | YES (SHP/GDB) | Analytics, MPA analysis | Non-commercial license; some areas point-only |
| Ports / harbours | SOURCE_GAP | **RESOLVED** | NGA WPI Pub 150 | OFFICIAL_REFERENCE | YES (CSV/JSON) | Port identification, planning | Fishing harbours may need CMFRI supplement |
| Shipping lanes | SOURCE_GAP | **EXTERNAL_SOURCE_REQUIRED** | INHD ENC (restricted) | AUTHORITATIVE | NO (controlled) | Navigation (if obtained) | ENC not publicly downloadable |
| Bathymetry | SOURCE_GAP | **PARTIALLY_RESOLVED** | GEBCO 2026 | SCIENTIFIC_REFERENCE | YES (NetCDF/GeoTIFF) | Analytics, planning, visualization, route-cost | NOT navigation-grade |
| Fisheries catch | SOURCE_GAP | **PARTIALLY_RESOLVED** | CMFRI annual publications | AUTHORITATIVE | NO (PDF only) | Trend analysis (after digitization) | Machine-readable access needed |
| TiTiler tiles | BLOCKED_ON_PREREQ | **IMPLEMENTATION_DEPENDENCY** | N/A (internal) | N/A | N/A | Raster map layers | Add TiTiler to compose + generate COGs |

---

## Concrete Next Actions

| # | Item | Action | Type | Effort |
|---|---|---|---|---|
| 1 | **Ports** | Download NGA WPI, parse JSON/CSV, ingest into `port` table | BUILD NOW | Small |
| 2 | **Bathymetry** | Download GEBCO Indian Ocean tile, process to COG, ingest into `bathymetry` | BUILD NOW | Medium |
| 3 | **TiTiler** | Add TiTiler container to compose.yaml, wire to MinIO | INTERNAL TASK | Small |
| 4 | **EEZ boundaries** | Download Marine Regions v12, extract India polygons, ingest into `marine_zone` | BUILD AFTER VERIFICATION | Medium |
| 5 | **MPAs** | Download WDPA India export, ingest marine PA polygons into `marine_zone` | BUILD AFTER VERIFICATION | Medium |
| 6 | **Fisheries** | Extract CMFRI PDF tables to structured data; or contact CMFRI for NMFDC access | BUILD AFTER VERIFICATION | Large |
| 7 | **Shipping lanes** | Cannot build without INHD ENC access; document as genuine gap | KEEP GAP | N/A |
