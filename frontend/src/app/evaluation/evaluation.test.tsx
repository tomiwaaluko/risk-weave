import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import EvaluationDashboard from "./EvaluationDashboard";
import type { EvaluationReport } from "./types";

// ---------------------------------------------------------------------------
// RIS-21: the dashboard is a pure render of a server-computed report. These
// tests assert the judge-legible surface — banner score, per-row target vs
// actual, and that a miss is flagged red (not hidden) — without a network call.
// ---------------------------------------------------------------------------

function report(overrides: Partial<EvaluationReport> = {}): EvaluationReport {
  return {
    snapshot_id: "cre-demo-2026-07-11",
    graph_version: "1.0.0",
    generated_at: "2026-07-15T00:00:00Z",
    all_passed: true,
    families: ["Relationship extraction", "Latency"],
    rows: [
      {
        key: "extraction_precision",
        label: "Extraction precision",
        family: "Relationship extraction",
        actual_display: "94.1%",
        target_display: "≥ 90%",
        passed: true,
        detail: "32 true / 2 false-positive / 4 missed.",
      },
      {
        key: "propagation_latency",
        label: "Propagation recompute (p95)",
        family: "Latency",
        actual_display: "0.07 ms",
        target_display: "≤ 500 ms",
        passed: true,
        detail: "",
      },
    ],
    ...overrides,
  };
}

describe("EvaluationDashboard", () => {
  it("shows the headline passing score", () => {
    const m = renderToStaticMarkup(<EvaluationDashboard report={report()} />);
    expect(m).toContain('id="evaluation-banner"');
    expect(m).toContain("2/2");
    expect(m).toContain("eval-banner-pass");
  });

  it("renders target vs actual for every row", () => {
    const m = renderToStaticMarkup(<EvaluationDashboard report={report()} />);
    expect(m).toContain("Extraction precision");
    expect(m).toContain("94.1%");
    expect(m).toContain("target ≥ 90%");
    expect(m).toContain('data-metric="propagation_latency"');
  });

  it("paints a miss red instead of hiding it (RW-SAFE-003 spirit)", () => {
    const missing = report({
      all_passed: false,
      rows: [
        {
          key: "extraction_recall",
          label: "Extraction recall",
          family: "Relationship extraction",
          actual_display: "72.0%",
          target_display: "≥ 80%",
          passed: false,
          detail: "below target",
        },
      ],
    });
    const m = renderToStaticMarkup(<EvaluationDashboard report={missing} />);
    expect(m).toContain("eval-row-miss");
    expect(m).toContain("MISS");
    expect(m).toContain("eval-banner-miss");
    expect(m).toContain("misses flagged below");
  });

  it("marks informational rows without a pass/fail", () => {
    const info = report({
      rows: [
        {
          key: "explanation_guard_latency",
          label: "Explanation numeric-guard (p95)",
          family: "Latency",
          actual_display: "0.0 ms",
          target_display: "informational",
          passed: null,
          detail: "",
        },
      ],
    });
    const m = renderToStaticMarkup(<EvaluationDashboard report={info} />);
    expect(m).toContain("eval-chip-info");
    // informational rows are excluded from the passing score denominator
    expect(m).toContain("0/0");
  });
});
