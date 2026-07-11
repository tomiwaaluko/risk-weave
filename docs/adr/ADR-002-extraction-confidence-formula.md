# ADR-002: Extraction Confidence Formula

## Status

Accepted for v1.

## Context

`RW-ALG-007` requires output confidence to represent extraction/model or
data-quality confidence, not a statistical guarantee. Confidence must support
review and demo trust without letting Gemini invent sensitivities, weights, or
financial magnitudes.

## Original Requirement

Choose the exact confidence formula while preserving `RW-ALG-007`: confidence is
extraction/model or data-quality confidence, not a statistical guarantee.

## Proposed Change

Adopt a deterministic weighted score over validation signals already available
from schema validation, quote alignment, parsing, source quality, and review
status.

## Reason

The score is reproducible, auditable, and tied to evidence quality instead of
model self-reporting.

## Decision

Store confidence as a deterministic score in `[0.0, 1.0]`, labeled
`extraction_confidence`, with a required UI label: "Extraction confidence, not
probability." Compute it from validation signals already present in the
extraction pipeline:

```text
extraction_confidence =
  0.30 * schema_validity_score +
  0.25 * quote_alignment_score +
  0.20 * deterministic_parse_score +
  0.15 * source_quality_score +
  0.10 * reviewer_status_score
```

Signal definitions:

- `schema_validity_score`: `1.0` only for strict-schema-valid output; otherwise
  the extraction is rejected, not downscored.
- `quote_alignment_score`: exact quote text and offsets match stored filing text.
- `deterministic_parse_score`: deterministic parser converts captured strings,
  units, dates, or identifiers without repair.
- `source_quality_score`: primary filings, XBRL facts, and FRED/ALFRED series
  score higher than derived or manually curated metadata.
- `reviewer_status_score`: reviewed/accepted extractions score higher than
  unreviewed machine-only extractions.

Thresholds:

- `< 0.60`: do not create an active propagation edge.
- `0.60..0.79`: create only if deterministic derivation succeeds; flag for review.
- `>= 0.80`: eligible for active graph use after deterministic derivation.

## Alternatives Considered

- Let Gemini report confidence: rejected because it would be model self-reporting
  and would not be reproducible.
- Binary confidence only: rejected because reviewers need triage priority.
- Statistical confidence intervals: rejected because most inputs are extracted
  disclosures and deterministic derivations, not sampled estimates.

## Consequences

Confidence is auditable and reproducible. It does not alter deterministic edge
weights; it gates whether an extraction is eligible for graph construction and
how prominently the UI flags it for review.

## User And Judging Impact

Users see low-confidence evidence as review risk rather than false precision.
Judges can verify that confidence never changes the deterministic weight math.

## Security, Data, Cost, And Performance Impact

No new data or vendor dependency. The score adds lightweight validation work and
requires test fixtures for exact quote/offset matching.

## Migration Or Rollback

Changing weights or thresholds requires an ADR amendment and a data snapshot
version bump.

## Human Approval Required

No for the initial formula. Yes for any change that lowers active-edge gates.

No MUST-level requirement is weakened by this ADR.

## Affected Requirements

`RW-ALG-001`, `RW-ALG-002`, `RW-ALG-003`, `RW-ALG-004`, `RW-ALG-007`,
`RW-ALG-032`, `RW-AI-001`, `RW-AI-010`, `RW-DATA-004`, `RW-FR-D04`.
