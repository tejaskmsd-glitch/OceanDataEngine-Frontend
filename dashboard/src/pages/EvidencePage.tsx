import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../lib/apiClient';
import { useAsyncData } from '../hooks/useAsyncData';
import { AsyncBoundary } from '../components/States';
import { StatusBadge } from '../components/StatusBadge';
import { formatDateTime } from '../lib/format';
import type { Evidence, SourceRef } from '../types/api';

/**
 * Lineage / evidence drill-down. Given a request/entity id, fetches the
 * provenance package from GET /v1/evidence/{request_id} and renders the source
 * chain, processing steps, quality, and the raw payload for full transparency.
 */
export function EvidencePage() {
  const [params, setParams] = useSearchParams();
  const initial = params.get('request_id') ?? '';
  const [input, setInput] = useState(initial);
  const requestId = params.get('request_id') ?? '';

  const evidence = useAsyncData(
    (signal) => api.evidence(requestId, { signal }),
    [requestId],
    { enabled: requestId.length > 0 },
  );

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const id = input.trim();
    if (id) setParams({ request_id: id });
    else setParams({});
  };

  return (
    <div>
      <div className="topbar">
        <div className="page-title">Lineage &amp; evidence</div>
      </div>

      <form className="control-row" onSubmit={submit}>
        <label className="field" style={{ flex: 1 }}>
          Request / entity ID
          <input
            className="text-input"
            style={{ minWidth: 320 }}
            type="text"
            placeholder="e.g. request id or warning/PFZ id"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
        </label>
        <button type="submit" className="btn btn--primary" style={{ alignSelf: 'flex-end' }}>
          Load evidence
        </button>
      </form>

      {!requestId ? (
        <div className="state-panel" role="status">
          Enter a request or entity ID to inspect its data lineage, sources, and processing steps.
          Alert rows link here directly.
        </div>
      ) : (
        <AsyncBoundary
          loading={evidence.loading}
          loaded={evidence.loaded}
          error={evidence.error}
          data={evidence.data}
          onRetry={evidence.refetch}
          emptyMessage="No evidence found for this ID."
        >
          {(ev) => <EvidenceDetail evidence={ev} />}
        </AsyncBoundary>
      )}
    </div>
  );
}

function EvidenceDetail({ evidence }: { evidence: Evidence }) {
  const sources = evidence.sources ?? [];
  const steps = evidence.processing_steps ?? [];

  return (
    <div className="row-gap">
      <section className="card">
        <h2 style={{ fontSize: 15 }}>Summary</h2>
        <dl className="detail-grid">
          <dt>Request ID</dt>
          <dd className="mono">{evidence.request_id}</dd>
          <dt>Capability</dt>
          <dd>{evidence.capability ?? '—'}</dd>
          <dt>Generated</dt>
          <dd>{formatDateTime(evidence.generated_at ?? evidence.meta?.generated_at)}</dd>
          <dt>Valid from</dt>
          <dd>{formatDateTime(evidence.meta?.valid_from)}</dd>
          <dt>Valid until</dt>
          <dd>{formatDateTime(evidence.meta?.valid_until)}</dd>
          <dt>Confidence</dt>
          <dd>
            {evidence.meta?.confidence !== undefined && evidence.meta?.confidence !== null
              ? `${Math.round((evidence.meta.confidence ?? 0) * 100)}%`
              : '—'}
          </dd>
          {evidence.quality?.quality_status && (
            <>
              <dt>Quality</dt>
              <dd>
                <StatusBadge
                  tone={
                    evidence.quality.quality_status.toUpperCase() === 'PASS' ? 'ok' : 'warn'
                  }
                  label={evidence.quality.quality_status}
                />
              </dd>
            </>
          )}
        </dl>
      </section>

      <section className="card">
        <h2 style={{ fontSize: 15 }}>Sources &amp; provenance</h2>
        {sources.length === 0 ? (
          <p className="muted">No source provenance attached.</p>
        ) : (
          <ul style={{ margin: 0, paddingLeft: '1.1rem' }}>
            {sources.map((s, i) => (
              <li key={i} style={{ marginBottom: '0.5rem' }}>
                <SourceItem source={s} />
              </li>
            ))}
          </ul>
        )}
        {evidence.input_datasets && evidence.input_datasets.length > 0 && (
          <p className="muted" style={{ marginBottom: 0 }}>
            Input datasets: {evidence.input_datasets.join(', ')}
          </p>
        )}
      </section>

      {steps.length > 0 && (
        <section className="card">
          <h2 style={{ fontSize: 15 }}>Processing steps</h2>
          <ol style={{ margin: 0, paddingLeft: '1.2rem' }}>
            {steps.map((step, i) => (
              <li key={i} style={{ marginBottom: '0.35rem' }}>
                <strong>{step.step}</strong>
                {step.status && <> — {step.status}</>}
                {step.processing_version && (
                  <span className="muted"> (v{step.processing_version})</span>
                )}
                {step.detail && <div className="muted">{step.detail}</div>}
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="card">
        <h2 style={{ fontSize: 15 }}>Raw evidence payload</h2>
        <pre className="evidence-json">{JSON.stringify(evidence, null, 2)}</pre>
      </section>
    </div>
  );
}

function SourceItem({ source }: { source: SourceRef }) {
  const title = source.dataset ?? source.dataset_id ?? source.source ?? source.provider ?? 'source';
  return (
    <div>
      <div style={{ fontWeight: 600 }}>
        {source.provider ?? source.source ?? '—'} · {title}
      </div>
      <div className="muted">
        issued {formatDateTime(source.issued_at)} · retrieved {formatDateTime(source.retrieved_at)}
        {source.processing_version ? ` · v${source.processing_version}` : ''}
      </div>
      {source.source_url && (
        <a href={source.source_url} target="_blank" rel="noreferrer noopener">
          {source.source_url}
        </a>
      )}
    </div>
  );
}
