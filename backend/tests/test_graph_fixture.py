"""Committed CRE fixture: Graft 2 gate, provenance, and engine round-trip (RIS-12).

These tests need neither Neo4j nor the driver — they exercise the pure-Python
path: fixture -> Graft 2 write gate -> AssembledGraph -> engine snapshot. The
Neo4j seed/read path is covered in ``test_graph_store.py`` (skipped when no DB).
"""

from __future__ import annotations

import copy
import json

import pytest

from riskweave.derivations import get_method
from riskweave.graph import GraphAssemblyError, load_graph_fixture
from riskweave.graph.fixture import DEFAULT_FIXTURE_PATH, FixtureError
from riskweave.propagation import Scenario, ShockFactor, propagate


@pytest.fixture(scope="module")
def graph():
    return load_graph_fixture()


def test_fixture_loads_curated_universe(graph):
    # Reduced hackathon scope: ~15 entities, all in the CRE pack.
    assert len(graph.entities) == 15
    assert graph.edges  # non-empty
    assert all("cre" in e.packs for e in graph.entities)


def test_every_edge_carries_complete_provenance(graph):
    # The whole point of Graft 2: no edge exists without full provenance.
    assert graph.provenance_coverage() == 1.0
    for edge in graph.edges:
        prov = edge.record.provenance
        assert prov.source_document_id.strip()
        assert prov.source_passage.strip()
        # offsets are half-open and exactly span the quoted passage
        assert prov.char_end - prov.char_start == len(prov.source_passage)
        assert 0.0 <= prov.extraction_confidence <= 1.0
        assert edge.record.data_timestamps


def test_every_edge_uses_a_registered_derivation_method(graph):
    for edge in graph.edges:
        # get_method raises for an unregistered id; assembly already enforces
        # this, but assert it explicitly against the committed fixture.
        assert get_method(edge.record.method_id).method_id == edge.record.method_id


def test_fixture_load_is_deterministic(graph):
    # Re-loading reproduces the same graph (checksum is the idempotency witness).
    assert load_graph_fixture().checksum == graph.checksum


def test_cre_scenario_runs_end_to_end(graph):
    snapshot = graph.to_snapshot(pack="cre")
    result = propagate(
        snapshot,
        Scenario(
            scenario_id="cre-office-decline",
            factors=(ShockFactor(factor_id="office-shock", node_id="cre-office", magnitude=1.0),),
        ),
    )
    # The office shock must reach downstream lenders and REITs.
    assert "slg" in result.impacts
    assert "wfc" in result.impacts
    # Every retained path hop still carries a provenance ref for the panel.
    for impact in result.impacts.values():
        for contribution in impact.contributions:
            for hop in contribution.edges:
                assert hop.provenance_ref


def test_pack_filter_keeps_cre(graph):
    assert {n.node_id for n in graph.to_snapshot(pack="cre").nodes} == {
        e.entity_id for e in graph.entities
    }


def test_unknown_pack_raises(graph):
    with pytest.raises(GraphAssemblyError):
        graph.to_snapshot(pack="does-not-exist")


def test_missing_provenance_field_is_rejected(tmp_path):
    payload = json.loads(DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    broken = copy.deepcopy(payload)
    # Drop a mandatory provenance field from the first edge.
    del broken["edges"][0]["weight"]["provenance"]["source_document_id"]
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(FixtureError):
        load_graph_fixture(path)
