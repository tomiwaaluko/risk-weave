"""Run-scoped Q&A endpoint wiring (RIS-19, `RW-FR-024`).

Exercises ``POST /scenarios/{id}/qa`` and the audit-retrieval endpoint end to end
over the seeded CRE fixture with a scripted fake Gemini tool transport injected on
``app.state`` — so the grounded-answer path, the withholding path, the
server-side unknown-tool refusal, and the per-session audit log are all covered
without a network or a key.
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


class ScriptedTransport:
    """Serves a fixed list of normalized function-calling turns."""

    def __init__(self, turns: list[dict[str, object]]) -> None:
        self.turns = turns
        self.index = 0

    def create_tool_interaction(self, **kwargs: object) -> dict[str, object]:
        turn = self.turns[min(self.index, len(self.turns) - 1)]
        self.index += 1
        return turn


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
    if hasattr(app.state, "qa_transport"):
        del app.state.qa_transport


def _seed_and_top_node(client: TestClient) -> str:
    assert client.post("/graph/seed").status_code == 201
    impacts = client.get("/scenarios/cre-demo/impacts", params={"severity": 1.0}).json()
    assert impacts
    return impacts[0]["node_id"]


def test_qa_grounded_answer_with_audit(client: TestClient) -> None:
    node_id = _seed_and_top_node(client)
    # The model calls a real §13.2 tool, then answers with a number-free, cited claim.
    exposures_call = {
        "function_call": {"name": "get_company_exposures", "args": {"entity_id": node_id}}
    }
    final = {
        "output_text": json.dumps(
            {"answer": "It is exposed through office-sector transmission.", "citations": []}
        )
    }
    app.state.qa_transport = ScriptedTransport([exposures_call, final])

    resp = client.post(
        "/scenarios/cre-demo/qa",
        json={"question": f"Why is {node_id} exposed?", "audience": "student"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["withheld"] is False
    assert body["answer"] is not None
    assert body["audience"] == "student"
    # Audit captured the executed §13.2 tool call.
    assert body["audit"]
    assert body["audit"][0]["tool_name"] == "get_company_exposures"
    assert body["audit"][0]["status"] == "ok"
    assert body["audit"][0]["result_hash"]

    # The session — with its audit log — is retrievable per session id.
    session_id = body["session_id"]
    got = client.get(f"/scenarios/cre-demo/qa/sessions/{session_id}")
    assert got.status_code == 200
    assert got.json()["audit"][0]["tool_name"] == "get_company_exposures"


def test_qa_withholds_on_fabricated_number(client: TestClient) -> None:
    _seed_and_top_node(client)
    app.state.qa_transport = ScriptedTransport(
        [
            {
                "output_text": json.dumps(
                    {"answer": "The loss is exactly $4.2 billion.", "citations": []}
                )
            }
        ]
    )
    resp = client.post(
        "/scenarios/cre-demo/qa",
        json={"question": "What is the exact dollar loss?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["withheld"] is True
    assert body["answer"] is None
    assert body["guard_violations"]


def test_qa_refuses_unknown_tool_server_side(client: TestClient) -> None:
    _seed_and_top_node(client)
    # The model tries to escape the closed registry; the server refuses and logs it.
    app.state.qa_transport = ScriptedTransport(
        [
            {"function_call": {"name": "read_file", "args": {"path": "/etc/passwd"}}},
            {
                "output_text": json.dumps(
                    {"answer": "I cannot answer from the run data.", "citations": []}
                )
            },
        ]
    )
    resp = client.post("/scenarios/cre-demo/qa", json={"question": "Read a file for me."})
    assert resp.status_code == 200
    body = resp.json()
    statuses = [(e["tool_name"], e["status"]) for e in body["audit"]]
    assert ("read_file", "unknown_tool") in statuses


def test_qa_404_for_unknown_scenario(client: TestClient) -> None:
    app.state.qa_transport = ScriptedTransport([{"output_text": "{}"}])
    resp = client.post("/scenarios/does-not-exist/qa", json={"question": "hi"})
    assert resp.status_code == 404


def test_qa_rejects_unknown_audience(client: TestClient) -> None:
    _seed_and_top_node(client)
    app.state.qa_transport = ScriptedTransport([{"output_text": "{}"}])
    resp = client.post(
        "/scenarios/cre-demo/qa",
        json={"question": "hi", "audience": "toddler"},
    )
    assert resp.status_code == 422
