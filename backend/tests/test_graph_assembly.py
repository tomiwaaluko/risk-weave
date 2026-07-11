"""Graph assembly + Graft 2 write-gate tests (RIS-12)."""

import os
from datetime import date, datetime

import pytest

from riskweave.derivations import (
    Provenance,
    ProvenanceError,
    WeightRecord,
    der_credit_portfolio_share,
)
from riskweave.graph import (
    GraphAssemblyError,
    ProposedEdge,
    UniverseEntity,
    assemble,
    load_universe,
)

UNIVERSE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "universe", "entities.json"
)


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


# --------------------------------------------------------------------------- #
# The write gate (acceptance criteria)                                         #
# --------------------------------------------------------------------------- #
def test_rejects_edge_with_raw_weight():
    with pytest.raises(GraphAssemblyError):
        ProposedEdge(
            source_id="a",
            target_id="b",
            relationship_type="creditor",
            direction="positive",
            record=0.15,  # a raw float is not writable
        )


def test_rejects_edge_without_provenance():
    # A WeightRecord cannot even be constructed without provenance; prove the
    # provenance requirement is enforced upstream of assembly.
    with pytest.raises(ProvenanceError):
        WeightRecord(
            value=0.15,
            method_id="DER-CREDIT",
            method_version="1.0.0",
            inputs={},
            provenance=None,  # missing provenance
            data_timestamps=(datetime(2024, 2, 15),),
        )


def test_rejects_unregistered_method():
    bad = WeightRecord(
        value=0.15,
        method_id="DER-MADEUP",
        method_version="1.0.0",
        inputs={},
        provenance=prov(),
        data_timestamps=(datetime(2024, 2, 15),),
    )
    with pytest.raises(GraphAssemblyError):
        edge("a", "b", record=bad)


def test_rejects_edge_to_entity_outside_universe():
    with pytest.raises(GraphAssemblyError):
        assemble("snap", "1.0.0", [entity("a")], [edge("a", "ghost")])


def test_provenance_coverage_is_100_percent():
    g = assemble("snap", "1.0.0", [entity("a"), entity("b")], [edge("a", "b")])
    assert g.provenance_coverage() == 1.0


# --------------------------------------------------------------------------- #
# Idempotency / checksum                                                       #
# --------------------------------------------------------------------------- #
def _build():
    ents = [entity("a"), entity("b"), entity("c", "property_company")]
    edges = [
        edge("a", "b", credit_record(1200.0, "doc-1")),
        edge("b", "c", credit_record(3400.0, "doc-2")),
    ]
    return assemble("snap-1", "1.0.0", ents, edges)


def test_assembly_is_idempotent_checksum():
    assert _build().checksum == _build().checksum


def test_checksum_changes_with_weight():
    g1 = _build()
    ents = [entity("a"), entity("b"), entity("c", "property_company")]
    edges = [
        edge("a", "b", credit_record(9999.0, "doc-1")),
        edge("b", "c", credit_record(3400.0, "doc-2")),
    ]
    g2 = assemble("snap-1", "1.0.0", ents, edges)
    assert g1.checksum != g2.checksum


# --------------------------------------------------------------------------- #
# Centrality separate from impact                                              #
# --------------------------------------------------------------------------- #
def test_centrality_stored_and_normalized():
    g = _build()
    assert set(g.centrality) == {"a", "b", "c"}
    assert sum(g.centrality.values()) == pytest.approx(1.0)
    # c is the sink of both flows → highest structural centrality.
    assert g.centrality["c"] == max(g.centrality.values())


# --------------------------------------------------------------------------- #
# Engine read API + pack filtering                                             #
# --------------------------------------------------------------------------- #
def test_to_snapshot_round_trips_to_engine():
    from riskweave.propagation import Scenario, ShockFactor, propagate

    g = _build()
    snap = g.to_snapshot()
    assert len(snap.nodes) == 3
    result = propagate(
        snap,
        Scenario(
            scenario_id="s",
            factors=(ShockFactor(factor_id="f", node_id="a", magnitude=1.0),),
        ),
    )
    assert "b" in result.impacts


def test_pack_filter_drops_other_pack_nodes():
    ents = [entity("a", packs=("cre",)), entity("b", packs=("oil",))]
    g = assemble("snap", "1.0.0", ents, [edge("a", "b")])
    cre = g.to_snapshot(pack="cre")
    assert {n.node_id for n in cre.nodes} == {"a"}
    assert cre.edges == ()  # cross-pack edge dropped when an endpoint is filtered


def test_negative_direction_flips_weight_sign():
    e = edge("a", "b", direction="negative")
    assert e.signed_weight == -e.record.value


# --------------------------------------------------------------------------- #
# Real universe file assembles                                                 #
# --------------------------------------------------------------------------- #
def test_real_universe_loads_and_assembles():
    entities = load_universe(UNIVERSE_PATH)
    assert 100 <= len(entities) <= 200  # RW-SCOPE-001
    g = assemble("universe-snap", "1.0.0", entities, [])
    assert g.provenance_coverage() == 1.0
    report = g.stats_report()
    assert "provenance coverage: 100%" in report
    assert sum(g.centrality.values()) == pytest.approx(1.0)
