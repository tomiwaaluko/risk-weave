"""Build the allowed-number payload from a computation result (`RW-AI-011`).

Gemini's explanation prompt must contain only computation output and provenance
records; this module derives the exact set of numbers that output contains, so
the guard can reject anything else. Assembling the payload here (rather than
hand-listing numbers at each call site) keeps the "only payload numbers" rule
mechanical.
"""

from __future__ import annotations

from riskweave.propagation import NodeImpact, PropagationResult

from .guard import ExplanationPayload


def payload_for_node(result: PropagationResult, node_id: str) -> ExplanationPayload:
    """Numbers an explanation of one node's impact may reference.

    Includes the node's risk score and raw impact, every contributing path's
    signed contribution and edge weights, and the run's damping/floor constants
    — the figures a per-node explanation legitimately cites.
    """
    impact: NodeImpact = result.impacts[node_id]
    numbers: list[float] = [
        impact.risk_score,
        round(impact.risk_score),
        impact.raw_impact,
        result.damping,
        result.floor,
        float(result.max_hops),
    ]
    for contribution in impact.contributions:
        numbers.append(contribution.contribution)
        numbers.append(float(contribution.hop_count))
        for edge in contribution.edges:
            numbers.append(edge.weight)
    return ExplanationPayload(numbers=tuple(numbers))


def payload_for_run(result: PropagationResult) -> ExplanationPayload:
    """Numbers a whole-run explanation may reference (union over all nodes)."""
    numbers: list[float] = [result.damping, result.floor, float(result.max_hops)]
    for node_id in result.impacts:
        numbers.extend(payload_for_node(result, node_id).numbers)
    return ExplanationPayload(numbers=tuple(numbers))
