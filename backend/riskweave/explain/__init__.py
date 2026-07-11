"""Evidence-bound explanation guard (RIS-19, `RW-AI-011`)."""

from .guard import (
    ExplanationPayload,
    GuardResult,
    extract_numeric_tokens,
    guard_explanation,
)
from .payload import payload_for_node, payload_for_run

__all__ = [
    "ExplanationPayload",
    "GuardResult",
    "extract_numeric_tokens",
    "guard_explanation",
    "payload_for_node",
    "payload_for_run",
]
