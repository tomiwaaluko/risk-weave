"""Evaluation-dashboard metrics (RIS-21, `RW-OPS-001`, spec §15)."""

from .labeling import LabeledRelationship, LabelError, load_labels
from .live_bridge import (
    confidence_distribution,
    extraction_keys_from_graph,
    method_distribution,
    resolution_pairs,
)
from .metrics import (
    ClassificationMetrics,
    EvaluationError,
    LatencySummary,
    citation_correctness_rate,
    entity_resolution_accuracy,
    extraction_metrics,
    latency_summary,
    scenario_stability,
    unsupported_claim_rate,
)

__all__ = [
    "LabeledRelationship",
    "LabelError",
    "load_labels",
    "ClassificationMetrics",
    "EvaluationError",
    "LatencySummary",
    "citation_correctness_rate",
    "entity_resolution_accuracy",
    "extraction_metrics",
    "latency_summary",
    "scenario_stability",
    "unsupported_claim_rate",
    "confidence_distribution",
    "extraction_keys_from_graph",
    "method_distribution",
    "resolution_pairs",
]
