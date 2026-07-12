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

/** One provenance record an evidence-bound explanation cites (RIS-19). */
export interface ExplanationCitation {
  citation_id: string;
  edge_id: string;
  source_name: string;
  target_name: string;
  relationship_type: string;
  method_id: string;
  source_document_id: string;
  source_passage: string;
  char_start: number;
  char_end: number;
  filing_date: string;
  data_timestamp: string;
  extraction_confidence: number;
}

/** A labeled verified figure shown when generated prose fails the guard. */
export interface StructuredNumber {
  label: string;
  value: number;
  citation_ids: string[];
}

/**
 * A guarded, evidence-bound explanation of one node's impact
 * (GET /scenarios/{id}/explanation/{node}, RIS-19, `RW-AI-011`).
 *
 * `prose` is present only when the generated text passed the numeric guard.
 * When `used_fallback` is true, `prose` is null and `structured_numbers`
 * carries the verified figures shown in its place — the rejected prose is
 * never sent to the client.
 */
export interface ExplanationResponse {
  node_id: string;
  node_name: string;
  prose: string | null;
  used_fallback: boolean;
  attempts: number;
  guard_violations: string[];
  citations: ExplanationCitation[];
  structured_numbers: StructuredNumber[];
  model: string;
}
