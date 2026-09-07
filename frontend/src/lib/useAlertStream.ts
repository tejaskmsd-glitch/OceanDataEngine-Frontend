"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { AlertModel } from "../types/api";

export type WebSocketStatus = "connecting" | "connected" | "disconnected" | "error";

export function playSonarChime() {
  if (typeof window === "undefined") return;
  try {
    const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = "sine";
    // Calming underwater sonar acoustic frequency (~520Hz dipping to ~440Hz)
    osc.frequency.setValueAtTime(520, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.6);

    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + 0.65);
  } catch {
    // Audio context may be blocked before user gesture
  }
}

export function useAlertStream(options: { soundEnabled?: boolean } = {}) {
  const [alerts, setAlerts] = useState<AlertModel[]>([]);
  const [status, setStatus] = useState<WebSocketStatus>("disconnected");
  const [lastEventAt, setLastEventAt] = useState<Date | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const shouldReconnectRef = useRef(true);

  const connect = useCallback(() => {
    if (typeof window === "undefined") return;

    // Close any prior socket
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    const rawBase =
      process.env.NEXT_PUBLIC_WS_BASE_URL ||
      (window.location.protocol === "https:" ? "wss:" : "ws:") +
        `//${window.location.hostname}:8000`;
    const wsUrl = rawBase.replace(/\/$/, "") + "/v1/stream/alerts";

    setStatus("connecting");

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("connected");
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload && (payload.alert_uid || payload.event_type)) {
            setAlerts((prev) => [payload as AlertModel, ...prev.slice(0, 99)]);
            setLastEventAt(new Date());

            if (options.soundEnabled) {
              playSonarChime();
            }
          }
        } catch {
          // Ignore malformed WS frame
        }
      };

      ws.onerror = () => {
        setStatus("error");
      };

      ws.onclose = () => {
        setStatus("disconnected");
        if (shouldReconnectRef.current) {
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, 5000);
        }
      };
    } catch {
      setStatus("error");
    }
  }, [options.soundEnabled]);

  useEffect(() => {
    shouldReconnectRef.current = true;
    connect();

    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return {
    alerts,
    status,
    lastEventAt,
    reconnect: connect,
  };
}
