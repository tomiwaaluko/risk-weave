"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SliderUpdate } from "./types";

const DEBOUNCE_MS = 50;

interface UseSliderSocketOptions {
  scenarioId: string | null;
  backendUrl?: string;
}

interface UseSliderSocketReturn {
  /** Send a severity value (0.0–1.0) through the WebSocket or REST fallback. */
  sendSeverity: (severity: number) => void;
  /** The latest slider update from the server. */
  latestUpdate: SliderUpdate | null;
  /** Whether we have an active connection. */
  connected: boolean;
  /** Last reported recompute latency in ms. */
  latencyMs: number | null;
}

/**
 * Tries WebSocket first; falls back to REST polling via POST /spike/run.
 * The current slider WebSocket is a stub, so the REST fallback is the
 * primary path until the full slider endpoint is built.
 */
export function useSliderSocket({
  scenarioId,
  backendUrl = "ws://localhost:8000",
}: UseSliderSocketOptions): UseSliderSocketReturn {
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [latestUpdate, setLatestUpdate] = useState<SliderUpdate | null>(null);
  const [connected, setConnected] = useState(false);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Derive HTTP URL from WS URL
  const httpUrl = backendUrl.replace(/^ws/, "http");

  useEffect(() => {
    const timer = window.setTimeout(() => setConnected(Boolean(scenarioId)), 0);
    return () => {
      window.clearTimeout(timer);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, [scenarioId]);

  const sendSeverity = useCallback(
    (severity: number) => {
      if (!scenarioId) return;

      if (debounceRef.current) clearTimeout(debounceRef.current);

      debounceRef.current = setTimeout(async () => {
        // Cancel any in-flight request
        if (abortRef.current) abortRef.current.abort();
        const controller = new AbortController();
        abortRef.current = controller;

        try {
          const resp = await fetch(
            `${httpUrl}/spike/run?severity=${severity}`,
            { method: "POST", signal: controller.signal },
          );
          if (!resp.ok) return;
          const data: SliderUpdate = await resp.json();
          setLatestUpdate(data);
          setLatencyMs(data.latency_ms);
        } catch {
          // Aborted or network error — ignore
        }
      }, DEBOUNCE_MS);
    },
    [scenarioId, httpUrl],
  );

  return { sendSeverity, latestUpdate, connected, latencyMs };
}
