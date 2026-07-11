import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import SeveritySlider from "./SeveritySlider";
import EvidencePanel from "./EvidencePanel";
import type {
  SpikeNode,
  SpikeEdge,
  NodeImpact,
  SelectedElement,
} from "./types";

// ---------------------------------------------------------------------------
// SeveritySlider
// ---------------------------------------------------------------------------

describe("SeveritySlider", () => {
  it("renders the slider input and severity label", () => {
    const markup = renderToStaticMarkup(
      <SeveritySlider severity={0.5} onSeverityChange={() => {}} />,
    );
    expect(markup).toContain("Severity");
    expect(markup).toContain('id="severity-input"');
    expect(markup).toContain("50%");
  });

  it("maps severity 0.0 to display 0%", () => {
    const markup = renderToStaticMarkup(
      <SeveritySlider severity={0} onSeverityChange={() => {}} />,
    );
    expect(markup).toContain("0%");
  });

  it("maps severity 1.0 to display 100%", () => {
    const markup = renderToStaticMarkup(
      <SeveritySlider severity={1.0} onSeverityChange={() => {}} />,
    );
    expect(markup).toContain("100%");
  });
});

// ---------------------------------------------------------------------------
// EvidencePanel
// ---------------------------------------------------------------------------

describe("EvidencePanel", () => {
  const sampleNode: SpikeNode = {
    node_id: "n0",
    node_type: "bank",
    name: "JPMorgan Chase",
  };

  const sampleEdge: SpikeEdge = {
    edge_id: "e0",
    source_id: "n0",
    target_id: "n1",
    weight: 0.45,
    method_id: "DER-CREDIT",
    provenance_ref: "prov:spike:e0",
  };

  const sampleImpact: NodeImpact = {
    node_id: "n0",
    raw_impact: 0.75,
    risk_score: 52.7,
    contributions: [
      {
        path_key: "test|f0|e0|n0",
        factor_id: "f0",
        hop_count: 1,
        contribution: 0.75,
        edge_ids: ["e0"],
        method_ids: ["DER-CREDIT"],
        provenance_refs: ["prov:spike:e0"],
      },
    ],
  };

  const nodeMap = new Map([["n0", sampleNode]]);
  const edgeMap = new Map([["e0", sampleEdge]]);

  it("renders nothing when nothing is selected", () => {
    const markup = renderToStaticMarkup(
      <EvidencePanel
        selected={null}
        nodeMap={nodeMap}
        edgeMap={edgeMap}
        impacts={null}
        onClose={() => {}}
      />,
    );
    expect(markup).toBe("");
  });

  it("renders node detail with impact data", () => {
    const selected: SelectedElement = {
      kind: "node",
      nodeId: "n0",
      data: sampleNode,
      impact: sampleImpact,
    };
    const markup = renderToStaticMarkup(
      <EvidencePanel
        selected={selected}
        nodeMap={nodeMap}
        edgeMap={edgeMap}
        impacts={{ n0: sampleImpact }}
        onClose={() => {}}
      />,
    );
    expect(markup).toContain("JPMorgan Chase");
    expect(markup).toContain("bank");
    expect(markup).toContain("52.7");
    expect(markup).toContain("DER-CREDIT");
    expect(markup).toContain("prov:spike:e0");
  });

  it("renders edge detail with weight and method", () => {
    const selected: SelectedElement = {
      kind: "edge",
      edgeId: "e0",
      data: sampleEdge,
    };
    const markup = renderToStaticMarkup(
      <EvidencePanel
        selected={selected}
        nodeMap={nodeMap}
        edgeMap={edgeMap}
        impacts={null}
        onClose={() => {}}
      />,
    );
    expect(markup).toContain("0.4500");
    expect(markup).toContain("DER-CREDIT");
    expect(markup).toContain("prov:spike:e0");
  });
});
