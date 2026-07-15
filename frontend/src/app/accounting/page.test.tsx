import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import AccountingPage from "./page";

describe("RIS-34 provider cost/quota accounting page (RW-DATA-005, RW-AI-003)", () => {
  it("renders the panel shell before data loads", () => {
    const markup = renderToStaticMarkup(<AccountingPage />);
    expect(markup).toContain("Provider cost");
    expect(markup).toContain("Loading provider usage");
  });
});
