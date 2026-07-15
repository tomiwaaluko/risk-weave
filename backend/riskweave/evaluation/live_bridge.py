"""Feed *real* live-pipeline output into the evaluation metrics (RIS-28 / RIS-21).

RIS-21's metrics (``extraction_metrics``, ``entity_resolution_accuracy``) were
originally exercised against fixtures. RIS-28 wires the live pipeline, so the
dashboard can now score the graph actually assembled from a real ingestion
snapshot. These adapters turn an :class:`~riskweave.graph.AssembledGraph` and a
:class:`~riskweave.graph.live.LiveBuildReport` into the key spaces the metric
functions consume — no fabricated numbers, just a shape adapter.

The metric *values* are recomputed once the live extraction run has populated
``relationship_extractions`` for the snapshot; see ``docs/live-pipeline.md`` for
the command. These adapters are what the dashboard calls to consume that output
instead of the fixture.
"""

from __future__ import annotations

from collections.abc import Sequence

from riskweave.graph.assembly import AssembledGraph


def extraction_keys_from_graph(graph: AssembledGraph) -> list[tuple[str, str, str]]:
    """Predicted relationship keys ``(source_id, target_id, relationship_type)``.

    These are the keys :func:`riskweave.evaluation.metrics.extraction_metrics`
    scores against a hand-labeled gold set. Keys are over resolved canonical
    entity ids, so the gold set must be labeled in the same id space (curated
    universe ids), keeping predicted and gold comparable.
    """
    return [(edge.source_id, edge.target_id, edge.relationship_type) for edge in graph.edges]


def confidence_distribution(graph: AssembledGraph, threshold: float) -> dict[str, int]:
    """Count live edges at or below vs. above a confidence badge threshold.

    Backs the honesty view that low-confidence edges are surfaced (badged),
    never hidden (`RW-SAFE-003`).
    """
    low = sum(1 for edge in graph.edges if edge.record.provenance.extraction_confidence < threshold)
    return {"low_confidence": low, "high_confidence": len(graph.edges) - low}


def method_distribution(graph: AssembledGraph) -> dict[str, int]:
    """Count live edges per registered derivation method (feeds the dashboard)."""
    counts: dict[str, int] = {}
    for edge in graph.edges:
        counts[edge.record.method_id] = counts.get(edge.record.method_id, 0) + 1
    return dict(sorted(counts.items()))


def resolution_pairs(
    resolved: Sequence[tuple[str, str | None]],
) -> list[tuple[str, str | None]]:
    """Pass-through kept as the dashboard's documented entry point for RIS-28.

    ``resolved`` is ``(mention, predicted_entity_id_or_None)`` gathered from the
    live build's audit log; handed straight to
    :func:`riskweave.evaluation.metrics.entity_resolution_accuracy`.
    """
    return list(resolved)
