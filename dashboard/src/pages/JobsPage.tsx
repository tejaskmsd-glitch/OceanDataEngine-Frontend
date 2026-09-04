import { useMemo, useState } from 'react';
import { api } from '../lib/apiClient';
import { useAsyncData } from '../hooks/useAsyncData';
import { AsyncBoundary } from '../components/States';
import { DataTable, type Column } from '../components/DataTable';
import { StatusBadge } from '../components/StatusBadge';
import { formatDateTime, formatDuration, jobStatusTone, relativeAge } from '../lib/format';
import type { ProcessingJob } from '../types/api';

const STATUS_FILTERS = [
  'ALL',
  'queued',
  'running',
  'succeeded',
  'failed',
  'retrying',
  'cancelled',
] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

export function JobsPage() {
  const [filter, setFilter] = useState<StatusFilter>('ALL');
  const jobs = useAsyncData((signal) => api.jobs({ signal }), [], { pollMs: 10_000 });

  const rows = useMemo(() => jobs.data ?? [], [jobs.data]);

  const filtered = useMemo(() => {
    const list =
      filter === 'ALL'
        ? rows
        : rows.filter((j) => (j.status ?? '').toLowerCase() === filter);
    return [...list].sort((a, b) => timeOf(b) - timeOf(a));
  }, [rows, filter]);

  return (
    <div>
      <div className="topbar">
        <div className="page-title">Processing jobs</div>
        <button type="button" className="btn" onClick={jobs.refetch}>
          Refresh
        </button>
      </div>

      <div className="control-row">
        <label className="field">
          Status
          <select value={filter} onChange={(e) => setFilter(e.target.value as StatusFilter)}>
            {STATUS_FILTERS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <span className="muted" style={{ alignSelf: 'flex-end' }}>
          {filtered.length} of {rows.length}
        </span>
      </div>

      <AsyncBoundary
        loading={jobs.loading}
        loaded={jobs.loaded}
        error={jobs.error}
        data={filtered}
        onRetry={jobs.refetch}
        isEmpty={(r) => r.length === 0}
        emptyMessage={
          rows.length === 0
            ? 'No processing jobs reported. The jobs endpoint may not be available yet.'
            : 'No jobs match the current filter.'
        }
      >
        {(list) => (
          <DataTable<ProcessingJob>
            caption="Processing jobs"
            columns={columns}
            rows={list}
            getRowKey={(j, i) => j.job_id ?? String(i)}
          />
        )}
      </AsyncBoundary>
    </div>
  );
}

function timeOf(j: ProcessingJob): number {
  const v = j.finished_at ?? j.started_at ?? j.queued_at;
  const t = v ? new Date(v).getTime() : 0;
  return Number.isNaN(t) ? 0 : t;
}

const columns: Column<ProcessingJob>[] = [
  { key: 'job', header: 'Job ID', render: (j) => <span className="mono">{j.job_id}</span> },
  { key: 'source', header: 'Source', render: (j) => j.source ?? '—' },
  { key: 'dataset', header: 'Dataset', render: (j) => j.dataset ?? '—' },
  { key: 'type', header: 'Type', render: (j) => j.job_type ?? '—' },
  {
    key: 'status',
    header: 'Status',
    render: (j) => (
      <div>
        <StatusBadge tone={jobStatusTone(j.status)} label={j.status ?? 'unknown'} />
        {(j.retry_count ?? 0) > 0 && (
          <span className="muted" style={{ marginLeft: 6 }}>
            ×{j.retry_count}
          </span>
        )}
      </div>
    ),
  },
  { key: 'queued', header: 'Queued', render: (j) => formatDateTime(j.queued_at) },
  { key: 'finished', header: 'Finished', render: (j) => relativeAge(j.finished_at) },
  {
    key: 'duration',
    header: 'Duration',
    render: (j) => formatDuration(j.duration_ms ?? deriveDuration(j)),
  },
  { key: 'worker', header: 'Worker', render: (j) => j.worker ?? '—' },
  {
    key: 'error',
    header: 'Error',
    render: (j) =>
      j.error ? (
        <span className="mono" title={j.error} style={{ color: 'var(--tone-error-fg)' }}>
          {truncate(j.error, 60)}
        </span>
      ) : (
        '—'
      ),
  },
];

function deriveDuration(j: ProcessingJob): number | null {
  if (!j.started_at || !j.finished_at) return null;
  const start = new Date(j.started_at).getTime();
  const end = new Date(j.finished_at).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  return end - start;
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n)}…` : s;
}
