"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CytoscapeGraph from "./CytoscapeGraph";
import EvidencePanel from "./EvidencePanel";
import SeveritySlider from "./SeveritySlider";
import { useSliderSocket } from "./useSliderSocket";
import type {
  SelectedElement,
  SpikeEdge,
  SpikeNode,
  SpikeSeedResponse,
} from "./types";
import "./styles.css";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const WS_BACKEND_URL = BACKEND_URL.replace(/^http/, "ws");

// Node type → legend color (matches CytoscapeGraph).
const TYPE_COLORS: Record<string, string> = {
  bank: "#3b82f6",
  company: "#8b5cf6",
  reit: "#ec4899",
  security: "#f59e0b",
  commodity: "#10b981",
  geography: "#06b6d4",
  sector: "#f97316",
};

export default function SpikePage() {
  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------
  const [seedData, setSeedData] = useState<SpikeSeedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [severity, setSeverity] = useState(0.5);
  const [selected, setSelected] = useState<SelectedElement>(null);
  const initialRunDone = useRef(false);

  // -----------------------------------------------------------------------
  // Derived lookups
  // -----------------------------------------------------------------------
  const nodeMap = useMemo(() => {
    if (!seedData) return new Map<string, SpikeNode>();
    return new Map(seedData.nodes.map((n) => [n.node_id, n]));
  }, [seedData]);

  const edgeMap = useMemo(() => {
    if (!seedData) return new Map<string, SpikeEdge>();
    return new Map(seedData.edges.map((e) => [e.edge_id, e]));
  }, [seedData]);

  const shockedNodeIds = useMemo(() => {
    if (!seedData) return new Set<string>();
    return new Set(seedData.factors.map((f) => f.node_id));
  }, [seedData]);

  // -----------------------------------------------------------------------
  // WebSocket
  // -----------------------------------------------------------------------
  const { sendSeverity, latestUpdate, connected, latencyMs } = useSliderSocket({
    scenarioId: seedData?.scenario_id ?? null,
    backendUrl: WS_BACKEND_URL,
  });

  // -----------------------------------------------------------------------
  // Seed the spike graph on mount
  // -----------------------------------------------------------------------
  const seedGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${BACKEND_URL}/spike/seed`, {
        method: "POST",
      });
      if (!resp.ok) {
        throw new Error(`Seed failed: ${resp.status} ${resp.statusText}`);
      }
      const data: SpikeSeedResponse = await resp.json();
      setSeedData(data);
    } catch (err) {
      setError(
        err instanceof TypeError
          ? `Backend unreachable at ${BACKEND_URL}. Set NEXT_PUBLIC_BACKEND_URL to a live backend or run the local stack.`
          : err instanceof Error
            ? err.message
            : String(err),
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void seedGraph();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [seedGraph]);

  // -----------------------------------------------------------------------
  // Trigger initial propagation run once connected
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (connected && !initialRunDone.current) {
      sendSeverity(severity);
      initialRunDone.current = true;
    }
  }, [connected, severity, sendSeverity]);

  // -----------------------------------------------------------------------
  // Slider handler
  // -----------------------------------------------------------------------
  const handleSeverityChange = useCallback(
    (newSeverity: number) => {
      setSeverity(newSeverity);
      sendSeverity(newSeverity);
    },
    [sendSeverity],
  );

  // -----------------------------------------------------------------------
  // Selection handlers
  // -----------------------------------------------------------------------
  const handleSelectNode = useCallback(
    (nodeId: string) => {
      const node = nodeMap.get(nodeId);
      if (node) {
        setSelected({
          kind: "node",
          nodeId,
          data: node,
          impact: latestUpdate?.impacts[nodeId] ?? null,
        });
      }
    },
    [nodeMap, latestUpdate],
  );

  const handleSelectEdge = useCallback(
    (edgeId: string) => {
      const edge = edgeMap.get(edgeId);
      if (edge) {
        setSelected({ kind: "edge", edgeId, data: edge });
      }
    },
    [edgeMap],
  );

  const handleDeselect = useCallback(() => {
    setSelected(null);
  }, []);

  // -----------------------------------------------------------------------
  // Latency classification for perf overlay
  // -----------------------------------------------------------------------
  const latencyClass =
    latencyMs === null
      ? ""
      : latencyMs < 200
        ? "good"
        : latencyMs < 500
          ? "warn"
          : "bad";

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------
  if (loading) {
    return (
      <div className="spike-loading" id="spike-loading">
        <div className="spinner" />
        <p>Seeding 200-node spike graph…</p>
      </div>
    );
  }

  if (error || !seedData) {
    return (
      <div className="spike-error" id="spike-error">
        <p>{error ?? "Failed to load spike data"}</p>
        <button className="retry-btn" onClick={seedGraph}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="spike-page" id="spike-page">
      {/* Header: title, slider, connection status */}
      <header className="spike-header">
        <h1 className="spike-title">
          RiskWeave
          <span>Cytoscape.js Spike · RIS-15</span>
        </h1>

        <SeveritySlider
          severity={severity}
          onSeverityChange={handleSeverityChange}
          disabled={!connected}
        />

        <div className="connection-status" id="connection-status">
          <span
            className={`connection-dot ${connected ? "connected" : "disconnected"}`}
          />
          {connected ? "Live" : "Disconnected"}
        </div>
      </header>

      {/* Body: graph + optional evidence panel */}
      <div className="spike-body">
        <div className="graph-area">
          <CytoscapeGraph
            nodes={seedData.nodes}
            edges={seedData.edges}
            shockedNodeIds={shockedNodeIds}
            sliderUpdate={latestUpdate}
            onSelectNode={handleSelectNode}
            onSelectEdge={handleSelectEdge}
            onDeselect={handleDeselect}
          />

          {/* Performance overlay */}
          <div className="perf-overlay" id="perf-overlay">
            <div className="perf-row">
              <span className="perf-label">Nodes</span>
              <span className="perf-value">{seedData.nodes.length}</span>
            </div>
            <div className="perf-row">
              <span className="perf-label">Edges</span>
              <span className="perf-value">{seedData.edges.length}</span>
            </div>
            <div className="perf-row">
              <span className="perf-label">Latency</span>
              <span className={`perf-value ${latencyClass}`}>
                {latencyMs !== null ? `${latencyMs.toFixed(1)} ms` : "—"}
              </span>
            </div>
            <div className="perf-row">
              <span className="perf-label">Impacted</span>
              <span className="perf-value">
                {latestUpdate ? Object.keys(latestUpdate.impacts).length : "—"}
              </span>
            </div>
            <div className="perf-row">
              <span className="perf-label">Cached</span>
              <span className="perf-value">
                {latestUpdate !== null
                  ? latestUpdate.cached
                    ? "yes"
                    : "no"
                  : "—"}
              </span>
            </div>
          </div>

          {/* Node type legend */}
          <div className="graph-legend" id="graph-legend">
            {Object.entries(TYPE_COLORS).map(([type, color]) => (
              <div key={type} className="legend-item">
                <span className="legend-dot" style={{ background: color }} />
                {type}
              </div>
            ))}
            <div className="legend-item">
              <span
                className="legend-dot"
                style={{
                  background: "transparent",
                  border: "2px solid #ef4444",
                  width: 8,
                  height: 8,
                }}
              />
              shock origin
            </div>
          </div>
        </div>

        {/* Evidence panel */}
        <EvidencePanel
          selected={selected}
          nodeMap={nodeMap}
          edgeMap={edgeMap}
          impacts={latestUpdate?.impacts ?? null}
          onClose={handleDeselect}
        />
      </div>
    </div>
  );
}
