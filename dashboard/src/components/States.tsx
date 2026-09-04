import type { ReactNode } from 'react';

/** Skeleton rows used while data is loading for the first time. */
export function LoadingState({ rows = 4, label = 'Loading…' }: { rows?: number; label?: string }) {
  return (
    <div className="state-panel" role="status" aria-live="polite">
      <span className="visually-hidden">{label}</span>
      <div className="row-gap" aria-hidden="true">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="skeleton" style={{ height: 16, width: `${90 - i * 8}%`, margin: '0 auto' }} />
        ))}
      </div>
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: Error;
  onRetry?: () => void;
}) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <p style={{ marginTop: 0 }}>
        <strong>Couldn’t load data.</strong>
      </p>
      <p className="mono" style={{ margin: '0 0 0.75rem' }}>
        {error.message}
      </p>
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="state-panel" role="status">
      {children}
    </div>
  );
}

/**
 * Standard wrapper that renders loading/error/empty/content based on async
 * state. Keeps previously loaded data visible during background refetches.
 */
export function AsyncBoundary<T>({
  loading,
  loaded,
  error,
  data,
  onRetry,
  isEmpty,
  emptyMessage = 'No data available.',
  loadingRows,
  children,
}: {
  loading: boolean;
  loaded: boolean;
  error: Error | null;
  data: T | null;
  onRetry?: () => void;
  isEmpty?: (data: T) => boolean;
  emptyMessage?: ReactNode;
  loadingRows?: number;
  children: (data: T) => ReactNode;
}) {
  if (error && !loaded) return <ErrorState error={error} onRetry={onRetry} />;
  if (!loaded && loading) return <LoadingState rows={loadingRows} />;
  if (data === null) return <EmptyState>{emptyMessage}</EmptyState>;
  if (isEmpty?.(data)) return <EmptyState>{emptyMessage}</EmptyState>;
  return <>{children(data)}</>;
}
