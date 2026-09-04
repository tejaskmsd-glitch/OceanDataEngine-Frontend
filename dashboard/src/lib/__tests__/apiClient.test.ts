import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { api, asList, buildUrl, isEnvelope, ApiError } from '../apiClient';

function mockFetchOnce(body: unknown, init: { ok?: boolean; status?: number } = {}) {
  const { ok = true, status = 200 } = init;
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    json: async () => body,
  });
}

describe('apiClient helpers', () => {
  it('detects envelopes', () => {
    expect(isEnvelope({ data: [] })).toBe(true);
    expect(isEnvelope({ items: [] })).toBe(false);
    expect(isEnvelope(null)).toBe(false);
    expect(isEnvelope('x')).toBe(false);
  });

  it('extracts lists from array or keyed container', () => {
    expect(asList<number>([1, 2, 3])).toEqual([1, 2, 3]);
    expect(asList<number>({ datasets: [1, 2] }, 'datasets')).toEqual([1, 2]);
    expect(asList<number>({ foo: [9] })).toEqual([9]);
    expect(asList<number>({})).toEqual([]);
  });

  it('builds urls with query params, skipping empties', () => {
    expect(buildUrl('/v1/alerts', { lat: 1, lon: 2, radius_km: undefined })).toBe(
      '/v1/alerts?lat=1&lon=2',
    );
    expect(buildUrl('v1/health')).toBe('/v1/health');
  });
});

describe('api endpoints', () => {
  const originalFetch = globalThis.fetch;
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('unwraps enveloped dataset list', async () => {
    globalThis.fetch = mockFetchOnce({ data: { datasets: [{ dataset_id: 'a' }] } });
    const result = await api.datasets();
    expect(result).toEqual([{ dataset_id: 'a' }]);
  });

  it('handles bare array payloads', async () => {
    globalThis.fetch = mockFetchOnce([{ dataset_id: 'b' }]);
    const result = await api.datasets();
    expect(result).toEqual([{ dataset_id: 'b' }]);
  });

  it('returns [] for jobs on 404', async () => {
    globalThis.fetch = mockFetchOnce({ detail: 'not found' }, { ok: false, status: 404 });
    const result = await api.jobs();
    expect(result).toEqual([]);
  });

  it('throws ApiError on non-404 failures', async () => {
    globalThis.fetch = mockFetchOnce({ detail: 'boom' }, { ok: false, status: 500 });
    await expect(api.alerts()).rejects.toBeInstanceOf(ApiError);
  });

  it('folds envelope provenance into evidence', async () => {
    globalThis.fetch = mockFetchOnce({
      data: { request_id: 'r1', capability: 'pfz' },
      sources: [{ provider: 'INCOIS' }],
      quality: { quality_status: 'PASS' },
      meta: { confidence: 0.9 },
    });
    const ev = await api.evidence('r1');
    expect(ev.request_id).toBe('r1');
    expect(ev.sources).toEqual([{ provider: 'INCOIS' }]);
    expect(ev.quality?.quality_status).toBe('PASS');
    expect(ev.meta?.confidence).toBe(0.9);
  });
});
