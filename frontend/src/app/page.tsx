"use client";

import { useMemo, useState } from "react";

import { EvidenceWorkbench } from "./workbench";

type Factor = {
  factorId: string;
  label: string;
  direction: "up" | "down" | "flat" | "ambiguous";
  magnitude: number;
  unit: string;
  horizon: string;
  shockPath: string;
  geography: string;
  sectorScope: string;
  parsingConfidence: number;
};

type Assumption = {
  kind: "user" | "source_derived" | "default" | "ai_inferred" | "unresolved";
  text: string;
};

const templates: Record<
  string,
  { prompt: string; factors: Factor[]; assumptions: Assumption[] }
> = {
  cre: {
    prompt:
      "Commercial real-estate values fall 20%, refinancing rates rise 150 basis points, stress persists six quarters.",
    factors: [
      factor(
        "cre_property_value",
        "Commercial real-estate value",
        "down",
        20,
        "percent",
      ),
      factor("refinancing_rate", "Refinancing rate", "up", 150, "basis_points"),
      factor("stress_duration", "Stress duration", "flat", 6, "quarters"),
      factor("office_occupancy", "Office occupancy", "down", 12, "percent"),
      factor(
        "credit_availability",
        "Credit availability",
        "down",
        8,
        "percent",
      ),
    ],
    assumptions: [
      {
        kind: "ai_inferred",
        text: "Scenario geography defaults to United States.",
      },
      {
        kind: "default",
        text: "Occupancy and credit defaults keep the CRE pack at five factors.",
      },
      {
        kind: "source_derived",
        text: "Prevalidated demo template can skip confirmation.",
      },
    ],
  },
  oil: {
    prompt:
      "Oil rises to $140 per barrel for six quarters, pressuring fuel-intensive airlines and logistics margins.",
    factors: [
      factor("oil_price", "Oil price", "up", 140, "usd_per_barrel"),
      factor("jet_fuel_cost", "Jet fuel cost", "up", 35, "percent"),
      factor("transport_margin", "Transport margin", "down", 10, "percent"),
      factor("refinancing_rate", "Refinancing rate", "up", 50, "basis_points"),
      factor("stress_duration", "Stress duration", "flat", 6, "quarters"),
    ],
    assumptions: [
      {
        kind: "ai_inferred",
        text: "Scenario geography defaults to United States.",
      },
      {
        kind: "default",
        text: "Oil template includes fuel, margin, rates, and duration factors.",
      },
      {
        kind: "source_derived",
        text: "Prevalidated demo template can skip confirmation.",
      },
    ],
  },
};

function factor(
  factorId: string,
  label: string,
  direction: Factor["direction"],
  magnitude: number,
  unit: string,
): Factor {
  return {
    factorId,
    label,
    direction,
    magnitude,
    unit,
    horizon: "6 quarters",
    shockPath: "Mapped through the supported v1 factor catalog",
    geography: "United States",
    sectorScope: factorId.startsWith("oil") ? "oil" : "cre",
    parsingConfidence: 0.84,
  };
}

function validateFactors(factors: Factor[]) {
  const issues: string[] = [];
  if (factors.length < 5) {
    issues.push("At least five simultaneous factors are required.");
  }
  for (const item of factors) {
    if (item.direction === "ambiguous") {
      issues.push(`${item.label}: direction is ambiguous.`);
    }
    if (!item.horizon.trim()) {
      issues.push(`${item.label}: horizon is missing.`);
    }
    if (item.magnitude <= 0 || item.magnitude > 1000) {
      issues.push(
        `${item.label}: magnitude is outside the supported demo range.`,
      );
    }
    if (item.factorId.startsWith("unsupported")) {
      issues.push(`${item.label}: factor is unsupported.`);
    }
  }
  return issues;
}

export default function Home() {
  const [selectedTemplate, setSelectedTemplate] = useState<"cre" | "oil">(
    "cre",
  );
  const [prompt, setPrompt] = useState(templates.cre.prompt);
  const [factors, setFactors] = useState<Factor[]>(templates.cre.factors);
  const [assumptions, setAssumptions] = useState<Assumption[]>(
    templates.cre.assumptions,
  );
  const issues = useMemo(() => validateFactors(factors), [factors]);

  function loadTemplate(next: "cre" | "oil") {
    setSelectedTemplate(next);
    setPrompt(templates[next].prompt);
    setFactors(templates[next].factors);
    setAssumptions(templates[next].assumptions);
  }

  function updateFactor(index: number, patch: Partial<Factor>) {
    setFactors((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item,
      ),
    );
  }

  return (
    <>
      <main className="workspace">
        <section className="topbar" aria-label="Scenario templates">
          <div>
            <p className="eyebrow">RiskWeave</p>
            <h1>Structured scenario review</h1>
          </div>
          <div className="templateSwitch">
            <button
              className={selectedTemplate === "cre" ? "active" : ""}
              onClick={() => loadTemplate("cre")}
              type="button"
            >
              CRE
            </button>
            <button
              className={selectedTemplate === "oil" ? "active" : ""}
              onClick={() => loadTemplate("oil")}
              type="button"
            >
              Oil
            </button>
          </div>
        </section>

        <section className="reviewGrid">
          <label className="promptPane">
            <span>Original shock text</span>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
            />
          </label>

          <div className="statusPane">
            <p className={issues.length === 0 ? "ready" : "invalid"}>
              {issues.length === 0 ? "READY" : "INVALID"}
            </p>
            <div>
              {issues.length === 0 ? (
                <p>
                  Validated factors can execute; edited fields did not reparse
                  the prompt.
                </p>
              ) : (
                issues.map((issue) => <p key={issue}>{issue}</p>)
              )}
            </div>
          </div>
        </section>

        <section
          className="factorTable"
          aria-label="Editable structured factors"
        >
          <div className="tableHeader">
            <span>Factor</span>
            <span>Direction</span>
            <span>Magnitude</span>
            <span>Unit</span>
            <span>Horizon</span>
          </div>
          {factors.map((item, index) => (
            <div className="factorRow" key={item.factorId}>
              <strong>{item.label}</strong>
              <select
                value={item.direction}
                onChange={(event) =>
                  updateFactor(index, {
                    direction: event.target.value as Factor["direction"],
                  })
                }
              >
                <option value="up">up</option>
                <option value="down">down</option>
                <option value="flat">flat</option>
                <option value="ambiguous">ambiguous</option>
              </select>
              <input
                type="number"
                value={item.magnitude}
                onChange={(event) =>
                  updateFactor(index, { magnitude: Number(event.target.value) })
                }
              />
              <input
                value={item.unit}
                onChange={(event) =>
                  updateFactor(index, { unit: event.target.value })
                }
              />
              <input
                value={item.horizon}
                onChange={(event) =>
                  updateFactor(index, { horizon: event.target.value })
                }
              />
            </div>
          ))}
        </section>

        <section
          className="assumptionRegistry"
          aria-label="Assumption registry"
        >
          <h2>Assumption registry</h2>
          {assumptions.map((assumption) => (
            <p key={`${assumption.kind}-${assumption.text}`}>
              <span>{assumption.kind.replace("_", " ")}</span>
              {assumption.text}
            </p>
          ))}
        </section>
      </main>

      <EvidenceWorkbench />
    </>
  );
}
