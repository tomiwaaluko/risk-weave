"""Tests for the spike seed endpoint (RIS-15)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from riskweave_api.main import app

# Required env vars for Settings validation in the lifespan.
_ENV = {
    "DATABASE_URL": "postgresql://riskweave:password@postgres:5432/riskweave",
    "NEO4J_URI": "bolt://neo4j:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "password",
    "REDIS_URL": "redis://redis:6379/0",
    "GEMINI_API_KEY": "test-placeholder",
}


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


class TestSpikeSeed:
    """POST /spike/seed creates a valid spike scenario."""

    def test_seed_returns_201_with_graph(self, client: TestClient) -> None:
        resp = client.post("/spike/seed")
        assert resp.status_code == 201
        data = resp.json()
        assert data["scenario_id"] == "spike-scenario"
        assert data["snapshot_id"] == "spike-snap"
        assert data["state"] == "READY"

    def test_seed_returns_200_nodes(self, client: TestClient) -> None:
        resp = client.post("/spike/seed")
        data = resp.json()
        assert len(data["nodes"]) == 200

    def test_seed_returns_representative_edge_density(self, client: TestClient) -> None:
        resp = client.post("/spike/seed")
        data = resp.json()
        # 200 nodes * 7 out-degree = 1400 edges
        assert len(data["edges"]) == 1400

    def test_seed_nodes_have_diverse_types(self, client: TestClient) -> None:
        resp = client.post("/spike/seed")
        data = resp.json()
        types = {n["node_type"] for n in data["nodes"]}
        expected = {"company", "bank", "reit", "security", "commodity", "geography", "sector"}
        assert types == expected

    def test_seed_edges_have_provenance(self, client: TestClient) -> None:
        resp = client.post("/spike/seed")
        data = resp.json()
        for edge in data["edges"]:
            assert edge["provenance_ref"], f"edge {edge['edge_id']} missing provenance"
            assert edge["method_id"], f"edge {edge['edge_id']} missing method_id"

    def test_seed_returns_factors(self, client: TestClient) -> None:
        resp = client.post("/spike/seed")
        data = resp.json()
        assert len(data["factors"]) == 5

    def test_seed_is_idempotent(self, client: TestClient) -> None:
        resp1 = client.post("/spike/seed")
        resp2 = client.post("/spike/seed")
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert len(resp1.json()["nodes"]) == len(resp2.json()["nodes"])


class TestSpikeRun:
    """POST /spike/run propagates the spike scenario."""

    def test_run_requires_seed_first(self, client: TestClient) -> None:
        resp = client.post("/spike/run?severity=0.5")
        assert resp.status_code == 404

    def test_run_returns_impacts(self, client: TestClient) -> None:
        client.post("/spike/seed")
        resp = client.post("/spike/run?severity=0.5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_id"] == "spike-scenario"
        assert data["severity"] == 0.5
        assert len(data["impacts"]) > 0
        assert len(data["ranked_entity_ids"]) > 0
        assert data["latency_ms"] > 0

    def test_run_impacts_have_contributions(self, client: TestClient) -> None:
        client.post("/spike/seed")
        resp = client.post("/spike/run?severity=1.0")
        data = resp.json()
        # At least the first impacted node should have contributions
        first_id = data["ranked_entity_ids"][0]
        impact = data["impacts"][first_id]
        assert impact["risk_score"] > 0
        assert len(impact["contributions"]) > 0
        contrib = impact["contributions"][0]
        assert "edge_ids" in contrib
        assert "method_ids" in contrib
        assert "provenance_refs" in contrib

    def test_run_is_deterministic(self, client: TestClient) -> None:
        """Identical severity produces identical results (RW-GOAL-006)."""
        client.post("/spike/seed")
        r1 = client.post("/spike/run?severity=0.75")
        r2 = client.post("/spike/run?severity=0.75")
        d1, d2 = r1.json(), r2.json()
        assert d1["ranked_entity_ids"] == d2["ranked_entity_ids"]
        assert d1["impacts"] == d2["impacts"]
