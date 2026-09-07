/**
 * Centralized API client for the OceanDataEngine backend.
 *
 * Design principles:
 * - Direct connection to backend via NEXT_PUBLIC_API_BASE_URL (defaults to http://localhost:8000)
 *   or via Next.js proxy /backend-api when running in browser.
 * - Defensive unrolling of the canonical response envelope.
 * - Categorized errors with HTTP status, URL, and server details.
 * - Honest representation of source gaps and availability states.
 */

import type {
  AdvisoryModel,
  AlertModel,
  DataHealthModel,
  DatasetModel,
  Envelope,
  EvidenceModel,
  FishingSuitabilityModel,
  ForecastModel,
  HealthData,
  JobModel,
  MarineRiskModel,
  ObservationModel,
  PFZModel,
  SafeRouteModel,
  SafeRouteRequest,
  StacCollection,
  StacItemCollection,
  ZoneModel,
} from "../types/api";

const IS_SERVER = typeof window === "undefined";

export const API_BASE_URL =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) ||
  "http://localhost:8000";

const DEFAULT_TIMEOUT_MS = 20_000;

export class ApiError extends Error {
  readonly status: number;
  readonly url: string;
  readonly detail?: string;

  constructor(message: string, status: number, url: string, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.url = url;
    this.detail = detail;
  }
}

export interface ApiResult<T> {
  data: T;
  envelope: Envelope<T> | null;
  warnings: string[];
  requestId?: string;
  isSourceUnavailable?: boolean;
}

function buildUrl(path: string, query?: Record<string, unknown>): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  // In the browser, we can either call the proxy /backend-api or direct API_BASE_URL
  const base = IS_SERVER ? API_BASE_URL : API_BASE_URL;
  const search = new URLSearchParams();
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      search.append(key, String(value));
    }
  }
  const qs = search.toString();
  return `${base}${normalizedPath}${qs ? `?${qs}` : ""}`;
}

async function request<T>(
  path: string,
  options: {
    method?: "GET" | "POST";
    body?: unknown;
    query?: Record<string, unknown>;
    signal?: AbortSignal;
    timeoutMs?: number;
  } = {}
): Promise<ApiResult<T>> {
  const url = buildUrl(path, options.query);
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(new DOMException("Request timed out", "TimeoutError")),
    options.timeoutMs ?? DEFAULT_TIMEOUT_MS
  );

  if (options.signal) {
    if (options.signal.aborted) controller.abort(options.signal.reason);
    else
      options.signal.addEventListener(
        "abort",
        () => controller.abort(options.signal?.reason),
        { once: true }
      );
  }

  try {
    const res = await fetch(url, {
      method: options.method || "GET",
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });

    if (!res.ok) {
      let detail = res.statusText;
      try {
        const errJson = (await res.json()) as { detail?: string; message?: string };
        detail = errJson.detail || errJson.message || detail;
      } catch {
        // Non-JSON error body
      }
      throw new ApiError(`API ${res.status}: ${detail}`, res.status, url, detail);
    }

    const json = (await res.json()) as unknown;

    // Check if canonical envelope
    if (json && typeof json === "object" && "data" in json && "meta" in json) {
      const envelope = json as Envelope<T>;
      const warnings = envelope.warnings || [];
      const isSourceUnavailable = warnings.some(
        (w) =>
          w.includes("SOURCE_NOT_INGESTED") ||
          w.includes("SOURCE_GAP") ||
          w.includes("NOT_AVAILABLE")
      );
      return {
        data: envelope.data,
        envelope,
        warnings,
        requestId: envelope.meta?.request_id,
        isSourceUnavailable,
      };
    }

    // Direct payload (e.g. STAC or raw responses)
    return {
      data: json as T,
      envelope: null,
      warnings: [],
      isSourceUnavailable: false,
    };
  } finally {
    clearTimeout(timeout);
  }
}

export interface QueryOpts {
  signal?: AbortSignal;
}

export const api = {
  // System
  async health(opts?: QueryOpts): Promise<HealthData> {
    const res = await request<HealthData>("/v1/health", { signal: opts?.signal });
    return res.data;
  },

  async dataHealth(opts?: QueryOpts): Promise<ApiResult<DataHealthModel[]>> {
    return request<DataHealthModel[]>("/v1/data-health", { signal: opts?.signal });
  },

  // Datasets
  async datasets(opts?: QueryOpts): Promise<ApiResult<DatasetModel[]>> {
    return request<DatasetModel[]>("/v1/datasets", { signal: opts?.signal });
  },

  async datasetStatus(key: string, opts?: QueryOpts): Promise<ApiResult<DatasetModel>> {
    return request<DatasetModel>(`/v1/datasets/${encodeURIComponent(key)}/status`, {
      signal: opts?.signal,
    });
  },

  async jobs(limit = 200, opts?: QueryOpts): Promise<ApiResult<JobModel[]>> {
    return request<JobModel[]>("/v1/jobs", {
      query: { limit },
      signal: opts?.signal,
    });
  },

  // Active Alerts
  async alerts(
    params?: {
      lat?: number;
      lon?: number;
      radius_km?: number;
      event_type?: string;
      active_only?: boolean;
      limit?: number;
    },
    opts?: QueryOpts
  ): Promise<ApiResult<AlertModel[]>> {
    return request<AlertModel[]>("/v1/alerts", {
      query: params,
      signal: opts?.signal,
    });
  },

  // Ocean Observations & Forecasts
  async oceanConditions(
    params: {
      lat: number;
      lon: number;
      radius_km?: number;
      time?: string;
    },
    opts?: QueryOpts
  ): Promise<ApiResult<ObservationModel[]>> {
    return request<ObservationModel[]>("/v1/ocean/conditions", {
      query: params,
      signal: opts?.signal,
    });
  },

  async oceanForecast(
    params: {
      lat: number;
      lon: number;
      radius_km?: number;
      time?: string;
    },
    opts?: QueryOpts
  ): Promise<ApiResult<ForecastModel[]>> {
    return request<ForecastModel[]>("/v1/ocean/forecast", {
      query: params,
      signal: opts?.signal,
    });
  },

  // Weather Observations & Forecasts
  async weatherConditions(
    params: {
      lat: number;
      lon: number;
      radius_km?: number;
      time?: string;
    },
    opts?: QueryOpts
  ): Promise<ApiResult<ObservationModel[]>> {
    return request<ObservationModel[]>("/v1/weather/conditions", {
      query: params,
      signal: opts?.signal,
    });
  },

  async weatherForecast(
    params: {
      lat: number;
      lon: number;
      radius_km?: number;
      time?: string;
    },
    opts?: QueryOpts
  ): Promise<ApiResult<ForecastModel[]>> {
    return request<ForecastModel[]>("/v1/weather/forecast", {
      query: params,
      signal: opts?.signal,
    });
  },

  // Fisheries
  async pfz(
    params: {
      lat: number;
      lon: number;
      radius_km?: number;
      include_expired?: boolean;
    },
    opts?: QueryOpts
  ): Promise<ApiResult<PFZModel[]>> {
    return request<PFZModel[]>("/v1/fishing/pfz", {
      query: params,
      signal: opts?.signal,
    });
  },

  async fishingAdvisories(
    params?: {
      lat?: number;
      lon?: number;
      radius_km?: number;
    },
    opts?: QueryOpts
  ): Promise<ApiResult<AdvisoryModel[]>> {
    return request<AdvisoryModel[]>("/v1/fishing/advisories", {
      query: params,
      signal: opts?.signal,
    });
  },

  async fishingSuitability(
    params: {
      lat: number;
      lon: number;
      radius_km?: number;
    },
    opts?: QueryOpts
  ): Promise<ApiResult<FishingSuitabilityModel>> {
    return request<FishingSuitabilityModel>("/v1/fishing/suitability", {
      query: params,
      signal: opts?.signal,
    });
  },

  // Tides
  async tides(
    params: {
      lat: number;
      lon: number;
      radius_km?: number;
      time?: string;
    },
    opts?: QueryOpts
  ): Promise<ApiResult<ObservationModel[]>> {
    return request<ObservationModel[]>("/v1/tides", {
      query: params,
      signal: opts?.signal,
    });
  },

  // Geofencing & Zones
  async geofenceCheck(
    lat: number,
    lon: number,
    opts?: QueryOpts
  ): Promise<ApiResult<ZoneModel[]>> {
    return request<ZoneModel[]>("/v1/geofence/check", {
      query: { lat, lon },
      signal: opts?.signal,
    });
  },

  async geofenceNearby(
    lat: number,
    lon: number,
    radius_km = 50,
    opts?: QueryOpts
  ): Promise<ApiResult<ZoneModel[]>> {
    return request<ZoneModel[]>("/v1/geofence/nearby", {
      query: { lat, lon, radius_km },
      signal: opts?.signal,
    });
  },

  async geofenceIntersections(
    geometry: any,
    opts?: QueryOpts
  ): Promise<ApiResult<ZoneModel[]>> {
    return request<ZoneModel[]>("/v1/geofence/intersections", {
      method: "POST",
      body: { geometry },
      signal: opts?.signal,
    });
  },

  // Risk Assessment
  async marineRisk(
    params: {
      lat: number;
      lon: number;
      radius_km?: number;
      time?: string;
      vessel_type?: string;
    },
    opts?: QueryOpts
  ): Promise<ApiResult<MarineRiskModel>> {
    return request<MarineRiskModel>("/v1/risk/marine", {
      query: params,
      signal: opts?.signal,
    });
  },

  // Safe Routing
  async safeRoutes(
    body: SafeRouteRequest,
    opts?: QueryOpts
  ): Promise<ApiResult<SafeRouteModel>> {
    return request<SafeRouteModel>("/v1/routes/safe", {
      method: "POST",
      body,
      signal: opts?.signal,
    });
  },

  // Evidence / Lineage Audit
  async evidence(requestId: string, opts?: QueryOpts): Promise<ApiResult<EvidenceModel>> {
    return request<EvidenceModel>(`/v1/evidence/${encodeURIComponent(requestId)}`, {
      signal: opts?.signal,
    });
  },

  // STAC
  async stacCollections(opts?: QueryOpts): Promise<{ collections: StacCollection[] }> {
    const res = await request<{ collections: StacCollection[] }>("/v1/stac/collections", {
      signal: opts?.signal,
    });
    return res.data;
  },

  async stacCollection(collectionId: string, opts?: QueryOpts): Promise<StacCollection> {
    const res = await request<StacCollection>(
      `/v1/stac/collections/${encodeURIComponent(collectionId)}`,
      { signal: opts?.signal }
    );
    return res.data;
  },

  async stacItems(
    collectionId: string,
    limit = 100,
    offset = 0,
    opts?: QueryOpts
  ): Promise<StacItemCollection> {
    const res = await request<StacItemCollection>(
      `/v1/stac/collections/${encodeURIComponent(collectionId)}/items`,
      {
        query: { limit, offset },
        signal: opts?.signal,
      }
    );
    return res.data;
  },
};
