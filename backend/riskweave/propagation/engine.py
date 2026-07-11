"""Deterministic 3-hop propagation engine (ADR-001, `RW-ALG-005/006`).

Implements exactly the ADR-001 formula — simple-path contribution tracking
with geometric hop damping:

    path_contribution(p) = shock_magnitude * product(edge_weight(e_i)) * DAMPING**(h - 1)

- ``DAMPING = 0.60``; first-order impact is preserved because ``DAMPING**0 = 1``.
- A path whose ``abs(contribution)`` falls below ``FLOOR = 0.005`` on the
  normalized scenario-impact scale is neither retained nor expanded.
- Traversal is capped at ``MAX_HOPS = 3`` (third-order pitch, `RW-FR-017`).
- Paths are **simple**: a path that would revisit any node is rejected before
  contributing, which is the ADR-001 cycle strategy — no double counting.

Node aggregation (`RW-ALG-006`):

    raw_node_impact = fsum(retained incoming path contributions)
    risk_score      = 100 * (1 - exp(-abs(raw_node_impact)))

``risk_score`` is bounded to ``[0, 100]``
(asymptotic in exact arithmetic; 100.0 is reached in floats only when
``exp(-|raw|)`` underflows) and is a display/ranking score only —
not a probability. The signed per-path contributions are kept on the result so
the evidence panel can decompose any score exactly (`RW-FR-018`).

The engine is a pure function of (snapshot, scenario): no randomness, no clock,
no I/O. The scenario ``seed`` is carried through to the result for the
reproducibility bundle (RW-GOAL-006) but is never consumed — identical inputs
are bit-identical by construction, seed or not.

If this implementation ever needs to diverge from ADR-001, update the ADR
first; do not change constants or semantics here silently.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .graph import GraphEdge, GraphSnapshot

ENGINE_VERSION = "1.0.0"

DAMPING = 0.60
FLOOR = 0.005
MAX_HOPS = 3


class ScenarioError(ValueError):
    """Raised when a scenario is malformed or references unknown nodes."""


@dataclass(frozen=True)
class ShockFactor:
    """One shock factor: an origin node and a signed, normalized magnitude."""

    factor_id: str
    node_id: str
    magnitude: float

    def __post_init__(self) -> None:
        for attr in ("factor_id", "node_id"):
            value = getattr(self, attr)
            if not isinstance(value, str) or not value.strip():
                raise ScenarioError(f"ShockFactor.{attr} must be a non-empty string")
        magnitude = self.magnitude
        if not isinstance(magnitude, (int, float)) or isinstance(magnitude, bool):
            raise ScenarioError("magnitude must be a real number")
        if math.isnan(magnitude) or math.isinf(magnitude):
            raise ScenarioError("magnitude must be finite")


@dataclass(frozen=True)
class Scenario:
    """A validated scenario: one or more simultaneous shock factors (`RW-FR-006`)."""

    scenario_id: str
    factors: tuple[ShockFactor, ...]
    seed: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise ScenarioError("scenario_id must be a non-empty string")
        if not self.factors:
            raise ScenarioError("a scenario needs at least one shock factor")
        factor_ids = [factor.factor_id for factor in self.factors]
        if len(set(factor_ids)) != len(factor_ids):
            raise ScenarioError("factor ids must be unique within a scenario")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ScenarioError("seed must be an integer")


@dataclass(frozen=True)
class PathContribution:
    """One retained simple path and its signed contribution.

    ``edges`` carries the full :class:`GraphEdge` objects, so weights, method
    ids, and provenance refs are available per hop for the evidence panel
    (`RW-ALG-004`). ``path_key`` is the ADR-001 stable key.
    """

    path_key: str
    factor_id: str
    target_node_id: str
    edges: tuple[GraphEdge, ...]
    hop_count: int
    contribution: float


@dataclass(frozen=True)
class NodeImpact:
    """Bounded, decomposable impact on one node (`RW-ALG-006`).

    ``contributions`` are ranked by absolute contribution (then path key), and
    ``raw_impact`` is exactly their float sum — the decomposition test holds to
    float precision because aggregation uses ``math.fsum`` over a canonical
    (path-key-sorted) order.
    """

    node_id: str
    raw_impact: float
    risk_score: float
    contributions: tuple[PathContribution, ...]


@dataclass(frozen=True)
class PropagationResult:
    """Full result of one propagation run, reproducibility metadata included."""

    engine_version: str
    snapshot_id: str
    graph_version: str
    scenario_id: str
    seed: int
    damping: float
    floor: float
    max_hops: int
    impacts: Mapping[str, NodeImpact]

    def ranked_entities(self) -> tuple[NodeImpact, ...]:
        """Impacted nodes, highest risk score first; node id breaks ties (`RW-FR-018`)."""
        return tuple(sorted(self.impacts.values(), key=lambda ni: (-ni.risk_score, ni.node_id)))


def _path_key(scenario_id: str, factor_id: str, edges: tuple[GraphEdge, ...]) -> str:
    edge_sequence = ">".join(edge.edge_id for edge in edges)
    return f"{scenario_id}|{factor_id}|{edge_sequence}|{edges[-1].target_id}"


def _expand_factor(
    snapshot: GraphSnapshot,
    scenario_id: str,
    factor: ShockFactor,
    retained: list[PathContribution],
) -> None:
    """Depth-first expansion of all retained simple paths from one factor origin.

    Iterative DFS with an explicit stack; adjacency is pre-sorted by edge id, so
    the retained order is deterministic.
    """
    # Stack entries: (current node, edges so far, visited node set, running weight product)
    stack: list[tuple[str, tuple[GraphEdge, ...], frozenset[str], float]] = [
        (factor.node_id, (), frozenset({factor.node_id}), 1.0)
    ]
    while stack:
        node_id, edges_so_far, visited, weight_product = stack.pop()
        hops = len(edges_so_far) + 1
        # LIFO reversal keeps expansion in edge_id order for identical results
        # across runs; correctness does not depend on it, reproducibility does.
        for edge in reversed(snapshot.outgoing(node_id)):
            if edge.target_id in visited:
                continue  # ADR-001 cycle strategy: simple paths only.
            product = weight_product * edge.weight
            contribution = factor.magnitude * product * DAMPING ** (hops - 1)
            if abs(contribution) < FLOOR:
                continue  # Below floor: not retained, not expanded.
            path_edges = edges_so_far + (edge,)
            retained.append(
                PathContribution(
                    path_key=_path_key(scenario_id, factor.factor_id, path_edges),
                    factor_id=factor.factor_id,
                    target_node_id=edge.target_id,
                    edges=path_edges,
                    hop_count=hops,
                    contribution=contribution,
                )
            )
            if hops < MAX_HOPS:
                stack.append((edge.target_id, path_edges, visited | {edge.target_id}, product))


def propagate(snapshot: GraphSnapshot, scenario: Scenario) -> PropagationResult:
    """Run the ADR-001 propagation of ``scenario`` over ``snapshot``.

    Pure and deterministic: identical (snapshot, scenario) inputs produce a
    bit-identical result.
    """
    for factor in scenario.factors:
        if not snapshot.has_node(factor.node_id):
            raise ScenarioError(
                f"factor {factor.factor_id!r} shocks unknown node {factor.node_id!r}"
            )

    retained: list[PathContribution] = []
    for factor in scenario.factors:
        _expand_factor(snapshot, scenario.scenario_id, factor, retained)

    by_node: dict[str, list[PathContribution]] = {}
    for contribution in retained:
        by_node.setdefault(contribution.target_node_id, []).append(contribution)

    impacts: dict[str, NodeImpact] = {}
    for node_id in sorted(by_node):
        contributions = by_node[node_id]
        # Canonical fsum order (path key) makes the aggregate independent of
        # traversal implementation details.
        raw_impact = math.fsum(
            c.contribution for c in sorted(contributions, key=lambda c: c.path_key)
        )
        ranked = tuple(sorted(contributions, key=lambda c: (-abs(c.contribution), c.path_key)))
        impacts[node_id] = NodeImpact(
            node_id=node_id,
            raw_impact=raw_impact,
            risk_score=100.0 * (1.0 - math.exp(-abs(raw_impact))),
            contributions=ranked,
        )

    return PropagationResult(
        engine_version=ENGINE_VERSION,
        snapshot_id=snapshot.snapshot_id,
        graph_version=snapshot.graph_version,
        scenario_id=scenario.scenario_id,
        seed=scenario.seed,
        damping=DAMPING,
        floor=FLOOR,
        max_hops=MAX_HOPS,
        impacts=MappingProxyType(impacts),
    )
