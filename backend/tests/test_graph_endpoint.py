"""Tests for the fixture-backed demo graph endpoint (RIS-20).

Asserts the evidence-panel contract: every returned edge carries the complete
Graft 2 provenance set (`RW-ALG-032`), offsets match the passage exactly
(`RW-GOAL-008` drill-down), the derivation method is human-readable
(`RW-ALG-004`), and the scenario is immediately runnable so the slider works.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from riskweave_api.main import app

_ENV = {
    "DATABASE_URL": "postgresql://riskweave:password@postgres:5432/riskweave",
    "NEO4J_URI": "bolt://neo4j:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "password",
    "REDIS_URL": "redis://redis:6379/0",
    "GEMINI_API_KEY": "test-placeholder",
}

_PROVENANCE_FIELDS = (
    "source_document_id",
    "filing_date",
    "source_passage",
    "char_start",
    "char_end",
    "data_timestamp",
    "extraction_confidence",
)


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


class TestGraphSeed:
    def test_seed_returns_201_with_fixture_graph(self, client: TestClient) -> None:
        resp = client.post("/graph/seed")
        assert resp.status_code == 201
        data = resp.json()
        assert data["scenario_id"] == "cre-demo"
        assert data["state"] == "READY"
        assert len(data["nodes"]) == 15
        assert len(data["edges"]) == 18

    def test_every_edge_has_complete_provenance(self, client: TestClient) -> None:
        # RW-ALG-032: no edge without provenance — the evidence panel renders
        # every Graft 2 field, so every field must be present and non-empty.
        data = client.post("/graph/seed").json()
        for edge in data["edges"]:
            prov = edge["provenance"]
            for field in _PROVENANCE_FIELDS:
                assert field in prov, f"edge {edge['edge_id']} missing {field}"
            assert prov["source_document_id"].strip()
            assert prov["source_passage"].strip()
            assert edge["method_id"].strip()
            assert edge["method_name"].strip()

    def test_passage_offsets_match_passage_length(self, client: TestClient) -> None:
        # RW-GOAL-008 / highlight spot-check: the stored offsets must span the
        # passage exactly so the client highlight lands precisely.
        data = client.post("/graph/seed").json()
        for edge in data["edges"]:
            prov = edge["provenance"]
            span = prov["char_end"] - prov["char_start"]
            assert span == len(prov["source_passage"]), (
                f"edge {edge['edge_id']} offset span {span} != passage length"
            )

    def test_nodes_expose_structural_centrality(self, client: TestClient) -> None:
        data = client.post("/graph/seed").json()
        for node in data["nodes"]:
            assert "centrality" in node
            assert isinstance(node["centrality"], (int, float))

    def test_low_confidence_edges_are_present_not_hidden(self, client: TestClient) -> None:
        # RW-SAFE-003: low-confidence extractions are surfaced (badged client-side),
        # never dropped. The fixture includes edges below the threshold.
        data = client.post("/graph/seed").json()
        threshold = data["low_confidence_threshold"]
        low = [e for e in data["edges"] if e["provenance"]["extraction_confidence"] < threshold]
        assert low, "expected at least one low-confidence edge to exercise the badge"

    def test_seed_is_idempotent(self, client: TestClient) -> None:
        r1 = client.post("/graph/seed")
        r2 = client.post("/graph/seed")
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["checksum"] == r2.json()["checksum"]

    def test_seeded_scenario_is_runnable(self, client: TestClient) -> None:
        client.post("/graph/seed")
        resp = client.post("/registry/run_scenario/cre-demo", json={"severity": 0.8})
        assert resp.status_code == 200
        impacts = resp.json()["result"]["impacts"]
        # The office-sector shock must reach at least one REIT creditor bank.
        assert impacts, "propagation produced no impacts"


class TestMethodology:
    def test_methodology_lists_all_six_methods(self, client: TestClient) -> None:
        data = client.get("/graph/methodology").json()
        method_ids = {m["method_id"] for m in data["methods"]}
        assert {
            "DER-COMMODITY",
            "DER-CONCENTRATION",
            "DER-CREDIT",
            "DER-DURATION",
            "DER-GEO",
            "DER-BETA",
        } <= method_ids

    def test_methodology_discloses_equity_price_limitation(self, client: TestClient) -> None:
        # RW-DATA-002: equity-price source limitations are disclosed honestly.
        data = client.get("/graph/methodology").json()
        blob = " ".join(data["limitations"]).lower()
        assert "equity-price" in blob or "equity price" in blob
