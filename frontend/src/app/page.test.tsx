import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import Home from "./page";

describe("Home", () => {
  it("renders the scaffold status", () => {
    const markup = renderToStaticMarkup(<Home />);

    expect(markup).toContain("RiskWeave");
    expect(markup).toContain("Scaffold ready");
  });
});
