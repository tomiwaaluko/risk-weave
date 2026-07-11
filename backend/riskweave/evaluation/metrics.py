"""Evaluation metrics — the "not a wrapper" dashboard core (`RW-OPS-001`, §15).

Deterministic metric functions over hand-labeled samples and run outputs. These
are the numbers demo beat 6 shows to separate RiskWeave from Gemini-wrapper
teams. Every function here is pure arithmetic on caller-supplied data; nothing
calls a model.

Minimum metric set (spec §15):
- relationship-extraction precision / recall / F1 on a hand-labeled sample
- entity-resolution accuracy on the curated universe
- unsupported-claim rate in explanations (numeric tokens absent from payload)
- citation-correctness spot-check rate
- scenario stability (same input → same output)
- latencies for parse / propagation / explanation
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from riskweave.explain import ExplanationPayload, guard_explanation


class EvaluationError(ValueError):
    """Raised on malformed evaluation inputs."""


@dataclass(frozen=True)
class ClassificationMetrics:
    """Precision / recall / F1 with the confusion counts behind them."""

    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def extraction_metrics(
    predicted: Sequence[frozenset | tuple],
    gold: Sequence[frozenset | tuple],
) -> ClassificationMetrics:
    """Precision/recall of extracted relationships against a hand-labeled gold set.

    Each item is a hashable key identifying one relationship (e.g.
    ``(source_id, target_id, relationship_type)``). Deduped to sets before
    comparison so double-extractions do not inflate counts.
    """
    pred_set = {_key(p) for p in predicted}
    gold_set = {_key(g) for g in gold}
    tp = len(pred_set & gold_set)
    return ClassificationMetrics(
        true_positives=tp,
        false_positives=len(pred_set - gold_set),
        false_negatives=len(gold_set - pred_set),
    )


def _key(item) -> tuple:
    if isinstance(item, frozenset):
        return tuple(sorted(item))
    return tuple(item)


def entity_resolution_accuracy(
    resolved: Sequence[tuple[str, str | None]],
    gold: dict[str, str],
) -> float:
    """Fraction of extracted mentions resolved to the correct canonical id.

    ``resolved`` is ``(mention, predicted_entity_id_or_None)``; ``gold`` maps
    mention → correct entity id. Mentions absent from ``gold`` are ignored.
    """
    scored = [(m, p) for m, p in resolved if m in gold]
    if not scored:
        raise EvaluationError("no scorable mentions (none present in gold)")
    correct = sum(1 for mention, pred in scored if pred == gold[mention])
    return correct / len(scored)


def unsupported_claim_rate(
    explanations: Sequence[tuple[str, ExplanationPayload]],
) -> float:
    """Fraction of explanations containing a number absent from their payload.

    Reuses the RIS-19 guard so the evaluation metric and the runtime gate can
    never diverge (`RW-AI-011`; §4.2 target: 0).
    """
    if not explanations:
        return 0.0
    violations = sum(
        0 if guard_explanation(text, payload).ok else 1 for text, payload in explanations
    )
    return violations / len(explanations)


def citation_correctness_rate(spot_checks: Sequence[bool]) -> float:
    """Fraction of spot-checked citations that resolve to the right passage."""
    if not spot_checks:
        raise EvaluationError("citation spot-check sample is empty")
    return sum(1 for ok in spot_checks if ok) / len(spot_checks)


def scenario_stability(checksums: Sequence[str]) -> bool:
    """True iff repeated runs of the same input produced identical output.

    ``checksums`` are the result fingerprints from N reruns of one scenario;
    stability requires them all equal (RW-GOAL-006, §15).
    """
    if not checksums:
        raise EvaluationError("need at least one run checksum")
    return len(set(checksums)) == 1


@dataclass(frozen=True)
class LatencySummary:
    """Latency percentiles for one pipeline stage, in milliseconds."""

    stage: str
    count: int
    p50_ms: float
    p95_ms: float
    max_ms: float


def latency_summary(stage: str, samples_ms: Sequence[float]) -> LatencySummary:
    """Summarize latency samples for parse / propagation / explanation stages."""
    if not samples_ms:
        raise EvaluationError(f"no latency samples for stage {stage!r}")
    ordered = sorted(float(s) for s in samples_ms)
    n = len(ordered)
    return LatencySummary(
        stage=stage,
        count=n,
        p50_ms=statistics.median(ordered),
        p95_ms=ordered[max(0, min(n - 1, round(0.95 * n) - 1))],
        max_ms=ordered[-1],
    )
