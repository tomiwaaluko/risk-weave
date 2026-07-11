# ADR-003: Filing Chunking With Stable Offsets

## Status

Accepted for v1.

## Context

Long filings must be chunked so provenance offsets survive (`RW-AI-004`), and
stored filing text must preserve character offsets (`RW-DATA-004`). Because
RiskWeave's defensibility depends on exact quoted passages, chunking cannot make
offsets ambiguous.

## Original Requirement

Choose a filing chunking strategy that preserves provenance offsets for long
filings and supports strict Gemini structured extraction.

## Proposed Change

Use self-managed canonical text extraction, section-aware chunking, absolute
document offsets, overlap metadata, and validator-enforced quote matching.

## Reason

RiskWeave must own offset math so evidence panels can show exact source spans
independent of any vendor-managed retrieval index.

## Decision

Use self-managed filing text extraction and chunking.

For every filing, store:

- immutable `source_document_id`, CIK, accession number, filing type, filing date,
  and retrieval timestamp;
- raw text bytes or canonical extracted text;
- a normalization map from canonical character offsets back to source byte spans
  where available;
- section metadata for filing item headings when detected.

Create chunks after canonicalization, not before it:

```text
target_chunk_size = 14_000 characters
target_overlap = 1_200 characters
hard_max_chunk_size = 18_000 characters
```

Prefer SEC item/section boundaries. If a section exceeds the hard max, split on
paragraph boundaries; if needed, split on sentence boundaries. Each chunk stores
absolute `document_char_start` and `document_char_end`, plus the overlap range.

Gemini extraction receives chunk-local text and must return:

- exact quote;
- chunk-local start/end offsets;
- source document ID;
- extraction schema fields.

The ingestion validator maps local offsets to absolute document offsets, checks
that the quote exactly matches the canonical stored text, and rejects the
extraction if the quote or offsets do not align.

## Alternatives Considered

- Provider-managed file search chunking: useful for retrieval, but rejected as
  the primary extraction path because exact offset control is a MUST-level
  provenance requirement.
- Fixed-size chunks with no section awareness: simpler, but can split disclosures
  and reduce quote alignment quality.
- Whole-filing prompts: rejected for cost, latency, and reproducibility.

## Consequences

Offset survival is controlled by RiskWeave, not delegated to a vendor index.
Chunk overlap may duplicate candidate extractions, so deduplication must use
`source_document_id + absolute_quote_offsets + schema_field`.

## User And Judging Impact

Users can inspect exact filing passages even when a disclosure crossed chunk
boundaries. Judges can audit quote-to-offset matching directly.

## Security, Data, Cost, And Performance Impact

No additional secrets. Storage increases because canonical text, offsets, and
chunk metadata are retained. Extraction cost is predictable because chunks have a
hard maximum size.

## Migration Or Rollback

Any parser or normalization change requires a new filing snapshot version.
Existing run snapshots must keep their original chunk metadata.

## Human Approval Required

No, unless a future change removes exact quote or absolute offset validation.

No MUST-level requirement is weakened by this ADR.

## Affected Requirements

`RW-DATA-001`, `RW-DATA-004`, `RW-DATA-005`, `RW-ALG-002`, `RW-ALG-004`,
`RW-ALG-032`, `RW-AI-001`, `RW-AI-004`, `RW-AI-010`, `RW-SEC-003`.
