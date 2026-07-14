"use client";

import { useCallback, useState } from "react";

export type AssumptionKind =
  "user" | "source_derived" | "default" | "ai_inferred" | "unresolved";

type Assumption = {
  kind: AssumptionKind;
  text: string;
};

type ValidationIssue = {
  code: string;
  field: string;
  message: string;
  factor_id: string | null;
};

export type ReviewFactor = {
  factor_id: string;
  label: string;
  direction: string;
  magnitude: number;
  unit: string;
  as_of_date: string;
  horizon: string;
  shock_path: string;
  geography: string;
  sector_scope: string;
  parsing_confidence: number;
};

export type ReviewScenario = {
  scenario_id: string;
  original_text: string;
  scenario_pack: string;
  factors: ReviewFactor[];
  assumptions: Assumption[];
  missing_information: string[];
  prompt_version: string;
  model_alias: string;
  parsing_confidence: number;
  status: string;
  validation: { status: string; issues: ValidationIssue[] };
  prevalidated_template: boolean;
};

export type FreeformParseResponse = {
  source: "gemini" | "fallback";
  model_alias: string;
  prompt_version: string;
  attempts: number;
  fallback_reason: string | null;
  scenario: ReviewScenario;
};

interface FreeformShockPanelProps {
  initialResult?: FreeformParseResponse | null;
  backendUrl?: string;
}

const DEFAULT_BACKEND_URL = "http://localhost:8000";

const ASSUMPTION_CLASSES: { kind: AssumptionKind; label: string }[] = [
  { kind: "user", label: "User" },
  { kind: "source_derived", label: "Source-derived" },
  { kind: "default", label: "Default" },
  { kind: "ai_inferred", label: "AI-inferred" },
  { kind: "unresolved", label: "Unresolved" },
];

/**
 * Full RIS-18 front door: freeform natural-language shock input parsed by live
 * Gemini Pro, then an editable structured review. Every factor is editable in
 * place; edits are revalidated server-side (`/review/validate`) and NEVER
 * re-prompt Gemini (`RW-FR-005`). The five assumption source classes
 * (`RW-FR-008`) are shown before the scenario can run, and Run is gated on the
 * deterministic READY state (`RW-FR-004`).
 */
export function FreeformShockPanel({
  initialResult = null,
  backendUrl = DEFAULT_BACKEND_URL,
}: FreeformShockPanelProps) {
  const [text, setText] = useState(initialResult?.scenario.original_text ?? "");
  const [result, setResult] = useState<FreeformParseResponse | null>(
    initialResult,
  );
  const [scenario, setScenario] = useState<ReviewScenario | null>(
    initialResult?.scenario ?? null,
  );
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runAccepted, setRunAccepted] = useState<boolean | null>(null);

  const parse = useCallback(async () => {
    if (!text.trim()) return;
    setParsing(true);
    setError(null);
    setRunAccepted(null);
    try {
      const resp = await fetch(`${backendUrl}/scenarios/parse/live`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!resp.ok) throw new Error(`parse failed (${resp.status})`);
      const data = (await resp.json()) as FreeformParseResponse;
      setResult(data);
      setScenario(data.scenario);
    } catch {
      setError("The parse request failed. Is the backend running?");
    } finally {
      setParsing(false);
    }
  }, [backendUrl, text]);

  // RW-FR-005: an edit revalidates the existing structured scenario; it never
  // sends the original text back to Gemini.
  const revalidate = useCallback(
    async (next: ReviewScenario) => {
      setScenario(next);
      setRunAccepted(null);
      try {
        const resp = await fetch(`${backendUrl}/scenarios/review/validate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(next),
        });
        if (!resp.ok) throw new Error(`validate failed (${resp.status})`);
        setScenario((await resp.json()) as ReviewScenario);
      } catch {
        setError("Revalidation failed.");
      }
    },
    [backendUrl],
  );

  const editFactor = useCallback(
    (index: number, patch: Partial<ReviewFactor>) => {
      if (!scenario) return;
      const factors = scenario.factors.map((factor, i) =>
        i === index ? { ...factor, ...patch } : factor,
      );
      void revalidate({ ...scenario, factors });
    },
    [scenario, revalidate],
  );

  const runScenario = useCallback(async () => {
    if (!scenario) return;
    try {
      const resp = await fetch(`${backendUrl}/scenarios/review/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(scenario),
      });
      if (!resp.ok) throw new Error(`run failed (${resp.status})`);
      const data: { accepted: boolean } = await resp.json();
      setRunAccepted(data.accepted);
    } catch {
      setError("The run request failed.");
    }
  }, [backendUrl, scenario]);

  const ready = scenario?.status === "READY";
  const issues = scenario?.validation.issues ?? [];

  return (
    <section className="shockParser" aria-label="Freeform shock parser">
      <div className="shockParserHead">
        <p className="eyebrow">RW-FR-001 • RW-FR-005 • RW-FR-007 • RW-FR-008</p>
        <h2>Freeform shock parser (Gemini)</h2>
        <p className="shockParserCopy">
          Describe any financial shock in your own words. Gemini Pro finds the
          numbers you wrote — it never invents them — and every factor stays
          editable here without re-prompting the model.
        </p>
      </div>

      <label className="shockParserField">
        <span>Natural-language shock</span>
        <textarea
          aria-label="Freeform shock text"
          rows={3}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="e.g. Commercial real-estate values fall 20%, refinancing rates rise 150 basis points, stress persists 6 quarters."
        />
      </label>
      <div className="shockParserRun">
        <button
          type="button"
          onClick={parse}
          disabled={!text.trim() || parsing}
        >
          {parsing ? "Parsing via Gemini…" : "Parse shock"}
        </button>
      </div>

      {error ? <p className="shockParserError">{error}</p> : null}

      {result && scenario ? (
        <div className="shockParserResult">
          <div className="shockParserMeta">
            <span
              className={`badge ${result.source === "gemini" ? "ok" : "warning"}`}
            >
              {result.source === "gemini"
                ? "Parsed live by Gemini"
                : "Deterministic fallback (Gemini unavailable)"}
            </span>
            <span>{result.model_alias}</span>
            <span>{result.prompt_version}</span>
            <span className={ready ? "ready" : "invalid"}>
              {scenario.status}
            </span>
          </div>

          <div className="factorTable" aria-label="Editable parsed factors">
            <div className="tableHeader">
              <span>Factor</span>
              <span>Direction</span>
              <span>Magnitude</span>
              <span>Unit</span>
              <span>Horizon</span>
            </div>
            {scenario.factors.map((factor, index) => (
              <div
                className="factorRow editable"
                key={`${factor.factor_id}-${index}`}
              >
                <strong>{factor.label}</strong>
                <input
                  aria-label={`direction ${factor.factor_id}`}
                  value={factor.direction}
                  onChange={(event) =>
                    editFactor(index, { direction: event.target.value })
                  }
                />
                <input
                  aria-label={`magnitude ${factor.factor_id}`}
                  type="number"
                  value={factor.magnitude}
                  onChange={(event) =>
                    editFactor(index, {
                      magnitude: Number(event.target.value),
                    })
                  }
                />
                <input
                  aria-label={`unit ${factor.factor_id}`}
                  value={factor.unit}
                  onChange={(event) =>
                    editFactor(index, { unit: event.target.value })
                  }
                />
                <input
                  aria-label={`horizon ${factor.factor_id}`}
                  value={factor.horizon}
                  onChange={(event) =>
                    editFactor(index, { horizon: event.target.value })
                  }
                />
              </div>
            ))}
            {scenario.factors.length === 0 ? (
              <p className="shockParserStatus">
                No supported factor was numerically stated in your input.
              </p>
            ) : null}
          </div>

          {issues.length > 0 ? (
            <div className="validationIssues" aria-label="Validation issues">
              <p className="eyebrow">Why this scenario cannot run yet</p>
              <ul>
                {issues.map((issue, i) => (
                  <li key={`${issue.code}-${i}`}>
                    <span className="badge warning">{issue.code}</span>{" "}
                    {issue.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="assumptionRegistry" aria-label="Assumption registry">
            <p className="eyebrow">Assumption registry (RW-FR-008)</p>
            {ASSUMPTION_CLASSES.map(({ kind, label }) => {
              const entries = scenario.assumptions.filter(
                (assumption) => assumption.kind === kind,
              );
              if (entries.length === 0) return null;
              return (
                <div className="assumptionClass" key={kind} data-kind={kind}>
                  <span className="assumptionKind">{label}</span>
                  <ul>
                    {entries.map((assumption, i) => (
                      <li key={`${kind}-${i}`}>{assumption.text}</li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>

          <div className="shockParserRun">
            <button type="button" onClick={runScenario} disabled={!ready}>
              Run scenario
            </button>
            {runAccepted !== null ? (
              <span className={runAccepted ? "ready" : "invalid"}>
                {runAccepted
                  ? "Accepted for propagation"
                  : "Rejected by validation gate"}
              </span>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
