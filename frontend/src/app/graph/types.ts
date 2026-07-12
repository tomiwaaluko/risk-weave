/**
 * Types for the RIS-20 evidence-panel graph, served by POST /graph/seed.
 *
 * These extend the RIS-15 spike shapes so the existing Cytoscape canvas and
 * ranked sidebar accept them unchanged, while adding the full Graft 2
 * provenance every edge carries (`RW-ALG-032`) for the drill-down panels.
 */

import type { SpikeNode, SpikeEdge } from "../spike/types";

/** Complete Graft 2 provenance for one edge weight (`RW-ALG-032`). */
export interface EdgeProvenance {
  source_document_id: string;
  filing_date: string;
  source_passage: string;
  char_start: number;
  char_end: number;
  data_timestamp: string;
  extraction_confidence: number;
}

export interface EvidenceNode extends SpikeNode {
  /** Structural transmission centrality — distinct from scenario impact. */
  centrality: number;
}

export interface EvidenceEdge extends SpikeEdge {
  relationship_type: string;
  direction: string;
  /** Unsigned derivation output; `weight` is the signed engine value. */
  magnitude: number;
  method_version: string;
  method_name: string;
  method_summary: string;
  method_source_data: string;
  provenance: EdgeProvenance;
}

export interface GraphFactor {
  factor_id: string;
  node_id: string;
  magnitude: number;
}

export interface GraphSeedResponse {
  scenario_id: string;
  snapshot_id: string;
  graph_version: string;
  state: string;
  checksum: string;
  low_confidence_threshold: number;
  nodes: EvidenceNode[];
  edges: EvidenceEdge[];
  factors: GraphFactor[];
}

/** Which graph element the evidence panel is currently drilled into. */
export type GraphSelection =
  { kind: "node"; id: string } | { kind: "edge"; id: string } | null;
