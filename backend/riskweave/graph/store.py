"""Neo4j read/write for the assembled knowledge graph (RIS-12).

This is the graph layer's **write gate** — the one place where nodes and edges
become durable — and the propagation engine's read API. Its defining guarantee
is Graft 2 (`RW-ALG-032`, `RW-FR-016`): *an edge that lacks any provenance field
is rejected at write time, not stored.* The gate is enforced twice, on purpose:

* Structurally, upstream: a :class:`~riskweave.graph.ProposedEdge` only accepts a
  :class:`~riskweave.derivations.WeightRecord`, itself unconstructible without a
  complete :class:`~riskweave.derivations.Provenance`.
* Again here, at the write boundary: :func:`validate_edge_row` re-checks every
  Graft 2 field on the flat property map actually handed to Cypher, so a row
  assembled by hand (bypassing ``ProposedEdge``) can never reach the store, and
  a raw-float weight is unstorable (its ``method_id`` must resolve in the
  registered `DER-*` registry).

Responsibilities:

* :meth:`Neo4jGraphStore.seed` writes an :class:`~riskweave.graph.AssembledGraph`
  into Neo4j as a **drop-then-reload** inside one transaction, so re-running the
  seed reproduces the exact same graph (`RW-FR-015`) and a partial seed is never
  observable. Every edge passes :func:`validate_edge_row` first.
* :func:`coverage_report` emits the per-run provenance-coverage report (feeds the
  RIS-21 dashboard); it is 100% by construction because the gate drops anything
  else.
* :meth:`Neo4jGraphStore.read_centrality` exposes structural centrality
  (`RW-FR-019`) on its own, separate from scenario impact.
* :meth:`Neo4jGraphStore.read_snapshot` is the propagation engine's read API:
  adjacency + signed weights + provenance refs as an immutable
  :class:`~riskweave.propagation.GraphSnapshot`, optionally filtered to one
  scenario pack (CRE is primary).

The ``neo4j`` driver is imported lazily so the rest of the package — the fixture
loader, the Graft 2 gate, the coverage report, the propagation round-trip —
imports and tests cleanly without the driver or a running database present.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from riskweave.derivations import UnknownMethodError, get_method
from riskweave.propagation import GraphEdge, GraphNode, GraphSnapshot

from .assembly import AssembledGraph

NODE_LABEL = "RiskWeaveNode"
META_LABEL = "RiskWeaveGraphMeta"
EDGE_TYPE = "EXPOSED_TO"

#: Graft 2 provenance fields that MUST be present on every stored edge.
REQUIRED_EDGE_KEYS: tuple[str, ...] = (
    "edge_id",
    "source_id",
    "target_id",
    "relationship_type",
    "direction",
    "weight",
    "method_id",
    "method_version",
    "provenance_ref",
    "source_document_id",
    "source_passage",
    "char_start",
    "char_end",
    "filing_date",
    "data_timestamp",
    "extraction_confidence",
)


class Neo4jWriteError(ValueError):
    """Raised when an edge fails the write-time gate (Graft 2, `RW-ALG-032`)."""


class Neo4jUnavailableError(RuntimeError):
    """Raised when the ``neo4j`` driver is not installed or no graph is seeded."""


def validate_edge_row(row: Mapping[str, Any]) -> None:
    """Reject any edge property map that violates Graft 2. Raises on failure.

    This is the gate the writer runs on **every** edge before issuing Cypher. It
    re-derives the "no edge without provenance" guarantee at the storage boundary
    so a hand-built row — one that never passed through ``ProposedEdge`` — cannot
    smuggle an un-provenanced or raw-float weight into the database. Raw floats
    are unstorable: an edge is only writable if its ``method_id`` resolves in the
    registered `DER-*` registry (`RW-ALG-001/004`).
    """
    missing = [key for key in REQUIRED_EDGE_KEYS if key not in row]
    if missing:
        raise Neo4jWriteError(
            f"edge missing provenance field(s) {missing}; "
            "no edge without provenance (Graft 2, RW-ALG-032)"
        )

    for key in ("source_document_id", "source_passage", "method_id", "provenance_ref"):
        value = row[key]
        if not isinstance(value, str) or not value.strip():
            raise Neo4jWriteError(f"edge field {key!r} must be a non-empty string")

    try:
        get_method(row["method_id"])
    except UnknownMethodError as exc:
        raise Neo4jWriteError(
            f"edge weight is not from a registered derivation method: {exc}"
        ) from exc

    weight = row["weight"]
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        raise Neo4jWriteError("edge weight must be a real number")
    if math.isnan(weight) or math.isinf(weight):
        raise Neo4jWriteError("edge weight must be finite")

    char_start, char_end = row["char_start"], row["char_end"]
    if not isinstance(char_start, int) or not isinstance(char_end, int):
        raise Neo4jWriteError("character offsets must be integers")
    if char_start < 0 or char_end <= char_start:
        raise Neo4jWriteError("character offsets must satisfy 0 <= char_start < char_end")
    if char_end - char_start != len(row["source_passage"]):
        raise Neo4jWriteError("character offset span does not match the quoted passage length")

    for key in ("filing_date", "data_timestamp"):
        value = row[key]
        if not isinstance(value, str) or not value.strip():
            raise Neo4jWriteError(f"edge field {key!r} must be an ISO-8601 timestamp string")

    conf = row["extraction_confidence"]
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        raise Neo4jWriteError("extraction_confidence must be a real number")
    if math.isnan(conf) or not (0.0 <= conf <= 1.0):
        raise Neo4jWriteError("extraction_confidence must be within [0, 1]")


def _graph_database() -> Any:
    """Import the ``neo4j`` driver lazily, with an actionable error if absent."""
    try:
        from neo4j import GraphDatabase
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised only without the driver
        raise Neo4jUnavailableError(
            "the 'neo4j' driver is required to seed or read the graph store. "
            "Install it with `uv add neo4j` (updates the lock) or `pip install neo4j`."
        ) from exc
    return GraphDatabase


def _edge_properties(graph: AssembledGraph) -> list[dict[str, Any]]:
    """Flatten each assembled edge into a gated, Neo4j-writable property map."""
    rows: list[dict[str, Any]] = []
    for edge in graph.edges:
        prov = edge.record.provenance
        row = {
            "edge_id": edge.edge_id,
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "relationship_type": edge.relationship_type,
            "direction": edge.direction,
            "weight": edge.signed_weight,
            "method_id": edge.record.method_id,
            "method_version": edge.record.method_version,
            "provenance_ref": edge.provenance_ref,
            "source_document_id": prov.source_document_id,
            "source_passage": prov.source_passage,
            "char_start": prov.char_start,
            "char_end": prov.char_end,
            "filing_date": prov.filing_date.isoformat(),
            "data_timestamp": prov.data_timestamp.isoformat(),
            "extraction_confidence": prov.extraction_confidence,
        }
        validate_edge_row(row)  # gate every row before it can be written
        rows.append(row)
    return rows


def coverage_report(graph: AssembledGraph) -> dict[str, Any]:
    """Provenance-coverage report emitted per seed run (feeds the RIS-21 dashboard).

    ``coverage`` is the fraction of stored edges carrying complete provenance —
    1.0 by construction, since :func:`validate_edge_row` gates every row, but
    measured rather than asserted so a regression in the gate surfaces here.
    """
    rows = _edge_properties(graph)
    by_method: dict[str, int] = {}
    for row in rows:
        by_method[row["method_id"]] = by_method.get(row["method_id"], 0) + 1
    return {
        "snapshot_id": graph.snapshot_id,
        "graph_version": graph.graph_version,
        "checksum": graph.checksum,
        "total_edges": len(rows),
        "provenanced_edges": len(rows),  # only provenanced edges survive the gate
        "coverage": graph.provenance_coverage(),
        "edges_by_method": dict(sorted(by_method.items())),
        "node_count": len(graph.entities),
    }


def _node_properties(graph: AssembledGraph) -> list[dict[str, Any]]:
    return [
        {
            "id": entity.entity_id,
            "name": entity.canonical_name,
            "type": entity.entity_type,
            "packs": list(entity.packs),
            "centrality": graph.centrality[entity.entity_id],
        }
        for entity in graph.entities
    ]


class Neo4jGraphStore:
    """Thin wrapper over a Neo4j driver for graph seed + engine read."""

    def __init__(self, driver: Any, database: str | None = None) -> None:
        self._driver = driver
        self._database = database

    # ------------------------------------------------------------------ #
    # Construction / lifecycle                                             #
    # ------------------------------------------------------------------ #
    @classmethod
    def connect(
        cls,
        uri: str,
        user: str,
        password: str,
        database: str | None = None,
    ) -> Neo4jGraphStore:
        driver = _graph_database().driver(uri, auth=(user, password))
        return cls(driver, database=database)

    def close(self) -> None:
        self._driver.close()

    @contextmanager
    def _session(self) -> Iterator[Any]:
        session = (
            self._driver.session(database=self._database)
            if self._database
            else self._driver.session()
        )
        try:
            yield session
        finally:
            session.close()

    # ------------------------------------------------------------------ #
    # Write                                                                #
    # ------------------------------------------------------------------ #
    def seed(self, graph: AssembledGraph) -> dict[str, int]:
        """Drop the existing graph and reload ``graph``. Idempotent.

        Returns a ``{"nodes": n, "edges": m}`` count. The whole operation runs
        in one transaction so a partial seed can never be observed.
        """
        nodes = _node_properties(graph)
        edges = _edge_properties(graph)
        meta = {
            "snapshot_id": graph.snapshot_id,
            "graph_version": graph.graph_version,
            "checksum": graph.checksum,
        }

        def _write(tx: Any) -> None:
            tx.run(f"MATCH (n) WHERE n:{NODE_LABEL} OR n:{META_LABEL} DETACH DELETE n")
            tx.run(
                f"UNWIND $nodes AS n CREATE (:{NODE_LABEL} "
                "{id: n.id, name: n.name, type: n.type, packs: n.packs, "
                "centrality: n.centrality})",
                nodes=nodes,
            )
            tx.run(
                f"UNWIND $edges AS e "
                f"MATCH (s:{NODE_LABEL} {{id: e.source_id}}) "
                f"MATCH (t:{NODE_LABEL} {{id: e.target_id}}) "
                f"CREATE (s)-[r:{EDGE_TYPE}]->(t) SET r = e",
                edges=edges,
            )
            tx.run(f"CREATE (:{META_LABEL} $meta)", meta=meta)

        with self._session() as session:
            session.execute_write(_write)
        return {"nodes": len(nodes), "edges": len(edges)}

    # ------------------------------------------------------------------ #
    # Read (propagation-engine API)                                        #
    # ------------------------------------------------------------------ #
    def read_metadata(self) -> dict[str, Any]:
        with self._session() as session:
            record = session.run(
                f"MATCH (m:{META_LABEL}) RETURN m.snapshot_id AS snapshot_id, "
                "m.graph_version AS graph_version, m.checksum AS checksum"
            ).single()
        if record is None:
            raise Neo4jUnavailableError("no seeded graph found; run the seed first")
        return dict(record)

    def read_nodes(self, pack: str | None = None) -> list[dict[str, Any]]:
        cypher = (
            f"MATCH (n:{NODE_LABEL}) "
            + ("WHERE $pack IN n.packs " if pack is not None else "")
            + "RETURN n.id AS id, n.name AS name, n.type AS type, "
            "n.packs AS packs, n.centrality AS centrality ORDER BY n.id"
        )
        with self._session() as session:
            return [dict(r) for r in session.run(cypher, pack=pack)]

    def read_centrality(self, pack: str | None = None) -> dict[str, float]:
        """Structural centrality per node (`RW-FR-019`), separate from scenario impact.

        Centrality is stored as a node property at seed time and exposed here on
        its own, so the API and UI can distinguish "systemically important in the
        exposure web" from "hit hard by this particular shock".
        """
        return {n["id"]: n["centrality"] for n in self.read_nodes(pack)}

    def read_edges(self, pack: str | None = None) -> list[dict[str, Any]]:
        """Return edge property maps (with full provenance) for surviving nodes.

        An edge survives only when both endpoints survive the pack filter — the
        same rule as :meth:`AssembledGraph.to_snapshot`.
        """
        pack_clause = "WHERE $pack IN s.packs AND $pack IN t.packs " if pack is not None else ""
        cypher = (
            f"MATCH (s:{NODE_LABEL})-[r:{EDGE_TYPE}]->(t:{NODE_LABEL}) "
            + pack_clause
            + "RETURN properties(r) AS props ORDER BY r.edge_id"
        )
        with self._session() as session:
            return [dict(r["props"]) for r in session.run(cypher, pack=pack)]

    def read_snapshot(self, pack: str | None = None) -> GraphSnapshot:
        """Assemble a propagation-ready snapshot from the seeded graph."""
        meta = self.read_metadata()
        nodes = self.read_nodes(pack)
        edges = self.read_edges(pack)
        return _build_snapshot(meta, nodes, edges)


def _build_snapshot(
    meta: Mapping[str, Any],
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> GraphSnapshot:
    graph_nodes = tuple(
        GraphNode(node_id=n["id"], node_type=n["type"], name=n["name"]) for n in nodes
    )
    graph_edges = tuple(
        GraphEdge(
            edge_id=e["edge_id"],
            source_id=e["source_id"],
            target_id=e["target_id"],
            weight=e["weight"],
            method_id=e["method_id"],
            provenance_ref=e["provenance_ref"],
        )
        for e in edges
    )
    return GraphSnapshot(
        snapshot_id=meta["snapshot_id"],
        graph_version=meta["graph_version"],
        nodes=graph_nodes,
        edges=graph_edges,
    )
