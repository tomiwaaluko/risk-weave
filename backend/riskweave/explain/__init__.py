"""Evidence-bound explanation guard + generation (RIS-19, `RW-AI-011`)."""

from .generation import (
    DEFAULT_EXPLANATION_MODEL,
    EXPLANATION_PROMPT_VERSION,
    EdgeEvidence,
    ExplanationTransport,
    GeneratedExplanation,
    NodeExplanationContext,
    PathSummary,
    StructuredNumber,
    build_node_context,
    citation_markers_in,
    generate_node_explanation,
    strip_citation_markers,
)
from .guard import (
    ExplanationPayload,
    GuardResult,
    extract_numeric_tokens,
    guard_explanation,
)
from .payload import payload_for_node, payload_for_run

__all__ = [
    "DEFAULT_EXPLANATION_MODEL",
    "EXPLANATION_PROMPT_VERSION",
    "EdgeEvidence",
    "ExplanationPayload",
    "ExplanationTransport",
    "GeneratedExplanation",
    "GuardResult",
    "NodeExplanationContext",
    "PathSummary",
    "StructuredNumber",
    "build_node_context",
    "citation_markers_in",
    "extract_numeric_tokens",
    "generate_node_explanation",
    "guard_explanation",
    "payload_for_node",
    "payload_for_run",
    "strip_citation_markers",
]
