# ADR-006: Gemini Retrieval And Model Aliases

## Status

Accepted for v1; model aliases require implementation-time recheck.

## Context

RiskWeave must use Gemini structured outputs and function calling, but Gemini
must not produce numerical truth. Section 24 left two related choices open:
Gemini File Search versus self-managed retrieval, and exact Gemini model aliases
at implementation time. The Gemini model page is actively updated, so aliases
must not be copied from stale training data.

As of 2026-07-11, the Google AI model docs list `gemini-3.5-flash` as a stable
Gemini 3 Flash model and `gemini-3.1-pro-preview` as the documented Pro-tier
replacement path for `gemini-2.5-pro`. The deprecations page lists
`gemini-2.5-pro` and `gemini-2.5-flash` shutdown dates in 2026, so new snapshots
must not rely on 2.5 aliases without a fresh deprecation check. The model docs
also distinguish stable, preview, latest, and experimental name patterns, with
stable model strings preferred for production apps.

## Original Requirement

Choose Gemini File Search versus self-managed retrieval and define how exact
Gemini model aliases are selected at implementation time.

## Proposed Change

Use self-managed retrieval for authoritative extraction and evidence. Recheck
official Gemini docs during implementation and persist exact model strings in
snapshots.

## Reason

Self-managed retrieval preserves offsets and reproducibility, while model alias
rechecks avoid freezing stale or near-deprecation names into the architecture.

## Decision

Use self-managed retrieval for extraction, provenance, and evidence panels.
Gemini File Search may be used only as an auxiliary discovery tool for
non-authoritative exploration, never as the source of propagation edges,
extraction offsets, or evidence panel citations.

At implementation time, run a fresh docs check against:

- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/deprecations
- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/gemini-api/docs/function-calling

Default model aliases as of 2026-07-11, unless the implementation-time recheck
changes availability or deprecation status:

- filing extraction: `gemini-3.5-flash`, if it supports the required strict
  structured output path for the target document input;
- shock parsing and evidence-bound explanation: `gemini-3.1-pro-preview`, unless
  a stable Pro-tier successor is available at implementation time;
- embeddings or retrieval helpers: current documented Gemini embedding model
  only for auxiliary search indices, not for numerical derivation.

Do not use `latest` aliases in reproducible ingestion or run snapshots. Do not
use 2.5 aliases for new snapshots unless the implementation-time check finds no
viable 3.x replacement and records the shutdown risk. Persist the exact model
string, docs check date, prompt/schema version, and response validation version
in every extraction snapshot.

## Alternatives Considered

- Gemini File Search as the primary retrieval layer: rejected because
  RiskWeave requires exact offsets, deterministic derivation references, and
  immutable evidence records.
- Hard-code today's model names in the spec: rejected because model availability
  and deprecations are time-sensitive.
- Use only Pro-tier models: rejected for cost; extraction is high-volume and the
  spec already prefers Flash-tier extraction.

## Consequences

The ingestion pipeline owns chunking, retrieval, offsets, and citations. Gemini
is used for structured interpretation of supplied text and for run-scoped
explanations over deterministic payloads.

## User And Judging Impact

Users and judges can trace evidence to RiskWeave-owned stored passages, not an
opaque managed index. The team can state which Gemini model string was used for
each snapshot.

## Security, Data, Cost, And Performance Impact

Self-managed retrieval increases implementation work and storage, but protects
provenance and reproducibility. Exact model strings and API keys remain
server-side only; no client bundle may contain Gemini credentials.

## Migration Or Rollback

If Gemini File Search later exposes the exact offset and snapshot controls
RiskWeave needs, a new ADR may permit it for primary retrieval. Model aliases may
change only through implementation-time docs checks recorded in snapshot
metadata.

## Human Approval Required

No for model alias refreshes that preserve tiering and requirements. Yes for any
change that delegates provenance or numeric derivation to Gemini-managed
retrieval.

No MUST-level requirement is weakened by this ADR.

## Affected Requirements

`RW-AI-001`, `RW-AI-002`, `RW-AI-003`, `RW-AI-004`, `RW-AI-010`, `RW-AI-011`,
`RW-AI-012`, `RW-DATA-004`, `RW-ALG-001`, `RW-ALG-032`, `RW-SEC-001`,
`RW-SEC-002`, `RW-SEC-003`.

## Sources

- Gemini models: https://ai.google.dev/gemini-api/docs/models
- Gemini File Search: https://ai.google.dev/gemini-api/docs/file-search
- Gemini structured output: https://ai.google.dev/gemini-api/docs/structured-output
