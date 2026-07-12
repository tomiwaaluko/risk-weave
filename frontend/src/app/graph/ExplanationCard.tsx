"use client";

import { Fragment, useEffect, useState } from "react";
import type { ExplanationCitation, ExplanationResponse } from "./types";

/**
 * RIS-19 evidence-bound explanation (`RW-AI-011`).
 *
 * Renders the guarded Gemini prose for the selected node, with inline `[cit-N]`
 * markers turned into clickable chips that drill into the cited edge's evidence.
 * Gemini wrote the sentence; every number in it was verified against the
 * computation payload server-side. When generation failed the numeric guard,
 * the backend returns no prose — only labeled verified figures — and this card
 * shows those instead, badged so the substitution is never hidden
 * (`RW-SAFE-003`).
 */

interface ExplanationCardProps {
  scenarioId: string;
  backendUrl: string;
  severity: number;
  nodeId: string;
  onSelectEdge: (edgeId: string) => void;
}

export default function ExplanationCard({
  scenarioId,
  backendUrl,
  severity,
  nodeId,
  onSelectEdge,
}: ExplanationCardProps) {
  // The parent remounts this card (keyed by node + severity) on every change,
  // so initial state is the reset state — no synchronous setState in the effect.
  const [data, setData] = useState<ExplanationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const url = `${backendUrl}/scenarios/${scenarioId}/explanation/${encodeURIComponent(
      nodeId,
    )}?severity=${severity}`;

    fetch(url)
      .then(async (resp) => {
        if (!resp.ok) throw new Error(`Explanation failed: ${resp.status}`);
        return (await resp.json()) as ExplanationResponse;
      })
      .then((body) => {
        if (!cancelled) setData(body);
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [scenarioId, backendUrl, severity, nodeId]);

  return (
    <section
      className="evidence-section explanation-block"
      id="explanation-block"
    >
      <h3 className="evidence-subtitle">
        AI explanation
        {data && (
          <span
            className={`explanation-badge ${data.used_fallback ? "fallback" : "verified"}`}
          >
            {data.used_fallback ? "Verified figures" : "Numbers verified"}
          </span>
        )}
      </h3>
      <p className="evidence-note">
        Written by Gemini from the computation payload; every number is checked
        against the run before display (RW-AI-011).
      </p>

      {loading && <p className="evidence-empty">Generating explanation…</p>}
      {error && !loading && (
        <p className="evidence-note missing-data" data-missing="explanation">
          Explanation unavailable — {error}
        </p>
      )}

      {data && !loading && (
        <>
          {data.prose ? (
            <p className="explanation-prose" id="explanation-prose">
              <ProseWithCitations
                prose={data.prose}
                citations={data.citations}
                onSelectEdge={onSelectEdge}
              />
            </p>
          ) : (
            <FallbackNumbers data={data} />
          )}

          {data.citations.length > 0 && (
            <CitationList
              citations={data.citations}
              onSelectEdge={onSelectEdge}
            />
          )}
          <p className="explanation-model mono">
            {data.model}
            {data.attempts > 1 ? ` · regenerated ${data.attempts - 1}×` : ""}
          </p>
        </>
      )}
    </section>
  );
}

function ProseWithCitations({
  prose,
  citations,
  onSelectEdge,
}: {
  prose: string;
  citations: ExplanationCitation[];
  onSelectEdge: (edgeId: string) => void;
}) {
  const byId = new Map(citations.map((c) => [c.citation_id, c]));
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;

  // A fresh regex per render — never mutate a shared module-level one.
  for (const match of prose.matchAll(/\[(cit-[A-Za-z0-9_-]+)\]/g)) {
    const index = match.index ?? 0;
    if (index > lastIndex) parts.push(prose.slice(lastIndex, index));
    const citation = byId.get(match[1]);
    const label = citation ? String(citations.indexOf(citation) + 1) : match[1];
    parts.push(
      <button
        key={`${match[1]}-${index}`}
        type="button"
        className="citation-chip"
        title={citation ? citation.source_passage : match[1]}
        onClick={() => citation && onSelectEdge(citation.edge_id)}
        disabled={!citation}
      >
        {label}
      </button>,
    );
    lastIndex = index + match[0].length;
  }
  if (lastIndex < prose.length) parts.push(prose.slice(lastIndex));

  return (
    <>
      {parts.map((part, i) => (
        <Fragment key={i}>{part}</Fragment>
      ))}
    </>
  );
}

function FallbackNumbers({ data }: { data: ExplanationResponse }) {
  return (
    <div className="explanation-fallback" id="explanation-fallback">
      <p className="evidence-note missing-data" data-missing="prose">
        Generated prose failed the numeric guard
        {data.guard_violations.length > 0
          ? ` (unbacked: ${data.guard_violations.join(", ")})`
          : ""}
        . Showing verified figures instead — the rejected text is never
        displayed.
      </p>
      <dl className="evidence-fields">
        {data.structured_numbers.map((n) => (
          <Fragment key={n.label}>
            <dt>{n.label}</dt>
            <dd className="mono">{n.value}</dd>
          </Fragment>
        ))}
      </dl>
    </div>
  );
}

function CitationList({
  citations,
  onSelectEdge,
}: {
  citations: ExplanationCitation[];
  onSelectEdge: (edgeId: string) => void;
}) {
  return (
    <div className="citation-list" id="citation-list">
      <h4 className="evidence-subtitle">Citations</h4>
      <ol>
        {citations.map((c, i) => (
          <li key={c.citation_id} className="citation-item">
            <button
              type="button"
              className="citation-chip"
              onClick={() => onSelectEdge(c.edge_id)}
              title={`${c.source_name} → ${c.target_name}`}
            >
              {i + 1}
            </button>
            <blockquote className="passage-quote citation-passage">
              “{c.source_passage}”
            </blockquote>
            <span className="citation-source mono">
              {c.source_document_id} · filed {c.filing_date}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
