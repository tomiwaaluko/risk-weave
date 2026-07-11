# RiskWeave — Pitch Deck (draft)

*Bloomberg Best FinTech Hack. Speaker notes in italics. One `##` = one slide.
The live demo carries the weight; this deck frames it against the judging
criteria (originality, impact, technical difficulty).*

---

## 1 — Title

# RiskWeave
### An AI-powered financial **contagion engine**
Turn a plain-English shock into an evidence-backed map of how it moves through
the financial system — with a number behind every edge.

*One line if we only get one: "We show you the second- and third-order exposure
a single filing can't, and we can prove every number on screen in 30 seconds."*

---

## 2 — The problem

Material risk is **scattered** — filings, footnotes, XBRL tables, economic
releases, inter-entity relationships. A shock hits one entity, then spreads
through lending, supplier, customer, geographic, and statistical links.

Today's tools:
- present isolated metrics
- summarize documents without quantifying a scenario
- hide their assumptions
- or emit a single unsupported prediction

*Nobody traces the path. Nobody shows the evidence. That's the gap.*

---

## 3 — What RiskWeave does (the demo, in one breath)

1. Type a shock in natural language: *"Commercial real estate values fall 30%."*
2. Gemini parses it into a **structured, reviewable scenario** — you confirm it.
3. The shock **propagates** through a curated knowledge graph, first to third order.
4. Drag the **severity slider** — every score and covenant headroom recomputes live (<500 ms).
5. Click a regional bank — see the **covenant math** and the **exact filing passage** behind each edge.
6. Ask a follow-up — Gemini answers with **citations**, using only computed numbers.

*This is a live demo, not a mockup. We drive all six beats on real SEC/FRED data.*

---

## 4 — Why this is not "just RAG over filings"

> Knowledge-graph-from-filings alone is commodity. It is **not** our pitch.

The differentiator is the layer underneath:

- A **deterministic propagation engine** that recomputes a whole scenario on a slider — RAG cannot do this.
- **Data-derived edge weights** — every weight comes from one of six registered derivation methods (cost-share, concentration, credit, duration, geo, beta). *Gemini finds the sentence; deterministic code turns it into the number.*
- **Universal provenance** — no edge exists without a source document, a quoted passage with character offsets, a timestamp, a method id, and a confidence.

*If a judge remembers one sentence: the AI never makes up a number, and we can prove it.*

---

## 5 — The hard invariant (our defensibility)

**Gemini interprets. Deterministic services calculate.**

- Gemini MUST NOT produce, estimate, or adjust any weight, ratio, or magnitude (`RW-AI-010`).
- The extraction schema deliberately has **no** `estimated_sensitivity` field — its absence is a requirement.
- Every numeric token in a generated explanation must exist in the computation payload — enforced by a deterministic post-generation check, and measured as a dashboard metric (target: **0** violations).

*This is the answer to "what if the LLM hallucinates a relationship." It structurally can't put a fabricated number into the math.*

---

## 6 — The three grafts (arithmetic, not vibes)

Each converts a guessed number into a defensible one:

1. **Breach-distance** — *"leverage 4.2x today, covenant limit 4.5x, projected 4.8x under this scenario — headroom exhausted."* Gemini extracts the covenant threshold from the credit agreement; deterministic code computes and projects the ratio from XBRL.
2. **Universal provenance** — every edge, node exposure, and claim carries its evidence. Click anything, see the source.
3. **Duration as rate transmission** — closed-form modified duration is the deterministic coefficient for how a rate move hits a debt-heavy issuer (ΔP/P ≈ −D_mod × Δy).

*The breach-distance beat is the moment the room goes quiet — it's live covenant math on a real bank.*

---

## 7 — How it works (architecture)

```
EDGAR + XBRL + FRED  ──(batch, pre-demo)──▶  Gemini extraction (strict JSON + provenance)
                                                        │
                                    layered entity resolution (IDs first, Gemini residuals)
                                                        │
                                    deterministic weight derivation (6 methods)
                                                        │
                                    Neo4j knowledge graph (typed, weighted, provenanced)
                                                        │
                                    Python/NumPy propagation engine (≤500 ms, 3-hop)
                                                        │
                                    FastAPI + WebSocket ──▶ Next.js interactive graph + slider
```

*Ingestion is batch and frozen for the demo — no live scraping on stage. The live parts are parsing, propagation, and explanation.*

---

## 8 — Model tiering (a deliberate tradeoff — MUST state, `RW-AI-003`)

- **Flash tier** — high-volume filing extraction. Cheap, fast, structured-output-constrained.
- **Pro tier** — shock parsing and explanation generation. Fewer calls, higher reasoning.

*We tier on purpose: pay for reasoning only where it moves the outcome, and keep
the closed tool registry so Gemini can only call vetted deterministic functions.
This is a cost and a safety decision, not just an optimization.*

---

## 9 — Impact (who this helps)

- **Investors** — find indirect exposure hiding two hops away.
- **Risk teams** — surface concentration and dependency risk across a book.
- **Students & researchers** — understand systemic finance from real evidence.
- **Journalists** — trace public inter-company relationships to their source.

*Two polished scenario packs: commercial real estate (primary) and oil-to-$140
(secondary), each end to end on real data.*

---

## 10 — Honesty & framing (what we deliberately don't do)

- Analytics and **scenario exploration**, not individualized investment advice (stated in the UI footer and here).
- **No price predictions. No buy/sell/hold.** Impact scores are relative, bounded, and explicitly *not* asset-price forecasts.
- Statistical association is never described as proven causation.
- Low-confidence extractions are **labeled, never hidden**; replay is labeled as replay.

*Judges reward teams that know the edges of their own tool. We state ours up front.*

---

## 11 — Roadmap (the DEFERRED list, on purpose)

Everything below is **intentionally parked** for v1 — we cut scope deliberately,
not by accident:

- **Monte Carlo uncertainty** over scenario parameters (`RW-FR-D06`) — v1 ships clean deterministic path decomposition first.
- **Scenario comparison** across two runs + reproducible report export (`RW-FR-D02/D03`).
- **Live news & CFPB complaint signals** as exogenous shock sources (`RW-DATA-D08/D09`).
- **Full covenant-diff (CovenantLens)** and **full fixed-income / "Bond DNA"** (`RW-FR-D10`, `RW-ALG-D11`) — we grafted in only the breach-distance and duration coefficients.
- **C++ propagation core** via pybind11 (`RW-ALG-D07`) — sequenced strictly after the Python engine, behaviorally identical.
- **Broad-market universe, more packs, collaboration, workspaces** (`RW-DATA-D12`).

*The roadmap is the discipline slide: we know exactly what we didn't build and why.*

---

## 12 — Why we win

- **Originality** — multi-hop propagation with defensible, data-derived weights and universal provenance. Not a chatbot, not a stock picker.
- **Impact** — real indirect-exposure discovery on real public data, for four distinct audiences.
- **Technical difficulty** — document intelligence, entity resolution, ontology + graph construction, deterministic simulation with path decomposition, and disciplined Gemini orchestration.

**Every number on screen traces to its source in under 30 seconds. That's the whole pitch.**

---

## Q&A readiness (presenter cheat-sheet — not a slide)

Prepared answers for the questions judges ask (spec §19):

- **"Where does that weight come from?"** → Section 12 derivation methods + the live evidence panel. Show one XBRL cost-share or one OLS beta if pressed.
- **"What if the LLM hallucinates a relationship?"** → confidence thresholds, the provenance requirement (no edge without a passage), the 0-unsupported-claim metric, and the tool-call audit log.
- **"How do you handle cycles / double counting?"** → simple-path contribution tracking, 3-hop cap, geometric damping (ADR-001) — a path that revisits a node is rejected before it contributes.
- **"Why believe the sensitivities?"** → XBRL cost shares and OLS regressions; show one regression on request.
- **"Isn't this just RAG over filings?"** → the propagation engine and deterministic weight layer. RAG can't recompute a scenario on a slider.
