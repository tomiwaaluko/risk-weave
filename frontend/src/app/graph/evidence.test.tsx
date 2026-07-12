import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import EvidencePanel from "./EvidencePanel";
import type { EvidenceEdge, EvidenceNode } from "./types";
import type { NodeImpact } from "../spike/types";

// ---------------------------------------------------------------------------
// Fixtures mirroring the /graph/seed payload shape
// ---------------------------------------------------------------------------

const PASSAGE =
  "Our portfolio consists primarily of Class A office properties, which represented approximately 92% of our total revenues.";
const CHAR_START = 41250;

const EDGE: EvidenceEdge = {
  edge_id: "edge:abc123",
  source_id: "cre-office",
  target_id: "bxp",
  weight: 0.92,
  magnitude: 0.92,
  method_id: "DER-CONCENTRATION",
  method_version: "1.0.0",
  method_name: "Supplier / customer dependency",
  method_summary:
    "Disclosed revenue-concentration percentage (validated verbatim).",
  method_source_data: "10-K concentration disclosures, XBRL segments",
  relationship_type: "sector_exposure",
  direction: "positive",
  provenance_ref: "0000038777-24-000012#41250-41371",
  provenance: {
    source_document_id: "0000038777-24-000012",
    filing_date: "2024-02-27",
    source_passage: PASSAGE,
    char_start: CHAR_START,
    char_end: CHAR_START + PASSAGE.length,
    data_timestamp: "2023-12-31T00:00:00",
    extraction_confidence: 0.62, // below the 0.75 threshold -> low-confidence
  },
};

const OFFICE: EvidenceNode = {
  node_id: "cre-office",
  node_type: "sector",
  name: "U.S. Office Commercial Real Estate",
  centrality: 0.184,
};
const BXP: EvidenceNode = {
  node_id: "bxp",
  node_type: "reit",
  name: "Boston Properties (BXP, Inc.)",
  centrality: 0.125,
};

const nodeMap = new Map<string, EvidenceNode>([
  [OFFICE.node_id, OFFICE],
  [BXP.node_id, BXP],
]);
const edgeMap = new Map<string, EvidenceEdge>([[EDGE.edge_id, EDGE]]);

const IMPACT: NodeImpact = {
  node_id: "bxp",
  raw_impact: 0.5,
  risk_score: 61.2,
  contributions: [
    {
      path_key: "p1",
      factor_id: "cre-office-shock",
      target_node_id: "bxp",
      hop_count: 1,
      contribution: 0.42,
      edge_ids: ["edge:abc123"],
      method_ids: ["DER-CONCENTRATION"],
      provenance_refs: ["0000038777-24-000012#41250-41371"],
    },
    {
      path_key: "p2",
      factor_id: "nyc-metro-shock",
      target_node_id: "bxp",
      hop_count: 2,
      contribution: 0.08,
      edge_ids: ["edge:abc123"],
      method_ids: ["DER-GEO"],
      provenance_refs: ["ref"],
    },
  ],
};

const noop = () => {};

function renderEdge() {
  return renderToStaticMarkup(
    <EvidencePanel
      selection={{ kind: "edge", id: EDGE.edge_id }}
      nodeMap={nodeMap}
      edgeMap={edgeMap}
      impacts={null}
      lowConfidenceThreshold={0.75}
      scenarioId="cre-demo"
      backendUrl="http://localhost:8000"
      severity={1}
      onSelectEdge={noop}
      onSelectNode={noop}
      onClose={noop}
    />,
  );
}

// ---------------------------------------------------------------------------
// Edge panel: every Graft 2 field renders (RW-ALG-032, RW-FR-021)
// ---------------------------------------------------------------------------

describe("EvidencePanel edge detail", () => {
  it("renders every Graft 2 provenance field", () => {
    const m = renderEdge();
    expect(m).toContain("sector_exposure"); // relationship type
    expect(m).toContain("positive"); // direction
    expect(m).toContain("0.9200"); // weight / magnitude
    expect(m).toContain("DER-CONCENTRATION"); // method id
    expect(m).toContain("Supplier / customer dependency"); // human method name
    expect(m).toContain("2024-02-27"); // filing date
    expect(m).toContain("2023-12-31T00:00:00"); // data as-of timestamp
    expect(m).toContain("0000038777-24-000012"); // source document id
    expect(m).toContain("0.62"); // extraction confidence value
  });

  it("labels confidence as extraction/data-quality, not risk probability", () => {
    expect(renderEdge()).toContain("Extraction / data-quality confidence");
  });

  it("badges low-confidence extractions instead of hiding them (RW-SAFE-003)", () => {
    const m = renderEdge();
    expect(m).toContain("low-confidence-badge");
    expect(m).toContain("Low confidence");
  });

  it("links the method to the methodology page (RW-ALG-004)", () => {
    expect(renderEdge()).toContain('href="/graph/methodology"');
  });

  it("highlights the exact quoted span at the stored offsets", () => {
    const m = renderEdge();
    // The mark must contain the passage verbatim and expose the offsets.
    expect(m).toContain(`data-char-start="${CHAR_START}"`);
    expect(m).toContain(`data-char-end="${CHAR_START + PASSAGE.length}"`);
    expect(m).toContain("approximately 92% of our total revenues");
    // Offset span must equal passage length exactly (highlight spot-check).
    expect(EDGE.provenance.char_end - EDGE.provenance.char_start).toBe(
      PASSAGE.length,
    );
    expect(m).toContain('id="passage-offsets"');
    expect(m).toContain(`[${CHAR_START}–${CHAR_START + PASSAGE.length}]`);
  });
});

// ---------------------------------------------------------------------------
// Node panel: centrality separated from impact; breach explicit-missing
// ---------------------------------------------------------------------------

describe("EvidencePanel node detail", () => {
  function renderNode(nodeId: string, impact: NodeImpact | null) {
    return renderToStaticMarkup(
      <EvidencePanel
        selection={{ kind: "node", id: nodeId }}
        nodeMap={nodeMap}
        edgeMap={edgeMap}
        impacts={impact ? { [nodeId]: impact } : {}}
        lowConfidenceThreshold={0.75}
        scenarioId="cre-demo"
        backendUrl="http://localhost:8000"
        severity={1}
        onSelectEdge={noop}
        onSelectNode={noop}
        onClose={noop}
      />,
    );
  }

  it("separates structural centrality from scenario impact", () => {
    const m = renderNode("bxp", IMPACT);
    expect(m).toContain("Structural centrality");
    expect(m).toContain("0.125"); // centrality value
    expect(m).toContain("Scenario impact");
    expect(m).toContain("61.2"); // risk score
  });

  it("splits direct vs indirect impact components", () => {
    const m = renderNode("bxp", IMPACT);
    expect(m).toContain("Direct (1 hop)");
    expect(m).toContain("Indirect (2+ hops)");
    expect(m).toContain("Top contributing paths");
  });

  it("shows breach-distance as explicitly missing for covenant-bearing nodes", () => {
    const m = renderNode("bxp", IMPACT);
    expect(m).toContain('data-missing="breach-distance"');
    expect(m).toContain("Not yet computed");
  });

  it("does not render a breach block for non-covenant entity types", () => {
    const m = renderNode("cre-office", null);
    expect(m).not.toContain('id="breach-block"');
  });
});
