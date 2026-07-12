"use client";

import { useState } from "react";
import type { NodeImpact, PathContribution } from "../spike/types";
import type { EvidenceEdge, EvidenceNode, GraphSelection } from "./types";
import ExplanationCard from "./ExplanationCard";

/**
 * RIS-20 evidence panel: the 30-second trace (`RW-GOAL-008`).
 *
 * Click any node or edge and drill from a displayed number to the exact filing
 * sentence behind it. Every Graft 2 provenance field is rendered for every edge
 * (`RW-ALG-032`), the derivation method is shown human-readably with a link to
 * the methodology page (`RW-ALG-004`), extraction confidence is labeled and
 * low-confidence extractions are badged not hidden (`RW-SAFE-003`), and each
 * hop of a contributing path expands to its own edge panel (journey 8.2).
 */

const METHODOLOGY_HREF = "/graph/methodology";

interface EvidencePanelProps {
  selection: GraphSelection;
  nodeMap: Map<string, EvidenceNode>;
  edgeMap: Map<string, EvidenceEdge>;
  impacts: Record<string, NodeImpact> | null;
  lowConfidenceThreshold: number;
  scenarioId: string;
  backendUrl: string;
  severity: number;
  onSelectEdge: (edgeId: string) => void;
  onSelectNode: (nodeId: string) => void;
  onClose: () => void;
}

export default function EvidencePanel({
  selection,
  nodeMap,
  edgeMap,
  impacts,
  lowConfidenceThreshold,
  scenarioId,
  backendUrl,
  severity,
  onSelectEdge,
  onSelectNode,
  onClose,
}: EvidencePanelProps) {
  if (!selection) return null;

  return (
    <aside className="evidence-panel" id="evidence-panel">
      <div className="evidence-header">
        <h2 className="evidence-title">
          {selection.kind === "node" ? "Node evidence" : "Edge evidence"}
        </h2>
        <button
          className="evidence-close"
          onClick={onClose}
          aria-label="Close panel"
          id="evidence-close-btn"
        >
          ✕
        </button>
      </div>

      {selection.kind === "node" ? (
        <NodeDetail
          nodeId={selection.id}
          nodeMap={nodeMap}
          edgeMap={edgeMap}
          impact={impacts?.[selection.id] ?? null}
          scenarioId={scenarioId}
          backendUrl={backendUrl}
          severity={severity}
          onSelectEdge={onSelectEdge}
        />
      ) : (
        <EdgeDetail
          edgeId={selection.id}
          edgeMap={edgeMap}
          nodeMap={nodeMap}
          lowConfidenceThreshold={lowConfidenceThreshold}
          onSelectNode={onSelectNode}
        />
      )}
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Node detail
// ---------------------------------------------------------------------------

function NodeDetail({
  nodeId,
  nodeMap,
  edgeMap,
  impact,
  scenarioId,
  backendUrl,
  severity,
  onSelectEdge,
}: {
  nodeId: string;
  nodeMap: Map<string, EvidenceNode>;
  edgeMap: Map<string, EvidenceEdge>;
  impact: NodeImpact | null;
  scenarioId: string;
  backendUrl: string;
  severity: number;
  onSelectEdge: (edgeId: string) => void;
}) {
  const node = nodeMap.get(nodeId);
  if (!node) return <p className="evidence-empty">Node not found</p>;

  const contributions = impact?.contributions ?? [];
  const direct = contributions
    .filter((c) => c.hop_count === 1)
    .reduce((sum, c) => sum + c.contribution, 0);
  const indirect = contributions
    .filter((c) => c.hop_count > 1)
    .reduce((sum, c) => sum + c.contribution, 0);
  const ranked = [...contributions].sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution),
  );

  return (
    <div className="evidence-body">
      <dl className="evidence-fields">
        <dt>Entity</dt>
        <dd>{node.name}</dd>
        <dt>Type</dt>
        <dd className="entity-type-badge">{node.node_type}</dd>
        <dt>ID</dt>
        <dd className="mono">{node.node_id}</dd>
      </dl>

      {/* Structural centrality — labeled separately from scenario impact so the
          two channels never blur (RW-FR-019). */}
      <section className="evidence-section" id="centrality-block">
        <h3 className="evidence-subtitle">Structural centrality</h3>
        <p className="evidence-note">
          Connectivity in the graph, independent of this scenario — not an
          impact score.
        </p>
        <div className="impact-summary">
          <div className="impact-metric">
            <span className="impact-label">Transmission centrality</span>
            <span className="impact-value">{node.centrality.toFixed(3)}</span>
          </div>
        </div>
      </section>

      {/* Breach-distance (Graft 1, RIS-16). Rendered conditionally; until the
          graft lands, missing data is shown explicitly, never blank
          (RW-SAFE-003). */}
      <BreachBlock node={node} />

      <section className="evidence-section" id="impact-block">
        <h3 className="evidence-subtitle">Scenario impact</h3>
        {impact ? (
          <>
            <div className="impact-summary">
              <div className="impact-metric">
                <span className="impact-label">Risk score</span>
                <span className="impact-value risk-score">
                  {impact.risk_score.toFixed(1)}
                </span>
              </div>
              <div className="impact-metric">
                <span className="impact-label">Raw impact</span>
                <span className="impact-value">
                  {impact.raw_impact.toFixed(4)}
                </span>
              </div>
            </div>
            <div className="component-split" id="impact-components">
              <div className="component-row">
                <span className="component-label">Direct (1 hop)</span>
                <span className="component-value mono">
                  {direct.toFixed(4)}
                </span>
              </div>
              <div className="component-row">
                <span className="component-label">Indirect (2+ hops)</span>
                <span className="component-value mono">
                  {indirect.toFixed(4)}
                </span>
              </div>
            </div>

            <h3 className="evidence-subtitle">
              Top contributing paths ({ranked.length})
            </h3>
            <div className="contributions-list">
              {ranked.slice(0, 8).map((c) => (
                <PathCard
                  key={c.path_key}
                  contribution={c}
                  edgeMap={edgeMap}
                  nodeMap={nodeMap}
                  onSelectEdge={onSelectEdge}
                />
              ))}
              {ranked.length > 8 && (
                <p className="contributions-overflow">
                  + {ranked.length - 8} more paths
                </p>
              )}
            </div>

            <ExplanationCard
              key={`${nodeId}:${severity}`}
              scenarioId={scenarioId}
              backendUrl={backendUrl}
              severity={severity}
              nodeId={nodeId}
              onSelectEdge={onSelectEdge}
            />
          </>
        ) : (
          <p className="evidence-empty">
            Not impacted at the current severity — move the slider to propagate
            a shock here.
          </p>
        )}
      </section>
    </div>
  );
}

function BreachBlock({ node }: { node: EvidenceNode }) {
  // Graft 1 (RIS-16) breach-distance is not yet wired into the fixture graph.
  // Only banks/REITs carry covenants, so we surface the gap explicitly for
  // those and stay silent for entity types that never would.
  const covenantBearing =
    node.node_type === "bank" || node.node_type === "reit";
  if (!covenantBearing) return null;
  return (
    <section className="evidence-section breach-block" id="breach-block">
      <h3 className="evidence-subtitle">Breach distance</h3>
      <p className="evidence-note missing-data" data-missing="breach-distance">
        Not yet computed — covenant breach-distance (Graft 1, RIS-16) lands
        separately. Shown as explicitly missing, not zero.
      </p>
    </section>
  );
}

function PathCard({
  contribution,
  edgeMap,
  nodeMap,
  onSelectEdge,
}: {
  contribution: PathContribution;
  edgeMap: Map<string, EvidenceEdge>;
  nodeMap: Map<string, EvidenceNode>;
  onSelectEdge: (edgeId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const c = contribution;

  return (
    <div className="contribution-card">
      <button
        type="button"
        className="contribution-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="contribution-factor">{c.factor_id}</span>
        <span className="contribution-hops">
          {c.hop_count} hop{c.hop_count !== 1 ? "s" : ""} {expanded ? "▾" : "▸"}
        </span>
      </button>
      <div className="contribution-value">
        Contribution: {c.contribution.toFixed(4)}
      </div>

      {expanded && (
        <ol className="hop-list">
          {c.edge_ids.map((edgeId, i) => {
            const edge = edgeMap.get(edgeId);
            const target = edge ? nodeMap.get(edge.target_id) : undefined;
            const source = edge ? nodeMap.get(edge.source_id) : undefined;
            return (
              <li key={edgeId} className="hop-row">
                <button
                  type="button"
                  className="hop-button"
                  onClick={() => onSelectEdge(edgeId)}
                >
                  <span className="hop-index">{i + 1}</span>
                  <span className="hop-label">
                    {edge ? (
                      <>
                        {source?.name ?? edge.source_id} →{" "}
                        {target?.name ?? edge.target_id}
                        <small>
                          {edge.relationship_type} · {edge.method_id}
                        </small>
                      </>
                    ) : (
                      <span className="mono">{edgeId}</span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Edge detail
// ---------------------------------------------------------------------------

function EdgeDetail({
  edgeId,
  edgeMap,
  nodeMap,
  lowConfidenceThreshold,
  onSelectNode,
}: {
  edgeId: string;
  edgeMap: Map<string, EvidenceEdge>;
  nodeMap: Map<string, EvidenceNode>;
  lowConfidenceThreshold: number;
  onSelectNode: (nodeId: string) => void;
}) {
  const edge = edgeMap.get(edgeId);
  if (!edge) return <p className="evidence-empty">Edge not found</p>;

  const source = nodeMap.get(edge.source_id);
  const target = nodeMap.get(edge.target_id);
  const prov = edge.provenance;
  const lowConfidence = prov.extraction_confidence < lowConfidenceThreshold;

  return (
    <div className="evidence-body">
      <dl className="evidence-fields">
        <dt>Source</dt>
        <dd>
          <button
            type="button"
            className="link-button"
            onClick={() => onSelectNode(edge.source_id)}
          >
            {source?.name ?? edge.source_id}
          </button>
        </dd>
        <dt>Target</dt>
        <dd>
          <button
            type="button"
            className="link-button"
            onClick={() => onSelectNode(edge.target_id)}
          >
            {target?.name ?? edge.target_id}
          </button>
        </dd>
        <dt>Relationship</dt>
        <dd>{edge.relationship_type}</dd>
        <dt>Direction</dt>
        <dd>{edge.direction}</dd>
        <dt>Weight (signed)</dt>
        <dd className="mono">{edge.weight.toFixed(4)}</dd>
        <dt>Magnitude</dt>
        <dd className="mono">{edge.magnitude.toFixed(4)}</dd>
        <dt>Method</dt>
        <dd>
          <a className="method-badge" href={METHODOLOGY_HREF}>
            {edge.method_id}
          </a>{" "}
          <span className="method-name">{edge.method_name}</span>
        </dd>
        <dt>Method version</dt>
        <dd className="mono">{edge.method_version}</dd>
      </dl>

      <p className="method-summary">{edge.method_summary}</p>

      <section className="evidence-section" id="confidence-block">
        <h3 className="evidence-subtitle">
          Extraction / data-quality confidence
        </h3>
        <p className="evidence-note">
          Confidence in reading this figure from the filing (RW-ALG-007) — not a
          probability the risk occurs.
        </p>
        <div className="confidence-row">
          <span className="impact-value mono">
            {prov.extraction_confidence.toFixed(2)}
          </span>
          {lowConfidence && (
            <span className="low-confidence-badge" id="low-confidence-badge">
              Low confidence
            </span>
          )}
        </div>
      </section>

      <section className="evidence-section" id="dates-block">
        <dl className="evidence-fields">
          <dt>Filing date</dt>
          <dd className="mono">{prov.filing_date}</dd>
          <dt>Data as-of</dt>
          <dd className="mono">{prov.data_timestamp}</dd>
        </dl>
      </section>

      <PassageViewer provenance={prov} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Passage viewer — "click the number, see the sentence"
// ---------------------------------------------------------------------------

function PassageViewer({
  provenance,
}: {
  provenance: EvidenceEdge["provenance"];
}) {
  const p = provenance;
  return (
    <section className="evidence-section passage-viewer" id="passage-viewer">
      <h3 className="evidence-subtitle">Source passage</h3>
      <dl className="evidence-fields">
        <dt>Document</dt>
        <dd className="mono">{p.source_document_id}</dd>
        <dt>Offsets</dt>
        <dd className="mono" id="passage-offsets">
          [{p.char_start}–{p.char_end}]
        </dd>
      </dl>
      <blockquote className="passage-quote">
        <span className="passage-context">…</span>
        <mark
          className="passage-highlight"
          id="passage-highlight"
          data-char-start={p.char_start}
          data-char-end={p.char_end}
        >
          {p.source_passage}
        </mark>
        <span className="passage-context">…</span>
      </blockquote>
      <p className="evidence-note">
        Exact quoted span highlighted at stored offsets [{p.char_start}–
        {p.char_end}] in {p.source_document_id}.
      </p>
    </section>
  );
}
