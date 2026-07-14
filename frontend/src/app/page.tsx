"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ContagionGraph from "../components/ContagionGraph";
import EntityDetail from "../components/EntityDetail";
import MetricsTicker from "../components/MetricsTicker";
import ScenarioPanel from "../components/ScenarioPanel";
import StatusBar from "../components/StatusBar";
import { useLiveSlider } from "./graph/useLiveSlider";
import type { SelectedElement, SpikeSeedResponse } from "./spike/types";
import { EvidenceWorkbench } from "./workbench";
import { ShockParserPanel } from "./ShockParserPanel";
import { FreeformShockPanel } from "./FreeformShockPanel";
import "./styles.css";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
// REST calls route through the same-origin proxy so the server-side
// RISKWEAVE_API_KEY (RIS-31 / ADR-010) never reaches the client bundle. The
// WebSocket slider stays on the direct backend URL above (unauthenticated,
// rate/connection-capped — see ADR-010).
const PROXY_BASE = "/api/backend";
const DEFAULT_SCENARIO =
  "Commercial real-estate values fall 20%, refinancing rates rise 150 basis points, stress persists six quarters.";

export default function Home() {
  const [seed, setSeed] = useState<SpikeSeedResponse | null>(null);
  const [scenario, setScenario] = useState(DEFAULT_SCENARIO);
  const [severity, setSeverity] = useState(0.5);
  const [selected, setSelected] = useState<SelectedElement>(null);
  const [filter, setFilter] = useState("all");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const initialRun = useRef(false);

  const loadGraph = useCallback(async () => {
    setState("loading");
    setError(null);
    try {
      const response = await fetch(`${PROXY_BASE}/spike/seed`, {
        method: "POST",
      });
      if (!response.ok)
        throw new Error(`Graph seed failed (${response.status})`);
      setSeed((await response.json()) as SpikeSeedResponse);
      setState("ready");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Backend unavailable");
      setState("error");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadGraph(), 0);
    return () => window.clearTimeout(timer);
  }, [loadGraph]);

  const { sendSeverity, latestUpdate, connected, latencyMs } = useLiveSlider({
    scenarioId: seed?.scenario_id ?? null,
    backendUrl: BACKEND_URL,
  });

  useEffect(() => {
    if (connected && !initialRun.current) {
      initialRun.current = true;
      sendSeverity(severity);
    }
  }, [connected, sendSeverity, severity]);

  const nodeMap = useMemo(
    () => new Map((seed?.nodes ?? []).map((node) => [node.node_id, node])),
    [seed],
  );
  const types = useMemo(
    () =>
      Array.from(
        new Set((seed?.nodes ?? []).map((node) => node.node_type)),
      ).sort(),
    [seed],
  );
  const visibleNodes = useMemo(
    () =>
      (seed?.nodes ?? []).filter(
        (node) => filter === "all" || node.node_type === filter,
      ),
    [filter, seed],
  );
  const shockedNodeIds = useMemo(
    () => new Set(seed?.factors.map((factor) => factor.node_id) ?? []),
    [seed],
  );

  const chooseNode = useCallback(
    (nodeId: string) => {
      const node = nodeMap.get(nodeId);
      if (node)
        setSelected({
          kind: "node",
          nodeId,
          data: node,
          impact: latestUpdate?.impacts[nodeId] ?? null,
        });
    },
    [latestUpdate, nodeMap],
  );

  const chooseEdge = useCallback(
    (edgeId: string) => {
      const edge = seed?.edges.find(
        (candidate) => candidate.edge_id === edgeId,
      );
      if (edge) setSelected({ kind: "edge", edgeId, data: edge });
    },
    [seed],
  );

  const updateSeverity = useCallback(
    (value: number) => {
      setSeverity(value);
      sendSeverity(value);
    },
    [sendSeverity],
  );

  return (
    <main className="terminal-shell">
      <StatusBar
        scenario={seed?.scenario_id ?? "AWAITING-SCENARIO"}
        connected={connected}
        state={state}
        latencyMs={latencyMs}
      />
      <div className="terminal-workspace">
        <ScenarioPanel
          scenario={scenario}
          onScenarioChange={setScenario}
          onAnalyze={loadGraph}
          severity={severity}
          onSeverityChange={updateSeverity}
          disabled={!seed}
          types={types}
          activeType={filter}
          onTypeChange={setFilter}
          nodes={visibleNodes}
          impacts={latestUpdate?.impacts ?? {}}
          selectedNodeId={selected?.kind === "node" ? selected.nodeId : null}
          onSelectNode={chooseNode}
        />
        <section className="graph-stage" aria-label="Financial contagion graph">
          <div className="graph-stage__header">
            <div>
              <span className="micro-label">NETWORK TOPOLOGY</span>
              <strong>CONTAGION MAP / LIVE</strong>
            </div>
            <div className="graph-stage__telemetry">
              <span>ZOOM: AUTO</span>
              <span>LAYOUT: FCOSE</span>
              <span>{seed?.graph_version ?? "--"}</span>
            </div>
          </div>
          {state === "loading" && (
            <div className="terminal-state">
              <span className="skeleton-line" />
              INITIALIZING GRAPH ENGINE
            </div>
          )}
          {state === "error" && (
            <div className="terminal-state terminal-state--error">
              <strong>DATA LINK FAILED</strong>
              <span>{error}</span>
              <button onClick={loadGraph}>RETRY CONNECTION</button>
            </div>
          )}
          {seed && (
            <ContagionGraph
              nodes={seed.nodes}
              edges={seed.edges}
              shockedNodeIds={shockedNodeIds}
              sliderUpdate={latestUpdate}
              focusNodeId={selected?.kind === "node" ? selected.nodeId : null}
              visibleNodeIds={new Set(visibleNodes.map((node) => node.node_id))}
              onSelectNode={chooseNode}
              onSelectEdge={chooseEdge}
              onDeselect={() => setSelected(null)}
            />
          )}
          <div className="graph-watermark">RW / DETERMINISTIC PROPAGATION</div>
        </section>
        <EntityDetail
          selected={selected}
          nodeMap={nodeMap}
          edges={seed?.edges ?? []}
          impacts={latestUpdate?.impacts ?? {}}
          onClose={() => setSelected(null)}
          onSelectNode={chooseNode}
        />
      </div>
      <MetricsTicker
        nodes={seed?.nodes ?? []}
        edges={seed?.edges ?? []}
        update={latestUpdate}
        latencyMs={latencyMs}
      />
      <section className="terminal-aux" aria-label="Evidence review workbench">
        <div className="terminal-aux__header">
          <div>
            <span className="micro-label">EVIDENCE TRACE</span>
            <strong>ANALYST WORKBENCH / FROZEN DEMO</strong>
          </div>
          <span>REPLAY + PROVENANCE DRILLDOWN</span>
        </div>
        <div className="terminal-aux__body">
          <FreeformShockPanel backendUrl={PROXY_BASE} />
          <ShockParserPanel backendUrl={PROXY_BASE} />
          <EvidenceWorkbench />
        </div>
      </section>
    </main>
  );
}
