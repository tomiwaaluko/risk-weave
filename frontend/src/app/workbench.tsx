"use client";

import { useState } from "react";

type PathRecord = {
  id: string;
  label: string;
  contribution: number;
  summary: string;
  hops: EdgeRecord[];
};

type NodeRecord = {
  id: string;
  name: string;
  type: string;
  directImpact: number;
  indirectImpact: number;
  riskScore: number;
  structuralCentrality: number;
  confidenceLabel: string;
  lowConfidence: boolean;
  missingDataNote?: string;
  breachDistance?: {
    currentValue: string;
    threshold: string;
    projectedValue: string;
    headroom: string;
    riskTier: string;
  };
  paths: PathRecord[];
};

type EdgeRecord = {
  id: string;
  source: string;
  target: string;
  relationshipType: string;
  direction: "positive" | "negative";
  weight: number;
  methodId: string;
  methodName: string;
  extractionConfidence: number;
  filingDate: string;
  asOfDate: string;
  provenanceRef: string;
  passage: {
    documentId: string;
    filingDate: string;
    charStart: number;
    charEnd: number;
    quote: string;
    contextBefore: string;
    contextAfter: string;
  };
};

type ScenarioBundle = {
  id: string;
  title: string;
  pack: string;
  nlInput: string;
  snapshotId: string;
  graphVersion: string;
  engineVersion: string;
  replayReady: boolean;
  replayLabel: string;
  node: NodeRecord;
  edges: EdgeRecord[];
};

const creEdges: EdgeRecord[] = [
  {
    id: "edge-cre-loans",
    source: "Atlantic Regional Bank",
    target: "Harbor Point REIT",
    relationshipType: "credit exposure",
    direction: "positive",
    weight: 0.31,
    methodId: "DER-CREDIT",
    methodName: "CRE loan-book share",
    extractionConfidence: 0.94,
    filingDate: "2025-02-14",
    asOfDate: "2025-03-31",
    provenanceRef: "0001456789-25-000044#24821-24898",
    passage: {
      documentId: "0001456789-25-000044",
      filingDate: "2025-02-14",
      charStart: 24821,
      charEnd: 24898,
      quote:
        "Commercial real estate loans represented 31% of total held-for-investment loans.",
      contextBefore:
        "At December 31, 2024, management continued to reduce office concentration, yet",
      contextAfter:
        "The portfolio remained weighted to multifamily and office refinancing commitments.",
    },
  },
  {
    id: "edge-reit-title",
    source: "Harbor Point REIT",
    target: "Summit Title Services",
    relationshipType: "transaction services dependency",
    direction: "positive",
    weight: 0.22,
    methodId: "DER-CONCENTRATION",
    methodName: "Segment revenue concentration",
    extractionConfidence: 0.67,
    filingDate: "2025-02-26",
    asOfDate: "2025-03-31",
    provenanceRef: "0001888031-25-000012#11302-11376",
    passage: {
      documentId: "0001888031-25-000012",
      filingDate: "2025-02-26",
      charStart: 11302,
      charEnd: 11376,
      quote:
        "Roughly twenty-two percent of fee revenue was tied to commercial property transaction volume.",
      contextBefore:
        "Title and escrow demand remained uneven across regions and management disclosed that",
      contextAfter:
        "A prolonged slowdown in refinancing would reduce order counts and escrow balances.",
    },
  },
  {
    id: "edge-title-cmbs",
    source: "Summit Title Services",
    target: "Metro CMBS Trust",
    relationshipType: "servicing and issuance linkage",
    direction: "positive",
    weight: 0.16,
    methodId: "DER-BETA",
    methodName: "Observed transmission beta",
    extractionConfidence: 0.58,
    filingDate: "2025-04-30",
    asOfDate: "2025-05-31",
    provenanceRef: "CMBS-SERVICING-2025Q1#1840-1913",
    passage: {
      documentId: "CMBS-SERVICING-2025Q1",
      filingDate: "2025-04-30",
      charStart: 1840,
      charEnd: 1913,
      quote:
        "Trust servicing advances and fee collections moved materially with CRE origination volumes.",
      contextBefore:
        "In the quarter, warehouse usage declined and the issuer observed that",
      contextAfter:
        "The relationship was directionally stable but based on a shorter post-2020 sample.",
    },
  },
];

const creNode: NodeRecord = {
  id: "node-arb",
  name: "Atlantic Regional Bank",
  type: "Bank",
  directImpact: 0.62,
  indirectImpact: 0.19,
  riskScore: 55.6,
  structuralCentrality: 0.18,
  confidenceLabel: "Extraction confidence, not probability",
  lowConfidence: true,
  missingDataNote:
    "Duration pass-through for two warehouse lines is not yet available in the frozen sample.",
  breachDistance: {
    currentValue: "4.2x leverage",
    threshold: "4.5x covenant limit",
    projectedValue: "4.8x under the current shock",
    headroom: "-0.3x",
    riskTier: "Headroom exhausted",
  },
  paths: [
    {
      id: "path-1",
      label: "Direct CRE loan-book hit",
      contribution: 0.62,
      summary:
        "Office refinancing stress lands directly on the bank's CRE portfolio.",
      hops: [creEdges[0]],
    },
    {
      id: "path-2",
      label: "REIT -> title services -> CMBS loop",
      contribution: 0.19,
      summary:
        "A surprising multi-hop path compounds the direct hit through transaction and servicing dependencies.",
      hops: [creEdges[0], creEdges[1], creEdges[2]],
    },
  ],
};

const oilEdges: EdgeRecord[] = [
  {
    id: "edge-refining-logistics",
    source: "North Coast Refining",
    target: "Apex Logistics",
    relationshipType: "fuel-cost pass-through",
    direction: "positive",
    weight: 0.47,
    methodId: "DER-COMMODITY",
    methodName: "Fuel cost share",
    extractionConfidence: 0.88,
    filingDate: "2025-03-11",
    asOfDate: "2025-04-01",
    provenanceRef: "OIL-PACK-2025Q1#4201-4273",
    passage: {
      documentId: "OIL-PACK-2025Q1",
      filingDate: "2025-03-11",
      charStart: 4201,
      charEnd: 4273,
      quote:
        "Fuel represented forty-seven percent of line-haul operating expense in the peak quarter.",
      contextBefore:
        "Apex Logistics disclosed that diesel and jet exposure remained the largest variable cost and",
      contextAfter:
        "Management's surcharge recovery lagged underlying spot-price moves by one reporting cycle.",
    },
  },
  {
    id: "edge-logistics-air",
    source: "Apex Logistics",
    target: "Harbor Air Cargo",
    relationshipType: "freight demand transmission",
    direction: "positive",
    weight: 0.29,
    methodId: "DER-CONCENTRATION",
    methodName: "Customer concentration share",
    extractionConfidence: 0.74,
    filingDate: "2025-02-28",
    asOfDate: "2025-03-31",
    provenanceRef: "AIR-CARGO-2025Q1#12010-12084",
    passage: {
      documentId: "AIR-CARGO-2025Q1",
      filingDate: "2025-02-28",
      charStart: 12010,
      charEnd: 12084,
      quote:
        "Roughly twenty-nine percent of premium cargo volume was tied to domestic logistics partners.",
      contextBefore:
        "Harbor Air Cargo noted that large contract customers deferred some shipments and",
      contextAfter:
        "Yield pressure intensified when fuel surcharges could not be passed through in full.",
    },
  },
  {
    id: "edge-air-retail",
    source: "Harbor Air Cargo",
    target: "Regional Retail Basket",
    relationshipType: "inventory and margin sensitivity",
    direction: "positive",
    weight: 0.18,
    methodId: "DER-BETA",
    methodName: "Observed transmission beta",
    extractionConfidence: 0.61,
    filingDate: "2025-04-18",
    asOfDate: "2025-05-15",
    provenanceRef: "RETAIL-SENSITIVITY-2025Q1#918-990",
    passage: {
      documentId: "RETAIL-SENSITIVITY-2025Q1",
      filingDate: "2025-04-18",
      charStart: 918,
      charEnd: 990,
      quote:
        "Short-cycle inventory margins compressed when expedited air freight remained elevated.",
      contextBefore:
        "Across the sample, management teams noted that markdown cadence worsened because",
      contextAfter:
        "The estimate is directionally useful but some regional fare-elasticity data is still missing.",
    },
  },
];

const oilNode: NodeRecord = {
  id: "node-apex",
  name: "Apex Logistics",
  type: "Logistics",
  directImpact: 0.51,
  indirectImpact: 0.27,
  riskScore: 54.1,
  structuralCentrality: 0.14,
  confidenceLabel: "Extraction confidence, not probability",
  lowConfidence: true,
  missingDataNote:
    "Regional fare elasticity is still missing for two downstream carriers, so the replay bundle keeps that gap visible.",
  paths: [
    {
      id: "oil-path-1",
      label: "Refining cost shock",
      contribution: 0.51,
      summary:
        "Fuel costs land directly on line-haul margins before surcharge recovery catches up.",
      hops: [oilEdges[0]],
    },
    {
      id: "oil-path-2",
      label: "Logistics -> air cargo -> retail sensitivity",
      contribution: 0.27,
      summary:
        "An oil shock propagates through freight demand into inventory-heavy retail exposure.",
      hops: [oilEdges[0], oilEdges[1], oilEdges[2]],
    },
  ],
};

const scenarios: ScenarioBundle[] = [
  {
    id: "cre",
    title: "CRE refinancing squeeze",
    pack: "Commercial real estate",
    nlInput:
      "Commercial real-estate values fall 20%, refinancing rates rise 150 basis points, and stress persists 6 quarters.",
    snapshotId: "cre-demo-2026-07-11",
    graphVersion: "1.0.0",
    engineVersion: "adr-001-simple-path-v1",
    replayReady: true,
    replayLabel: "Replay mode: precomputed results from frozen bundle",
    node: creNode,
    edges: creEdges,
  },
  {
    id: "oil",
    title: "Oil price shock",
    pack: "Energy transmission",
    nlInput:
      "Oil prices jump 25%, jet fuel costs stay elevated for two quarters, and airlines pass only part of the shock through to fares.",
    snapshotId: "cre-demo-2026-07-11",
    graphVersion: "1.0.0",
    engineVersion: "adr-001-simple-path-v1",
    replayReady: true,
    replayLabel: "Replay mode: precomputed results from frozen bundle",
    node: oilNode,
    edges: oilEdges,
  },
];

const methodology = [
  {
    title: "Registered derivations only",
    detail:
      "Edge weights surface one of the six Section 12 methods. The UI always shows the method id, human-readable name, and evidence reference used to produce the number.",
  },
  {
    title: "As-of honesty",
    detail:
      "Every panel carries filing dates and market-data as-of dates so no impact score looks timeless.",
  },
  {
    title: "Data limitations",
    detail:
      "Free-tier equity-price inputs and short post-2020 samples are called out explicitly where they inform beta-style transmission edges.",
  },
];

function formatSigned(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function EvidenceWorkbench() {
  const [scenarioId, setScenarioId] = useState(scenarios[0].id);
  const [mode, setMode] = useState<"live" | "replay">("live");
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<
    Record<string, string>
  >(() =>
    Object.fromEntries(
      scenarios.map((scenario) => [scenario.id, scenario.edges[0].id]),
    ),
  );
  const [expandedPathIds, setExpandedPathIds] = useState<
    Record<string, string>
  >(() =>
    Object.fromEntries(
      scenarios.map((scenario) => [
        scenario.id,
        scenario.node.paths[1]?.id ?? scenario.node.paths[0]?.id ?? "",
      ]),
    ),
  );
  const scenario =
    scenarios.find((item) => item.id === scenarioId) ?? scenarios[0];
  const node = scenario.node;
  const edges = scenario.edges;
  const selectedEdgeId = selectedEdgeIds[scenario.id] ?? edges[0].id;
  const expandedPathId =
    expandedPathIds[scenario.id] ??
    node.paths[1]?.id ??
    node.paths[0]?.id ??
    "";

  const selectedEdge =
    edges.find((edge) => edge.id === selectedEdgeId) ?? edges[0];
  const highlightedPassage = `${selectedEdge.passage.contextBefore} ${selectedEdge.passage.quote} ${selectedEdge.passage.contextAfter}`;

  return (
    <main className="app-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">RW-FR-021 • RW-ALG-032 • RW-GOAL-008</p>
          <h1>Trace any visible number to its source in under 30 seconds.</h1>
          <p className="hero-copy">
            This evidence workbench turns the graph into a click-through audit
            trail: node impact, contributing path, derivation method, source
            passage, and exact character offsets.
          </p>
        </div>
        <div className="hero-card">
          <p className="hero-kicker">
            {mode === "live" ? "Live recompute" : "Replay fallback"}
          </p>
          <strong>3 clicks from score to source sentence</strong>
          <span>
            {mode === "live"
              ? "Node panel → path hop → passage viewer"
              : scenario.replayLabel}
          </span>
        </div>
      </section>

      <section className="demo-toolbar panel" aria-label="Frozen demo controls">
        <div className="toolbar-block">
          <p className="panel-eyebrow">Scenario pack</p>
          <div className="pill-row">
            {scenarios.map((item) => (
              <button
                className={`pill ${item.id === scenario.id ? "active" : ""}`}
                key={item.id}
                type="button"
                onClick={() => setScenarioId(item.id)}
              >
                {item.title}
              </button>
            ))}
          </div>
          <p className="toolbar-copy">{scenario.nlInput}</p>
        </div>

        <div className="toolbar-block">
          <p className="panel-eyebrow">Mode</p>
          <div className="pill-row">
            <button
              className={`pill ${mode === "live" ? "active" : ""}`}
              type="button"
              onClick={() => setMode("live")}
            >
              Live recompute
            </button>
            <button
              className={`pill ${mode === "replay" ? "active" : ""}`}
              type="button"
              onClick={() => setMode("replay")}
            >
              Replay fallback
            </button>
          </div>
          <div className="bundle-meta">
            <span>Snapshot: {scenario.snapshotId}</span>
            <span>Graph: {scenario.graphVersion}</span>
            <span>Engine: {scenario.engineVersion}</span>
          </div>
        </div>
      </section>

      <section className="workspace-grid" aria-label="Evidence panel demo">
        <article className="panel graph-panel">
          <div className="panel-header">
            <div>
              <p className="panel-eyebrow">Selected node</p>
              <h2>{node.name}</h2>
            </div>
            <span className="badge warning">
              Low-confidence evidence present
            </span>
          </div>

          <div className="metrics-grid">
            <div className="metric">
              <span>Direct impact</span>
              <strong>{formatSigned(node.directImpact)}</strong>
            </div>
            <div className="metric">
              <span>Indirect impact</span>
              <strong>{formatSigned(node.indirectImpact)}</strong>
            </div>
            <div className="metric">
              <span>Risk score</span>
              <strong>{node.riskScore.toFixed(1)}</strong>
            </div>
            <div className="metric">
              <span>Structural centrality</span>
              <strong>{formatPercent(node.structuralCentrality)}</strong>
            </div>
          </div>

          <div className="callout">
            <strong>Breach-distance block</strong>
            <p>
              {node.breachDistance?.currentValue} today against a{" "}
              {node.breachDistance?.threshold}; projected to{" "}
              {node.breachDistance?.projectedValue} with{" "}
              {node.breachDistance?.headroom} of headroom. Risk tier:{" "}
              {node.breachDistance?.riskTier}.
            </p>
          </div>

          <div className="callout subtle">
            <strong>{node.confidenceLabel}</strong>
            <p>{node.missingDataNote}</p>
          </div>

          <div
            className="path-list"
            role="list"
            aria-label="Contributing paths"
          >
            {node.paths.map((path) => {
              const isExpanded = path.id === expandedPathId;

              return (
                <div className="path-card" key={path.id}>
                  <button
                    className="path-button"
                    type="button"
                    onClick={() =>
                      setExpandedPathIds((current) => ({
                        ...current,
                        [scenario.id]: isExpanded ? "" : path.id,
                      }))
                    }
                  >
                    <span>
                      {path.label}
                      <small>{path.summary}</small>
                    </span>
                    <strong>{formatSigned(path.contribution)}</strong>
                  </button>

                  {isExpanded ? (
                    <div className="hop-list" role="list">
                      {path.hops.map((hop, index) => (
                        <button
                          className={`hop-card ${hop.id === selectedEdgeId ? "active" : ""}`}
                          key={hop.id}
                          type="button"
                          onClick={() =>
                            setSelectedEdgeIds((current) => ({
                              ...current,
                              [scenario.id]: hop.id,
                            }))
                          }
                        >
                          <span className="hop-index">Hop {index + 1}</span>
                          <span className="hop-route">
                            {hop.source} → {hop.target}
                          </span>
                          <span className="hop-meta">
                            {hop.relationshipType} • {hop.methodId} •{" "}
                            {formatSigned(hop.weight)}
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </article>

        <article className="panel edge-panel">
          <div className="panel-header">
            <div>
              <p className="panel-eyebrow">Selected edge</p>
              <h2>
                {selectedEdge.source} → {selectedEdge.target}
              </h2>
            </div>
            <span
              className={`badge ${selectedEdge.extractionConfidence < 0.7 ? "warning" : "ok"}`}
            >
              {Math.round(selectedEdge.extractionConfidence * 100)}% confidence
            </span>
          </div>

          <dl className="detail-grid">
            <div>
              <dt>Relationship type</dt>
              <dd>{selectedEdge.relationshipType}</dd>
            </div>
            <div>
              <dt>Direction</dt>
              <dd>{selectedEdge.direction}</dd>
            </div>
            <div>
              <dt>Weight</dt>
              <dd>{formatSigned(selectedEdge.weight)}</dd>
            </div>
            <div>
              <dt>Method</dt>
              <dd>
                {selectedEdge.methodId} · {selectedEdge.methodName}
              </dd>
            </div>
            <div>
              <dt>Filing date</dt>
              <dd>{selectedEdge.filingDate}</dd>
            </div>
            <div>
              <dt>As-of date</dt>
              <dd>{selectedEdge.asOfDate}</dd>
            </div>
            <div>
              <dt>Provenance ref</dt>
              <dd>{selectedEdge.provenanceRef}</dd>
            </div>
          </dl>

          <div className="methodology-link">
            <span>Methodology / honesty page</span>
            <a href="#methodology">Review derivation and source limitations</a>
          </div>
        </article>

        <article className="panel passage-panel">
          <div className="panel-header">
            <div>
              <p className="panel-eyebrow">Passage viewer</p>
              <h2>Exact quoted span with surrounding context</h2>
            </div>
          </div>

          <div className="passage-meta">
            <span>Doc ID: {selectedEdge.passage.documentId}</span>
            <span>Filed: {selectedEdge.passage.filingDate}</span>
            <span>
              Offsets: {selectedEdge.passage.charStart}-
              {selectedEdge.passage.charEnd}
            </span>
          </div>

          <p className="passage">
            {highlightedPassage.split(selectedEdge.passage.quote)[0]}
            <mark>{selectedEdge.passage.quote}</mark>
            {highlightedPassage.split(selectedEdge.passage.quote)[1]}
          </p>
        </article>
      </section>

      <section className="methodology-panel panel" id="methodology">
        <div className="panel-header">
          <div>
            <p className="panel-eyebrow">Methodology / honesty page</p>
            <h2>What the presenter can say when judges probe the number</h2>
          </div>
        </div>

        <div className="methodology-grid">
          {methodology.map((item) => (
            <article className="method-card" key={item.title}>
              <h3>{item.title}</h3>
              <p>{item.detail}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
