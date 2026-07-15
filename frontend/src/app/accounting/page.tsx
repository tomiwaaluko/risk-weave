"use client";

import { useCallback, useEffect, useState } from "react";
import type {
  GeminiBudgetStatus,
  GeminiRollupRow,
  ProviderUsage,
} from "./types";
import "../spike/styles.css";

// RIS-34: provider cost/quota accounting panel. RIS-21's evaluation-dashboard
// shell has not landed yet, so this stands alone for now; it is built to be
// dropped into that dashboard as a panel once it exists.
const PROXY_BASE = "/api/backend";

export default function AccountingPage() {
  const [rollup, setRollup] = useState<GeminiRollupRow[] | null>(null);
  const [budget, setBudget] = useState<GeminiBudgetStatus | null>(null);
  const [providers, setProviders] = useState<ProviderUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rollupResp, budgetResp, providersResp] = await Promise.all([
        fetch(`${PROXY_BASE}/accounting/gemini/rollup?days=7`),
        fetch(`${PROXY_BASE}/accounting/gemini/budget`),
        fetch(`${PROXY_BASE}/accounting/providers/latest`),
      ]);
      if (!rollupResp.ok || !budgetResp.ok || !providersResp.ok) {
        throw new Error("Failed to load provider cost/usage accounting");
      }
      setRollup(await rollupResp.json());
      setBudget(await budgetResp.json());
      setProviders(await providersResp.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const totalCost = (rollup ?? []).reduce((sum, row) => sum + row.cost_usd, 0);

  return (
    <div className="spike-page" id="accounting-page">
      <header className="spike-header">
        <h1 className="spike-title">
          RiskWeave
          <span>Provider cost &amp; quota accounting (RIS-34)</span>
        </h1>
      </header>

      <div
        className="spike-body"
        style={{ flexDirection: "column", gap: "1.5rem", padding: "1.5rem" }}
      >
        {loading && <p>Loading provider usage…</p>}
        {error && (
          <div className="spike-error">
            <p>{error}</p>
            <button className="retry-btn" onClick={load}>
              Retry
            </button>
          </div>
        )}

        {budget && (
          <section aria-label="Gemini daily budget">
            <h2>Gemini daily budget — {budget.day}</h2>
            <p>
              Spent ${budget.spent_usd.toFixed(2)} of $
              {budget.hard_threshold_usd.toFixed(2)} hard cap (soft threshold $
              {budget.soft_threshold_usd.toFixed(2)}).
            </p>
            {budget.hard_breached && (
              <p role="alert">
                Hard budget threshold reached — extraction batches are paused.
              </p>
            )}
            {!budget.hard_breached && budget.soft_breached && (
              <p role="alert">Soft budget threshold reached.</p>
            )}
          </section>
        )}

        {rollup && (
          <section aria-label="Gemini usage rollup">
            <h2>Gemini usage — last 7 days (total ${totalCost.toFixed(2)})</h2>
            <table>
              <thead>
                <tr>
                  <th>Day</th>
                  <th>Purpose</th>
                  <th>Model</th>
                  <th>Calls</th>
                  <th>Input tokens</th>
                  <th>Output tokens</th>
                  <th>Cost (USD)</th>
                </tr>
              </thead>
              <tbody>
                {rollup.map((row) => (
                  <tr key={`${row.day}-${row.purpose}-${row.model}`}>
                    <td>{row.day}</td>
                    <td>{row.purpose}</td>
                    <td>{row.model}</td>
                    <td>{row.calls}</td>
                    <td>{row.input_tokens.toLocaleString()}</td>
                    <td>{row.output_tokens.toLocaleString()}</td>
                    <td>{row.cost_usd.toFixed(4)}</td>
                  </tr>
                ))}
                {rollup.length === 0 && (
                  <tr>
                    <td colSpan={7}>No Gemini calls recorded yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </section>
        )}

        {providers && (
          <section aria-label="SEC/FRED provider usage">
            <h2>SEC EDGAR &amp; FRED fair-use (latest ingestion run)</h2>
            {providers.ingestion_run_id === null ? (
              <p>No ingestion run has completed yet.</p>
            ) : (
              <pre>{JSON.stringify(providers.provider_usage, null, 2)}</pre>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
