"""Live pipeline assembly: extraction → resolution → DER-* → graph (RIS-28).

Uses small synthetic extraction inputs. Weights are never invented in the test
data — they are produced by registered DER-* callables from disclosed_magnitude
strings or recorded numeric inputs (`RW-AI-010`, `RW-ALG-001`).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from riskweave.derivations import (
    Provenance,
    ProvenanceError,
    der_concentration_disclosed,
    parse_disclosed_magnitude,
)
from riskweave.entity_resolution import Resolver
from riskweave.graph.live import (
    ExtractedRelationshipInput,
    LiveAssemblyError,
    NumericDerivationInputs,
    assemble_live_graph,
    derive_weight_for_relationship,
    edge_input_key,
    method_for_relationship,
)
from riskweave_api.main import app

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE = ROOT / "data" / "universe" / "entities.json"

_ENV = {
    "DATABASE_URL": "postgresql://riskweave:password@postgres:5432/riskweave",
    "NEO4J_URI": "bolt://neo4j:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "password",
    "REDIS_URL": "redis://redis:6379/0",
    "GEMINI_API_KEY": "test-placeholder",
}

_REGISTERED = {
    "DER-COMMODITY",
    "DER-CONCENTRATION",
    "DER-CREDIT",
    "DER-DURATION",
    "DER-GEO",
    "DER-BETA",
}


def _rel(
    *,
    source: str,
    target: str,
    relationship_type: str,
    magnitude: str | None,
    passage: str,
    doc: str = "0000019617-24-000001",
    char_start: int = 100,
    confidence: float = 0.91,
) -> ExtractedRelationshipInput:
    return ExtractedRelationshipInput(
        source_entity=source,
        target_entity=target,
        relationship_type=relationship_type,
        direction="positive",
        disclosed_magnitude=magnitude,
        source_passage=passage,
        source_document_id=doc,
        char_start=char_start,
        char_end=char_start + len(passage),
        extraction_confidence=confidence,
        filing_date=date(2024, 2, 15),
        data_timestamp=datetime(2024, 2, 15, 0, 0, 0),
    )


@pytest.fixture
def resolver() -> Resolver:
    return Resolver.from_universe_file(UNIVERSE)


def test_rejects_generated_edge_missing_provenance(resolver: Resolver) -> None:
    # RW-ALG-032: incomplete provenance cannot become a live edge.
    passage = "CRE loans were 12% of the portfolio"
    bad = ExtractedRelationshipInput(
        source_entity="Wells Fargo",
        target_entity="Boston Properties",
        relationship_type="creditor",
        direction="positive",
        disclosed_magnitude="12% of the portfolio",
        source_passage=passage,
        source_document_id="",  # missing source document id
        char_start=0,
        char_end=len(passage),
        extraction_confidence=0.9,
        filing_date=date(2024, 2, 15),
        data_timestamp=datetime(2024, 2, 15),
    )
    with pytest.raises((LiveAssemblyError, ProvenanceError)):
        assemble_live_graph(
            snapshot_id="live-test",
            relationships=[bad],
            resolver=resolver,
            universe_path=UNIVERSE,
        )


def test_live_assembly_weights_come_only_from_der_methods(resolver: Resolver) -> None:
    # Disclosed magnitudes are verbatim strings; deterministic parser → DER-*.
    passage_a = "loans secured by commercial real estate totaled approximately 12% of the portfolio"
    passage_b = "office properties represented approximately 28% of our total revenues"
    relationships = [
        _rel(
            source="Wells Fargo",
            target="Boston Properties",
            relationship_type="creditor",
            magnitude="approximately 12% of the portfolio",
            passage=passage_a,
            doc="0000019617-24-000001",
        ),
        _rel(
            source="Boston Properties",
            target="Wells Fargo",
            relationship_type="customer",
            magnitude="approximately 28% of our total revenues",
            passage=passage_b,
            doc="0000038777-24-000012",
            char_start=200,
        ),
    ]

    expected_credit = parse_disclosed_magnitude("approximately 12% of the portfolio").value
    expected_conc = parse_disclosed_magnitude("approximately 28% of our total revenues").value

    graph, report = assemble_live_graph(
        snapshot_id="live-test-snap",
        relationships=relationships,
        resolver=resolver,
        universe_path=UNIVERSE,
    )

    assert report.edges_built == 2
    assert graph.provenance_coverage() == 1.0
    for edge in graph.edges:
        assert edge.record.method_id in _REGISTERED
        assert edge.record.method_id.startswith("DER-")
        prov = edge.record.provenance
        assert prov.source_document_id.strip()
        assert prov.source_passage.strip()
        assert prov.char_end - prov.char_start == len(prov.source_passage)
        assert 0.0 <= prov.extraction_confidence <= 1.0

    by_method = {e.record.method_id: e.record.value for e in graph.edges}
    assert by_method["DER-CREDIT"] == pytest.approx(expected_credit)
    assert by_method["DER-CONCENTRATION"] == pytest.approx(expected_conc)
    # Cross-check: same number the DER callable itself would emit.
    conc_prov = next(
        e.record.provenance for e in graph.edges if e.record.method_id == "DER-CONCENTRATION"
    )
    assert der_concentration_disclosed(expected_conc, conc_prov).value == pytest.approx(
        expected_conc
    )


def test_live_assembly_uses_recorded_xbrl_inputs_not_invented_weights(
    resolver: Resolver,
) -> None:
    # No disclosed_magnitude — weight comes from recorded segment share inputs.
    passage = "Segment revenue is reported in the accompanying notes."
    relationships = [
        _rel(
            source="Boston Properties",
            target="Wells Fargo",
            relationship_type="sector_exposure",
            magnitude=None,
            passage=passage,
        )
    ]
    source_id = "reit:bxp"
    target_id = "bank:wfc"
    key = edge_input_key(source_id, target_id, "sector_exposure")
    numeric = NumericDerivationInputs(segment_shares={key: (450.0, 1500.0)})

    graph, report = assemble_live_graph(
        snapshot_id="live-xbrl",
        relationships=relationships,
        resolver=resolver,
        universe_path=UNIVERSE,
        numeric=numeric,
    )
    assert report.edges_built == 1
    edge = graph.edges[0]
    assert edge.record.method_id == "DER-CONCENTRATION"
    assert edge.record.value == pytest.approx(0.3)
    assert edge.record.inputs["segment_revenue"] == 450.0
    assert edge.record.inputs["total_revenue"] == 1500.0


def test_live_assembly_skips_when_no_magnitude_and_no_numeric_inputs(
    resolver: Resolver,
) -> None:
    passage = "We maintain lending relationships with various counterparties."
    relationships = [
        _rel(
            source="Wells Fargo",
            target="Boston Properties",
            relationship_type="creditor",
            magnitude=None,
            passage=passage,
        )
    ]
    with pytest.raises(LiveAssemblyError, match="produced no edges"):
        assemble_live_graph(
            snapshot_id="live-empty",
            relationships=relationships,
            resolver=resolver,
            universe_path=UNIVERSE,
        )


def test_method_for_relationship_maps_only_to_registered_ids() -> None:
    for rel_type in ("creditor", "customer", "geographic_exposure", "commodity_dependency"):
        method = method_for_relationship(rel_type)
        assert method in _REGISTERED


def test_derive_weight_requires_provenance_for_disclosed_share() -> None:
    with pytest.raises(ProvenanceError):
        Provenance(
            source_document_id="doc",
            filing_date=date(2024, 1, 1),
            source_passage="",
            char_start=0,
            char_end=0,
            data_timestamp=datetime(2024, 1, 1),
            extraction_confidence=0.9,
        )


def test_fixture_seed_path_still_returns_committed_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)

    with TestClient(app) as client:
        resp = client.post("/graph/seed")
        assert resp.status_code == 201
        data = resp.json()
        assert data["source"] == "fixture"
        assert data["scenario_id"] == "cre-demo"
        assert data["snapshot_id"] == "cre-demo-2026-07-11"
        assert len(data["nodes"]) == 15
        assert len(data["edges"]) == 18


def test_live_seed_without_extractions_returns_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)

    def _boom(*_a, **_k):
        raise LiveAssemblyError("no extracted relationships for snapshot_id=3")

    monkeypatch.setattr(
        "riskweave_api.routers.graph._assemble_live",
        _boom,
    )

    with TestClient(app) as client:
        resp = client.post("/graph/seed?source=live")
        assert resp.status_code == 422
        assert "no extracted relationships" in resp.json()["detail"]


def test_live_seed_fallback_to_fixture_only_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)

    def _boom(*_a, **_k):
        raise LiveAssemblyError("no extracted relationships")

    monkeypatch.setattr("riskweave_api.routers.graph._assemble_live", _boom)

    with TestClient(app) as client:
        resp = client.post("/graph/seed?source=live&fallback_to_fixture=true")
        assert resp.status_code == 201
        data = resp.json()
        assert data["source"] == "fixture"
        assert data["snapshot_id"] == "cre-demo-2026-07-11"


def test_live_info_documents_snapshot_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LIVE_GRAPH_SNAPSHOT_ID", "3")

    with TestClient(app) as client:
        resp = client.get("/graph/live-info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_snapshot_id"] == 3
        assert "assemble_live" in data["assemble_command"]
        assert any("RW-FR-015" in note for note in data["notes"])


def test_derive_weight_for_relationship_is_deterministic() -> None:
    passage = "fuel was approximately 28% of operating expenses"
    prov = Provenance(
        source_document_id="doc-1",
        filing_date=date(2024, 3, 1),
        source_passage=passage,
        char_start=10,
        char_end=10 + len(passage),
        data_timestamp=datetime(2024, 3, 1),
        extraction_confidence=0.88,
    )
    first = derive_weight_for_relationship(
        relationship_type="commodity_dependency",
        disclosed_magnitude="approximately 28% of operating expenses",
        provenance=prov,
        source_id="a",
        target_id="b",
    )
    second = derive_weight_for_relationship(
        relationship_type="commodity_dependency",
        disclosed_magnitude="approximately 28% of operating expenses",
        provenance=prov,
        source_id="a",
        target_id="b",
    )
    assert first is not None and second is not None
    assert first.method_id == "DER-COMMODITY"
    assert first.value == second.value == pytest.approx(0.28)
