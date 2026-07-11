---
title: "RiskWeave — Master Product and System Requirements Specification (Merged)"
version: "2.1.0"
status: "Baseline for downstream design, planning, implementation, and testing"
date: "2026-07-10"
required_ai_platform: "Gemini API"
initial_scenario_pack: "Commercial real-estate financial contagion"
secondary_scenario_pack: "Oil price shock"
target_context: "Hackathon (Bloomberg Best FinTech Hack) — judged live on originality, impact, technical difficulty"
---

# RiskWeave — Master Product and System Requirements Specification (Merged v2.1.0)

> **Change note (v2.0.0 → v2.1.0).** Additive only: new Section 26 (Agent Tooling — MCPs, Plugins, and Workflows) and a matching `agent_tooling` block in the Section 22 manifest. No product requirement was added, weakened, or reinterpreted; Section 26 is development-process guidance and is explicitly subordinate to all `RW-*` requirements.

> **Merge note.** This version keeps the governance rigor of the formal requirements spec (requirement IDs, normative language, traceability, change control, decision priority, reproducibility bundle, machine-readable manifest) and imposes hackathon scope discipline plus the project's defensibility core: an explicit edge-weight derivation policy (Section 12), three first-class grafts (breach-distance, provenance, duration), a curated entity universe sized for a live demo, and explicit DEFERRED marking of every deliberately excluded idea so nothing looks accidentally dropped. Where the two source specs conflicted, correctness and demo-defensibility won and enterprise-scale features were demoted to DEFERRED.

---

## 0. Purpose and Instructions for Future AI Agents

This document is the source-of-truth specification for RiskWeave. It defines the product outcome, required behavior, domain rules, data requirements, AI boundaries, analytical requirements, user experience, security posture, quality gates, and acceptance criteria.

Future AI agents will later produce separate design/architecture, planning/delivery, implementation, data, prompt-and-AI-evaluation, testing, and deployment specifications. Those downstream documents MUST derive from this document and MUST NOT silently redefine it.

### 0.1 Normative language
- **MUST** — required for conformance.
- **MUST NOT** — prohibited.
- **SHOULD** — expected unless a documented decision justifies otherwise.
- **SHOULD NOT** — avoid unless a documented decision justifies it.
- **MAY** — optional.
- **DEFERRED** — intentionally excluded from the initial release. The architecture SHOULD NOT foreclose it, but no agent may build it for v1 without an approved requirement change.

### 0.2 Traceability rule
Every downstream task, component, test, and decision SHOULD reference one or more requirement IDs from this specification. Requirement prefixes:
- `RW-GOAL-*` product goals
- `RW-FR-*` functional requirements
- `RW-DATA-*` data requirements
- `RW-AI-*` Gemini and AI requirements
- `RW-ALG-*` analytical and algorithmic requirements
- `RW-UX-*` user experience requirements
- `RW-NFR-*` nonfunctional requirements
- `RW-SEC-*` security and privacy requirements
- `RW-OPS-*` observability and operations requirements
- `RW-ACC-*` acceptance criteria
- `RW-NG-*` non-goals

Any work that does not map to a requirement MUST be labeled enabling work, experimentation, technical debt, or an approved requirement change.

### 0.3 Change control
An agent MUST NOT silently weaken, remove, or reinterpret a MUST-level requirement. A proposed change MUST be recorded in an Architecture Decision Record (ADR) or Product Decision Record (PDR) containing: affected requirement IDs, original requirement, proposed change, reason, alternatives considered, user and judging impact, security/data/cost/performance impact, migration or rollback plan, and whether human approval is required.

### 0.4 Decision priority (tie-breaker ordering)
When this specification leaves a choice open, agents MUST optimize in this order:
1. Financial correctness
2. Evidence provenance
3. User trust and explainability
4. Reproducibility
5. Reliable end-to-end demo behavior
6. Simplicity
7. Performance
8. Cost
9. Extensibility

Visual novelty MUST NOT override correctness, provenance, or reproducibility. **Scope breadth MUST NOT override demo reliability** (see Section 5).

### 0.5 The one failure mode this document is built to prevent
RiskWeave's defining risk in front of Bloomberg engineers is that a propagation number is revealed to be an LLM guess. Every structural choice here exists to prevent that. The governing rule: **Gemini finds the sentence; deterministic code turns the sentence or the raw data into the number; the sentence is stored as provenance.** Any downstream proposal that routes a model-produced magnitude into propagation math is an automatic MUST-level violation (`RW-AI-010`).

---

## 1. Executive Summary

RiskWeave is an AI-assisted financial contagion and scenario-analysis platform. It converts public financial filings, structured company facts, macroeconomic data, and validated company relationships into an interactive graph showing how a financial shock propagates through companies, industries, lenders, borrowers, suppliers, customers, securities, and the broader economy.

A user enters a scenario in natural language (for example: "Commercial real-estate values fall 20%, refinancing rates rise 150 basis points, stress persists six quarters"). RiskWeave converts it into a structured, reviewable scenario; identifies directly exposed entities; runs deterministic graph propagation with data-derived weights; ranks entities and pathways by modeled impact; renders an interactive contagion graph with a live severity slider; and explains results with source-backed evidence that the user can inspect down to the exact filing passage.

Gemini understands unstructured documents, extracts structured relationships, interprets user intent, orchestrates approved tools, and generates evidence-bound explanations. Gemini is not the source of numerical truth and MUST NOT invent financial values, relationship weights, or citations.

The initial complete release centers on commercial real-estate contagion, with a second polished pack for an oil price shock. The architecture remains extensible to other packs, but no other pack is built for v1.

---

## 2. Product Vision and Positioning

**Vision.** Make systemic financial risk understandable by turning fragmented evidence into an interactive, explainable map of how shocks move through the economy.

**Positioning.** RiskWeave is an AI-powered financial contagion engine that transforms filings, economic data, and company relationships into an evidence-backed graph of how market shocks may propagate through the financial system.

**Why it fits the Bloomberg challenge.**
- *Originality:* not a budgeting assistant, stock picker, or document chatbot. The differentiator is multi-hop propagation with **defensible, data-derived weights**, universal evidence provenance, and second/third-order effects a human analyst would not have front-of-mind. Knowledge-graph-from-filings alone is commodity and MUST NOT be pitched as the differentiator.
- *Impact:* helps investors find indirect exposure, risk teams find concentration/dependency risk, students understand systemic finance, researchers and journalists trace public relationships.
- *Technical difficulty:* document intelligence, entity resolution, ontology and knowledge-graph construction, deterministic scenario simulation, path decomposition, provenance, interactive rendering, and disciplined Gemini orchestration.

---

## 3. Problem Definition

Material risk is scattered across filings, tables, footnotes, economic releases, and inter-entity relationships. A shock hits an entity directly, then spreads through funding, lending, customer, supplier, ownership, geographic, sector, and statistical relationships. Existing tools present isolated metrics, summarize documents without quantifying scenarios, hide assumptions, confuse correlation with causation, or emit unsupported single-number predictions.

RiskWeave answers: which entities are directly exposed; through which relationships the effect spreads; which paths contribute most to an entity's modeled impact; which assumptions materially move the result; what source evidence supports each relationship; which conclusions are weak or uncertain; and how sensitive results are to shock magnitude. RiskWeave is a scenario-analysis and relative-risk system, **not** a guaranteed price-prediction engine.

---

## 4. Goals, Success Metrics, and Non-Goals

### 4.1 Product goals
- `RW-GOAL-001` — Reveal first-, second-, and third-order exposure that is hard to see from a single filing or metric.
- `RW-GOAL-002` — Every material relationship MUST be traceable to source evidence, a deterministic derivation, reviewed curation, a labeled statistical method, or an explicitly labeled modeling assumption.
- `RW-GOAL-003` — Gemini interprets, extracts, retrieves, orchestrates, and explains. Deterministic services perform all calculation, propagation, ranking, and uncertainty computation.
- `RW-GOAL-004` — Users can create, edit, validate, execute, and inspect scenarios. (Compare/clone/export are DEFERRED per Section 5.)
- `RW-GOAL-005` — Communicate confidence, uncertainty, sensitivity, missing data, and limitations rather than presenting modeled outputs as facts.
- `RW-GOAL-006` — A completed run MUST be reproducible from its scenario input, data snapshot, graph version, algorithm version, prompt version, model configuration, and random seed.
- `RW-GOAL-007` — The main workflow MUST visibly connect natural-language input, structured interpretation, analytical processing, graph propagation, and exact source evidence.
- `RW-GOAL-008` (defensibility) — For any number displayed in the demo path, a presenter MUST be able to trace source data, derivation method, and provenance record in under 30 seconds.

### 4.2 Target success metrics (release scope)

| Metric | Target |
|---|---:|
| Material graph edges with provenance | 100% |
| Unsupported material claims in release evaluation set | 0 |
| Numeric tokens in generated explanations absent from computation payload | 0 |
| Structured extraction schema validity after bounded retry | >= 99% |
| Relationship extraction precision (hand-labeled sample) | >= 0.90 |
| Relationship extraction recall (hand-labeled sample) | >= 0.80 |
| Entity-resolution precision for supported universe | >= 0.95 |
| Same-input analytical reproducibility | 100% within numeric tolerance |
| Live severity-slider recompute latency (curated graph) | <= 500 ms |
| Shock parse latency | <= 3 s |
| Top-ten impacted entities with evidence access | 100% |
| Critical demo-flow completion | 100% |
| Private keys in client or logs | 0 |

> **Scope correction from source specs.** The prior 10,000-node / 50,000-edge / 5-second performance target is **DEFERRED** (`RW-NFR-D01`). It contradicted the curated-universe scope and served no demo purpose. The live metric that matters is sub-500ms slider recompute on the curated graph.

### 4.3 Non-goals
- `RW-NG-001` — MUST NOT place or route real financial orders.
- `RW-NG-002` — MUST NOT tell a user to buy, sell, hold, short, or allocate a portfolio.
- `RW-NG-003` — Impact scores MUST NOT be presented as guaranteed asset-price movements.
- `RW-NG-004` — MUST NOT access, scrape, store, or redistribute data in violation of provider terms.
- `RW-NG-005` — Base application MUST function without Bloomberg proprietary data.
- `RW-NG-006` — Statistical association MUST NOT be described as proven causation.
- `RW-NG-007` — MUST NOT autonomously publish conclusions about companies without deliberate human action.

---

## 5. Scope (hackathon reality)

### 5.1 In scope for v1 (the buildable, demo-able release)
- `RW-SCOPE-001` — A curated entity universe of **100 to 200 entities**, chosen deep across the two demo sectors rather than broad and shallow. Depth beats breadth; judges probe depth.
- `RW-SCOPE-002` — Two fully polished scenario packs end to end: **commercial real estate decline** (primary) and **oil price shock** (secondary). Other packs MAY exist in schema but MUST NOT be built for v1.
- `RW-SCOPE-003` — Deterministic propagation engine with the weight derivations of Section 12.
- `RW-SCOPE-004` — The three grafts (Section 11): breach-distance node metric, universal provenance, duration-based rate transmission.
- `RW-SCOPE-005` — Interactive graph visualization with a severity slider and node-click evidence panels.
- `RW-SCOPE-006` — Natural-language shock input, structured-scenario review, and evidence-bound explanation via Gemini.
- `RW-SCOPE-007` — Evaluation dashboard (Section 15).
- `RW-SCOPE-008` — Batch ingestion pipeline for SEC EDGAR filings, XBRL company facts, and FRED series, run before the demo.

### 5.2 Minimum supported universe
The release MUST contain at least: 10 banks with meaningful commercial-lending exposure; 10 REITs or property-related companies; 10 additional connected companies or proxies for the CRE pack; the energy/airline/logistics slice for the oil pack; relevant macro factors; and at least three reporting periods where public data allows. Breach-distance coverage (Section 11) is required for at least 10 to 20 entities, not universally. Selection criteria MUST be documented and MUST NOT imply wrongdoing, endorsement, or investment recommendation.

### 5.3 DEFERRED (explicitly parked; do not build for v1; roadmap-slide material)
Marking these keeps exclusion intentional so no agent treats them as forgotten.
- `RW-NFR-D01` — 10,000-node / 5-second performance target.
- `RW-FR-D02` — Scenario comparison across two completed runs.
- `RW-FR-D03` — Reproducible report export.
- `RW-FR-D04` — Reviewer approval / curation workflow with version history.
- `RW-UX-D05` — Full WCAG 2.2 AA across all flows (keep basic accessibility hygiene; full audit deferred).
- `RW-FR-D06` — Monte Carlo uncertainty over scenario parameters. (Deterministic propagation with clean path decomposition is the v1 requirement; stochastic uncertainty is a stretch.)
- `RW-ALG-D07` — Optional C++ propagation core via pybind11. Stretch only, sequenced strictly after the Python engine passes all tests, and behaviorally identical under the same test suite.
- `RW-DATA-D08` — Live news materiality feed as an exogenous shock source (the news/price-dislocation concept). Entire second streaming system.
- `RW-DATA-D09` — CFPB consumer-complaint burst detection as a leading-indicator node signal (the ComplaintSignal concept).
- `RW-FR-D10` — Full semantic disclosure diff (the CovenantLens product; only the breach-distance metric is grafted in, see `RW-ALG-030`).
- `RW-ALG-D11` — Full fixed-income analytics and bond-similarity ("Bond DNA"); only duration as a transmission coefficient is grafted in (see `RW-ALG-031`).
- `RW-DATA-D12` — Broad-market entity universe, additional scenario packs, cross-lingual ingestion, portfolio overlays, collaboration, org workspaces, entitlements, real-time event ingestion.

Agents MUST NOT silently expand scope. New ideas go to this list via an ADR/PDR, not into the build.

---

## 6. Users and Personas (abbreviated)

- **Financial analyst:** fast scenario creation, assumption inspection, hidden-exposure discovery, source evidence. Success: hypothesis to evidence-backed scenario without reading every source document.
- **Finance student:** plain-language explanations, visual paths, clear fact/assumption/output separation. Success: can explain why a shock reaches an entity through multiple pathways.
- **Risk manager:** sensitivity, confidence and data-quality indicators, reproducibility, auditability. Success: identifies the most important modeled vulnerabilities and their evidence.
- **Journalist/researcher:** relationship discovery, provenance, clear limitations. Success: traces a relationship to its public source and separates fact from inference.
- **Demo presenter:** a reliable guided workflow, pre-ingested validated data, a frozen fallback, and the ability to change at least one factor live. Success: the whole story demonstrates without developer intervention.

---

## 7. Product Principles

- `RW-PRIN-001` Evidence before eloquence.
- `RW-PRIN-002` Language models do not own financial arithmetic, propagation, probability, ranking, or scoring.
- `RW-PRIN-003` Every result has an as-of date; no output appears timeless.
- `RW-PRIN-004` Uncertainty is a first-class feature.
- `RW-PRIN-005` No material impact score exists without an inspectable explanation path.
- `RW-PRIN-006` Correlation is not causation; relationship type and evidence class are always explicit.
- `RW-PRIN-007` AI output is untrusted until schema-validated, evidence-validated, and deterministically checked.
- `RW-PRIN-008` Graceful incompleteness: abstain or return a clearly labeled partial result rather than fabricate completeness.
- `RW-PRIN-009` Demo reliability is a product feature: deterministic, cached, replayable behavior is required.
- `RW-PRIN-010` Every displayed number is traceable to a Section 12 derivation in under 30 seconds.

---

## 8. Core User Journeys

**8.1 Create and run a scenario.** User opens the workspace, selects a template or types natural language, Gemini converts it to a structured scenario, the system displays factors/units/magnitudes/horizon/scope/assumptions/parsing-confidence, user confirms or edits, the system validates supported factors and data coverage, user runs, the graph and ranked impacts render, user inspects top paths and evidence.

**8.2 Investigate an impacted entity.** User selects an entity; the detail panel shows direct and indirect components and top contributing paths; expanding a path shows each edge's relationship type, transfer semantics, confidence, date, and provenance; user opens the exact source passage and reviews the calculation method.

**8.3 Ask a run-scoped question.** User asks; Gemini receives only approved run results, evidence, and approved tools; Gemini calls calculation/graph/evidence tools; the answer carries machine-resolvable citations; unsupported information is explicitly withheld.

**8.4 Replay the demo.** Presenter selects a validated scenario bound to a frozen snapshot; progress events replay consistently; identical seed and configuration reproduce the result; presenter changes one magnitude and triggers a real recomputation.

---

## 9. Functional Requirements

### 9.1 Scenario definition and lifecycle
- `RW-FR-001` MUST accept a natural-language description of one or more financial shocks.
- `RW-FR-002` MUST provide editable CRE and oil-shock scenario templates.
- `RW-FR-003` Before execution, MUST display a structured scenario: factor, direction, magnitude, unit, as-of/start date, horizon, shock path, geography/sector scope, assumptions, missing information, parsing confidence.
- `RW-FR-004` A newly parsed scenario MUST NOT execute until it passes validation. Explicit confirmation MAY be skipped only for a prevalidated demo template.
- `RW-FR-005` Users MUST be able to edit structured factors without rewriting the prompt.
- `RW-FR-006` MUST support at least five simultaneous shock factors.
- `RW-FR-007` Validation MUST flag or reject unsupported factors, invalid units, impossible dates, ambiguous direction, missing horizon, contradictory inputs, and out-of-bound magnitudes.
- `RW-FR-008` Every scenario MUST maintain an assumption registry separating user assumptions, source-derived assumptions, defaults, AI-inferred assumptions, and unresolved assumptions.
- `RW-FR-009` The lifecycle MUST support `DRAFT -> VALIDATING -> READY -> QUEUED -> RUNNING -> COMPLETED` with terminal alternatives `PARTIAL`, `FAILED`, `CANCELLED`.

### 9.2 Data ingestion
- `RW-FR-010` MUST resolve supported companies by name, alias, ticker, and CIK.
- `RW-FR-011` MUST ingest configured SEC filing types and preserve original metadata and content references.
- `RW-FR-012` MUST ingest relevant SEC XBRL company facts where available.
- `RW-FR-013` MUST ingest configured macroeconomic series and preserve observation and retrieval metadata.
- `RW-FR-014` Ingestion MUST be idempotent and MAY be incremental after initial load.
- `RW-FR-015` A scenario run MUST bind to an immutable logical data snapshot.

### 9.3 Graph, propagation, and results
- `RW-FR-016` MUST construct a typed, weighted, provenanced knowledge graph (nodes: companies, banks, securities, commodities, geographies, sectors).
- `RW-FR-017` MUST compute first-order impact on directly exposed nodes and propagate to at least third order.
- `RW-FR-018` MUST rank impacted entities and decompose each entity's impact into contributing paths.
- `RW-FR-019` MUST compute and display a separate structural systemic-importance score (centrality) clearly distinguished from scenario impact.
- `RW-FR-020` MUST recompute results live when the severity slider changes, meeting `RW-NFR` latency.
- `RW-FR-021` MUST render an interactive graph with node-click evidence panels exposing all provenance fields of Section 11 Graft 2.

### 9.4 Explanation and Q&A
- `RW-FR-022` MUST generate evidence-bound explanations of results with audience variants (analyst, student, retail).
- `RW-FR-023` Generated explanations MUST reference only numbers present in the computation payload (`RW-AI-011`).
- `RW-FR-024` Run-scoped Q&A MUST answer only from approved run state and approved tools, with citations, withholding unsupported claims.

---

## 10. Data Requirements

- `RW-DATA-001` Sources for v1: SEC EDGAR filings (10-K, 10-Q, 8-K), SEC XBRL company facts, FRED (or ALFRED) macro/commodity series, and curated entity metadata. All free; no licensed or Bloomberg data.
- `RW-DATA-002` Historical equity prices MAY come from a free-tier source for return regressions; the source and its limitations MUST be disclosed on the methodology/honesty view.
- `RW-DATA-003` Every ingested record MUST retain source identifier, retrieval timestamp, and as-of/filing date.
- `RW-DATA-004` Filing text MUST be stored chunked with character offsets so provenance spans survive chunking.
- `RW-DATA-005` Provider terms (SEC fair-use rate limits, FRED terms, price-source terms) MUST be respected; ingestion MUST rate-limit accordingly.
- `RW-DATA-006` The demo dataset MUST be frozen and MUST include at least one legitimate, surprising, evidence-backed multi-hop path, at least one low-confidence or missing-data example, and precomputed fallback results.

---

## 11. The Three Grafts (first-class requirements)

Each graft was deliberately absorbed because it converts a guessed number into a defensible one. These are not optional polish.

### Graft 1 — Breach-distance node metric (`RW-ALG-030`)
For financial-institution and leveraged-corporate nodes, compute covenant headroom under the active scenario. Gemini extracts covenant thresholds (leverage limits, interest-coverage minimums, minimum liquidity) from credit agreements and filings into a strict schema with the source passage stored; deterministic code computes current ratios from XBRL and projects them under the propagated shock. The node evidence panel MUST show current value, threshold, projected value, headroom, and a qualitative breach-risk tier. Required for at least 10 to 20 entities, not universally. Demo beat: a regional bank showing "leverage 4.2x today, covenant limit 4.5x, projected 4.8x under this scenario, headroom exhausted" is arithmetic, not vibes.

### Graft 2 — Evidence provenance (`RW-ALG-032`, applies everywhere)
Every edge, node exposure, and generated claim MUST carry: source document id and filing date; exact supporting passage (quoted span with offsets); data timestamp for any market/economic input; calculation-method id (which Section 12 derivation); and extraction confidence. The UI MUST surface all of this on click. **If an edge has no provenance, the edge MUST NOT exist.** Tests MUST fail any pipeline output missing provenance fields.

### Graft 3 — Duration as rate-shock transmission (`RW-ALG-031`)
For interest-rate scenarios and debt-heavy nodes in any scenario, compute modified duration from bond/debt terms in closed form and use it as the deterministic coefficient for how a rate move propagates to a debt instrument or debt-heavy issuer. Scope guard: this is one function and one edge-weight type; it MUST NOT expand into yield-curve bootstrapping or bond-similarity features (those are `RW-ALG-D11`, DEFERRED).

---

## 12. Edge-Weight Derivation Policy (the defensibility core)

> This section is the heart of the spec. It is normative, not deferred to design. It exists so no weight entering propagation is ever an LLM guess. The prior specs deferred "the exact propagation and aggregation formula"; the exact formula MAY be a design choice, but the **source of every weight** is fixed here.

- `RW-ALG-001` Every propagation edge weight MUST be produced by a registered deterministic derivation method with a method id. Gemini MUST NOT produce, estimate, or adjust any weight.
- `RW-ALG-002` If a document discloses a magnitude verbatim (e.g. "fuel was approximately 28% of operating expenses"), Gemini captures it into a `disclosed_magnitude` string; a deterministic parser validates and converts it. The verbatim passage is stored as provenance.
- `RW-ALG-003` If no magnitude is disclosed, the weight comes from the derivations below, never from the model.

### 12.1 Derivation table (each edge type maps to a method and a source)

| Edge / exposure type | Deterministic derivation | Source data | Method id |
|---|---|---|---|
| Commodity dependency (e.g. jet fuel) | Cost-line share of operating expenses from XBRL; else historical return regression vs the commodity series (factor beta) | XBRL, FRED/commodity history, market returns | `DER-COMMODITY` |
| Supplier / customer dependency | Disclosed revenue-concentration percentage (verbatim, validated); else segment revenue share | 10-K concentration disclosures, XBRL segments | `DER-CONCENTRATION` |
| Creditor / lending exposure | Reported loan-portfolio composition and exposure disclosures | Bank 10-K/10-Q disclosures | `DER-CREDIT` |
| Interest-rate sensitivity (debt / security nodes) | Modified duration, closed-form (Graft 3) | Bond terms from filings, current yield inputs | `DER-DURATION` |
| Geographic exposure | Revenue-by-geography from XBRL segment reporting | XBRL | `DER-GEO` |
| Equity market sensitivity | OLS beta from historical returns regression | Market history | `DER-BETA` |

- `RW-ALG-004` Every stored edge MUST record its method id, the inputs used, and a provenance reference. The evidence panel MUST be able to display the derivation for any on-screen edge.
- `RW-ALG-005` (propagation, design-tunable within these constraints) First-order impact = shock magnitude × edge weight. Multi-hop impact propagates along outgoing edges with damping and stops below a floor threshold. Traversal depth is capped at 3 hops (matching the third-order pitch). The design spec MUST choose a cycle-handling strategy (visited-path contribution tracking or equivalent) that prevents double counting and MUST justify it in an ADR.
- `RW-ALG-006` Node risk score MUST be a bounded aggregate of incoming impact contributions and MUST be decomposable so the evidence panel can show which paths contributed what.
- `RW-ALG-007` Confidence displayed on any output is extraction/model or data-quality confidence, not a statistical guarantee, and MUST be labeled as such.

---

## 13. Gemini Integration Contract

- `RW-AI-001` Gemini MUST be used via structured outputs (strict JSON schema) for every extraction task. Free-text extraction is prohibited.
- `RW-AI-002` Gemini MUST orchestrate deterministic backend functions via function calling against the registered tool registry (Section 13.2). Arbitrary tool execution is prohibited.
- `RW-AI-003` Model tiering: a Flash-tier model SHOULD serve high-volume filing extraction; a Pro-tier model SHOULD serve shock parsing and explanation generation. The tradeoff MUST be stated in the demo.
- `RW-AI-004` Long filings MUST be chunked so provenance offsets survive; the chunking strategy is a design decision recorded in an ADR.
- `RW-AI-010` Gemini MUST NOT calculate or estimate any sensitivity, beta, exposure magnitude, ratio, price, or propagation weight. (Cross-ref `RW-ALG-001`.)
- `RW-AI-011` Explanation prompts MUST contain only computation output and provenance records; every numeric token in a generated explanation MUST exist in that payload. Tests MUST assert this.
- `RW-AI-012` Entity resolution MUST be layered: deterministic identifiers (CIK, ticker, LEI) resolve first; Gemini proposes merges only for ambiguous residuals above a confidence threshold; every merge is logged and inspectable.

### 13.1 Canonical relationship-extraction schema (fields MUST be preserved)
```json
{
  "source_entity": "string (as written in document)",
  "target_entity": "string (as written in document)",
  "relationship_type": "supplier | customer | creditor | commodity_dependency | geographic_exposure | ...",
  "direction": "positive | negative",
  "disclosed_magnitude": "nullable string, verbatim from document if disclosed",
  "source_passage": "exact quoted span",
  "passage_location": "document id + character offsets",
  "extraction_confidence": "0-1"
}
```
There is deliberately no `estimated_sensitivity` field. Its absence is a requirement, not an omission.

### 13.2 Deterministic tool registry (minimum, exposed via function calling)
```
resolve_entity(name)
get_company_exposures(entity_id)
run_scenario(scenario_params)
propagate_shock(factor_id, magnitude)
get_propagation_paths(entity_id, scenario_id)
calculate_breach_distance(entity_id, scenario_id)
calculate_duration(security_id)
get_ratio(entity_id, ratio_name)
retrieve_filing_passage(provenance_id)
retrieve_fred_series(series_id, range)
```

---

## 14. System Architecture

```
EDGAR filings + XBRL + FRED + historical market data
                     │
                     ▼        (batch, run pre-demo — no live scraping in demo)
        Ingestion & normalization pipeline
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
 Structured financial data   Filing text (chunked, offsets preserved)
 (PostgreSQL; time-series             │
  via Timescale ext. optional)        ▼
        │                    Gemini extraction (strict JSON,
        │                    provenance capture, confidence)
        │                             │
        └────────────┬────────────────┘
                     ▼
        Entity resolution & reconciliation
        (identifiers first; Gemini residual merges; audit log)
                     ▼
        Deterministic weight derivation (Section 12 methods)
                     ▼
        Financial knowledge graph (Neo4j) — typed, weighted, provenanced
                     ▼
        Propagation engine (Python/NumPy; C++ core DEFERRED)
                     ▼
        FastAPI backend + WebSocket (live slider recompute; Redis cache)
                     ▼
        Next.js + TypeScript frontend
        (React Flow or Cytoscape.js graph; D3/Plotly charts)

Gemini also sits at the API layer for NL shock parsing, function-calling
orchestration, and post-computation explanation generation.
```

### 14.1 Settled architectural decisions (do not re-open without an ADR)
- `RW-NFR-001` Ingestion is batch and pre-demo. The live parts are shock parsing, propagation recompute, and explanation. No live scraping during the demo.
- `RW-NFR-002` Propagation is synchronous and MUST meet <= 500 ms recompute on the curated graph so the slider feels live. This constrains graph size, reinforcing the curated universe.
- `RW-NFR-003` Neo4j for the graph; PostgreSQL for financials, provenance, and time series.
- `RW-NFR-004` Redis caches scenario results for slider smoothness.
- `RW-NFR-005` Packaging is Docker Compose. Kafka/Redpanda and Kubernetes are prohibited for v1 (no streaming, no orchestration need).
- `RW-NFR-006` The C++ propagation core (`RW-ALG-D07`) is a stretch goal sequenced strictly after the Python engine passes all tests and MUST be behaviorally identical under the same suite.

---

## 15. Evaluation Dashboard (`RW-OPS-001`, required feature)

A visible internal-quality view that separates RiskWeave from Gemini-wrapper teams. Minimum metrics: relationship-extraction precision/recall on a hand-labeled sample (label 50 to 100 passages; schedule this task explicitly); entity-resolution accuracy on the curated universe; unsupported-claim rate in explanations (numeric tokens absent from payload); citation-correctness spot checks; scenario stability (same input yields same output); and latencies for parse, propagation, and explanation. The dashboard MUST be shown in the demo.

---

## 16. Security and Privacy

- `RW-SEC-001` API keys and provider credentials MUST be server-side only; no secret in the client or logs.
- `RW-SEC-002` The tool registry exposed to Gemini MUST be closed; arbitrary code or tool execution is prohibited.
- `RW-SEC-003` User inputs and document content passed to Gemini MUST be treated as untrusted; extraction outputs are validated before use.
- `RW-SEC-004` No secret may exist in the repository. Setup MUST work from documented environment configuration.

---

## 17. Safety, Honesty, and Framing

- `RW-SAFE-001` The product provides analytics and scenario exploration, not individualized investment advice; stated in the UI footer and the pitch.
- `RW-SAFE-002` No price predictions, no buy/sell/hold outputs.
- `RW-SAFE-003` Low-confidence extractions are labeled, never hidden.
- `RW-SAFE-004` All data is timestamped; the demo does not present historical data as live. Replay is labeled as replay.

---

## 18. Suggested Stack (defaults; substitutions require an ADR)

```
Frontend:   Next.js + TypeScript, React Flow or Cytoscape.js (graph),
            D3/Plotly (charts), WebSocket client
Backend:    Python 3.11+, FastAPI, Pydantic v2
Quant:      NumPy/SciPy/pandas, statsmodels (regressions);
            C++ + pybind11 core DEFERRED (stretch)
AI:         Gemini API — Flash tier (extraction), Pro tier (reasoning/
            explanation), structured outputs, function calling
Graph:      Neo4j
Relational: PostgreSQL (financials, provenance, time series; Timescale opt.)
Cache:      Redis (scenario result caching)
Infra:      Docker Compose (no Kubernetes, no Kafka)
```

---

## 19. Demonstration Specification

**Primary scenario — Commercial real-estate contagion.** Chain: CRE value decline → property-owner cash flow stress → loan default probability → regional-bank exposure (breach-distance moment) → credit tightening → downstream corporate and local-economy nodes.

Beats: (1) type the shock in natural language, show the parsed structured scenario side by side; (2) graph animates propagation outward, first to third order; (3) drag the severity slider, scores and breach-distances recompute live; (4) click a regional bank, see covenant math (Graft 1) and filing passages behind each edge (Graft 2); (5) ask a natural-language follow-up, Gemini orchestrates tool calls and answers with citations; (6) show the evaluation dashboard briefly (the "not a wrapper" moment).

**Secondary scenario — Oil to $140.** Same beats over the energy/airline/logistics slice, demonstrating the `DER-COMMODITY` factor-beta derivation.

**Q&A readiness (`RW-ACC` gate).** For every visible number, the team traces source → derivation method → provenance in under 30 seconds. The planning spec MUST include a provenance-drill checklist over the demo path. Prepared answers for: "where does that weight come from" (Section 12 + live panel); "what if the LLM hallucinates a relationship" (confidence thresholds, provenance requirement, unsupported-claim rate, audit logs); "how do you handle cycles/double counting" (`RW-ALG-005`); "why believe the sensitivities" (regressions and XBRL shares, show one regression if pressed); "isn't this just RAG over filings" (the propagation engine and deterministic weight layer; RAG projects cannot recompute a scenario on a slider).

---

## 20. Build Priorities (ordering constraint for the planning agent)

Dependency-ordered spine; the known-risky items (2, 3, 5) are front-loaded because UI polish is late and cheap for an agentic team while defensible numbers are early and expensive.

1. Curated entity universe + batch ingestion (filings/XBRL/FRED) — `RW-SCOPE-001`, `RW-FR-010..015`
2. Deterministic weight derivations with provenance — Section 12, `RW-ALG-001..004`
3. Gemini extraction pipeline (schemas) + layered entity resolution — `RW-AI-001`, `RW-AI-012`
4. Graph assembly in Neo4j — `RW-FR-016`
5. Propagation engine + tests (determinism, decomposition, cycles) — `RW-ALG-005/006`, `RW-FR-017/018`
6. FastAPI + WebSocket + minimal graph UI with slider — `RW-FR-020/021`
7. Grafts: breach-distance, duration (provenance is built in from step 2) — `RW-ALG-030/031`
8. NL shock parsing + explanation generation + orchestration — `RW-FR-001/022/024`, `RW-AI-011`
9. Evidence panels + demo polish + evaluation dashboard — `RW-FR-021`, `RW-OPS-001`
10. Stretch: C++ core, Monte Carlo, additional packs — `RW-ALG-D07`, `RW-FR-D06`

---

## 21. Definition of Product Completion (release scope)

RiskWeave v1 is complete when: build-priority steps 1 through 9 are implemented; MUST-level requirements in release scope have traceable evidence; critical acceptance criteria pass; both the CRE and oil packs work end to end; results are reproducible from their snapshot/version/seed bundle; every displayed material relationship has provenance; Gemini output is schema-validated and citation-bound; all financial calculation runs outside the model; the live severity slider meets latency; the evaluation dashboard renders; the main demo (Section 19) is reliable with a frozen fallback; methodology and known limitations are visible; no secret exists in the repo or client; setup works from documented instructions; and a new AI agent can understand architecture, contracts, and the next task from the docs without undocumented chat history.

---

## 22. Machine-Readable Project Manifest

```yaml
project:
  name: RiskWeave
  version: 2.1.0
  type: financial_contagion_scenario_platform
  context: hackathon_bloomberg_best_fintech
  primary_scenario_pack: commercial_real_estate
  secondary_scenario_pack: oil_price_shock
  required_ai_provider: Gemini API
  product_mode: analytics_not_advice

invariants:
  - every_material_relationship_has_provenance
  - no_edge_without_provenance
  - every_weight_from_registered_deterministic_method
  - llm_never_produces_numbers_entering_propagation
  - every_completed_run_has_immutable_snapshot
  - financial_calculations_are_deterministic
  - ai_output_is_schema_validated
  - material_claims_are_citation_bound
  - explanation_numbers_exist_in_computation_payload
  - correlation_is_not_labeled_causation
  - completed_runs_are_reproducible
  - secrets_are_server_side
  - provider_terms_are_respected
  - uncertainty_is_visible

curated_universe:
  min_entities: 100
  max_entities: 200
  breach_distance_min_coverage: 10

grafts:
  - breach_distance_node_metric        # RW-ALG-030
  - universal_evidence_provenance      # RW-ALG-032
  - duration_rate_transmission         # RW-ALG-031

required_vertical_slice:
  - natural_language_scenario
  - structured_scenario_review
  - scenario_validation
  - graph_selection
  - direct_impact
  - three_hop_propagation
  - ranked_impacts
  - interactive_graph_with_live_slider
  - path_decomposition
  - evidence_viewer
  - evaluation_dashboard

weight_derivation_methods:
  - DER-COMMODITY
  - DER-CONCENTRATION
  - DER-CREDIT
  - DER-DURATION
  - DER-GEO
  - DER-BETA

required_data_sources:
  - SEC_EDGAR
  - SEC_XBRL_COMPANY_FACTS
  - FRED_OR_ALFRED
  - CURATED_ENTITY_METADATA
  - FREE_TIER_EQUITY_PRICES  # disclosed on honesty view

deferred:
  - perf_10k_nodes_5s          # RW-NFR-D01
  - scenario_comparison        # RW-FR-D02
  - report_export              # RW-FR-D03
  - reviewer_workflow          # RW-FR-D04
  - full_wcag_aa               # RW-UX-D05
  - monte_carlo_uncertainty    # RW-FR-D06
  - cpp_propagation_core       # RW-ALG-D07
  - live_news_feed             # RW-DATA-D08
  - complaint_signals          # RW-DATA-D09
  - full_semantic_diff         # RW-FR-D10
  - full_fixed_income          # RW-ALG-D11
  - broad_market_and_platform  # RW-DATA-D12

prohibited:
  - trade_execution
  - personalized_investment_advice
  - unsupported_financial_claims
  - price_predictions
  - unauthorized_data_access
  - hidden_model_assumptions
  - llm_owned_financial_arithmetic
  - arbitrary_tool_execution
  - client_side_private_api_keys
  - kafka_or_kubernetes_v1

infra:
  packaging: docker_compose
  graph_db: neo4j
  relational_db: postgresql
  cache: redis

downstream_specs:
  - design
  - planning
  - implementation
  - data
  - ai_evaluation
  - testing
  - operations

agent_tooling:  # development process only — never part of the product runtime (Section 25)
  ticket_system: linear_mcp
  workflow_definitions: workflows/
  methodology: compound_engineering_loop
  memory: [claude_mem, docs_solutions_learnings]
  recommended_mcps:
    - linear
    - claude_in_chrome        # UI/latency verification, RW-FR-020/021
    - context7_docs_research  # Section 23 recheck rule
    - figma                   # UI mocks: graph canvas, evidence panels, dashboard
    - railway                 # optional demo mirror only, Section 25.3
    - canva                   # pitch materials
  recommended_plugins:
    - compound_engineering
    - claude_mem
    - codex_second_opinion    # propagation math review, RW-ALG-005/006
  hosting_posture:
    demo_primary: local_docker_compose
    cloud_mirror_optional: railway
    frontend_previews_only: vercel
    avoid: supabase
  boundary: gemini_tool_registry_is_closed  # Section 13.2; dev tooling never enters it
```

---

## 23. Official Technical References

Recheck before implementation; APIs and model availability change.

**Gemini API** — Function calling: https://ai.google.dev/gemini-api/docs/function-calling · Structured output: https://ai.google.dev/gemini-api/docs/structured-output · Embeddings: https://ai.google.dev/gemini-api/docs/embeddings · File Search: https://ai.google.dev/gemini-api/docs/file-search · Models: https://ai.google.dev/gemini-api/docs/models · Deprecations: https://ai.google.dev/gemini-api/docs/deprecations · API keys: https://ai.google.dev/gemini-api/docs/api-key

**SEC EDGAR** — APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces · Access/fair-use: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data · Data host: https://data.sec.gov/

**FRED / ALFRED** — API: https://fred.stlouisfed.org/docs/api/fred/ · Series observations: https://fred.stlouisfed.org/docs/api/fred/series_observations.html

---

## 24. Open Decisions for the Design Phase

Left intentionally to downstream design, each resolved via an ADR using Section 0.4 priorities: exact propagation damping/aggregation formula and floor threshold (within `RW-ALG-005` constraints); exact confidence formula; exact CRE and oil entity lists; exact macro-series catalog; exact filing parser; exact Gemini model aliases at implementation time; Gemini File Search versus self-managed retrieval; WebSocket versus SSE; graph visualization library; and whether the C++ core (`RW-ALG-D07`) is worth attempting given remaining time.

Note that unlike the source specification, the *sourcing* of every edge weight is NOT an open decision. Section 12 fixes it. Only the aggregation formula that combines already-derived weights is design-tunable.

---

## 25. Agent Tooling — MCPs, Plugins, and Workflows (development process; non-normative for the product)

This section governs how AI agents *work on* RiskWeave, not what RiskWeave *is*. Nothing here overrides any `RW-*` requirement, and none of this tooling ships inside the product. Where a tool conflicts with a requirement (e.g., demo reliability, secrets handling), the requirement wins per Section 0.4.

### 25.1 Ticket-driven workflow (required process)

- `RW-PROC-001` — Work SHOULD flow from Linear tickets through the branch-type workflows in `workflows/` (feature, bugfix, spike, etc.). Each workflow embeds the compound-engineering loop (brainstorm → plan → work → simplify → review → compound) and ends by linking a PR to the ticket.
- `RW-PROC-002` — Tickets and PRs MUST cite the `RW-*` requirement IDs they implement (restates Section 0.2 for the ticket workflow).
- `RW-PROC-003` — Learnings captured via `/ce-compound` land in `docs/solutions/` and SHOULD be consulted (`mem-search`, `docs/solutions/`) before starting new work, so decisions like the propagation aggregation formula (Section 24) are made once, not re-derived per session.

### 25.2 Recommended MCP servers and plugins (mapped to build phases)

| Tool | Kind | Use in this project | Build-priority phases (Section 20) |
|---|---|---|---|
| **Linear MCP** | MCP | Ticket lifecycle: read, status, comments, PR links | All |
| **claude-in-chrome** | MCP (Chrome extension) | Verify graph UI, slider latency feel, evidence panels (`RW-FR-020/021`); inspect WebSocket traffic; spot-check EDGAR/FRED endpoints | 1, 6, 7, 9 |
| **Context7 / docs researchers** | MCP + agents | Current API docs for Gemini (Section 23 recheck rule), Neo4j/Cypher, React Flow vs Cytoscape.js, FastAPI/Pydantic v2 | 2, 3, 4, 6, 8 |
| **WebFetch / web research** | Built-in | SEC EDGAR and FRED API documentation, provider terms verification (`RW-DATA-005`) | 1 |
| **claude-mem + compound-engineering** | Plugins | Cross-session memory and documented learnings; multi-agent code review; the `/ce-*` skill loop | All |
| **Codex plugin** | Plugin | Second-opinion pass on correctness-critical math: propagation, cycle handling, path decomposition (`RW-ALG-005/006`) | 5 |
| **Figma MCP** | MCP | Mock the graph canvas, evidence panels, and evaluation dashboard before building | 6, 9 |
| **Railway MCP** | MCP | Optional cloud mirror of the Docker Compose stack (see 25.3); deploy, logs, env vars | 9 (demo prep) |
| **Canva MCP** | MCP | Pitch deck, including the roadmap/DEFERRED slide (Section 5.3) | Demo prep |

Agents SHOULD load only the tools relevant to the ticket at hand (per-workflow guidance lives in `workflows/README.md`).

### 25.3 Hosting posture for the demo

- Primary demo target is **local Docker Compose** (`RW-NFR-005`); the ≤500 ms slider budget (`RW-NFR-002`) is easiest to guarantee without a network hop.
- Railway MAY host a shareable mirror of the same containers; this does not constitute a packaging substitution and needs no ADR. The mirror MUST NOT be the demo-critical path.
- Vercel MAY host frontend previews during development only. Supabase SHOULD NOT be used: plain PostgreSQL in Compose is settled (`RW-NFR-003`), and a swap would require an ADR for no demo benefit.
- Regardless of host: the Gemini API key lives server-side only (`RW-SEC-001`) — Railway/host env vars, never the client bundle, never the repo.

### 25.4 Boundary rule

Development-agent tooling (MCPs, plugins) is **not** part of the RiskWeave runtime. The only AI provider inside the product is the Gemini API (`RW-AI-*`), and the only tools Gemini may call are those in the closed registry of Section 13.2. Nothing in this section adds tools to that registry.

---

## 26. Final Instruction to Future Agents

RiskWeave MUST NOT become a chatbot that summarizes financial documents. Its defining loop is:

```
Financial evidence
      ↓
Validated entities and relationships
      ↓
Structured, reviewable scenario
      ↓
Deterministic propagation with data-derived weights
      ↓
Interactive paths and ranked impacts (live slider)
      ↓
Evidence-bound Gemini explanation
```

Protect this loop, and protect Section 12, in every design, planning, implementation, and testing decision. The fastest way to lose this competition is to let a number that no one can source appear on screen. The fastest way to win it is to make every number clickable back to the sentence it came from.
