/** TypeScript types for the RIS-15 Cytoscape.js spike (mirrors backend models). */

// ---------------------------------------------------------------------------
// Graph topology from POST /spike/seed
// ---------------------------------------------------------------------------

export interface SpikeNode {
  node_id: string;
  node_type: string;
  name: string;
}

export interface SpikeEdge {
  edge_id: string;
  source_id: string;
  target_id: string;
  weight: number;
  method_id: string;
  provenance_ref: string;
}

export interface SpikeFactor {
  factor_id: string;
  node_id: string;
  magnitude: number;
}

export interface SpikeSeedResponse {
  scenario_id: string;
  snapshot_id: string;
  graph_version: string;
  state: string;
  nodes: SpikeNode[];
  edges: SpikeEdge[];
  factors: SpikeFactor[];
}

// ---------------------------------------------------------------------------
// Propagation results from POST /spike/run
// ---------------------------------------------------------------------------

export interface PathContribution {
  path_key: string;
  factor_id: string;
  target_node_id: string;
  hop_count: number;
  contribution: number;
  edge_ids: string[];
  method_ids: string[];
  provenance_refs: string[];
}

export interface NodeImpact {
  node_id: string;
  raw_impact: number;
  risk_score: number;
  contributions: PathContribution[];
}

/** Response from POST /spike/run and used by the slider hook. */
export interface SliderUpdate {
  scenario_id: string;
  severity: number;
  impacts: Record<string, NodeImpact>;
  ranked_entity_ids: string[];
  latency_ms: number;
  cached: boolean;
}

// ---------------------------------------------------------------------------
// UI state
// ---------------------------------------------------------------------------

export type SelectedElement =
  | { kind: "node"; nodeId: string; data: SpikeNode; impact: NodeImpact | null }
  | { kind: "edge"; edgeId: string; data: SpikeEdge }
  | null;
