"""Knowledge-graph assembly with the Graft 2 write gate (RIS-12).

Assembles resolved entities + derived weights into a typed, weighted,
provenanced graph (`RW-FR-016`), keyed to a snapshot id + graph version
(`RW-FR-015`, RW-GOAL-006).

**The write gate is structural.** A :class:`ProposedEdge` accepts its weight
only as a :class:`~riskweave.derivations.WeightRecord` — there is no parameter
that takes a raw float — and a ``WeightRecord`` is itself unconstructible
without a validated ``Provenance``. An edge that lacks any provenance field is
rejected at construction, not stored (`RW-ALG-032`): if an edge has no
provenance, the edge does not exist.

Weight sign convention: the engine edge weight is ``record.value`` for
``direction="positive"`` and ``-record.value`` for ``direction="negative"``,
matching the DER-DURATION rate-transmission convention (RIS-17).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from riskweave.derivations import UnknownMethodError, WeightRecord, get_method
from riskweave.propagation import GraphEdge, GraphNode, GraphSnapshot

from .centrality import transmission_centrality

DIRECTIONS = ("positive", "negative")


class GraphAssemblyError(ValueError):
    """Raised when an entity or edge fails write-time validation."""


@dataclass(frozen=True)
class UniverseEntity:
    """A resolved entity from the curated universe file (`RW-SCOPE-001`)."""

    entity_id: str
    canonical_name: str
    entity_type: str
    packs: tuple[str, ...]

    def __post_init__(self) -> None:
        for attr in ("entity_id", "canonical_name", "entity_type"):
            value = getattr(self, attr)
            if not isinstance(value, str) or not value.strip():
                raise GraphAssemblyError(f"UniverseEntity.{attr} must be a non-empty string")
        if not isinstance(self.packs, tuple) or not all(
            isinstance(p, str) and p.strip() for p in self.packs
        ):
            raise GraphAssemblyError("UniverseEntity.packs must be a tuple of pack names")

    @classmethod
    def from_universe_record(cls, record: Mapping) -> UniverseEntity:
        """Build from one ``data/universe/entities.json`` entity record."""
        return cls(
            entity_id=record["id"],
            canonical_name=record["canonical_name"],
            entity_type=record["entity_type"],
            packs=tuple(record.get("packs", ())),
        )


def load_universe(path: str) -> tuple[UniverseEntity, ...]:
    """Load the curated universe file into entities, preserving file order."""
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return tuple(UniverseEntity.from_universe_record(rec) for rec in payload["entities"])


@dataclass(frozen=True)
class ProposedEdge:
    """A candidate graph edge whose weight can only come from a WeightRecord.

    This is the API that makes writing a raw float impossible: ``record`` is
    type-checked to be a ``WeightRecord`` (which itself cannot exist without
    complete provenance), and the derivation method must be registered
    (`RW-ALG-001/004`).
    """

    source_id: str
    target_id: str
    relationship_type: str
    direction: str
    record: WeightRecord

    def __post_init__(self) -> None:
        for attr in ("source_id", "target_id", "relationship_type"):
            value = getattr(self, attr)
            if not isinstance(value, str) or not value.strip():
                raise GraphAssemblyError(f"ProposedEdge.{attr} must be a non-empty string")
        if self.source_id == self.target_id:
            raise GraphAssemblyError("self-loops are prohibited")
        if self.direction not in DIRECTIONS:
            raise GraphAssemblyError(
                f"direction must be one of {DIRECTIONS}, got {self.direction!r}"
            )
        if not isinstance(self.record, WeightRecord):
            raise GraphAssemblyError(
                "edge weight must be a WeightRecord — a raw number is not writable "
                "(Graft 2: no edge without provenance)"
            )
        try:
            get_method(self.record.method_id)
        except UnknownMethodError as exc:
            raise GraphAssemblyError(str(exc)) from exc

    @property
    def edge_id(self) -> str:
        """Deterministic id from the edge identity and its evidence span."""
        prov = self.record.provenance
        material = "|".join(
            (
                self.source_id,
                self.target_id,
                self.relationship_type,
                self.record.method_id,
                prov.source_document_id,
                str(prov.char_start),
                str(prov.char_end),
            )
        )
        return "edge:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    @property
    def signed_weight(self) -> float:
        return self.record.value if self.direction == "positive" else -self.record.value

    @property
    def provenance_ref(self) -> str:
        prov = self.record.provenance
        return f"{prov.source_document_id}#{prov.char_start}-{prov.char_end}"


@dataclass(frozen=True)
class AssembledGraph:
    """An assembled, validated graph bound to snapshot id + version."""

    snapshot_id: str
    graph_version: str
    entities: tuple[UniverseEntity, ...]
    edges: tuple[ProposedEdge, ...]
    centrality: Mapping[str, float] = field(init=False, compare=False)
    checksum: str = field(init=False, compare=False)

    def __post_init__(self) -> None:
        for attr in ("snapshot_id", "graph_version"):
            value = getattr(self, attr)
            if not isinstance(value, str) or not value.strip():
                raise GraphAssemblyError(f"AssembledGraph.{attr} must be a non-empty string")
        ids = [entity.entity_id for entity in self.entities]
        known = set(ids)
        if len(known) != len(ids):
            raise GraphAssemblyError("duplicate entity ids in universe input")
        edge_ids: set[str] = set()
        for edge in self.edges:
            if edge.source_id not in known or edge.target_id not in known:
                raise GraphAssemblyError(
                    f"edge {edge.source_id}->{edge.target_id} references an entity "
                    "outside the curated universe"
                )
            if edge.edge_id in edge_ids:
                raise GraphAssemblyError(
                    f"duplicate edge (same endpoints, type, method, and evidence span): "
                    f"{edge.edge_id}"
                )
            edge_ids.add(edge.edge_id)
        object.__setattr__(
            self,
            "centrality",
            transmission_centrality(
                node_ids=tuple(sorted(known)),
                arcs=tuple((e.source_id, e.target_id, abs(e.signed_weight)) for e in self.edges),
            ),
        )
        object.__setattr__(self, "checksum", self._compute_checksum())

    def _compute_checksum(self) -> str:
        """SHA-256 over a canonical serialization — the idempotency witness."""
        canonical = {
            "snapshot_id": self.snapshot_id,
            "graph_version": self.graph_version,
            "nodes": [
                {
                    "id": e.entity_id,
                    "name": e.canonical_name,
                    "type": e.entity_type,
                    "packs": sorted(e.packs),
                    "centrality": f"{self.centrality[e.entity_id]:.15e}",
                }
                for e in sorted(self.entities, key=lambda e: e.entity_id)
            ],
            "edges": [
                {
                    "id": edge.edge_id,
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "type": edge.relationship_type,
                    "direction": edge.direction,
                    "weight": f"{edge.signed_weight:.15e}",
                    "method_id": edge.record.method_id,
                    "method_version": edge.record.method_version,
                    "provenance_ref": edge.provenance_ref,
                    "filing_date": edge.record.provenance.filing_date.isoformat(),
                    "data_timestamps": [ts.isoformat() for ts in edge.record.data_timestamps],
                    "extraction_confidence": edge.record.provenance.extraction_confidence,
                }
                for edge in sorted(self.edges, key=lambda e: e.edge_id)
            ],
        }
        blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------ #
    # Read API for the propagation engine                                  #
    # ------------------------------------------------------------------ #
    def to_snapshot(self, pack: str | None = None) -> GraphSnapshot:
        """Engine-ready snapshot; optionally restricted to one scenario pack.

        Pack filtering keeps a node when it belongs to ``pack`` and an edge
        when both endpoints survive.
        """
        entities = self.entities
        if pack is not None:
            entities = tuple(e for e in entities if pack in e.packs)
            if not entities:
                raise GraphAssemblyError(f"no entities in pack {pack!r}")
        kept = {e.entity_id for e in entities}
        nodes = tuple(
            GraphNode(node_id=e.entity_id, node_type=e.entity_type, name=e.canonical_name)
            for e in entities
        )
        edges = tuple(
            GraphEdge(
                edge_id=edge.edge_id,
                source_id=edge.source_id,
                target_id=edge.target_id,
                weight=edge.signed_weight,
                method_id=edge.record.method_id,
                provenance_ref=edge.provenance_ref,
            )
            for edge in self.edges
            if edge.source_id in kept and edge.target_id in kept
        )
        return GraphSnapshot(
            snapshot_id=self.snapshot_id,
            graph_version=self.graph_version,
            nodes=nodes,
            edges=edges,
        )

    # ------------------------------------------------------------------ #
    # Post-assembly report                                                 #
    # ------------------------------------------------------------------ #
    def provenance_coverage(self) -> float:
        """Fraction of edges whose provenance is complete.

        By construction this is 1.0 — the write gate makes anything else
        unrepresentable — but the report *measures* it rather than asserting
        it, so a regression in the gate would surface here (and in tests).
        """
        if not self.edges:
            return 1.0
        complete = 0
        for edge in self.edges:
            prov = edge.record.provenance
            if (
                prov.source_document_id.strip()
                and prov.source_passage.strip()
                and prov.char_end > prov.char_start
                and edge.record.method_id.strip()
                and edge.record.data_timestamps
                and not math.isnan(prov.extraction_confidence)
            ):
                complete += 1
        return complete / len(self.edges)

    def stats_report(self) -> str:
        """Human-readable post-assembly report (ticket acceptance output)."""
        node_counts: dict[str, int] = {}
        pack_counts: dict[str, int] = {}
        for entity in self.entities:
            node_counts[entity.entity_type] = node_counts.get(entity.entity_type, 0) + 1
            for pack in entity.packs:
                pack_counts[pack] = pack_counts.get(pack, 0) + 1
        edge_counts: dict[str, int] = {}
        method_counts: dict[str, int] = {}
        linked: set[str] = set()
        for edge in self.edges:
            edge_counts[edge.relationship_type] = edge_counts.get(edge.relationship_type, 0) + 1
            method_counts[edge.record.method_id] = method_counts.get(edge.record.method_id, 0) + 1
            linked.add(edge.source_id)
            linked.add(edge.target_id)
        orphans = sorted(e.entity_id for e in self.entities if e.entity_id not in linked)

        lines = [
            f"graph {self.snapshot_id} v{self.graph_version} checksum={self.checksum[:12]}",
            f"nodes: {len(self.entities)} "
            + ", ".join(f"{t}={n}" for t, n in sorted(node_counts.items())),
            "packs: " + ", ".join(f"{p}={n}" for p, n in sorted(pack_counts.items())),
            f"edges: {len(self.edges)} "
            + ", ".join(f"{t}={n}" for t, n in sorted(edge_counts.items())),
            "methods: " + ", ".join(f"{m}={n}" for m, n in sorted(method_counts.items())),
            f"provenance coverage: {self.provenance_coverage():.0%}",
            f"orphan nodes: {len(orphans)}" + (f" ({', '.join(orphans)})" if orphans else ""),
        ]
        return "\n".join(lines)


def assemble(
    snapshot_id: str,
    graph_version: str,
    entities: Iterable[UniverseEntity],
    edges: Sequence[ProposedEdge],
) -> AssembledGraph:
    """Assemble and validate the graph. Raises on any Graft 2 violation."""
    return AssembledGraph(
        snapshot_id=snapshot_id,
        graph_version=graph_version,
        entities=tuple(entities),
        edges=tuple(edges),
    )
