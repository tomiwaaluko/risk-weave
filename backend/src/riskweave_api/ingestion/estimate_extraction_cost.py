"""Estimate the Gemini cost of a full-extraction batch before running it (RIS-34).

RIS-28 wires up the live pipeline's bulk extraction over the full chunk corpus
(22,384 chunks at time of writing) — the single largest planned Gemini spend.
This is a pre-execution estimate only: it multiplies the *measured* average
chunk size by the registered per-model pricing (`riskweave.accounting.pricing`)
to bound the expected cost before the batch runs, per RIS-34's acceptance
criterion. It never substitutes for the real per-call accounting that RIS-28's
run will produce (`gemini_usage_records`).

Assumptions (documented, not hidden):
* Two Flash calls per chunk (relationship extraction + covenant extraction).
* ``target_size`` chunk characters (default 14,000, `chunking.chunk_text`'s
  default) approximate 1 token per 4 characters (a standard rough English-text
  ratio; the real count comes from `usageMetadata` once the batch runs).
* A fixed prompt-overhead token allowance per call for the instruction text
  wrapped around the chunk (see `GeminiExtractionClient._relationship_prompt`
  / `_covenant_prompt`).
* Output tokens per call are estimated from a small fixed allowance since
  structured extraction JSON is short relative to the input chunk; this is
  the least certain input and the most likely to move on a real run.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal

from riskweave.accounting.pricing import estimate_cost_usd

GEMINI_EXTRACTION_MODEL = "gemini-3.5-flash"
CALLS_PER_CHUNK = 2  # relationship extraction + covenant extraction
CHARS_PER_TOKEN = 4
PROMPT_OVERHEAD_TOKENS = 150
ESTIMATED_OUTPUT_TOKENS_PER_CALL = 400


@dataclass(frozen=True)
class BatchCostEstimate:
    chunk_count: int
    chunk_target_chars: int
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


def estimate_batch_cost(
    *,
    chunk_count: int,
    chunk_target_chars: int = 14_000,
    calls_per_chunk: int = CALLS_PER_CHUNK,
    model: str = GEMINI_EXTRACTION_MODEL,
) -> BatchCostEstimate:
    input_tokens_per_call = (chunk_target_chars // CHARS_PER_TOKEN) + PROMPT_OVERHEAD_TOKENS
    calls = chunk_count * calls_per_chunk
    input_tokens = calls * input_tokens_per_call
    output_tokens = calls * ESTIMATED_OUTPUT_TOKENS_PER_CALL
    cost = estimate_cost_usd(model, input_tokens, output_tokens)
    return BatchCostEstimate(
        chunk_count=chunk_count,
        chunk_target_chars=chunk_target_chars,
        calls=calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Estimate the Gemini cost of RIS-28's full-extraction batch"
    )
    parser.add_argument("--chunks", type=int, default=22_384, help="chunk count (RIS-28)")
    parser.add_argument("--chunk-chars", type=int, default=14_000)
    args = parser.parse_args()

    estimate = estimate_batch_cost(chunk_count=args.chunks, chunk_target_chars=args.chunk_chars)
    print(f"chunks: {estimate.chunk_count}")
    print(f"Gemini calls (2/chunk): {estimate.calls}")
    print(f"estimated input tokens: {estimate.input_tokens:,}")
    print(f"estimated output tokens: {estimate.output_tokens:,}")
    print(f"estimated cost: ${estimate.cost_usd:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
