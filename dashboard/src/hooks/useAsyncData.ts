import { useCallback, useEffect, useRef, useState } from 'react';

export type AsyncState<T> = {
  data: T | null;
  loading: boolean;
  error: Error | null;
  /** True after the first successful load (used to keep stale data visible). */
  loaded: boolean;
  lastUpdated: number | null;
};

export interface UseAsyncDataOptions {
  /** Poll interval in ms. 0/undefined disables polling. */
  pollMs?: number;
  /** When false, the fetch is not run (e.g. waiting on user input). */
  enabled?: boolean;
}

/**
 * Runs an async fetcher with loading/error state, manual refetch, optional
 * polling, and abort on unmount. Keeps previously loaded data visible during
 * refetches so the UI does not flash empty on every poll.
 */
export function useAsyncData<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: React.DependencyList,
  options: UseAsyncDataOptions = {},
): AsyncState<T> & { refetch: () => void } {
  const { pollMs = 0, enabled = true } = options;
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    loading: enabled,
    error: null,
    loaded: false,
    lastUpdated: null,
  });

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const run = useCallback(async (signal: AbortSignal) => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const result = await fetcherRef.current(signal);
      if (signal.aborted || !mountedRef.current) return;
      setState({
        data: result,
        loading: false,
        error: null,
        loaded: true,
        lastUpdated: Date.now(),
      });
    } catch (err) {
      if (signal.aborted || !mountedRef.current) return;
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setState((s) => ({
        ...s,
        loading: false,
        error: err instanceof Error ? err : new Error(String(err)),
      }));
    }
  }, []);

  const [nonce, setNonce] = useState(0);
  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!enabled) {
      setState((s) => ({ ...s, loading: false }));
      return;
    }
    const controller = new AbortController();
    void run(controller.signal);

    let interval: ReturnType<typeof setInterval> | undefined;
    if (pollMs && pollMs > 0) {
      interval = setInterval(() => {
        if (document.visibilityState === 'visible') void run(controller.signal);
      }, pollMs);
    }

    return () => {
      controller.abort();
      if (interval) clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, pollMs, enabled, nonce, ...deps]);

  return { ...state, refetch };
}
