"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import "../spike/styles.css";
import "../graph/graph.css";
import "./evaluation.css";

import EvaluationDashboard from "./EvaluationDashboard";
import type { EvaluationReport } from "./types";

/**
 * RIS-21 evaluation dashboard page (`RW-OPS-001`, spec §15, demo beat 6).
 *
 * The internal-quality view that separates RiskWeave from Gemini-wrapper teams:
 * relationship-extraction precision/recall on a hand-labeled sample,
 * entity-resolution accuracy, unsupported-claim rate, citation correctness,
 * scenario stability, and latencies — each with target vs actual and a
 * green/red status. Metrics are computed server-side from committed fixtures.
 */

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export default function EvaluationPage() {
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const resp = await fetch(`${BACKEND_URL}/evaluation/report`);
      if (!resp.ok) throw new Error(`Load failed: ${resp.status}`);
      setReport((await resp.json()) as EvaluationReport);
    } catch (err) {
      setError(
        err instanceof TypeError
          ? `Backend unreachable at ${BACKEND_URL}.`
          : err instanceof Error
            ? err.message
            : String(err),
      );
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <div className="evaluation-page" id="evaluation-page">
      <header className="spike-header">
        <h1 className="spike-title">
          RiskWeave
          <span>Evaluation dashboard</span>
        </h1>
        <Link className="methodology-link" href="/graph">
          ← Back to graph
        </Link>
      </header>

      <main className="evaluation-main">
        <p className="evaluation-intro">
          Internal quality metrics (spec §15) — computed from committed fixtures
          and deterministic runs, not hand-entered. This is the &ldquo;not a
          wrapper&rdquo; view: every number is scored against a target, and any
          miss is flagged red rather than hidden.
        </p>

        {error && <p className="spike-error-inline">{error}</p>}
        {!report && !error && (
          <p className="evidence-note">Computing evaluation report…</p>
        )}
        {report && <EvaluationDashboard report={report} />}
      </main>

      <footer className="disclaimer-footer" id="disclaimer-footer">
        Analytics only — not investment, trading, or advisory guidance.
      </footer>
    </div>
  );
}
