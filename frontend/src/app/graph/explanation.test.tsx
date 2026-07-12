import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import ExplanationCard from "./ExplanationCard";

// ---------------------------------------------------------------------------
// RIS-19: the AI explanation is evidence-bound. renderToStaticMarkup never runs
// effects, so the card renders in its initial loading state — the deterministic,
// network-free surface these tests assert on (matching evidence.test.tsx).
// ---------------------------------------------------------------------------

function render(nodeId = "bxp") {
  return renderToStaticMarkup(
    <ExplanationCard
      scenarioId="cre-demo"
      backendUrl="http://localhost:8000"
      severity={1}
      nodeId={nodeId}
      onSelectEdge={() => {}}
    />,
  );
}

describe("ExplanationCard", () => {
  it("labels the panel as AI-written but number-verified (RW-AI-011)", () => {
    const m = render();
    expect(m).toContain("AI explanation");
    expect(m).toContain("RW-AI-011");
  });

  it("shows a generating state before the fetch resolves", () => {
    expect(render()).toContain("Generating explanation…");
  });

  it("scopes the block so the graph page can find it", () => {
    expect(render()).toContain('id="explanation-block"');
  });
});
