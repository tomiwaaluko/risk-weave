import type { SliderUpdate, SpikeEdge, SpikeNode } from "../app/spike/types";

export default function MetricsTicker({
  nodes,
  edges,
  update,
  latencyMs,
}: {
  nodes: SpikeNode[];
  edges: SpikeEdge[];
  update: SliderUpdate | null;
  latencyMs: number | null;
}) {
  const impacts = Object.values(update?.impacts ?? {});
  const depth = Math.max(
    0,
    ...impacts.flatMap((impact) =>
      impact.contributions.map((path) => path.hop_count),
    ),
  );
  const leader = update?.ranked_entity_ids[0];
  const leaderName =
    nodes.find((node) => node.node_id === leader)?.name ?? "PENDING";
  return (
    <footer className="metrics-ticker">
      <div className="ticker-label">PROPAGATION SUMMARY</div>
      <TickerItem label="ENTITIES" value={nodes.length.toString()} />
      <TickerItem label="AFFECTED" value={impacts.length.toString()} accent />
      <TickerItem label="MAX DEPTH" value={`${depth} HOPS`} />
      <TickerItem label="HIGHEST IMPACT" value={leaderName} warning />
      <TickerItem label="GRAPH EDGES" value={edges.length.toString()} />
      <TickerItem
        label="RECOMPUTE"
        value={latencyMs === null ? "---" : `${latencyMs.toFixed(0)} MS`}
      />
      <div className="ticker-disclaimer">
        MODELED RISK / NOT INVESTMENT ADVICE
      </div>
    </footer>
  );
}
function TickerItem({
  label,
  value,
  accent,
  warning,
}: {
  label: string;
  value: string;
  accent?: boolean;
  warning?: boolean;
}) {
  return (
    <div className="ticker-item">
      <span>{label}</span>
      <strong className={accent ? "accent" : warning ? "warning" : ""}>
        {value}
      </strong>
    </div>
  );
}
