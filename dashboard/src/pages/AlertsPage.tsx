import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/apiClient';
import { useAsyncData } from '../hooks/useAsyncData';
import { useAlertStream } from '../hooks/useAlertStream';
import { AsyncBoundary } from '../components/States';
import { DataTable, type Column } from '../components/DataTable';
import { StatusBadge } from '../components/StatusBadge';
import { ConnectionIndicator } from '../components/ConnectionIndicator';
import {
  formatDateTime,
  isAlertActive,
  relativeAge,
  severityRank,
  severityTone,
} from '../lib/format';
import type { Alert } from '../types/api';

export function AlertsPage() {
  const [activeOnly, setActiveOnly] = useState(true);
  const stream = useAlertStream();
  const live = stream.status === 'open';
  const pollMs = live ? 30_000 : 8_000;

  // Track the envelope's request_id so we can link to evidence
  const [lastRequestId, setLastRequestId] = useState<string | null>(null);

  const alerts = useAsyncData(
    async (signal) => {
      const result = await api.alertsWithMeta({}, { signal });
      if (result.meta?.request_id) {
        setLastRequestId(result.meta.request_id);
      }
      return result.data;
    },
    [stream.eventCount],
    { pollMs },
  );

  const rows = useMemo(() => alerts.data ?? [], [alerts.data]);

  const filtered = useMemo(() => {
    const list = activeOnly ? rows.filter((a) => isAlertActive(a.expires_at)) : rows;
    return [...list].sort((a, b) => severityRank(b.severity) - severityRank(a.severity));
  }, [rows, activeOnly]);

  return (
    <div>
      <div className="topbar">
        <div className="page-title">Alerts &amp; warnings</div>
        <div className="control-row" style={{ margin: 0 }}>
          <ConnectionIndicator status={stream.status} />
          <button type="button" className="btn" onClick={alerts.refetch}>
            Refresh
          </button>
        </div>
      </div>

      <div className="control-row">
        <label
          className="field"
          style={{ flexDirection: 'row', alignItems: 'center', gap: '0.4rem' }}
        >
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={(e) => setActiveOnly(e.target.checked)}
          />
          Active only
        </label>
        <span className="muted" style={{ alignSelf: 'flex-end' }}>
          {filtered.length} shown
        </span>
      </div>

      <AsyncBoundary
        loading={alerts.loading}
        loaded={alerts.loaded}
        error={alerts.error}
        data={filtered}
        onRetry={alerts.refetch}
        isEmpty={(r) => r.length === 0}
        emptyMessage={activeOnly ? 'No active alerts.' : 'No alerts reported.'}
      >
        {(list) => (
          <DataTable<Alert>
            caption="Marine alerts and warnings"
            columns={buildColumns(lastRequestId)}
            rows={list}
            getRowKey={(a, i) => a.warning_id ?? String(i)}
          />
        )}
      </AsyncBoundary>
    </div>
  );
}

function buildColumns(requestId: string | null): Column<Alert>[] {
  return [
    {
      key: 'event',
      header: 'Event',
      render: (a) => (
        <div>
          <div style={{ fontWeight: 600 }}>{a.event_type ?? 'warning'}</div>
          {a.headline && <div className="muted">{a.headline}</div>}
        </div>
      ),
    },
    {
      key: 'severity',
      header: 'Severity',
      render: (a) => (
        <StatusBadge tone={severityTone(a.severity)} label={a.severity ?? 'Unknown'} />
      ),
    },
    { key: 'area', header: 'Area', render: (a) => a.area_description ?? '—' },
    { key: 'source', header: 'Source', render: (a) => a.source ?? '—' },
    { key: 'issued', header: 'Issued', render: (a) => formatDateTime(a.issued_at) },
    {
      key: 'expires',
      header: 'Expires',
      render: (a) => (
        <span>
          {relativeAge(a.expires_at)}{' '}
          {!isAlertActive(a.expires_at) && (
            <span className="badge badge--neutral">expired</span>
          )}
        </span>
      ),
    },
    {
      key: 'evidence',
      header: 'Lineage',
      render: () =>
        requestId ? (
          <Link to={`/evidence?request_id=${encodeURIComponent(requestId)}`}>Evidence</Link>
        ) : (
          <span className="muted">—</span>
        ),
    },
  ];
}
