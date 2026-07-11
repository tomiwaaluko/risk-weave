from __future__ import annotations

from dataclasses import asdict
from typing import Any

from riskweave.propagation import PropagationResult


def propagation_result_to_payload(result: PropagationResult, severity: float) -> dict[str, Any]:
    ranked = result.ranked_entities()
    return {
        "scenario_id": result.scenario_id,
        "seed": result.seed,
        "severity": severity,
        "ranked_entity_ids": [impact.node_id for impact in ranked],
        "impacts": {impact.node_id: impact.risk_score for impact in ranked},
        "paths": [asdict(path) for impact in ranked for path in impact.contributions],
    }
