"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ContagionGraph, { TYPE_COLORS } from "./ContagionGraph";
import RankedSidebar from "./RankedSidebar";
import EvidencePanel from "./EvidencePanel";
import { useLiveSlider } from "./useLiveSlider";
import SeveritySlider from "../spike/SeveritySlider";
import type {
  EvidenceEdge,
  EvidenceNode,
  GraphSeedResponse,
  GraphSelection,
} from "./types";
import "../spike/styles.css";
import "./graph.css";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
// REST calls route through the same-origin proxy so the server-side
// RISKWEAVE_API_KEY (RIS-31 / ADR-010) never reaches the client bundle. The
// WebSocket slider stays on the direct backend URL (unauthenticated,
// rate/connection-capped — see ADR-010).
const PROXY_BASE = "/api/backend";

export default function GraphPage() {
  const [seedData, setSeedData] = useState<GraphSeedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [severity, setSeverity] = useState(0.5);
  const [selected, setSelected] = useState<GraphSelection>(null);
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);
  const initialRunDone = useRef(false);

  const nodeMap = useMemo(() => {
    if (!seedData) return new Map<string, EvidenceNode>();
    return new Map(seedData.nodes.map((n) => [n.node_id, n]));
  }, [seedData]);

  const edgeMap = useMemo(() => {
    if (!seedData) return new Map<string, EvidenceEdge>();
    return new Map(seedData.edges.map((e) => [e.edge_id, e]));
  }, [seedData]);

  const shockedNodeIds = useMemo(() => {
    if (!seedData) return new Set<string>();
    return new Set(seedData.factors.map((f) => f.node_id));
  }, [seedData]);

  const { sendSeverity, latestUpdate, connected, latencyMs } = useLiveSlider({
    scenarioId: seedData?.scenario_id ?? null,
    backendUrl: BACKEND_URL,
  });

  const seedGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${PROXY_BASE}/graph/seed`, { method: "POST" });
      if (!resp.ok)
        throw new Error(`Seed failed: ${resp.status} ${resp.statusText}`);
      const data: GraphSeedResponse = await resp.json();
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
    const timer = window.setTimeout(() => void seedGraph(), 0);
    return () => window.clearTimeout(timer);
  }, [seedGraph]);

  useEffect(() => {
    if (connected && !initialRunDone.current) {
      sendSeverity(severity);
      initialRunDone.current = true;
    }
  }, [connected, severity, sendSeverity]);

  const handleSeverityChange = useCallback(
    (newSeverity: number) => {
      setSeverity(newSeverity);
      sendSeverity(newSeverity);
    },
    [sendSeverity],
  );

  const handleSelectNode = useCallback(
    (nodeId: string) => {
      if (nodeMap.has(nodeId)) {
        setSelected({ kind: "node", id: nodeId });
        setFocusNodeId(nodeId);
      }
    },
    [nodeMap],
  );

  const handleSelectEdge = useCallback(
    (edgeId: string) => {
      if (edgeMap.has(edgeId)) setSelected({ kind: "edge", id: edgeId });
    },
    [edgeMap],
  );

  const handleDeselect = useCallback(() => {
    setSelected(null);
    setFocusNodeId(null);
  }, []);

  const handleFocusNode = useCallback(
    (nodeId: string) => {
      setFocusNodeId(nodeId);
      handleSelectNode(nodeId);
    },
    [handleSelectNode],
  );

  const latencyClass =
    latencyMs === null
      ? ""
      : latencyMs < 200
        ? "good"
        : latencyMs < 500
          ? "warn"
          : "bad";

  if (loading) {
    return (
      <div className="spike-loading" id="graph-loading">
        <div className="spinner" />
        <p>Loading contagion graph…</p>
      </div>
    );
  }

  if (error || !seedData) {
    return (
      <div className="spike-error" id="graph-error">
        <p>{error ?? "Failed to load graph data"}</p>
        <button className="retry-btn" onClick={seedGraph}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="spike-page" id="graph-page">
      <header className="spike-header">
        <h1 className="spike-title">
          RiskWeave
          <span>Contagion graph — CRE decline</span>
        </h1>

        <SeveritySlider
          severity={severity}
          onSeverityChange={handleSeverityChange}
          disabled={!connected}
        />

        <div className="header-right">
          <Link className="methodology-link" href="/graph/methodology">
            Methodology
          </Link>
          <div className="connection-status" id="connection-status">
            <span
              className={`connection-dot ${connected ? "connected" : "disconnected"}`}
            />
            {connected ? "Live" : "Reconnecting…"}
          </div>
        </div>
      </header>

      <div className="spike-body">
        <RankedSidebar
          nodeMap={nodeMap}
          update={latestUpdate}
          focusNodeId={focusNodeId}
          onFocusNode={handleFocusNode}
        />

        <div className="graph-area">
          <ContagionGraph
            nodes={seedData.nodes}
            edges={seedData.edges}
            shockedNodeIds={shockedNodeIds}
            sliderUpdate={latestUpdate}
            focusNodeId={focusNodeId}
            onSelectNode={handleSelectNode}
            onSelectEdge={handleSelectEdge}
            onDeselect={handleDeselect}
          />

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
          </div>

          <div className="graph-legend" id="graph-legend">
            <div className="legend-group">
              <span className="legend-group-label">Type (fill)</span>
              {Object.entries(TYPE_COLORS).map(([type, color]) => (
                <div key={type} className="legend-item">
                  <span className="legend-dot" style={{ background: color }} />
                  {type}
                </div>
              ))}
            </div>
            <div className="legend-group">
              <span className="legend-group-label">Scenario impact</span>
              <div className="legend-item">
                <span
                  className="legend-dot"
                  style={{ background: "#ef4444" }}
                />
                high risk score (fill tint + size)
              </div>
            </div>
            <div className="legend-group">
              <span className="legend-group-label">Structural centrality</span>
              <div className="legend-item">
                <span
                  className="legend-dot"
                  style={{
                    background: "transparent",
                    border: "2px solid #38bdf8",
                  }}
                />
                connection density (ring)
              </div>
            </div>
            <div className="legend-group">
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
        </div>

        <EvidencePanel
          selection={selected}
          nodeMap={nodeMap}
          edgeMap={edgeMap}
          impacts={latestUpdate?.impacts ?? null}
          lowConfidenceThreshold={seedData.low_confidence_threshold}
          scenarioId={seedData.scenario_id}
          backendUrl={PROXY_BASE}
          severity={severity}
          onSelectEdge={handleSelectEdge}
          onSelectNode={handleSelectNode}
          onClose={handleDeselect}
        />
      </div>

      <footer className="disclaimer-footer" id="disclaimer-footer">
        Analytics only — not investment, trading, or advisory guidance.
        RiskWeave surfaces deterministic scenario propagation over curated,
        provenance-backed data; it does not predict prices or recommend
        buy/sell/hold decisions.
      </footer>
    </div>
  );
}
