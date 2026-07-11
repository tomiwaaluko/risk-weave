"""Neo4j seed/read for the assembled graph (RIS-12).

Split in two:

* Helper tests (``_node_properties`` / ``_edge_properties`` / ``_build_snapshot``)
  run everywhere — they need neither the driver nor a database.
* Integration tests seed a real local Neo4j and read it back; they are skipped
  when the ``neo4j`` driver is absent or no database is reachable, so CI without
  the graph stack stays green while the demo path is still covered locally.
"""

from __future__ import annotations

import os

import pytest

from riskweave.graph import load_graph_fixture
from riskweave.graph.store import (
    _build_snapshot,
    _edge_properties,
    _node_properties,
)
from riskweave.propagation import Scenario, ShockFactor, propagate


@pytest.fixture(scope="module")
def graph():
    return load_graph_fixture()


# --------------------------------------------------------------------------- #
# Driver-free helper tests                                                     #
# --------------------------------------------------------------------------- #
def test_node_properties_include_centrality(graph):
    rows = _node_properties(graph)
    assert len(rows) == len(graph.entities)
    row = rows[0]
    assert set(row) == {"id", "name", "type", "packs", "centrality"}
    assert isinstance(row["packs"], list)


def test_edge_properties_carry_full_provenance(graph):
    rows = _edge_properties(graph)
    assert len(rows) == len(graph.edges)
    required = {
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
    }
    for row in rows:
        assert required <= set(row)
        assert row["char_end"] - row["char_start"] == len(row["source_passage"])


def test_build_snapshot_round_trips_property_maps(graph):
    meta = {"snapshot_id": graph.snapshot_id, "graph_version": graph.graph_version}
    snapshot = _build_snapshot(meta, _node_properties(graph), _edge_properties(graph))
    assert len(snapshot.nodes) == len(graph.entities)
    assert len(snapshot.edges) == len(graph.edges)
    # The reconstructed snapshot is engine-ready.
    result = propagate(
        snapshot,
        Scenario(
            scenario_id="s",
            factors=(ShockFactor(factor_id="f", node_id="cre-office", magnitude=1.0),),
        ),
    )
    assert result.impacts


# --------------------------------------------------------------------------- #
# Integration: real Neo4j (skipped when unavailable)                           #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def store():
    pytest.importorskip("neo4j", reason="neo4j driver not installed")
    from riskweave.graph.store import Neo4jGraphStore

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "change-me-for-local-development")
    database = os.environ.get("NEO4J_DATABASE")

    store = Neo4jGraphStore.connect(uri, user, password, database=database)
    try:
        store._driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001 - any connection failure means skip
        store.close()
        pytest.skip(f"no Neo4j reachable at {uri}: {exc}")
    yield store
    store.close()


def test_seed_then_read_round_trips(store, graph):
    counts = store.seed(graph)
    assert counts == {"nodes": len(graph.entities), "edges": len(graph.edges)}

    snapshot = store.read_snapshot(pack="cre")
    assert len(snapshot.nodes) == len(graph.entities)
    assert len(snapshot.edges) == len(graph.edges)

    result = propagate(
        snapshot,
        Scenario(
            scenario_id="cre-office-decline",
            factors=(ShockFactor(factor_id="office-shock", node_id="cre-office", magnitude=1.0),),
        ),
    )
    assert "slg" in result.impacts


def test_reseed_reproduces_the_same_graph(store, graph):
    store.seed(graph)
    first = store.read_metadata()
    store.seed(graph)  # drop + reload again
    second = store.read_metadata()
    assert first == second
    assert second["checksum"] == graph.checksum


def test_read_edges_all_have_complete_provenance(store, graph):
    store.seed(graph)
    edges = store.read_edges(pack="cre")
    assert len(edges) == len(graph.edges)
    for edge in edges:
        assert edge["source_document_id"].strip()
        assert edge["source_passage"].strip()
        assert edge["char_end"] - edge["char_start"] == len(edge["source_passage"])
        assert 0.0 <= edge["extraction_confidence"] <= 1.0
        assert edge["method_id"].strip()
