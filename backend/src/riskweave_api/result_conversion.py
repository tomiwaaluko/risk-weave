"""Convert propagation engine results to API response models."""

from __future__ import annotations

from riskweave.propagation import PropagationResult

from .models import NodeImpactOut, PathContributionOut, RunResult


def propagation_result_to_run_result(
    result: PropagationResult,
    severity: float,
    latency_ms: float,
) -> RunResult:
    impacts_out: dict[str, NodeImpactOut] = {}
    for node_id, ni in result.impacts.items():
        contributions_out = [
            PathContributionOut(
                path_key=pc.path_key,
                factor_id=pc.factor_id,
                hop_count=pc.hop_count,
                contribution=pc.contribution,
                edge_ids=[e.edge_id for e in pc.edges],
                method_ids=[e.method_id for e in pc.edges],
                provenance_refs=[e.provenance_ref for e in pc.edges],
            )
            for pc in ni.contributions
        ]
        impacts_out[node_id] = NodeImpactOut(
            node_id=node_id,
            raw_impact=ni.raw_impact,
            risk_score=ni.risk_score,
            contributions=contributions_out,
        )

    ranked = [ni.node_id for ni in result.ranked_entities()]

    return RunResult(
        scenario_id=result.scenario_id,
        snapshot_id=result.snapshot_id,
        graph_version=result.graph_version,
        engine_version=result.engine_version,
        seed=result.seed,
        severity=severity,
        damping=result.damping,
        floor=result.floor,
        max_hops=result.max_hops,
        impacts=impacts_out,
        ranked_entity_ids=ranked,
        latency_ms=latency_ms,
    )
