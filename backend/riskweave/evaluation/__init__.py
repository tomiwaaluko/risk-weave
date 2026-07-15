"""Evaluation-dashboard metrics (RIS-21, `RW-OPS-001`, spec §15)."""

from .labeling import LabeledRelationship, LabelError, load_labels, positive_keys
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
from .report import EvaluationReport, MetricRow, run_evaluation

__all__ = [
    "LabeledRelationship",
    "LabelError",
    "load_labels",
    "positive_keys",
    "EvaluationReport",
    "MetricRow",
    "run_evaluation",
    "ClassificationMetrics",
    "EvaluationError",
    "LatencySummary",
    "citation_correctness_rate",
    "entity_resolution_accuracy",
    "extraction_metrics",
    "latency_summary",
    "scenario_stability",
    "unsupported_claim_rate",
]
