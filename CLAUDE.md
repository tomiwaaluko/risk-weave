# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

This repository currently contains **no code** — the source-of-truth product/system requirements specification `RISKWEAVE_MASTER_SPEC_MERGED.md` (v2.1.0) and the `workflows/` folder of branch-type agent workflows (see spec §25 for the agent tooling and MCP policy). All design, planning, implementation, and testing work MUST derive from that spec and MUST NOT silently redefine it. Read it before doing anything substantive; this file is only an orientation layer.

There are no build, lint, or test commands yet. When the codebase is scaffolded, update this file with the actual commands.

## What RiskWeave is

An AI-assisted financial contagion platform for a hackathon (Bloomberg Best FinTech Hack). Users describe a financial shock in natural language; the system parses it into a structured scenario, propagates it through a curated knowledge graph (100–200 entities) with deterministic, data-derived edge weights, and renders an interactive graph with a live severity slider and per-edge evidence panels. Two scenario packs: commercial real estate decline (primary) and oil price shock (secondary).

## Non-negotiable invariants (MUST-level; violating these is the project's defining failure mode)

- **Gemini finds the sentence; deterministic code turns it into the number.** Gemini (the required AI provider) MUST NOT produce, estimate, or adjust any weight, ratio, sensitivity, or magnitude entering propagation (`RW-AI-010`, `RW-ALG-001`).
- **No edge without provenance.** Every edge, node exposure, and generated claim carries source document id, exact quoted passage with character offsets, data timestamp, calculation-method id, and extraction confidence (`RW-ALG-032`). Tests must fail pipeline output missing provenance.
- **Every edge weight comes from a registered deterministic derivation method** (Section 12 of the spec): `DER-COMMODITY`, `DER-CONCENTRATION`, `DER-CREDIT`, `DER-DURATION`, `DER-GEO`, `DER-BETA`. The weight *sourcing* policy is fixed; only the aggregation formula is design-tunable.
- **Explanations reference only numbers present in the computation payload** (`RW-AI-011`) — tests must assert this.
- All Gemini extraction uses **strict JSON structured outputs**; tool use is limited to the closed registered tool registry (spec Section 13.2). The extraction schema deliberately has no `estimated_sensitivity` field.
- Runs bind to an immutable data snapshot and are reproducible from snapshot + versions + seed.
- No price predictions, no buy/sell/hold advice, no trade execution, no secrets in repo/client/logs.
- **Do not silently weaken or reinterpret a MUST requirement** — changes require an ADR/PDR (spec §0.3). Do not expand scope: new ideas go to the DEFERRED list (spec §5.3), not the build. Kafka and Kubernetes are prohibited for v1.

## Decision priority when the spec leaves a choice open (spec §0.4)

Financial correctness > evidence provenance > user trust/explainability > reproducibility > reliable demo behavior > simplicity > performance > cost > extensibility.

## Planned architecture (spec §14, settled — reopening requires an ADR)

Batch pre-demo ingestion (SEC EDGAR filings, XBRL company facts, FRED series — all free-tier, rate-limited per provider terms) → Gemini structured extraction with provenance capture → layered entity resolution (deterministic identifiers first: CIK/ticker/LEI; Gemini merges only ambiguous residuals) → deterministic weight derivation → Neo4j knowledge graph → Python/NumPy propagation engine (synchronous, ≤500 ms slider recompute, 3-hop cap) → FastAPI + WebSocket backend with Redis result caching → Next.js + TypeScript frontend (React Flow or Cytoscape.js).

Stack defaults (substitutions require an ADR): Python 3.11+ / FastAPI / Pydantic v2 backend; PostgreSQL for financials/provenance/time series; Neo4j for the graph; Redis cache; Docker Compose packaging; Gemini Flash tier for extraction, Pro tier for shock parsing and explanation.

## Build order (spec §20 — dependency-ordered; risky items front-loaded)

1. Curated entity universe + batch ingestion
2. Deterministic weight derivations with provenance
3. Gemini extraction pipeline + layered entity resolution
4. Neo4j graph assembly
5. Propagation engine + tests (determinism, path decomposition, cycle handling)
6. FastAPI + WebSocket + minimal graph UI with slider
7. Grafts: breach-distance (`RW-ALG-030`) and duration (`RW-ALG-031`)
8. NL shock parsing + explanation generation + orchestration
9. Evidence panels + evaluation dashboard + demo polish

The three "grafts" (breach-distance node metric, universal provenance, duration-based rate transmission) are first-class requirements, not polish.

## Traceability

Reference spec requirement IDs (`RW-FR-*`, `RW-ALG-*`, `RW-AI-*`, etc.) in downstream tasks, components, and tests. Work that maps to no requirement must be labeled enabling work, experimentation, tech debt, or an approved requirement change.

## Development conventions

Until the application is scaffolded, do not invent build, lint, test, or local-run commands in documentation. When adding a toolchain, expose a small, reproducible command set and update this file with the actual commands and directory layout.

Follow the formatter and linter defaults committed for each language. Use four-space indentation and `snake_case` for Python modules and functions. Use two-space indentation, `PascalCase` for React components, and `camelCase` for TypeScript values. Prefer explicit domain names over abbreviations.

New implementation work must include focused tests for its requirements. Prioritize deterministic propagation, reproducibility, cycle handling, path decomposition, strict Gemini JSON schemas, provenance completeness, and the rule that explanations use only computation-payload numbers. Name tests by observable behavior, for example `test_rejects_edge_without_provenance`.

## Commits and pull requests

The repository does not yet have a mature commit convention. Use imperative, scoped subjects such as `backend: validate edge provenance`. Pull requests should summarize behavior, cite requirement IDs, identify tests run, link relevant issues or ADRs, and include screenshots for UI changes. Explicitly call out schema, data-source, and reproducibility impacts.

## Security and configuration

Never commit API keys, credentials, financial secrets, or sensitive data. Keep secrets out of clients and logs. Preserve source document IDs, exact quotations with offsets, timestamps, derivation methods, and extraction confidence for every computed relationship.
