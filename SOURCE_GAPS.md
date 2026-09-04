# Source Gaps & Verification Actions

This document records, for the platform/operations layer, **exactly which
sources are usable today, which are blocked, and the precise action required to
unblock each one**. It is derived from the research artifact
[`source_mapping.md`](./source_mapping.md) (§2, §14, §15, §19, §20, §21) and the
requirements (`marine_data_layer_requirements.md` §25/§28, `prompt.md` §27/§28).

**Scope rule (three providers only):** IMD, INCOIS, MOSDAC. Where the three
providers do not cover a required parameter, the gap is **marked, never filled
with a fabricated or external dataset**. No additional provider is introduced as
a solution anywhere in this platform.

**Epistemics:** Anything not confirmed against a live response is written as
`UNKNOWN — requires verification (ACTION-ID)`. Assumed access/auth/format is
never recorded as fact. Licensing statements are **observed provider policy
only** — no legal interpretation is made here.

---

## 1. What is verified and usable today

| Interface | Provider | Status | Enabled in stack |
|---|---|---|---|
| CAP alerts (RSS index + signed CAP 1.2 items) | IMD | **VERIFIED (V1/V2)** — public-domain string observed | `imd_cap_alerts_poll` DAG + `worker-alerts` |
| ERDDAP catalog (16 dataset IDs) | INCOIS | **CATALOG VERIFIED (V3)**; per-dataset schema pending ERDDAP-INFO | `incois_erddap_ingest` DAG + `worker-ingest` |
| OpenSearch discovery API (`datasets.json`) | MOSDAC | **SEARCH VERIFIED (V4)**; downloads blocked (AUTH-A) | `mosdac_search_registry` DAG (catalog only) |
| Official `mdapi.py` download client contract | MOSDAC | **SOURCE VERIFIED (V5)**; live auth not exercised | connector spec only |

These are the only machine-readable access paths confirmed live this session.
Everything below is blocked or unverified and is kept **disabled** until the
named action is completed.

---

## 2. PFZ — the P0 prerequisite (HAR-A)

**INCOIS Potential Fishing Zone (PFZ)** is one of the most important domain
entities (requirements §9), but its machine geometry is **not verified**:

- Entry page (wire-verified): `https://incois.gov.in/MarineFisheries/PfzAdvisory`
- Machine geometry / XHR endpoint / format: **`UNKNOWN — requires verification (HAR-A)`**

**Disposition:** PFZ is a **P0 *prerequisite*, not a shippable P0 connector.**
The `incois_pfz` dataset is seeded in the registry as **DISABLED** and the `pfz`
table exists (SRID 4326) so nearest-PFZ / suitability inputs can be enabled the
moment HAR-A succeeds — but **no PFZ geometry is fabricated** in the meantime.

**HAR-A action (exact):** From `https://incois.gov.in/MarineFisheries/PfzAdvisory`,
open DevTools → Network → XHR/Fetch → record every JSON/GeoJSON/WFS/NetCDF
request → export HAR → confirm the geometry endpoint URL, format, auth, and
update cadence. Only after HAR-A is confirmed should the `incois_pfz` connector
be implemented and the registry row promoted.

---

## 3. All source gaps (marked, not filled)

### 3.1 In-scope but blocked/unverified (unblock via the named action)

| Gap | Requirement driver | Status | Action | Priority |
|---|---|---|---|---|
| PFZ machine geometry/XHR | PFZ, suitability | entry page only | **HAR-A** | **P0 prerequisite** |
| INCOIS OSF surface currents dataset | currents, routing | unverified | HAR-B | P1 |
| INCOIS OSF wave/swell/wind-wave dataset | waves, windows, routing | unverified | HAR-B | P1 |
| INCOIS HWA / swell alert JSON | high-wave/swell alert | unverified | HAR-C | P1 |
| INCOIS storm surge feed | storm surge | unverified | HAR-C | P1 |
| INCOIS TEWS tsunami feed | tsunami (safety-critical) | unverified | HAR-C | P1 |
| INCOIS tide **prediction** feed | tides, windows | unverified; may not exist as a feed | HAR-D | P1 |
| INCOIS TCHP | TCHP | unverified | HAR-C | P2 |
| INCOIS LAS / ESSDP data protocols | remote sensing/analysis | unverified | HAR-F | P2 |
| ERDDAP per-dataset schema (16 datasets) | SST/CHL/wind/ARGO numeric | catalog only | ERDDAP-INFO | P0 (before numeric ingest) |
| IMD structured cyclone (track/cone/intensity) | cyclone | blocked/unverified (RSMC) | REG-A / HAR | P1 (CAP polygon partial interim) |
| IMD numeric NWP (wind/rain/pressure/humidity) | weather | token-gated; public pages VISUAL-ONLY | REG-A | P1 |
| IMD authenticated API marine endpoints | weather, obs | 401/403 on legacy; token required | REG-A | P1 |
| IMD radar / GIS numeric service | radar | image tiles only | HAR-E | P2 |
| MOSDAC authenticated download (all products) | ocean/atmos numeric | search open; download not exercised | AUTH-A | P1 |
| MOSDAC open-data datasetIds (CHL/current/SSS/subsurface/eddies/rainfall) | numeric params | to resolve via search | DSID-* | P1 |
| IMD buoy update cadence + station IDs | in-situ obs | HTML pattern only | OBS-BUOY | P1 |
| CAP issued-event coverage | alert taxonomy | measured, not assumed | OBS-CAP | P1 |
| CAP `ds:Signature` trust chain | safety-critical trust | key retrieval unknown | SIG-A | P1 (before trusting CAP for automation) |
| MOSDAC OpenSearch descriptor | discovery | not fetched | OSDD-A | P2 |

### 3.2 Out of in-scope providers — hard GAPs (do **not** fabricate)

These are required by the requirements/geofencing/routing scope but are **not
supplied by any of IMD/INCOIS/MOSDAC**. The corresponding tables (`zone`,
`bathymetry`) exist in the schema so the capabilities work once an authoritative
external GIS dataset is sourced later — but they are intentionally **empty of
fabricated data**.

| Gap | Requirement driver | Disposition |
|---|---|---|
| EEZ / international maritime boundaries | geofence | **GAP — external authoritative GIS required later; do not fabricate** |
| Restricted zones / MPAs / ecologically sensitive zones | geofence | **GAP — do not fabricate** |
| Ports / harbours | reference | **GAP** |
| Shipping lanes | routing | **GAP** |
| Bathymetry / depth | routing, shallow-water safety | **GAP — do not infer depth from other parameters** |
| Fisheries catch / effort / productivity | fisheries analysis | **GAP — no productivity attribution claims until sourced** |

### 3.3 Build-dependencies (not provider gaps)

| Item | Note |
|---|---|
| Anomaly baselines (SST/CHL/current/wave/rainfall/pressure) | Not a source; requires retaining history over time before anomaly/percentile products are meaningful. |

---

## 4. Visualization-only sources (excluded from numeric ingest)

Per source_mapping §14, products returning only images/tiles/PDF with no
machine-readable numeric payload are **not** treated as data sources:

- IMD NWP / coastal-forecast charts (PNG/PDF) — use registered GRIB2 (REG-A) instead; do not OCR charts.
- IMD radar imagery (image tiles) — not numeric precipitation data.
- MOSDAC gallery quicklooks (PNG/GIF/JPG) — use the corresponding `.h5`/`.nc` product file instead.
- INCOIS portal / LAS / ESSDP rendered map views — capture the underlying XHR (HAR-A/B/F) or use ERDDAP.

---

## 5. Licensing / redistribution posture (observed only)

Recorded as the literal published provider policy; **no legal interpretation**.
Redistribution / commercial-use clearance is a separate legal/procurement action.

| Provider | Observed policy | Note |
|---|---|---|
| IMD CAP | RSS `<copyright>public domain</copyright>` (V1) | Confirm scope covers derived redistribution before commercial reliance. |
| IMD API / DSP | Registration + possible payment + license terms | Terms `UNKNOWN — verify (REG-A)`. |
| IMD buoy page | No explicit license string observed | Absence of a notice is **not** a grant; treat as restricted. |
| INCOIS ERDDAP / data | INCOIS data policy; bulk data **may be chargeable** | Cite published pricing/policy at access time. |
| INCOIS PFZ / advisories | INCOIS advisory policy | Reuse terms `UNKNOWN — verify (HAR-A)`. |
| MOSDAC search | Search open; `author=MOSDAC,SAC-ISRO,India` on results | Search-open ≠ redistribution grant. |
| MOSDAC download / open-data | Account-gated download | Download license `UNKNOWN — verify (AUTH-A)`. |

---

## 6. How this maps into the platform

- **Credentials blank ⇒ connector disabled.** `.env.example` ships `MOSDAC_*`
  and `IMD_API_TOKEN` blank; the corresponding registry rows are seeded
  `DISABLED`/`DEGRADED` so nothing attempts unverified authenticated access.
- **TLS:** INCOIS ERDDAP omits its intermediate cert (V3-TLS). Connectors must
  bundle the GlobalSign intermediate (`INCOIS_CA_BUNDLE`) and **never disable
  TLS verification**.
- **Schema ready, data empty:** `zone` and `bathymetry` tables exist for
  geofencing/routing but hold **no fabricated boundaries or depths**.
- **Safety-critical freshness:** CAP, tsunami, and surge datasets must never be
  served as fresh without an explicit age/status flag (requirements §16;
  `dataset_freshness` hypertable + `dataset_freshness_sweep` DAG).

---

## 7. Outstanding verification actions (quick reference)

| Action | Target |
|---|---|
| **HAR-A** | INCOIS PFZ machine geometry endpoint/schema (**P0 prerequisite**) |
| HAR-B | INCOIS OSF currents/waves/swell/wind-wave dataset URL + schema |
| HAR-C | INCOIS HWA / storm surge / TEWS / TCHP feeds + schemas |
| HAR-D | INCOIS tide observation endpoint + whether a prediction feed exists |
| HAR-E | IMD radar/GIS numeric service (else VISUAL-ONLY) |
| HAR-F | INCOIS LAS/ESSDP per-product data protocol |
| ERDDAP-INFO | Per-dataset variables/units/axes/coverage/resolution for the 16 IDs |
| REG-A | IMD `api.imd.gov.in` token + marine/NWP endpoint list |
| AUTH-A | MOSDAC `gettoken` → `download` end-to-end with real credentials |
| DSID-* | MOSDAC datasetIds for CHL/current/SSS/subsurface/eddies/rainfall |
| OBS-CAP | Enumerate the CAP event families IMD actually issues |
| OBS-BUOY | IMD buoy update cadence + station IDs |
| OSDD-A | MOSDAC OpenSearch descriptor contents |
| SIG-A | IMD CAP `ds:Signature` key retrieval/verification procedure |
