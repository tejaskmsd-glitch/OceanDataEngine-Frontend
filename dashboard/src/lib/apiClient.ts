/**
 * REST client for the Marine Data Layer API.
 *
 * Design goals:
 *  - Same-origin relative requests by default (works behind a shared gateway).
 *  - Configurable base URL via VITE_API_BASE_URL for split deployments.
 *  - Defensive envelope unwrapping: tolerate both enveloped `{ data, meta }`
 *    responses and bare payloads so the dashboard degrades gracefully as the
 *    backend evolves.
 *  - Typed, well-scoped errors with abort/timeout support.
 */

import type {
  Alert,
  DataHealth,
  Dataset,
  EnvelopeMeta,
  Evidence,
  Pfz,
  ProcessingJob,
  ResponseEnvelope,
} from '../types/api';

declare global {
  interface Window {
    __RUNTIME_CONFIG__?: {
      API_BASE_URL?: string;
    };
  }
}

const RAW_BASE = (window.__RUNTIME_CONFIG__?.API_BASE_URL ?? import.meta.env.VITE_API_BASE_URL ?? '').trim();
/** Normalized base URL without a trailing slash. Empty means same-origin. */
export const API_BASE_URL = RAW_BASE.replace(/\/$/, '');

const DEFAULT_TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  readonly status: number;
  readonly url: string;

  constructor(message: string, status: number, url: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.url = url;
  }
}

export interface EnvelopeResult<T> {
  data: T;
  envelope: ResponseEnvelope<T> | null;
}

function buildUrl(path: string, query?: Record<string, unknown>): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const base = API_BASE_URL || '';
  const search = new URLSearchParams();
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === '') continue;
      search.append(key, String(value));
    }
  }
  const qs = search.toString();
  return `${base}${normalizedPath}${qs ? `?${qs}` : ''}`;
}

/** Returns true when the value looks like a canonical response envelope. */
function isEnvelope(value: unknown): value is ResponseEnvelope<unknown> {
  return (
    typeof value === 'object' &&
    value !== null &&
    'data' in (value as Record<string, unknown>)
  );
}

async function request<T>(
  path: string,
  options: {
    query?: Record<string, unknown>;
    signal?: AbortSignal;
    timeoutMs?: number;
  } = {},
): Promise<EnvelopeResult<T>> {
  const url = buildUrl(path, options.query);
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(new DOMException('Request timed out', 'TimeoutError')),
    options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  );

  // Chain any externally provided signal into our controller.
  if (options.signal) {
    if (options.signal.aborted) controller.abort(options.signal.reason);
    else
      options.signal.addEventListener('abort', () => controller.abort(options.signal?.reason), {
        once: true,
      });
  }

  try {
    const res = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });

    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = (await res.json()) as { detail?: string; message?: string };
        detail = body.detail ?? body.message ?? detail;
      } catch {
        /* non-JSON error body — keep statusText */
      }
      throw new ApiError(`Request failed (${res.status}): ${detail}`, res.status, url);
    }

    const body = (await res.json()) as unknown;
    if (isEnvelope(body)) {
      const env = body as ResponseEnvelope<T>;
      return { data: env.data, envelope: env };
    }
    return { data: body as T, envelope: null };
  } finally {
    clearTimeout(timeout);
  }
}

/** Extract a list from either an array payload or a keyed container. */
function asList<T>(data: unknown, key?: string): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if (key && Array.isArray(obj[key])) return obj[key] as T[];
    // Fall back to the first array-valued property.
    for (const value of Object.values(obj)) {
      if (Array.isArray(value)) return value as T[];
    }
  }
  return [];
}

export interface RequestOptions {
  signal?: AbortSignal;
}

export const api = {
  async health(opts: RequestOptions = {}): Promise<{ status: string; raw: unknown }> {
    const { data } = await request<unknown>('/v1/health', { signal: opts.signal });
    const status =
      (data as { status?: string })?.status ?? (typeof data === 'string' ? data : 'unknown');
    return { status: String(status), raw: data };
  },

  async dataHealth(opts: RequestOptions = {}): Promise<DataHealth> {
    const { data } = await request<DataHealth>('/v1/data-health', { signal: opts.signal });
    return (data ?? {}) as DataHealth;
  },

  async datasets(opts: RequestOptions = {}): Promise<Dataset[]> {
    const { data } = await request<unknown>('/v1/datasets', { signal: opts.signal });
    return asList<Dataset>(data, 'datasets');
  },

  async datasetStatus(id: string, opts: RequestOptions = {}): Promise<Dataset> {
    const { data } = await request<Dataset>(
      `/v1/datasets/${encodeURIComponent(id)}/status`,
      { signal: opts.signal },
    );
    return (data ?? { dataset_id: id }) as Dataset;
  },

  async jobs(opts: RequestOptions = {}): Promise<ProcessingJob[]> {
    // Not in the documented core contract but expected by the ops dashboard;
    // tolerate 404 by returning an empty list so the view still renders.
    try {
      const { data } = await request<unknown>('/v1/jobs', { signal: opts.signal });
      return asList<ProcessingJob>(data, 'jobs');
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return [];
      throw err;
    }
  },

  async alerts(
    params: { lat?: number; lon?: number; radius_km?: number } = {},
    opts: RequestOptions = {},
  ): Promise<Alert[]> {
    const { data } = await request<unknown>('/v1/alerts', {
      query: params,
      signal: opts.signal,
    });
    return asList<Alert>(data, 'alerts');
  },

  /** Same as alerts() but returns the full envelope so callers can read meta.request_id. */
  async alertsWithMeta(
    params: { lat?: number; lon?: number; radius_km?: number } = {},
    opts: RequestOptions = {},
  ): Promise<{ data: Alert[]; meta: EnvelopeMeta | undefined }> {
    const { data, envelope } = await request<unknown>('/v1/alerts', {
      query: params,
      signal: opts.signal,
    });
    return {
      data: asList<Alert>(data, 'alerts'),
      meta: envelope?.meta as EnvelopeMeta | undefined,
    };
  },

  async pfz(
    params: { lat?: number; lon?: number; radius_km?: number } = {},
    opts: RequestOptions = {},
  ): Promise<Pfz[]> {
    const { data } = await request<unknown>('/v1/fishing/pfz', {
      query: params,
      signal: opts.signal,
    });
    return asList<Pfz>(data, 'pfz');
  },

  async evidence(requestId: string, opts: RequestOptions = {}): Promise<Evidence> {
    const { data, envelope } = await request<Evidence>(
      `/v1/evidence/${encodeURIComponent(requestId)}`,
      { signal: opts.signal },
    );
    const evidence = (data ?? { request_id: requestId }) as Evidence;
    // Fold envelope-level provenance in when the payload doesn't carry it.
    if (envelope) {
      evidence.sources ??= envelope.sources;
      evidence.quality ??= envelope.quality;
      evidence.meta ??= envelope.meta;
    }
    return evidence;
  },
};

export { asList, buildUrl, isEnvelope };
