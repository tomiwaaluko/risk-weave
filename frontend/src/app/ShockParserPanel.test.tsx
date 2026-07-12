import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ShockParserPanel, type PresetSummary } from "./ShockParserPanel";

const presets: PresetSummary[] = [
  {
    preset_id: "cre",
    label: "Commercial real-estate decline",
    prompt_text: "Commercial real-estate values fall 20%.",
  },
  {
    preset_id: "oil",
    label: "Oil price shock",
    prompt_text: "Oil rises to $140 per barrel.",
  },
];

describe("ShockParserPanel", () => {
  it("renders the heading and the invariant framing", () => {
    const markup = renderToStaticMarkup(
      <ShockParserPanel initialPresets={presets} />,
    );
    expect(markup).toContain("Live shock parser (Gemini)");
    expect(markup).toContain("echoed verbatim");
  });

  it("surfaces each preset as a clickable prompt", () => {
    const markup = renderToStaticMarkup(
      <ShockParserPanel initialPresets={presets} />,
    );
    expect(markup).toContain("Commercial real-estate decline");
    expect(markup).toContain("Oil price shock");
  });
});
