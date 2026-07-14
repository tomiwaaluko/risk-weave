"""Neo4j write-time gate, coverage report, and separable centrality (RIS-12).

Complements ``test_graph_store.py`` (helper + live round-trip tests) with the
Graft 2 write gate itself. Every test here runs without the ``neo4j`` driver:
the gate and row builders are pure, and ``seed`` is driven through the *real*
``Neo4jGraphStore`` code path with a recording driver double — the real writer,
not a fixture shim. Live round-trips stay in ``test_graph_store.py``.
"""

from __future__ import annotations

import copy
from datetime import date, datetime

import pytest

from riskweave.derivations import Provenance, WeightRecord, der_credit_portfolio_share
from riskweave.graph import (
    Neo4jGraphStore,
    Neo4jWriteError,
    ProposedEdge,
    UniverseEntity,
    assemble,
    coverage_report,
    validate_edge_row,
)
from riskweave.graph.store import _edge_properties, _node_properties


# --------------------------------------------------------------------------- #
# Builders                                                                     #
# --------------------------------------------------------------------------- #
def prov(doc: str = "0000019617-24-000001") -> Provenance:
    passage = "loans secured by commercial real estate totaled 12% of the portfolio"
    return Provenance(
        source_document_id=doc,
        filing_date=date(2024, 2, 15),
        source_passage=passage,
        char_start=1000,
        char_end=1000 + len(passage),
        data_timestamp=datetime(2024, 2, 15, 0, 0, 0),
        extraction_confidence=0.9,
    )


def credit_record(numerator: float = 1200.0, doc: str = "0000019617-24-000001") -> WeightRecord:
    return der_credit_portfolio_share(numerator, 10000.0, prov(doc))


def entity(eid: str, etype: str = "bank", packs=("cre",)) -> UniverseEntity:
    return UniverseEntity(
        entity_id=eid, canonical_name=eid.upper(), entity_type=etype, packs=tuple(packs)
    )


def edge(src: str, dst: str, record=None, direction="positive", rel="creditor") -> ProposedEdge:
    return ProposedEdge(
        source_id=src,
        target_id=dst,
        relationship_type=rel,
        direction=direction,
        record=record or credit_record(),
    )


def build_graph():
    ents = [entity("a"), entity("b"), entity("c", "property_company")]
    edges = [
        edge("a", "b", credit_record(1200.0, "doc-1")),
        edge("b", "c", credit_record(3400.0, "doc-2")),
    ]
    return assemble("snap-1", "1.0.0", ents, edges)


def good_row() -> dict:
    return copy.deepcopy(_edge_properties(build_graph())[0])


# --------------------------------------------------------------------------- #
# Recording driver double — the real seed path, no live database              #
# --------------------------------------------------------------------------- #
class _EmptyResult:
    def single(self):
        return None

    def __iter__(self):
        return iter(())


class _RecordingTx:
    def __init__(self, log):
        self.log = log

    def run(self, cypher, **params):
        self.log.append((cypher, params))
        return _EmptyResult()


class _RecordingSession:
    def __init__(self, log):
        self.log = log

    def execute_write(self, fn):
        return fn(_RecordingTx(self.log))

    def run(self, cypher, **params):
        self.log.append((cypher, params))
        return _EmptyResult()

    def close(self):
        pass


class _RecordingDriver:
    def __init__(self):
        self.log = []

    def session(self, database=None):
        return _RecordingSession(self.log)

    def close(self):
        pass


# --------------------------------------------------------------------------- #
# The write gate (acceptance criteria) — real gate, no shim                    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "field",
    [
        "source_document_id",
        "source_passage",
        "char_start",
        "char_end",
        "filing_date",
        "data_timestamp",
        "method_id",
        "extraction_confidence",
        "provenance_ref",
    ],
)
def test_rejects_edge_without_provenance(field):
    """Dropping any Graft 2 field makes the edge unwritable (RW-ALG-032)."""
    row = good_row()
    del row[field]
    with pytest.raises(Neo4jWriteError):
        validate_edge_row(row)


def test_rejects_edge_with_raw_weight():
    """A raw float whose method id is not a registered DER-* is unstorable."""
    row = good_row()
    row["method_id"] = "DER-MADEUP"  # a raw, unregistered weight
    with pytest.raises(Neo4jWriteError):
        validate_edge_row(row)


def test_rejects_non_finite_weight():
    row = good_row()
    row["weight"] = float("nan")
    with pytest.raises(Neo4jWriteError):
        validate_edge_row(row)


def test_rejects_offset_span_mismatch():
    row = good_row()
    row["char_end"] = row["char_start"] + 3  # no longer matches the passage length
    with pytest.raises(Neo4jWriteError):
        validate_edge_row(row)


def test_rejects_confidence_out_of_range():
    row = good_row()
    row["extraction_confidence"] = 1.5
    with pytest.raises(Neo4jWriteError):
        validate_edge_row(row)


def test_good_row_passes_the_gate():
    validate_edge_row(good_row())  # does not raise


def test_edge_properties_gate_every_row():
    for row in _edge_properties(build_graph()):
        validate_edge_row(row)  # every emitted row survives the gate
        assert row["char_end"] - row["char_start"] == len(row["source_passage"])


# --------------------------------------------------------------------------- #
# Coverage report                                                              #
# --------------------------------------------------------------------------- #
def test_coverage_report_is_100_percent():
    report = coverage_report(build_graph())
    assert report["coverage"] == 1.0
    assert report["total_edges"] == report["provenanced_edges"] == 2
    assert report["edges_by_method"] == {"DER-CREDIT": 2}
    assert report["checksum"] == build_graph().checksum


# --------------------------------------------------------------------------- #
# Centrality on nodes, separate from scenario impact                           #
# --------------------------------------------------------------------------- #
def test_node_rows_carry_structural_centrality():
    graph = build_graph()
    rows = _node_properties(graph)
    assert {r["id"]: r["centrality"] for r in rows} == dict(graph.centrality)


# --------------------------------------------------------------------------- #
# seed() runs the real writer through the gate + stores checksum (recording)   #
# --------------------------------------------------------------------------- #
def _seed_log(graph):
    driver = _RecordingDriver()
    counts = Neo4jGraphStore(driver).seed(graph)
    return counts, driver.log


def test_seed_writes_nodes_edges_and_checksum():
    counts, log = _seed_log(build_graph())
    assert counts == {"nodes": 3, "edges": 2}
    meta_params = [p["meta"] for c, p in log if "meta" in p]
    assert meta_params and meta_params[-1]["checksum"] == build_graph().checksum


def test_seed_edge_params_carry_centrality_and_provenance():
    _counts, log = _seed_log(build_graph())
    node_params = next(p["nodes"] for c, p in log if "nodes" in p)
    assert all("centrality" in n for n in node_params)
    edge_params = next(p["edges"] for c, p in log if "edges" in p)
    for e in edge_params:
        validate_edge_row(e)
        assert e["method_id"].startswith("DER-")


def test_reseed_is_byte_identical():
    """Same snapshot + versions ⇒ identical write plan (idempotent, RW-FR-015)."""
    assert _seed_log(build_graph())[1] == _seed_log(build_graph())[1]
