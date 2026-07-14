import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  FreeformShockPanel,
  type FreeformParseResponse,
} from "./FreeformShockPanel";

function makeResult(
  overrides: Partial<FreeformParseResponse["scenario"]> = {},
): FreeformParseResponse {
  return {
    source: "gemini",
    model_alias: "gemini-pro-shock-parser",
    prompt_version: "shock-parse-v1",
    attempts: 1,
    fallback_reason: null,
    scenario: {
      scenario_id: "scn-1",
      original_text: "Commercial real-estate values fall 20%.",
      scenario_pack: "cre",
      factors: [
        {
          factor_id: "cre_property_value",
          label: "Commercial real-estate value",
          direction: "down",
          magnitude: 20,
          unit: "percent",
          as_of_date: "2026-07-11",
          horizon: "6 quarters",
          shock_path: "CRE",
          geography: "United States",
          sector_scope: "cre",
          parsing_confidence: 0.9,
        },
      ],
      assumptions: [
        { kind: "user", text: "Magnitudes taken verbatim from your input." },
        { kind: "ai_inferred", text: "Gemini located the factors." },
        { kind: "source_derived", text: "Bounds from the catalog." },
        { kind: "default", text: "As-of date defaulted." },
      ],
      missing_information: [],
      prompt_version: "shock-parse-v1",
      model_alias: "gemini-pro-shock-parser",
      parsing_confidence: 0.9,
      status: "READY",
      validation: { status: "READY", issues: [] },
      prevalidated_template: false,
      ...overrides,
    },
  };
}

describe("FreeformShockPanel", () => {
  it("renders the heading and the RW-FR-005 no-reprompt framing", () => {
    const markup = renderToStaticMarkup(<FreeformShockPanel />);
    expect(markup).toContain("Freeform shock parser (Gemini)");
    expect(markup).toContain("without re-prompting");
  });

  it("renders every parsed factor as editable inputs", () => {
    const markup = renderToStaticMarkup(
      <FreeformShockPanel initialResult={makeResult()} />,
    );
    expect(markup).toContain("Editable parsed factors");
    expect(markup).toContain("magnitude cre_property_value");
    expect(markup).toContain('value="20"');
  });

  it("renders the assumption registry source classes", () => {
    const markup = renderToStaticMarkup(
      <FreeformShockPanel initialResult={makeResult()} />,
    );
    expect(markup).toContain("Assumption registry");
    expect(markup).toContain('data-kind="user"');
    expect(markup).toContain('data-kind="ai_inferred"');
    expect(markup).toContain('data-kind="source_derived"');
    expect(markup).toContain('data-kind="default"');
  });

  it("explains why an INVALID scenario cannot run and disables Run", () => {
    const invalid = makeResult({
      status: "INVALID",
      validation: {
        status: "INVALID",
        issues: [
          {
            code: "out_of_bound_magnitude",
            field: "factors[0].magnitude",
            message: "Magnitude 900 percent is outside the supported range.",
            factor_id: "cre_property_value",
          },
        ],
      },
      assumptions: [
        { kind: "user", text: "Magnitudes taken verbatim." },
        { kind: "unresolved", text: "A factor was dropped." },
      ],
    });
    const markup = renderToStaticMarkup(
      <FreeformShockPanel initialResult={invalid} />,
    );
    expect(markup).toContain("Why this scenario cannot run yet");
    expect(markup).toContain("out_of_bound_magnitude");
    expect(markup).toContain('data-kind="unresolved"');
    // Run is gated on READY.
    expect(markup).toContain("Run scenario</button>");
    expect(markup).toMatch(/disabled[^>]*>Run scenario/);
  });

  it("surfaces the deterministic fallback badge when Gemini is unavailable", () => {
    const markup = renderToStaticMarkup(
      <FreeformShockPanel
        initialResult={{ ...makeResult(), source: "fallback" }}
      />,
    );
    expect(markup).toContain("Deterministic fallback");
  });
});
