import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Home from "./page";
import MetricsTicker from "../components/MetricsTicker";
import ScenarioPanel from "../components/ScenarioPanel";
import StatusBar from "../components/StatusBar";

describe("RiskWeave terminal", () => {
  it("renders the dense scenario controls and entity universe", () => {
    const markup = renderToStaticMarkup(
      <ScenarioPanel
        scenario="CRE falls 20%"
        onScenarioChange={() => {}}
        onAnalyze={() => {}}
        severity={0.5}
        onSeverityChange={() => {}}
        disabled={false}
        types={["bank"]}
        activeType="all"
        onTypeChange={() => {}}
        nodes={[
          { node_id: "bank-1", node_type: "bank", name: "Northstar Bank" },
        ]}
        impacts={{}}
        selectedNodeId={null}
        onSelectNode={() => {}}
      />,
    );
    expect(markup).toContain("SCENARIO INPUT");
    expect(markup).toContain("PROPAGATION CONTROL");
    expect(markup).toContain("ENTITY UNIVERSE");
    expect(markup).toContain("Northstar Bank");
    expect(markup).toContain("50%");
  });

  it("renders live status and propagation metrics", () => {
    const status = renderToStaticMarkup(
      <StatusBar
        scenario="scenario-01"
        connected
        state="ready"
        latencyMs={81}
      />,
    );
    const ticker = renderToStaticMarkup(
      <MetricsTicker nodes={[]} edges={[]} update={null} latencyMs={81} />,
    );
    expect(status).toContain("RISKWEAVE");
    expect(status).toContain("LIVE");
    expect(ticker).toContain("PROPAGATION SUMMARY");
    expect(ticker).toContain("NOT INVESTMENT ADVICE");
  });

  it("keeps the evidence workbench available under the terminal shell", () => {
    const markup = renderToStaticMarkup(<Home />);

    expect(markup).toContain("RISKWEAVE");
    expect(markup).toContain(
      "Trace any visible number to its source in under 30 seconds.",
    );
    expect(markup).toContain("Breach-distance block");
    expect(markup).toContain("Methodology / honesty page");
    expect(markup).toContain("Exact quoted span with surrounding context");
    expect(markup).toContain("Replay fallback");
    expect(markup).toContain("cre-demo-2026-07-11");
  });
});
