import { describe, it, expect } from 'vitest';
import { resolveWsUrl } from '../useAlertStream';

describe('resolveWsUrl', () => {
  it('derives ws url from page origin when no env override', () => {
    // jsdom default origin is http://localhost
    const url = resolveWsUrl();
    expect(url).toMatch(/^ws:\/\//);
    expect(url).toContain('/v1/stream/alerts');
  });
});
