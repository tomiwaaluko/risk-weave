import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import Home from "./page";

describe("Home", () => {
  it("renders the structured scenario review surface", () => {
    const markup = renderToStaticMarkup(<Home />);

    expect(markup).toContain("RiskWeave");
    expect(markup).toContain("Structured scenario review");
    expect(markup).toContain("Original shock text");
    expect(markup).toContain("Assumption registry");
    expect(markup).toContain("READY");
  });
});
