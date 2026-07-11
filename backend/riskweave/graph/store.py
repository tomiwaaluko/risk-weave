"""Neo4j read/write for the assembled knowledge graph (RIS-12, reduced scope).

Two responsibilities:

* :meth:`Neo4jGraphStore.seed` writes an :class:`~riskweave.graph.AssembledGraph`
  into a single local Neo4j instance. The write is a **drop-then-reload** inside
  one transaction, so re-running the seed reproduces the exact same graph
  (`RW-FR-015`) — the acceptance criterion for the demo. Every edge is written
  with its complete provenance fields (doc id, quoted passage, char offsets,
  filing date, data timestamp, derivation method + version, confidence); there
  is no code path that writes an edge without them, because the source
  ``AssembledGraph`` cannot contain one (Graft 2, `RW-ALG-032`).

* :meth:`Neo4jGraphStore.read_snapshot` is the read API the propagation engine
  consumes: adjacency + signed weights + provenance refs as an immutable
  :class:`~riskweave.propagation.GraphSnapshot`, optionally filtered to one
  scenario pack (CRE is primary).

The ``neo4j`` driver is imported lazily so the rest of the package — the
fixture loader, the Graft 2 gate, the propagation round-trip — imports and
tests cleanly without the driver or a running database present.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from riskweave.propagation import GraphEdge, GraphNode, GraphSnapshot

from .assembly import AssembledGraph

NODE_LABEL = "RiskWeaveNode"
META_LABEL = "RiskWeaveGraphMeta"
EDGE_TYPE = "EXPOSED_TO"


class Neo4jUnavailableError(RuntimeError):
    """Raised when the ``neo4j`` driver is not installed."""


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
    """Flatten each assembled edge into a Neo4j-writable property map."""
    rows: list[dict[str, Any]] = []
    for edge in graph.edges:
        prov = edge.record.provenance
        rows.append(
            {
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
        )
    return rows


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
