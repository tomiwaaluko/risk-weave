"""Layered entity resolution for RIS-11 (`RW-AI-012`, `RW-FR-010`)."""

from .resolver import (
    ENTITY_RESOLUTION_CONFIDENCE_THRESHOLD,
    AuditEvent,
    EntityRecord,
    GeminiMergeProposal,
    ResolutionResult,
    Resolver,
    UnresolvedMention,
    load_universe,
    normalize_identifier,
    normalize_name,
)

__all__ = [
    "ENTITY_RESOLUTION_CONFIDENCE_THRESHOLD",
    "AuditEvent",
    "EntityRecord",
    "GeminiMergeProposal",
    "ResolutionResult",
    "Resolver",
    "UnresolvedMention",
    "load_universe",
    "normalize_identifier",
    "normalize_name",
]
