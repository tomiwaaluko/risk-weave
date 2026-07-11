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

const edges: EdgeRecord[] = [
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

const node: NodeRecord = {
  id: "node-arb",
  name: "Atlantic Regional Bank",
  type: "Bank",
  directImpact: 0.62,
  indirectImpact: 0.19,
  riskScore: 55.6,
  structuralCentrality: 0.18,
  confidenceLabel: "Extraction confidence, not probability",
  lowConfidence: true,
  missingDataNote: "Duration pass-through for two warehouse lines is not yet available in the frozen sample.",
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
      summary: "Office refinancing stress lands directly on the bank's CRE portfolio.",
      hops: [edges[0]],
    },
    {
      id: "path-2",
      label: "REIT -> title services -> CMBS loop",
      contribution: 0.19,
      summary: "A surprising multi-hop path compounds the direct hit through transaction and servicing dependencies.",
      hops: [edges[0], edges[1], edges[2]],
    },
  ],
};

const methodology = [
  {
    title: "Registered derivations only",
    detail: "Edge weights surface one of the six Section 12 methods. The UI always shows the method id, human-readable name, and evidence reference used to produce the number.",
  },
  {
    title: "As-of honesty",
    detail: "Every panel carries filing dates and market-data as-of dates so no impact score looks timeless.",
  },
  {
    title: "Data limitations",
    detail: "Free-tier equity-price inputs and short post-2020 samples are called out explicitly where they inform beta-style transmission edges.",
  },
];

function formatSigned(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function EvidenceWorkbench() {
  const [selectedEdgeId, setSelectedEdgeId] = useState(edges[0].id);
  const [expandedPathId, setExpandedPathId] = useState(node.paths[1].id);

  const selectedEdge = edges.find((edge) => edge.id === selectedEdgeId) ?? edges[0];
  const highlightedPassage = `${selectedEdge.passage.contextBefore} ${selectedEdge.passage.quote} ${selectedEdge.passage.contextAfter}`;

  return (
    <main className="app-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">RW-FR-021 • RW-ALG-032 • RW-GOAL-008</p>
          <h1>Trace any visible number to its source in under 30 seconds.</h1>
          <p className="hero-copy">
            This evidence workbench turns the graph into a click-through audit trail:
            node impact, contributing path, derivation method, source passage, and
            exact character offsets.
          </p>
        </div>
        <div className="hero-card">
          <p className="hero-kicker">Timed drill</p>
          <strong>3 clicks from score to source sentence</strong>
          <span>Node panel → path hop → passage viewer</span>
        </div>
      </section>

      <section className="workspace-grid" aria-label="Evidence panel demo">
        <article className="panel graph-panel">
          <div className="panel-header">
            <div>
              <p className="panel-eyebrow">Selected node</p>
              <h2>{node.name}</h2>
            </div>
            <span className="badge warning">Low-confidence evidence present</span>
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
              {node.breachDistance?.projectedValue} with {node.breachDistance?.headroom}{" "}
              of headroom. Risk tier: {node.breachDistance?.riskTier}.
            </p>
          </div>

          <div className="callout subtle">
            <strong>{node.confidenceLabel}</strong>
            <p>{node.missingDataNote}</p>
          </div>

          <div className="path-list" role="list" aria-label="Contributing paths">
            {node.paths.map((path) => {
              const isExpanded = path.id === expandedPathId;

              return (
                <div className="path-card" key={path.id}>
                  <button
                    className="path-button"
                    type="button"
                    onClick={() => setExpandedPathId(isExpanded ? "" : path.id)}
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
                          onClick={() => setSelectedEdgeId(hop.id)}
                        >
                          <span className="hop-index">Hop {index + 1}</span>
                          <span className="hop-route">
                            {hop.source} → {hop.target}
                          </span>
                          <span className="hop-meta">
                            {hop.relationshipType} • {hop.methodId} • {formatSigned(hop.weight)}
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
            <span className={`badge ${selectedEdge.extractionConfidence < 0.7 ? "warning" : "ok"}`}>
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
              Offsets: {selectedEdge.passage.charStart}-{selectedEdge.passage.charEnd}
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
