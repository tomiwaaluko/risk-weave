import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import Home from "./page";

describe("Home", () => {
  it("renders the structured review and evidence trace workflow", () => {
    const markup = renderToStaticMarkup(<Home />);

    expect(markup).toContain("Structured scenario review");
    expect(markup).toContain("Original shock text");
    expect(markup).toContain("Assumption registry");
    expect(markup).toContain("READY");
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
