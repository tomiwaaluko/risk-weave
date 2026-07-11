"""In-memory graph snapshot the propagation engine runs on.

The engine never touches Neo4j (`RW-NFR-002`): the graph is loaded once per
scenario into this immutable snapshot, and every slider recompute runs against
it in memory. Assembly from stored edges is RIS-12's job; this module only
defines the contract.

Graft 2 holds here too: a :class:`GraphEdge` cannot be constructed without a
method id and a provenance reference, so a snapshot containing an
un-provenanced edge is unrepresentable (`RW-ALG-032`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


class SnapshotError(ValueError):
    """Raised when a snapshot or one of its elements is malformed."""


@dataclass(frozen=True)
class GraphNode:
    """A typed node: company, bank, REIT, security, commodity, geography, sector."""

    node_id: str
    node_type: str
    name: str

    def __post_init__(self) -> None:
        for attr in ("node_id", "node_type", "name"):
            value = getattr(self, attr)
            if not isinstance(value, str) or not value.strip():
                raise SnapshotError(f"GraphNode.{attr} must be a non-empty string")


@dataclass(frozen=True)
class GraphEdge:
    """A directed, weighted edge with its derivation method and evidence ref.

    ``weight`` is the deterministic §12.1 derivation output; ``method_id`` and
    ``provenance_ref`` are mandatory so path decomposition can surface the
    derivation and evidence for every hop (`RW-ALG-004`).
    """

    edge_id: str
    source_id: str
    target_id: str
    weight: float
    method_id: str
    provenance_ref: str

    def __post_init__(self) -> None:
        for attr in ("edge_id", "source_id", "target_id", "method_id", "provenance_ref"):
            value = getattr(self, attr)
            if not isinstance(value, str) or not value.strip():
                raise SnapshotError(f"GraphEdge.{attr} must be a non-empty string")
        if self.source_id == self.target_id:
            raise SnapshotError(f"edge {self.edge_id!r} is a self-loop, which is prohibited")
        weight = self.weight
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            raise SnapshotError(f"edge {self.edge_id!r} weight must be a real number")
        if math.isnan(weight) or math.isinf(weight):
            raise SnapshotError(f"edge {self.edge_id!r} weight must be finite")


@dataclass(frozen=True)
class GraphSnapshot:
    """An immutable graph bound to a snapshot id + version (`RW-FR-015`).

    Adjacency is precomputed at construction, with outgoing edges sorted by
    ``edge_id`` so traversal order — and therefore output — is deterministic.
    """

    snapshot_id: str
    graph_version: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    _adjacency: Mapping[str, tuple[GraphEdge, ...]] = field(init=False, repr=False, compare=False)
    _node_ids: frozenset[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for attr in ("snapshot_id", "graph_version"):
            value = getattr(self, attr)
            if not isinstance(value, str) or not value.strip():
                raise SnapshotError(f"GraphSnapshot.{attr} must be a non-empty string")

        node_ids = [node.node_id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise SnapshotError("duplicate node ids in snapshot")
        known = set(node_ids)

        edge_ids = [edge.edge_id for edge in self.edges]
        if len(set(edge_ids)) != len(edge_ids):
            raise SnapshotError("duplicate edge ids in snapshot")
        adjacency: dict[str, list[GraphEdge]] = {}
        for edge in self.edges:
            if edge.source_id not in known or edge.target_id not in known:
                raise SnapshotError(f"edge {edge.edge_id!r} references a node not in the snapshot")
            adjacency.setdefault(edge.source_id, []).append(edge)

        frozen = {
            source: tuple(sorted(out, key=lambda e: e.edge_id)) for source, out in adjacency.items()
        }
        object.__setattr__(self, "_adjacency", MappingProxyType(frozen))
        object.__setattr__(self, "_node_ids", frozenset(known))

    def outgoing(self, node_id: str) -> tuple[GraphEdge, ...]:
        """Outgoing edges of ``node_id``, in deterministic (edge_id) order."""
        return self._adjacency.get(node_id, ())

    def has_node(self, node_id: str) -> bool:
        return node_id in self._node_ids
