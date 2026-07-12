"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import "../../spike/styles.css";
import "../graph.css";
import "./methodology.css";

/**
 * RIS-20 methodology / honesty page (`RW-DATA-002`).
 *
 * Describes every registered §12.1 derivation method, the free-tier data
 * sources behind the graph, and the known limitations a viewer must see to
 * trust the numbers — including equity-price source limitations. Backs the
 * "Methodology" links from every edge evidence panel.
 */

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

interface Method {
  method_id: string;
  version: string;
  name: string;
  source_data: string;
  summary: string;
  variants: string[];
}

interface Methodology {
  low_confidence_threshold: number;
  methods: Method[];
  data_sources: string[];
  limitations: string[];
}

export default function MethodologyPage() {
  const [data, setData] = useState<Methodology | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const resp = await fetch(`${BACKEND_URL}/graph/methodology`);
      if (!resp.ok) throw new Error(`Load failed: ${resp.status}`);
      setData((await resp.json()) as Methodology);
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
    <div className="methodology-page" id="methodology-page">
      <header className="spike-header">
        <h1 className="spike-title">
          RiskWeave
          <span>Methodology &amp; honesty</span>
        </h1>
        <Link className="methodology-link" href="/graph">
          ← Back to graph
        </Link>
      </header>

      <main className="methodology-body">
        <p className="methodology-intro">
          Every edge weight is produced by a registered deterministic derivation
          method and bound to a quoted source passage. Gemini locates the
          disclosure; deterministic code turns it into the number — Gemini never
          estimates a weight, ratio, or sensitivity.
        </p>

        {error && <p className="spike-error-inline">{error}</p>}
        {!data && !error && <p className="evidence-note">Loading…</p>}

        {data && (
          <>
            <section>
              <h2 className="methodology-h2">Derivation methods (§12.1)</h2>
              <div className="method-cards">
                {data.methods.map((m) => (
                  <article className="method-card" key={m.method_id}>
                    <div className="method-card-head">
                      <span className="method-badge">{m.method_id}</span>
                      <span className="method-version mono">v{m.version}</span>
                    </div>
                    <h3 className="method-card-name">{m.name}</h3>
                    <p className="method-card-summary">{m.summary}</p>
                    <p className="method-card-source">
                      <span className="detail-label">Source data:</span>{" "}
                      {m.source_data}
                    </p>
                  </article>
                ))}
              </div>
            </section>

            <section>
              <h2 className="methodology-h2">Data sources</h2>
              <ul className="methodology-list">
                {data.data_sources.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </section>

            <section>
              <h2 className="methodology-h2">Known limitations</h2>
              <ul className="methodology-list limitations">
                {data.limitations.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
              <p className="evidence-note">
                Edges with an extraction/data-quality confidence below{" "}
                {data.low_confidence_threshold.toFixed(2)} are badged
                low-confidence in the evidence panels — surfaced, never hidden.
              </p>
            </section>
          </>
        )}
      </main>

      <footer className="disclaimer-footer" id="disclaimer-footer">
        Analytics only — not investment, trading, or advisory guidance.
      </footer>
    </div>
  );
}
