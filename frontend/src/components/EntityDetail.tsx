"use client";

import type {
  NodeImpact,
  SelectedElement,
  SpikeEdge,
  SpikeNode,
} from "@/app/spike/types";

export default function EntityDetail({
  selected,
  nodeMap,
  edges,
  impacts,
  onClose,
  onSelectNode,
}: {
  selected: SelectedElement;
  nodeMap: Map<string, SpikeNode>;
  edges: SpikeEdge[];
  impacts: Record<string, NodeImpact>;
  onClose: () => void;
  onSelectNode: (id: string) => void;
}) {
  if (!selected) return null;
  if (selected.kind === "edge") {
    const edge = selected.data;
    return (
      <aside className="entity-detail">
        <DetailHeader title="RELATIONSHIP DETAIL" onClose={onClose} />
        <div className="detail-scroll">
          <p className="detail-kicker">
            {nodeMap.get(edge.source_id)?.name ?? edge.source_id} →{" "}
            {nodeMap.get(edge.target_id)?.name ?? edge.target_id}
          </p>
          <Metric label="TRANSMISSION WEIGHT" value={edge.weight.toFixed(4)} />
          <DataRows
            rows={[
              ["DERIVATION", edge.method_id],
              ["PROVENANCE REF", edge.provenance_ref],
              ["EDGE ID", edge.edge_id],
            ]}
          />
        </div>
      </aside>
    );
  }
  const node = selected.data;
  const impact = impacts[node.node_id];
  const connected = edges.filter(
    (edge) =>
      edge.source_id === node.node_id || edge.target_id === node.node_id,
  );
  const score = impact?.risk_score ?? 0;
  const provenance = Array.from(
    new Set(
      impact?.contributions.flatMap((item) => item.provenance_refs) ?? [],
    ),
  );
  return (
    <aside className="entity-detail">
      <DetailHeader title="ENTITY INTELLIGENCE" onClose={onClose} />
      <div className="detail-scroll">
        <div className="entity-identity">
          <span className="entity-orb" data-type={node.node_type} />
          <div>
            <p>{node.node_type.toUpperCase()}</p>
            <h2>{node.name}</h2>
            <code>{node.node_id}</code>
          </div>
        </div>
        <Metric
          label="CURRENT IMPACT SCORE"
          value={score.toFixed(1)}
          suffix="/100"
          tone={score >= 60 ? "danger" : score >= 30 ? "warning" : "cool"}
        />
        <div className="impact-meter">
          <span style={{ width: `${Math.min(100, score)}%` }} />
        </div>
        <DataRows
          rows={[
            ["RAW IMPACT", impact?.raw_impact.toFixed(4) ?? "NOT COMPUTED"],
            ["SECTOR", "NOT SUPPLIED"],
            ["BREACH DISTANCE", "NOT SUPPLIED"],
          ]}
        />
        <section className="detail-section">
          <h3>
            EXPOSURE PATHS <span>{impact?.contributions.length ?? 0}</span>
          </h3>
          {impact?.contributions.slice(0, 5).map((path) => (
            <div className="path-row" key={path.path_key}>
              <div>
                <strong>{path.factor_id}</strong>
                <span>
                  {path.hop_count} HOP / {path.method_ids.join(" → ")}
                </span>
              </div>
              <b>{path.contribution.toFixed(4)}</b>
            </div>
          )) ?? <p className="empty-data">AWAITING PROPAGATION RESULT</p>}
        </section>
        <section className="detail-section">
          <h3>
            CONNECTED ENTITIES <span>{connected.length}</span>
          </h3>
          {connected.slice(0, 8).map((edge) => {
            const id =
              edge.source_id === node.node_id ? edge.target_id : edge.source_id;
            return (
              <button
                className="connection-row"
                onClick={() => onSelectNode(id)}
                key={edge.edge_id}
              >
                <span>{nodeMap.get(id)?.name ?? id}</span>
                <b>{edge.weight.toFixed(2)}</b>
              </button>
            );
          })}
        </section>
        <section className="detail-section">
          <h3>
            EVIDENCE / PROVENANCE <span>{provenance.length}</span>
          </h3>
          {provenance.length ? (
            provenance.slice(0, 6).map((ref) => (
              <div className="provenance-row" key={ref}>
                <span>VERIFIED REF</span>
                <code>{ref}</code>
              </div>
            ))
          ) : (
            <p className="empty-data">
              NO PROVENANCE REFERENCES IN CURRENT RESULT
            </p>
          )}
        </section>
      </div>
    </aside>
  );
}

function DetailHeader({
  title,
  onClose,
}: {
  title: string;
  onClose: () => void;
}) {
  return (
    <header className="detail-header">
      <span>{title}</span>
      <button aria-label="Close detail panel" onClick={onClose}>
        ×
      </button>
    </header>
  );
}
function Metric({
  label,
  value,
  suffix,
  tone = "cool",
}: {
  label: string;
  value: string;
  suffix?: string;
  tone?: string;
}) {
  return (
    <div className={`hero-metric ${tone}`}>
      <span>{label}</span>
      <strong>
        {value}
        <small>{suffix}</small>
      </strong>
    </div>
  );
}
function DataRows({ rows }: { rows: string[][] }) {
  return (
    <dl className="data-rows">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
