import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
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
});
