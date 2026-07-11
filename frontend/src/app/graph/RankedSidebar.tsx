"use client";

import type { SpikeNode, SliderUpdate } from "../spike/types";

interface RankedSidebarProps {
  nodeMap: Map<string, SpikeNode>;
  update: SliderUpdate | null;
  focusNodeId: string | null;
  onFocusNode: (nodeId: string) => void;
}

const MAX_ROWS = 30;

export default function RankedSidebar({
  nodeMap,
  update,
  focusNodeId,
  onFocusNode,
}: RankedSidebarProps) {
  const ranked = update?.ranked_entity_ids.slice(0, MAX_ROWS) ?? [];

  return (
    <aside
      className="ranked-sidebar"
      id="ranked-sidebar"
      aria-label="Ranked impacted entities"
    >
      <div className="ranked-sidebar-header">
        <h2>Impacted entities</h2>
        <span className="ranked-count">
          {update?.ranked_entity_ids.length ?? 0}
        </span>
      </div>

      {ranked.length === 0 ? (
        <p className="evidence-empty">
          Run propagation to rank impacted entities.
        </p>
      ) : (
        <ol className="ranked-list" role="list">
          {ranked.map((nodeId, index) => {
            const node = nodeMap.get(nodeId);
            const impact = update?.impacts[nodeId];
            if (!node || !impact) return null;
            return (
              <li key={nodeId}>
                <button
                  type="button"
                  className={`ranked-row ${nodeId === focusNodeId ? "active" : ""}`}
                  onClick={() => onFocusNode(nodeId)}
                >
                  <span className="ranked-index">{index + 1}</span>
                  <span className="ranked-name">
                    {node.name}
                    <small>{node.node_type}</small>
                  </span>
                  <span className="ranked-score">
                    {impact.risk_score.toFixed(1)}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </aside>
  );
}
