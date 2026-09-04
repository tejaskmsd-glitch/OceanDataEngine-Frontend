import type { DatasetStatus, JobStatus, AlertSeverity } from '../types/api';

/** Format an ISO timestamp for display; returns em dash when missing/invalid. */
export function formatDateTime(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Human-friendly relative age, e.g. "3 min ago", "2 h ago". */
export function relativeAge(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const diffMs = Date.now() - d.getTime();
  const future = diffMs < 0;
  const abs = Math.abs(diffMs);
  const min = Math.round(abs / 60_000);
  let text: string;
  if (min < 1) text = 'just now';
  else if (min < 60) text = `${min} min`;
  else if (min < 60 * 24) text = `${Math.round(min / 60)} h`;
  else text = `${Math.round(min / (60 * 24))} d`;
  if (text === 'just now') return text;
  return future ? `in ${text}` : `${text} ago`;
}

export function formatMinutes(min?: number | null): string {
  if (min === undefined || min === null || Number.isNaN(min)) return '—';
  if (min < 60) return `${Math.round(min)} min`;
  if (min < 60 * 24) return `${(min / 60).toFixed(1)} h`;
  return `${(min / (60 * 24)).toFixed(1)} d`;
}

export function formatDuration(ms?: number | null): string {
  if (ms === undefined || ms === null || Number.isNaN(ms)) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = s / 60;
  if (m < 60) return `${m.toFixed(1)} min`;
  return `${(m / 60).toFixed(1)} h`;
}

export type StatusTone = 'ok' | 'warn' | 'error' | 'neutral' | 'info';

export function datasetStatusTone(status?: DatasetStatus): StatusTone {
  switch ((status ?? '').toUpperCase()) {
    case 'HEALTHY':
      return 'ok';
    case 'STALE':
    case 'DEGRADED':
      return 'warn';
    case 'FAILED':
      return 'error';
    case 'DISABLED':
      return 'neutral';
    default:
      return 'neutral';
  }
}

export function jobStatusTone(status?: JobStatus): StatusTone {
  switch ((status ?? '').toLowerCase()) {
    case 'succeeded':
      return 'ok';
    case 'running':
      return 'info';
    case 'queued':
    case 'retrying':
      return 'warn';
    case 'failed':
      return 'error';
    case 'cancelled':
      return 'neutral';
    default:
      return 'neutral';
  }
}

export function severityTone(severity?: AlertSeverity): StatusTone {
  switch ((severity ?? '').toLowerCase()) {
    case 'extreme':
    case 'severe':
      return 'error';
    case 'moderate':
      return 'warn';
    case 'minor':
      return 'info';
    default:
      return 'neutral';
  }
}

/** Rank severities so alert lists can sort most-critical first. */
export function severityRank(severity?: AlertSeverity): number {
  switch ((severity ?? '').toLowerCase()) {
    case 'extreme':
      return 4;
    case 'severe':
      return 3;
    case 'moderate':
      return 2;
    case 'minor':
      return 1;
    default:
      return 0;
  }
}

export function isAlertActive(expiresAt?: string | null): boolean {
  if (!expiresAt) return true; // no expiry known → treat as active
  const d = new Date(expiresAt);
  if (Number.isNaN(d.getTime())) return true;
  return d.getTime() > Date.now();
}
