"""Explanation endpoint wiring (RIS-19).

Exercises ``GET /scenarios/{id}/explanation/{node}`` end to end over the seeded
CRE fixture with a fake Gemini transport injected on ``app.state`` — so the
success path, the citation resolution, and the guard-failure fallback are all
covered without a network or a key.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

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


class FakeTransport:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls = 0

    def create_interaction(self, **kwargs: object) -> dict[str, object]:
        self.calls += 1
        return {"output_text": json.dumps(self.response)}


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
    # Reset the injected transport between tests.
    if hasattr(app.state, "gemini_transport"):
        del app.state.gemini_transport


def _seed_and_pick_node(client: TestClient) -> str:
    seed = client.post("/graph/seed")
    assert seed.status_code == 201
    impacts = client.get("/scenarios/cre-demo/impacts", params={"severity": 1.0}).json()
    assert impacts, "fixture run should impact at least one node"
    return impacts[0]["node_id"]


def test_explanation_success_with_citation(client: TestClient) -> None:
    node_id = _seed_and_pick_node(client)
    # A clean, number-free explanation that cites the first evidence record.
    app.state.gemini_transport = FakeTransport(
        {
            "explanation": "Exposed through office-sector transmission [cit-1].",
            "citations": ["cit-1"],
        }
    )

    resp = client.get(f"/scenarios/cre-demo/explanation/{node_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["used_fallback"] is False
    assert body["prose"] is not None
    assert body["guard_violations"] == []
    assert body["citations"]
    assert body["citations"][0]["citation_id"] == "cit-1"
    assert body["citations"][0]["source_passage"]


def test_explanation_falls_back_on_hallucinated_number(client: TestClient) -> None:
    node_id = _seed_and_pick_node(client)
    transport = FakeTransport(
        {"explanation": "Default probability is 73% [cit-1].", "citations": ["cit-1"]}
    )
    app.state.gemini_transport = transport

    resp = client.get(f"/scenarios/cre-demo/explanation/{node_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["used_fallback"] is True
    assert body["prose"] is None
    assert "73" in body["guard_violations"]
    assert body["structured_numbers"]
    assert transport.calls == 2  # regenerated exactly once before falling back


def test_explanation_404_for_unimpacted_node(client: TestClient) -> None:
    client.post("/graph/seed")
    app.state.gemini_transport = FakeTransport({"explanation": "n/a", "citations": []})
    resp = client.get("/scenarios/cre-demo/explanation/does-not-exist")
    assert resp.status_code == 404
