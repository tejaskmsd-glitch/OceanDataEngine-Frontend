import { useMemo, useState } from 'react';
import { api } from '../lib/apiClient';
import { useAsyncData } from '../hooks/useAsyncData';
import { AsyncBoundary } from '../components/States';
import { DataTable, type Column } from '../components/DataTable';
import { StatusBadge } from '../components/StatusBadge';
import {
  datasetStatusTone,
  formatDateTime,
  formatMinutes,
  relativeAge,
} from '../lib/format';
import type { Dataset } from '../types/api';

const STATUS_FILTERS = ['ALL', 'HEALTHY', 'STALE', 'DEGRADED', 'FAILED', 'DISABLED'] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

export function DatasetsPage() {
  const [filter, setFilter] = useState<StatusFilter>('ALL');
  const [search, setSearch] = useState('');
  const datasets = useAsyncData((signal) => api.datasets({ signal }), [], { pollMs: 30_000 });

  const rows = useMemo(() => datasets.data ?? [], [datasets.data]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((d) => {
      const status = (d.status ?? '').toUpperCase();
      if (filter !== 'ALL' && status !== filter) return false;
      if (!q) return true;
      return (
        d.dataset_id.toLowerCase().includes(q) ||
        (d.provider ?? '').toLowerCase().includes(q) ||
        (d.product ?? '').toLowerCase().includes(q) ||
        (d.parameters ?? []).some((p) => p.toLowerCase().includes(q))
      );
    });
  }, [rows, filter, search]);

  return (
    <div>
      <div className="topbar">
        <div className="page-title">Datasets &amp; freshness</div>
        <button type="button" className="btn" onClick={datasets.refetch}>
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
        <label className="field">
          Search
          <input
            className="text-input"
            type="search"
            placeholder="dataset, provider, parameter…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <span className="muted" style={{ alignSelf: 'flex-end' }}>
          {filtered.length} of {rows.length}
        </span>
      </div>

      <AsyncBoundary
        loading={datasets.loading}
        loaded={datasets.loaded}
        error={datasets.error}
        data={filtered}
        onRetry={datasets.refetch}
        isEmpty={(r) => r.length === 0}
        emptyMessage={
          rows.length === 0 ? 'No datasets registered yet.' : 'No datasets match the current filter.'
        }
      >
        {(list) => (
          <DataTable<Dataset>
            caption="Dataset registry with freshness"
            columns={columns}
            rows={list}
            getRowKey={(d, i) => d.dataset_id ?? String(i)}
          />
        )}
      </AsyncBoundary>
    </div>
  );
}

function freshnessLabel(d: Dataset): string {
  if (d.age_minutes !== undefined && d.age_minutes !== null) return formatMinutes(d.age_minutes);
  const ref = d.last_updated ?? d.last_success;
  return ref ? relativeAge(ref) : '—';
}

const columns: Column<Dataset>[] = [
  {
    key: 'dataset',
    header: 'Dataset',
    render: (d) => (
      <div>
        <div style={{ fontWeight: 600 }}>{d.dataset_id}</div>
        {d.product && <div className="muted">{d.product}</div>}
      </div>
    ),
  },
  { key: 'provider', header: 'Provider', render: (d) => d.provider ?? '—' },
  {
    key: 'params',
    header: 'Parameters',
    render: (d) => (d.parameters?.length ? d.parameters.join(', ') : '—'),
  },
  { key: 'resolution', header: 'Resolution', render: (d) => d.spatial_resolution ?? '—' },
  { key: 'format', header: 'Format', render: (d) => d.format ?? '—' },
  {
    key: 'status',
    header: 'Status',
    render: (d) => <StatusBadge tone={datasetStatusTone(d.status)} label={d.status ?? 'unknown'} />,
  },
  { key: 'age', header: 'Age', render: (d) => freshnessLabel(d) },
  {
    key: 'last',
    header: 'Last success',
    render: (d) => formatDateTime(d.last_success ?? d.last_updated),
  },
];
