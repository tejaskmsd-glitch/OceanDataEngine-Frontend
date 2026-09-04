import { useCallback, useEffect, useRef, useState } from 'react';
import type { StreamEvent } from '../types/api';
import { API_BASE_URL } from '../lib/apiClient';

export type WsStatus = 'connecting' | 'open' | 'closed' | 'reconnecting' | 'disabled';

/** Resolve the alert-stream WebSocket URL from env or the current origin. */
export function resolveWsUrl(): string {
  const explicit = (import.meta.env.VITE_WS_URL ?? '').trim();
  if (explicit) return explicit;

  // Derive from API base or page origin, upgrading http(s) → ws(s).
  const base = API_BASE_URL || window.location.origin;
  try {
    const u = new URL(base);
    u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
    u.pathname = '/v1/stream/alerts';
    u.search = '';
    return u.toString();
  } catch {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}/v1/stream/alerts`;
  }
}

export interface UseAlertStreamOptions {
  enabled?: boolean;
  onEvent?: (event: StreamEvent) => void;
  maxBackoffMs?: number;
}

export interface AlertStreamState {
  status: WsStatus;
  lastEvent: StreamEvent | null;
  lastEventAt: number | null;
  /** Increments on each received event; handy as a polling-trigger dependency. */
  eventCount: number;
  attempts: number;
}

/**
 * Subscribes to the alert WebSocket stream with exponential backoff + jitter
 * reconnection. When the socket cannot stay open, callers should fall back to
 * REST polling — expose `status` so views can widen their poll interval only
 * while connected.
 */
export function useAlertStream(options: UseAlertStreamOptions = {}): AlertStreamState {
  const { enabled = true, onEvent, maxBackoffMs = 30_000 } = options;

  const [state, setState] = useState<AlertStreamState>({
    status: enabled ? 'connecting' : 'disabled',
    lastEvent: null,
    lastEventAt: null,
    eventCount: 0,
    attempts: 0,
  });

  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const wsRef = useRef<WebSocket | null>(null);
  const attemptsRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedByUsRef = useRef(false);

  const connect = useCallback(() => {
    if (typeof WebSocket === 'undefined') {
      setState((s) => ({ ...s, status: 'disabled' }));
      return;
    }
    const url = resolveWsUrl();
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      scheduleReconnect();
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      attemptsRef.current = 0;
      setState((s) => ({ ...s, status: 'open', attempts: 0 }));
    };

    ws.onmessage = (evt) => {
      let parsed: StreamEvent;
      try {
        parsed = JSON.parse(evt.data as string) as StreamEvent;
      } catch {
        parsed = { type: 'message', payload: evt.data };
      }
      onEventRef.current?.(parsed);
      setState((s) => ({
        ...s,
        lastEvent: parsed,
        lastEventAt: Date.now(),
        eventCount: s.eventCount + 1,
      }));
    };

    ws.onerror = () => {
      // onclose will follow; reconnect is handled there.
    };

    ws.onclose = () => {
      wsRef.current = null;
      if (closedByUsRef.current) {
        setState((s) => ({ ...s, status: 'closed' }));
        return;
      }
      scheduleReconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const scheduleReconnect = useCallback(() => {
    attemptsRef.current += 1;
    const attempt = attemptsRef.current;
    const backoff = Math.min(maxBackoffMs, 1000 * 2 ** Math.min(attempt, 6));
    const jitter = Math.random() * 0.3 * backoff;
    const delay = backoff + jitter;
    setState((s) => ({ ...s, status: 'reconnecting', attempts: attempt }));
    timerRef.current = setTimeout(() => connect(), delay);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [maxBackoffMs, connect]);

  useEffect(() => {
    if (!enabled) {
      setState((s) => ({ ...s, status: 'disabled' }));
      return;
    }
    closedByUsRef.current = false;
    attemptsRef.current = 0;
    connect();

    return () => {
      closedByUsRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [enabled, connect]);

  return state;
}
