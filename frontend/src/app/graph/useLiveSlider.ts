"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SliderUpdate } from "../spike/types";

const DEBOUNCE_MS = 40;
const RECONNECT_DELAY_MS = 1500;

interface UseLiveSliderOptions {
  scenarioId: string | null;
  /** Base HTTP backend URL, e.g. http://localhost:8000 */
  backendUrl: string;
}

interface UseLiveSliderReturn {
  sendSeverity: (severity: number) => void;
  latestUpdate: SliderUpdate | null;
  connected: boolean;
  latencyMs: number | null;
}

/**
 * Drives the live severity channel over the RIS-14 WebSocket
 * (`/scenarios/{id}/slider`), falling back to the REST results endpoint
 * if the socket cannot connect.
 */
export function useLiveSlider({
  scenarioId,
  backendUrl,
}: UseLiveSliderOptions): UseLiveSliderReturn {
  const [latestUpdate, setLatestUpdate] = useState<SliderUpdate | null>(null);
  const [connected, setConnected] = useState(false);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingSeverityRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const httpUrl = backendUrl.replace(/\/$/, "");
  const wsUrl = httpUrl.replace(/^http/, "ws");

  const restFallback = useCallback(
    (severity: number) => {
      if (abortRef.current) abortRef.current.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      fetch(`${httpUrl}/scenarios/${scenarioId}/results?severity=${severity}`, {
        signal: controller.signal,
      })
        .then((resp) => (resp.ok ? resp.json() : null))
        .then((data) => {
          if (!data) return;
          setLatestUpdate({
            scenario_id: scenarioId ?? "",
            severity,
            impacts: data.impacts,
            ranked_entity_ids: data.ranked_entity_ids,
            cached: false,
            latency_ms: data.latency_ms,
          });
          setLatencyMs(data.latency_ms);
        })
        .catch(() => {
          // Aborted or network error — ignore.
        });
    },
    [httpUrl, scenarioId],
  );

  useEffect(() => {
    if (!scenarioId) return undefined;

    let cancelled = false;

    function connect() {
      const socket = new WebSocket(`${wsUrl}/scenarios/${scenarioId}/slider`);
      wsRef.current = socket;

      socket.onopen = () => {
        if (cancelled) return;
        setConnected(true);
        if (pendingSeverityRef.current !== null) {
          socket.send(JSON.stringify({ severity: pendingSeverityRef.current }));
        }
      };

      socket.onmessage = (event) => {
        try {
          const data: SliderUpdate = JSON.parse(event.data);
          setLatestUpdate(data);
          setLatencyMs(data.latency_ms);
        } catch {
          // Malformed frame — ignore.
        }
      };

      socket.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        reconnectRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
      };

      socket.onerror = () => {
        socket.close();
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
      wsRef.current = null;
      setConnected(false);
    };
  }, [scenarioId, wsUrl]);

  const sendSeverity = useCallback(
    (severity: number) => {
      if (!scenarioId) return;
      pendingSeverityRef.current = severity;

      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        const socket = wsRef.current;
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ severity }));
        } else {
          restFallback(severity);
        }
      }, DEBOUNCE_MS);
    },
    [scenarioId, restFallback],
  );

  return { sendSeverity, latestUpdate, connected, latencyMs };
}
