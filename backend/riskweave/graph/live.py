"""Assemble the *live* knowledge graph from real extraction output (RIS-28).

This is the module that finally connects the four already-built, already-merged
components — Gemini extraction (RIS-10), layered entity resolution (RIS-11),
deterministic weight derivation (RIS-9), and graph assembly (RIS-12) — into one
pipeline over a real ingestion snapshot, replacing the hand-authored demo
fixture (RIS-12's reduced scope) that ``/graph/seed`` serves today.

Pipeline, per resolved relationship row:

1. **Resolve** the ``source_entity`` / ``target_entity`` mention strings to
   curated-universe ids via the RIS-11 :class:`~riskweave.entity_resolution.Resolver`
   (deterministic identifiers first, Gemini only for ambiguous residuals). A
   relationship whose endpoints do not both resolve is *dropped with a recorded
   reason* — never guessed into existence.
2. **Turn the disclosed sentence into a number deterministically.** Gemini
   captured a verbatim ``disclosed_magnitude`` phrase; the RIS-9
   :func:`~riskweave.derivations.parse_disclosed_magnitude` parser — never the
   model — converts it to a fraction, and
   :func:`~riskweave.derivations.der_concentration_disclosed` records it as a
   registered ``DER-CONCENTRATION`` weight (`RW-AI-010`, `RW-ALG-001`). A row
   with no parseable magnitude yields no edge (`RW-PRIN-008`): no fabricated
   numbers.
3. **Provenance is mandatory and comes straight from the extraction row** —
   source document id, verbatim passage, absolute character offsets, filing
   date, data timestamp, extraction confidence — so every *generated* edge
   carries the same full Graft 2 provenance the fixture edges do (`RW-ALG-032`).
   The :class:`~riskweave.derivations.Provenance` /
   :class:`~riskweave.derivations.WeightRecord` types make an under-provenanced
   edge unconstructible; this module never bypasses them.
4. **Assemble** the survivors through the same
   :func:`~riskweave.graph.assemble` write gate as the fixture path, bound to
   the ingestion snapshot id + a graph version (`RW-FR-015`).

The relationship's economic category (``creditor``, ``geographic_exposure``,
``supplier`` …) is preserved verbatim as the edge ``relationship_type``; the
``method_id`` records *how the number was sourced* (a validated disclosed
fraction), which is ``DER-CONCENTRATION`` for every disclosed-percentage
relationship. Numerator/denominator XBRL-derived variants (DER-CREDIT / DER-GEO
/ DER-COMMODITY share, and the DER-BETA / DER-DURATION series methods) are
already unit-tested in RIS-9 and activate once the XBRL/FRED numeric joins are
wired — see ``docs/live-pipeline.md``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from riskweave.derivations import (
    MagnitudeParseError,
    ProvenanceError,
    der_concentration_disclosed,
    parse_disclosed_magnitude,
)
from riskweave.derivations.provenance import Provenance
from riskweave.entity_resolution import Resolver

from .assembly import AssembledGraph, GraphAssemblyError, ProposedEdge, UniverseEntity, assemble

#: Weight *sourcing* is fixed (CLAUDE.md): a disclosed-percentage relationship
#: is a validated disclosed concentration fraction, so every live edge derived
#: from a ``disclosed_magnitude`` uses the registered ``DER-CONCENTRATION``
#: method. The economic flavor lives on the edge's ``relationship_type``.
DISCLOSED_FRACTION_METHOD = "DER-CONCENTRATION"

#: Preferred seed-node entity types for the default demo scenario (a shock
#: enters the exposure web at a sector/macro/commodity origin and cascades out).
_SEED_NODE_TYPES = ("sector", "macro_factor", "commodity", "geography")
_DEFAULT_SEED_MAGNITUDES = (1.0, 0.8, 0.6)


@dataclass(frozen=True)
class ExtractedRelationship:
    """One RIS-10 relationship extraction, decoupled from the ORM row.

    Carries exactly the fields the live builder needs; the CLI maps a
    ``RelationshipExtraction`` + its ``Document`` onto this so the pure builder
    stays free of SQLAlchemy and is trivially testable.
    """

    source_entity: str
    target_entity: str
    relationship_type: str
    direction: str
    disclosed_magnitude: str | None
    source_passage: str
    source_document_id: str
    char_start: int
    char_end: int
    extraction_confidence: float
    filing_date: date
    data_timestamp: datetime

    def sort_key(self) -> tuple:
        """Stable ordering so the build is deterministic regardless of DB order."""
        return (
            self.source_document_id,
            self.char_start,
            self.char_end,
            self.source_entity,
            self.target_entity,
            self.relationship_type,
        )


@dataclass(frozen=True)
class DroppedRelationship:
    """A relationship that could not become an edge, with an auditable reason."""

    source_entity: str
    target_entity: str
    relationship_type: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class LiveBuildReport:
    """Post-build audit of the live assembly (feeds docs + the eval dashboard)."""

    relationships_seen: int
    edges_built: int
    entities_covered: tuple[str, ...]
    resolution_layers: Mapping[str, int]
    drops_by_reason: Mapping[str, int]
    dropped: tuple[DroppedRelationship, ...] = field(default_factory=tuple)

    @property
    def entity_coverage(self) -> int:
        return len(self.entities_covered)


@dataclass(frozen=True)
class LiveBuildResult:
    """The assembled live graph plus its build report and default seed factors."""

    graph: AssembledGraph
    report: LiveBuildReport
    default_factors: tuple[tuple[str, str, float], ...]


def build_live_graph(
    relationships: Iterable[ExtractedRelationship],
    resolver: Resolver,
    universe_entities: Sequence[UniverseEntity],
    *,
    snapshot_id: str,
    graph_version: str,
) -> LiveBuildResult:
    """Resolve, derive, and assemble real extraction rows into a live graph.

    ``resolver`` and ``universe_entities`` are both built from the same curated
    universe file so a resolved id is always assemblable. The build is
    deterministic: identical inputs give an identical checksum, no seed
    required.
    """
    universe_by_id = {entity.entity_id: entity for entity in universe_entities}

    ordered = sorted(relationships, key=ExtractedRelationship.sort_key)
    edges: list[ProposedEdge] = []
    covered: set[str] = set()
    layers: dict[str, int] = {}
    drops_by_reason: dict[str, int] = {}
    dropped: list[DroppedRelationship] = []
    seen_edge_ids: set[str] = set()

    def _drop(rel: ExtractedRelationship, reason: str, detail: str = "") -> None:
        drops_by_reason[reason] = drops_by_reason.get(reason, 0) + 1
        dropped.append(
            DroppedRelationship(
                source_entity=rel.source_entity,
                target_entity=rel.target_entity,
                relationship_type=rel.relationship_type,
                reason=reason,
                detail=detail,
            )
        )

    for rel in ordered:
        source = resolver.resolve(rel.source_entity)
        target = resolver.resolve(rel.target_entity)
        if source.entity_id is None or target.entity_id is None:
            unresolved = rel.source_entity if source.entity_id is None else rel.target_entity
            _drop(rel, "unresolved_endpoint", unresolved)
            continue
        if source.layer is not None:
            layers[source.layer] = layers.get(source.layer, 0) + 1
        if target.layer is not None:
            layers[target.layer] = layers.get(target.layer, 0) + 1

        if source.entity_id == target.entity_id:
            _drop(rel, "self_loop", source.entity_id)
            continue
        if source.entity_id not in universe_by_id or target.entity_id not in universe_by_id:
            _drop(rel, "endpoint_outside_universe")
            continue

        if rel.disclosed_magnitude is None or not rel.disclosed_magnitude.strip():
            _drop(rel, "no_disclosed_magnitude")
            continue
        try:
            parsed = parse_disclosed_magnitude(rel.disclosed_magnitude)
        except MagnitudeParseError as exc:
            _drop(rel, "unparseable_magnitude", str(exc))
            continue

        try:
            provenance = Provenance(
                source_document_id=rel.source_document_id,
                filing_date=rel.filing_date,
                source_passage=rel.source_passage,
                char_start=rel.char_start,
                char_end=rel.char_end,
                data_timestamp=rel.data_timestamp,
                extraction_confidence=rel.extraction_confidence,
            )
            record = der_concentration_disclosed(parsed.value, provenance)
            edge = ProposedEdge(
                source_id=source.entity_id,
                target_id=target.entity_id,
                relationship_type=rel.relationship_type,
                direction=rel.direction,
                record=record,
            )
        except (ProvenanceError, GraphAssemblyError, ValueError) as exc:
            _drop(rel, "invalid_edge", str(exc))
            continue

        if edge.edge_id in seen_edge_ids:
            _drop(rel, "duplicate_evidence_span", edge.edge_id)
            continue
        seen_edge_ids.add(edge.edge_id)
        edges.append(edge)
        covered.add(source.entity_id)
        covered.add(target.entity_id)

    # Assemble only the entities that participate in at least one edge, so the
    # live graph is the real exposure web rather than 125 mostly-orphan nodes.
    entities = tuple(universe_by_id[eid] for eid in sorted(covered) if eid in universe_by_id)
    graph = assemble(snapshot_id, graph_version, entities, edges)

    report = LiveBuildReport(
        relationships_seen=len(ordered),
        edges_built=len(edges),
        entities_covered=tuple(sorted(covered)),
        resolution_layers=dict(sorted(layers.items())),
        drops_by_reason=dict(sorted(drops_by_reason.items())),
        dropped=tuple(dropped),
    )
    factors = _default_factors(graph)
    return LiveBuildResult(graph=graph, report=report, default_factors=factors)


def graph_to_artifact(
    result: LiveBuildResult,
    *,
    note: str = "",
) -> dict:
    """Serialize a built live graph into the committed artifact schema.

    The schema is a superset of the fixture schema (RIS-12), so the same
    :func:`~riskweave.graph.load_graph_fixture` loader re-assembles it — through
    the Graft 2 write gate again — on the server. ``factors`` and ``report`` are
    extra keys the fixture loader ignores but the ``/graph/live`` endpoint reads
    for a runnable default scenario and the honesty page.
    """
    graph = result.graph
    nodes = [
        {
            "id": entity.entity_id,
            "canonical_name": entity.canonical_name,
            "entity_type": entity.entity_type,
            "packs": list(entity.packs),
        }
        for entity in graph.entities
    ]
    edges = []
    for edge in graph.edges:
        prov = edge.record.provenance
        edges.append(
            {
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "relationship_type": edge.relationship_type,
                "direction": edge.direction,
                "weight": {
                    "value": edge.record.value,
                    "method_id": edge.record.method_id,
                    "method_version": edge.record.method_version,
                    "inputs": dict(edge.record.inputs),
                    "data_timestamps": [ts.isoformat() for ts in edge.record.data_timestamps],
                    "provenance": {
                        "source_document_id": prov.source_document_id,
                        "filing_date": prov.filing_date.isoformat(),
                        "source_passage": prov.source_passage,
                        "char_start": prov.char_start,
                        "data_timestamp": prov.data_timestamp.isoformat(),
                        "extraction_confidence": prov.extraction_confidence,
                    },
                },
            }
        )
    return {
        "snapshot_id": graph.snapshot_id,
        "graph_version": graph.graph_version,
        "note": note,
        "checksum": graph.checksum,
        "factors": [
            {"factor_id": fid, "node_id": nid, "magnitude": mag}
            for fid, nid, mag in result.default_factors
        ],
        "report": {
            "relationships_seen": result.report.relationships_seen,
            "edges_built": result.report.edges_built,
            "entity_coverage": result.report.entity_coverage,
            "resolution_layers": dict(result.report.resolution_layers),
            "drops_by_reason": dict(result.report.drops_by_reason),
        },
        "nodes": nodes,
        "edges": edges,
    }


def _default_factors(graph: AssembledGraph) -> tuple[tuple[str, str, float], ...]:
    """Pick runnable default shock origins for the live demo scenario.

    Prefers sector/macro/commodity/geography origins that actually anchor edges;
    falls back to the highest-centrality endpoints. Guarantees every returned
    node id exists in the graph so the scenario is immediately runnable and the
    WebSocket slider round-trips (RIS-28 acceptance).
    """
    endpoints = {e.source_id for e in graph.edges} | {e.target_id for e in graph.edges}
    if not endpoints:
        return ()
    preferred = [
        e.entity_id
        for e in graph.entities
        if e.entity_id in endpoints and e.entity_type in _SEED_NODE_TYPES
    ]
    ranked = sorted(endpoints, key=lambda nid: (-graph.centrality.get(nid, 0.0), nid))
    ordering = list(dict.fromkeys([*preferred, *ranked]))
    chosen = ordering[: len(_DEFAULT_SEED_MAGNITUDES)]
    return tuple(
        (f"{node_id}-shock", node_id, magnitude)
        for node_id, magnitude in zip(chosen, _DEFAULT_SEED_MAGNITUDES, strict=False)
    )
