"""Deterministic propagation engine (RIS-13, ADR-001)."""

from .engine import (
    DAMPING,
    ENGINE_VERSION,
    FLOOR,
    MAX_HOPS,
    NodeImpact,
    PathContribution,
    PropagationResult,
    Scenario,
    ScenarioError,
    ShockFactor,
    propagate,
)
from .graph import GraphEdge, GraphNode, GraphSnapshot, SnapshotError

__all__ = [
    "DAMPING",
    "ENGINE_VERSION",
    "FLOOR",
    "MAX_HOPS",
    "GraphEdge",
    "GraphNode",
    "GraphSnapshot",
    "NodeImpact",
    "PathContribution",
    "PropagationResult",
    "Scenario",
    "ScenarioError",
    "ShockFactor",
    "SnapshotError",
    "propagate",
]
