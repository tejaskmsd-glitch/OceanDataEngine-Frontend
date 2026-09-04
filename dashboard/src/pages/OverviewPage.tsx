import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { api } from '../lib/apiClient';
import { useAsyncData } from '../hooks/useAsyncData';
import { useAlertStream } from '../hooks/useAlertStream';
import { StatCard } from '../components/StatCard';
import { AsyncBoundary } from '../components/States';
import { ConnectionIndicator } from '../components/ConnectionIndicator';
import { DataTable, type Column } from '../components/DataTable';
import { StatusBadge } from '../components/StatusBadge';
import {
  datasetStatusTone,
  formatDateTime,
  isAlertActive,
  jobStatusTone,
  relativeAge,
} from '../lib/format';
import type { Dataset, ProcessingJob } from '../types/api';

const POLL_CONNECTED = 30_000;
const POLL_FALLBACK = 10_000;

export function OverviewPage() {
  const stream = useAlertStream();
  const live = stream.status === 'open';
  const pollMs = live ? POLL_CONNECTED : POLL_FALLBACK;

  const datasets = useAsyncData((signal) => api.datasets({ signal }), [], { pollMs });
  const jobs = useAsyncData((signal) => api.jobs({ signal }), [], { pollMs });
  // Refetch alerts whenever a stream event arrives (or on the poll interval).
  const alerts = useAsyncData((signal) => api.alerts({}, { signal }), [stream.eventCount], {
    pollMs,
  });

  const dsList = useMemo(() => datasets.data ?? [], [datasets.data]);
  const jobList = useMemo(() => jobs.data ?? [], [jobs.data]);
  const alertList = useMemo(() => alerts.data ?? [], [alerts.data]);

  const healthy = dsList.filter((d) => (d.status ?? '').toUpperCase() === 'HEALTHY').length;
  const stale = dsList.filter((d) =>
    ['STALE', 'DEGRADED'].includes((d.status ?? '').toUpperCase()),
  ).length;
  const failedDs = dsList.filter((d) => (d.status ?? '').toUpperCase() === 'FAILED').length;

  const jobsActive = jobList.filter((j) =>
    ['running', 'queued', 'retrying'].includes((j.status ?? '').toLowerCase()),
  ).length;
  const jobsFailed = jobList.filter((j) => (j.status ?? '').toLowerCase() === 'failed').length;

  const activeAlerts = alertList.filter((a) => isAlertActive(a.expires_at)).length;

  const lastIngestion = useMemo(() => {
    const times = dsList
      .map((d) => d.last_success ?? d.last_updated)
      .filter((v): v is string => Boolean(v))
      .map((v) => new Date(v).getTime())
      .filter((n) => !Number.isNaN(n));
    if (times.length === 0) return null;
    return new Date(Math.max(...times)).toISOString();
  }, [dsList]);

  const recentJobs = useMemo(() => {
    return [...jobList]
      .sort((a, b) => timeOf(b) - timeOf(a))
      .slice(0, 8);
  }, [jobList]);

  const jobsByType = useMemo(() => {
    const counts = new Map<string, number>();
    for (const j of jobList) {
      const key = j.job_type ?? j.source ?? 'unknown';
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return Array.from(counts, ([name, count]) => ({ name, count })).slice(0, 10);
  }, [jobList]);

  const anyLoading = datasets.loading && !datasets.loaded;

  return (
    <div>
      <div className="topbar">
        <div className="page-title">Overview</div>
        <div className="control-row" style={{ margin: 0 }}>
          <ConnectionIndicator status={stream.status} />
          <button
            type="button"
            className="btn"
            onClick={() => {
              datasets.refetch();
              jobs.refetch();
              alerts.refetch();
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="card-grid">
        <StatCard
          label="Healthy datasets"
          value={anyLoading ? '—' : healthy}
          tone="ok"
          hint={`${dsList.length} total`}
        />
        <StatCard
          label="Stale / degraded"
          value={anyLoading ? '—' : stale}
          tone={stale > 0 ? 'warn' : 'neutral'}
        />
        <StatCard
          label="Failed datasets"
          value={anyLoading ? '—' : failedDs}
          tone={failedDs > 0 ? 'error' : 'neutral'}
        />
        <StatCard
          label="Jobs active"
          value={jobs.loaded ? jobsActive : '—'}
          tone={jobsActive > 0 ? 'info' : 'neutral'}
          hint={jobs.loaded ? undefined : jobs.error ? 'jobs API unavailable' : undefined}
        />
        <StatCard
          label="Jobs failed"
          value={jobs.loaded ? jobsFailed : '—'}
          tone={jobsFailed > 0 ? 'error' : 'neutral'}
        />
        <StatCard
          label="Active alerts"
          value={alerts.loaded ? activeAlerts : '—'}
          tone={activeAlerts > 0 ? 'warn' : 'neutral'}
        />
        <StatCard
          label="Last ingestion"
          value={lastIngestion ? relativeAge(lastIngestion) : '—'}
          hint={lastIngestion ? formatDateTime(lastIngestion) : 'no successful runs yet'}
        />
      </div>

      <div className="row-gap">
        <section className="card">
          <h2 style={{ fontSize: 15 }}>Recent processing</h2>
          <AsyncBoundary
            loading={jobs.loading}
            loaded={jobs.loaded}
            error={jobs.error}
            data={recentJobs}
            onRetry={jobs.refetch}
            isEmpty={(r) => r.length === 0}
            emptyMessage="No processing jobs reported yet."
          >
            {(rows) => (
              <>
                {jobsByType.length > 0 && (
                  <div style={{ height: 200, marginBottom: '1rem' }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={jobsByType} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                        <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-15} height={48} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 11 }} width={28} />
                        <Tooltip />
                        <Bar dataKey="count" fill="var(--accent)" radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
                <DataTable<ProcessingJob>
                  caption="Recent processing jobs"
                  columns={recentJobColumns}
                  rows={rows}
                  getRowKey={(j, i) => j.job_id ?? String(i)}
                />
              </>
            )}
          </AsyncBoundary>
        </section>

        <section className="card">
          <h2 style={{ fontSize: 15 }}>Datasets at a glance</h2>
          <AsyncBoundary
            loading={datasets.loading}
            loaded={datasets.loaded}
            error={datasets.error}
            data={dsList}
            onRetry={datasets.refetch}
            isEmpty={(r) => r.length === 0}
            emptyMessage="No datasets registered yet."
          >
            {(rows) => (
              <DataTable<Dataset>
                caption="Dataset summary"
                columns={datasetSummaryColumns}
                rows={rows.slice(0, 8)}
                getRowKey={(d, i) => d.dataset_id ?? String(i)}
              />
            )}
          </AsyncBoundary>
        </section>
      </div>
    </div>
  );
}

function timeOf(j: ProcessingJob): number {
  const v = j.finished_at ?? j.started_at ?? j.queued_at;
  const t = v ? new Date(v).getTime() : 0;
  return Number.isNaN(t) ? 0 : t;
}

const recentJobColumns: Column<ProcessingJob>[] = [
  { key: 'job', header: 'Job', render: (j) => <span className="mono">{j.job_id}</span> },
  { key: 'type', header: 'Type', render: (j) => j.job_type ?? j.source ?? '—' },
  {
    key: 'status',
    header: 'Status',
    render: (j) => <StatusBadge tone={jobStatusTone(j.status)} label={j.status ?? 'unknown'} />,
  },
  { key: 'when', header: 'Finished', render: (j) => relativeAge(j.finished_at ?? j.started_at) },
];

const datasetSummaryColumns: Column<Dataset>[] = [
  { key: 'dataset', header: 'Dataset', render: (d) => d.dataset_id },
  { key: 'provider', header: 'Provider', render: (d) => d.provider ?? '—' },
  {
    key: 'status',
    header: 'Status',
    render: (d) => (
      <StatusBadge tone={datasetStatusTone(d.status)} label={d.status ?? 'unknown'} />
    ),
  },
  { key: 'updated', header: 'Updated', render: (d) => relativeAge(d.last_updated ?? d.last_success) },
];
