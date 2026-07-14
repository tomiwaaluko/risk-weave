"use client";

import { useCallback, useEffect, useState } from "react";

export type PresetSummary = {
  preset_id: string;
  label: string;
  prompt_text: string;
};

type ParsedFactor = {
  factor_id: string;
  label: string;
  direction: string;
  magnitude: number;
  unit: string;
  horizon: string;
  geography: string;
  sector_scope: string;
};

type ParsedScenario = {
  scenario_id: string;
  original_text: string;
  scenario_pack: string;
  status: string;
  factors: ParsedFactor[];
};

type PresetParseResponse = {
  preset_id: string;
  source: "gemini" | "fallback";
  model_alias: string;
  prompt_version: string;
  attempts: number;
  fallback_reason: string | null;
  scenario: ParsedScenario;
};

interface ShockParserPanelProps {
  initialPresets?: PresetSummary[];
  backendUrl?: string;
}

// Same-origin proxy (RIS-31 / ADR-010) so the server-side RISKWEAVE_API_KEY
// gating this Gemini-calling endpoint never reaches the client bundle.
const DEFAULT_BACKEND_URL = "/api/backend";

/**
 * Reduced RIS-18 demo beat 1: offer clickable preset shock prompts, send the
 * selected one to a real Gemini structured parse, and display the parsed
 * scenario read-only before the user runs it through propagation.
 */
export function ShockParserPanel({
  initialPresets = [],
  backendUrl = DEFAULT_BACKEND_URL,
}: ShockParserPanelProps) {
  const [presets, setPresets] = useState<PresetSummary[]>(initialPresets);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [result, setResult] = useState<PresetParseResponse | null>(null);
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runAccepted, setRunAccepted] = useState<boolean | null>(null);

  useEffect(() => {
    if (presets.length > 0) return;
    let cancelled = false;
    fetch(`${backendUrl}/scenarios/presets`)
      .then((resp) => (resp.ok ? resp.json() : Promise.reject(resp.status)))
      .then((data: PresetSummary[]) => {
        if (!cancelled) setPresets(data);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load presets from the backend.");
      });
    return () => {
      cancelled = true;
    };
  }, [presets.length, backendUrl]);

  const parsePreset = useCallback(
    async (presetId: string) => {
      setActiveId(presetId);
      setParsing(true);
      setError(null);
      setResult(null);
      setRunAccepted(null);
      try {
        const resp = await fetch(
          `${backendUrl}/scenarios/presets/${presetId}/parse`,
          { method: "POST" },
        );
        if (!resp.ok) throw new Error(`parse failed (${resp.status})`);
        setResult((await resp.json()) as PresetParseResponse);
      } catch {
        setError("The parse request failed. Is the backend running?");
      } finally {
        setParsing(false);
      }
    },
    [backendUrl],
  );

  const runScenario = useCallback(async () => {
    if (!result) return;
    try {
      const resp = await fetch(`${backendUrl}/scenarios/review/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(result.scenario),
      });
      if (!resp.ok) throw new Error(`run failed (${resp.status})`);
      const data: { accepted: boolean } = await resp.json();
      setRunAccepted(data.accepted);
    } catch {
      setError("The run request failed.");
    }
  }, [backendUrl, result]);

  return (
    <section className="shockParser" aria-label="Live shock parser">
      <div className="shockParserHead">
        <p className="eyebrow">RW-FR-001 • RW-AI-003 • RW-AI-010</p>
        <h2>Live shock parser (Gemini)</h2>
        <p className="shockParserCopy">
          Pick a preset. It is parsed by a real Gemini structured call —
          magnitudes are echoed verbatim from the sentence, never invented.
        </p>
      </div>

      <div className="pill-row" role="group" aria-label="Preset prompts">
        {presets.map((preset) => (
          <button
            className={`pill ${preset.preset_id === activeId ? "active" : ""}`}
            key={preset.preset_id}
            type="button"
            onClick={() => parsePreset(preset.preset_id)}
          >
            {preset.label}
          </button>
        ))}
      </div>

      {error ? <p className="shockParserError">{error}</p> : null}
      {parsing ? (
        <p className="shockParserStatus">Parsing via Gemini…</p>
      ) : null}

      {result ? (
        <div className="shockParserResult">
          <p className="shockParserPrompt">
            <span>Original prompt</span>
            {result.scenario.original_text}
          </p>

          <div className="shockParserMeta">
            <span
              className={`badge ${result.source === "gemini" ? "ok" : "warning"}`}
            >
              {result.source === "gemini"
                ? "Parsed live by Gemini"
                : "Committed fallback (Gemini unavailable)"}
            </span>
            <span>{result.model_alias}</span>
            <span>{result.prompt_version}</span>
            <span
              className={
                result.scenario.status === "READY" ? "ready" : "invalid"
              }
            >
              {result.scenario.status}
            </span>
          </div>

          <div className="factorTable" aria-label="Parsed factors (read-only)">
            <div className="tableHeader">
              <span>Factor</span>
              <span>Direction</span>
              <span>Magnitude</span>
              <span>Unit</span>
              <span>Horizon</span>
            </div>
            {result.scenario.factors.map((factor) => (
              <div className="factorRow" key={factor.factor_id}>
                <strong>{factor.label}</strong>
                <span>{factor.direction}</span>
                <span>{factor.magnitude}</span>
                <span>{factor.unit}</span>
                <span>{factor.horizon}</span>
              </div>
            ))}
          </div>

          <div className="shockParserRun">
            <button
              type="button"
              onClick={runScenario}
              disabled={result.scenario.status !== "READY"}
            >
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
