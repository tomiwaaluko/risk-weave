"use client";

import type {
  SelectedElement,
  SpikeNode,
  SpikeEdge,
  NodeImpact,
} from "./types";

interface EvidencePanelProps {
  selected: SelectedElement;
  nodeMap: Map<string, SpikeNode>;
  edgeMap: Map<string, SpikeEdge>;
  impacts: Record<string, NodeImpact> | null;
  onClose: () => void;
}

export default function EvidencePanel({
  selected,
  nodeMap,
  edgeMap,
  impacts,
  onClose,
}: EvidencePanelProps) {
  if (!selected) return null;

  return (
    <aside className="evidence-panel" id="evidence-panel">
      <div className="evidence-header">
        <h2 className="evidence-title">
          {selected.kind === "node" ? "Node Detail" : "Edge Detail"}
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

      {selected.kind === "node" && (
        <NodeDetail
          nodeId={selected.nodeId}
          nodeMap={nodeMap}
          impact={impacts?.[selected.nodeId] ?? null}
        />
      )}

      {selected.kind === "edge" && (
        <EdgeDetail
          edgeId={selected.edgeId}
          edgeMap={edgeMap}
          nodeMap={nodeMap}
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
  impact,
}: {
  nodeId: string;
  nodeMap: Map<string, SpikeNode>;
  impact: NodeImpact | null;
}) {
  const node = nodeMap.get(nodeId);
  if (!node) return <p className="evidence-empty">Node not found</p>;

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

      {impact ? (
        <>
          <div className="impact-summary">
            <div className="impact-metric">
              <span className="impact-label">Risk Score</span>
              <span className="impact-value risk-score">
                {impact.risk_score.toFixed(1)}
              </span>
            </div>
            <div className="impact-metric">
              <span className="impact-label">Raw Impact</span>
              <span className="impact-value">
                {impact.raw_impact.toFixed(4)}
              </span>
            </div>
          </div>

          <h3 className="evidence-subtitle">
            Path Contributions ({impact.contributions.length})
          </h3>
          <div className="contributions-list">
            {impact.contributions.slice(0, 10).map((c) => (
              <div key={c.path_key} className="contribution-card">
                <div className="contribution-header">
                  <span className="contribution-factor">{c.factor_id}</span>
                  <span className="contribution-hops">
                    {c.hop_count} hop{c.hop_count !== 1 ? "s" : ""}
                  </span>
                </div>
                <div className="contribution-value">
                  Contribution: {c.contribution.toFixed(4)}
                </div>
                <div className="contribution-detail">
                  <span className="detail-label">Methods:</span>{" "}
                  {c.method_ids.join(" → ")}
                </div>
                <div className="contribution-detail">
                  <span className="detail-label">Provenance:</span>{" "}
                  {c.provenance_refs.join(", ")}
                </div>
                <div className="contribution-detail">
                  <span className="detail-label">Edges:</span>{" "}
                  {c.edge_ids.join(" → ")}
                </div>
              </div>
            ))}
            {impact.contributions.length > 10 && (
              <p className="contributions-overflow">
                + {impact.contributions.length - 10} more paths
              </p>
            )}
          </div>
        </>
      ) : (
        <p className="evidence-empty">No impact data — run propagation first</p>
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
}: {
  edgeId: string;
  edgeMap: Map<string, SpikeEdge>;
  nodeMap: Map<string, SpikeNode>;
}) {
  const edge = edgeMap.get(edgeId);
  if (!edge) return <p className="evidence-empty">Edge not found</p>;

  const source = nodeMap.get(edge.source_id);
  const target = nodeMap.get(edge.target_id);

  return (
    <div className="evidence-body">
      <dl className="evidence-fields">
        <dt>Source</dt>
        <dd>{source?.name ?? edge.source_id}</dd>
        <dt>Target</dt>
        <dd>{target?.name ?? edge.target_id}</dd>
        <dt>Weight</dt>
        <dd className="mono">{edge.weight.toFixed(4)}</dd>
        <dt>Derivation Method</dt>
        <dd className="method-badge">{edge.method_id}</dd>
        <dt>Provenance</dt>
        <dd className="mono">{edge.provenance_ref}</dd>
        <dt>Edge ID</dt>
        <dd className="mono">{edge.edge_id}</dd>
      </dl>
    </div>
  );
}
