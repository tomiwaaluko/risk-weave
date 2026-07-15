"""Deterministic Gemini cost estimation (RIS-34).

This module only turns already-measured token counts into a dollar figure; it
never estimates or adjusts a token count itself (that stays in `.gemini`'s
`usageMetadata` parsing). Pricing is a plain per-model lookup table, kept
separate from the transport so it can be updated without touching call sites.

Prices are $/1,000,000 tokens, input and output tracked separately since
output tokens are priced higher on every current Gemini tier. `PRICING_CHECKED_AT`
records when these figures were last reconciled against the live Gemini
pricing page; an attempt to re-verify them via WebFetch on 2026-07-15 was
blocked (HTTP 403 from the pricing host), so treat these as the last-known
figures and re-check before relying on them for a real invoice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

PRICING_CHECKED_AT = date(2026, 7, 11)


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal


# Flash tier for high-volume extraction; Pro tier for shock parsing, explanation,
# and Q&A (`RW-AI-003`). Registered explicitly, mirroring the closed-registry
# spirit of the rest of the Gemini integration: an unpriced model is a bug to
# fix here, not a call to guess a number for.
_PRICING: dict[str, ModelPricing] = {
    "gemini-3.5-flash": ModelPricing(
        input_usd_per_million=Decimal("0.075"),
        output_usd_per_million=Decimal("0.30"),
    ),
    "gemini-3.1-pro-preview": ModelPricing(
        input_usd_per_million=Decimal("1.25"),
        output_usd_per_million=Decimal("5.00"),
    ),
}


class PricingError(ValueError):
    """Raised for an unregistered model alias, never a guessed price."""


def model_pricing(model: str) -> ModelPricing:
    try:
        return _PRICING[model]
    except KeyError as exc:
        raise PricingError(f"no registered pricing for Gemini model {model!r}") from exc


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Compute the cost of one call from its measured token counts.

    ``input_tokens``/``output_tokens`` must already be real counts from
    ``usageMetadata`` (or a caller's own estimate for pre-execution budgeting);
    this function does no estimation of its own.
    """
    pricing = model_pricing(model)
    cost = (Decimal(input_tokens) * pricing.input_usd_per_million / Decimal(1_000_000)) + (
        Decimal(output_tokens) * pricing.output_usd_per_million / Decimal(1_000_000)
    )
    return cost
