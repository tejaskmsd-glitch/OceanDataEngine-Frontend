# Marine Data Layer — Operations Dashboard

A lightweight **React + TypeScript + Vite** operations/observability dashboard for
the Marine Intelligence Data Layer. It is read-heavy and consumes the shared
FastAPI REST + WebSocket APIs directly — there is **no separate backend** and no
second data-access path.

This is an operational dashboard, not the end-user marine application and not a
conversational/AI UI.

## Features

- **Overview** — cards for healthy/stale/failed datasets, active/failed jobs,
  active alerts, last ingestion, plus a recent-processing table and jobs-by-type
  chart.
- **Datasets & freshness** — dataset registry with status, freshness/age, format,
  resolution, provider; searchable and filterable by status.
- **Jobs** — processing job list with status, timings, duration, worker, retries,
  and error detail; filterable by status.
- **Alerts** — active/recent marine warnings sorted by severity, with live
  updates via WebSocket and drill-down to lineage.
- **Map explorer** — Leaflet map overlaying PFZ polygons and warning geometries
  as toggleable GeoJSON layers, with an optional lat/lon/radius area query.
- **Lineage & evidence** — provenance drill-down against `/v1/evidence/{id}`
  showing sources, processing steps, quality, confidence, and the raw payload.

## Resilience

- Every view has explicit **loading / error / empty** states; previously loaded
  data stays visible during background refetches.
- The alert **WebSocket** reconnects with exponential backoff + jitter. When the
  stream is not connected, views automatically **fall back to faster polling**;
  when live, polling intervals widen.
- The API client tolerates both the canonical `{ data, meta, sources, ... }`
  envelope and bare payloads, and degrades gracefully (e.g. a missing `/v1/jobs`
  endpoint yields an empty list rather than an error).
- A top-level error boundary prevents any single view from blanking the app.

## API endpoints consumed

`GET /v1/health`, `GET /v1/data-health`, `GET /v1/datasets`,
`GET /v1/datasets/{id}/status`, `GET /v1/jobs` (optional), `GET /v1/alerts`,
`GET /v1/fishing/pfz`, `GET /v1/evidence/{request_id}`, and
`WS /v1/stream/alerts`.

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

| Variable            | Purpose                                                                 |
| ------------------- | ----------------------------------------------------------------------- |
| `VITE_API_BASE_URL` | REST base URL. Empty → same-origin relative requests (recommended).     |
| `VITE_WS_URL`       | WebSocket URL. Empty → derived from origin + `/v1/stream/alerts`.       |
| `VITE_API_TARGET`   | Dev-only proxy target for `/v1` REST + WS during `npm run dev`.          |

In development, `vite` proxies `/v1` (REST and WebSocket) to `VITE_API_TARGET`
(default `http://localhost:8000`), so the app can use same-origin relative URLs.

## Scripts

```bash
npm install         # install pinned dependencies
npm run dev         # start dev server (proxies /v1 to the FastAPI backend)
npm run build       # typecheck (tsc -b) + production build
npm run typecheck   # type-check only
npm run test        # run unit/component tests (Vitest)
npm run lint        # ESLint
```

## Stack

React 18, TypeScript 5 (strict), Vite 5, React Router 6, Leaflet + react-leaflet,
Recharts, Vitest + Testing Library. All dependency versions are pinned exactly.
