import { describe, it, expect } from 'vitest';
import {
  datasetStatusTone,
  formatDuration,
  formatMinutes,
  isAlertActive,
  jobStatusTone,
  relativeAge,
  severityRank,
  severityTone,
} from '../format';

describe('format helpers', () => {
  it('formats minutes across units', () => {
    expect(formatMinutes(30)).toBe('30 min');
    expect(formatMinutes(90)).toBe('1.5 h');
    expect(formatMinutes(60 * 25)).toBe('1.0 d');
    expect(formatMinutes(null)).toBe('—');
    expect(formatMinutes(undefined)).toBe('—');
  });

  it('formats durations from ms', () => {
    expect(formatDuration(500)).toBe('500 ms');
    expect(formatDuration(1500)).toBe('1.5 s');
    expect(formatDuration(90_000)).toBe('1.5 min');
    expect(formatDuration(null)).toBe('—');
  });

  it('computes relative age', () => {
    const past = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(relativeAge(past)).toBe('5 min ago');
    const future = new Date(Date.now() + 2 * 60 * 60_000).toISOString();
    expect(relativeAge(future)).toBe('in 2 h');
    expect(relativeAge(null)).toBe('—');
  });

  it('maps dataset status to tones', () => {
    expect(datasetStatusTone('HEALTHY')).toBe('ok');
    expect(datasetStatusTone('stale')).toBe('warn');
    expect(datasetStatusTone('FAILED')).toBe('error');
    expect(datasetStatusTone('DISABLED')).toBe('neutral');
    expect(datasetStatusTone(undefined)).toBe('neutral');
  });

  it('maps job status to tones', () => {
    expect(jobStatusTone('succeeded')).toBe('ok');
    expect(jobStatusTone('running')).toBe('info');
    expect(jobStatusTone('failed')).toBe('error');
    expect(jobStatusTone('queued')).toBe('warn');
  });

  it('ranks and tones severities', () => {
    expect(severityRank('Extreme')).toBeGreaterThan(severityRank('Moderate'));
    expect(severityRank('Minor')).toBeGreaterThan(severityRank('Unknown'));
    expect(severityTone('Severe')).toBe('error');
    expect(severityTone('Moderate')).toBe('warn');
  });

  it('treats missing expiry as active and expired past as inactive', () => {
    expect(isAlertActive(null)).toBe(true);
    expect(isAlertActive(new Date(Date.now() + 3600_000).toISOString())).toBe(true);
    expect(isAlertActive(new Date(Date.now() - 3600_000).toISOString())).toBe(false);
  });
});
