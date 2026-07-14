"""RIS-30: scenario/run REST endpoints against the PostgreSQL-backed store.

Skipped without TEST_DATABASE_URL. Exercises the full FastAPI app with
SCENARIO_STORE_BACKEND=postgres so the lifespan wiring (`main._build_store`)
and the new /runs endpoints are covered end-to-end, not just the store class.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from riskweave.propagation import GraphEdge, GraphNode, GraphSnapshot
from riskweave_api.ingestion.database import session_factory
from riskweave_api.main import app

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for PostgreSQL persistence integration tests",
)


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    sf = session_factory(TEST_DATABASE_URL)
    with sf() as session:
        session.execute(text("DELETE FROM scenario_runs"))
        session.execute(text("DELETE FROM stored_scenarios"))
        session.execute(text("DELETE FROM stored_graph_snapshots"))
        session.commit()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("SCENARIO_STORE_BACKEND", "postgres")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    with TestClient(app, raise_server_exceptions=True) as c:
        snapshot = GraphSnapshot(
            snapshot_id="snap-api-1",
            graph_version="v1",
            nodes=(
                GraphNode(node_id="bank-a", node_type="bank", name="Bank Alpha"),
                GraphNode(node_id="bank-b", node_type="bank", name="Bank Beta"),
            ),
            edges=(
                GraphEdge(
                    edge_id="e1",
                    source_id="bank-a",
                    target_id="bank-b",
                    weight=0.5,
                    method_id="DER-CREDIT",
                    provenance_ref="prov:001",
                ),
            ),
        )
        c.app.state.store.register_snapshot(snapshot)
        c.app.state.redis = None
        yield c


def test_backend_selects_postgres_scenario_store(client) -> None:
    from riskweave_api.postgres_scenario_store import PostgresScenarioStore

    assert isinstance(client.app.state.store, PostgresScenarioStore)


def test_scenario_survives_restart_via_rest_api(client) -> None:
    resp = client.post(
        "/scenarios",
        json={
            "scenario_id": "scen-api-1",
            "snapshot_id": "snap-api-1",
            "graph_version": "v1",
            "factors": [{"factor_id": "f1", "node_id": "bank-a", "magnitude": 1.0}],
        },
    )
    assert resp.status_code == 201
    client.post("/scenarios/scen-api-1/validate")

    run_resp = client.post("/scenarios/scen-api-1/run", json={"severity": 1.0})
    assert run_resp.status_code == 200
    run_payload = run_resp.json()

    runs_resp = client.get("/scenarios/scen-api-1/runs")
    assert runs_resp.status_code == 200
    summaries = runs_resp.json()
    assert len(summaries) == 1
    run_id = summaries[0]["run_id"]

    fetched_resp = client.get(f"/scenarios/scen-api-1/runs/{run_id}")
    assert fetched_resp.status_code == 200
    assert fetched_resp.json() == run_payload

    # A brand new store instance ("restart") must still serve the same scenario.
    from riskweave_api.postgres_scenario_store import PostgresScenarioStore

    restarted_store = PostgresScenarioStore(session_factory(TEST_DATABASE_URL))
    record = restarted_store.get("scen-api-1")
    assert record.state.value == "COMPLETED"
    refetched_run = restarted_store.get_run("scen-api-1", run_id).result
    assert refetched_run.model_dump() == run_payload


def test_get_run_unknown_id_returns_404(client) -> None:
    client.post(
        "/scenarios",
        json={
            "scenario_id": "scen-api-2",
            "snapshot_id": "snap-api-1",
            "graph_version": "v1",
            "factors": [{"factor_id": "f1", "node_id": "bank-a", "magnitude": 1.0}],
        },
    )
    resp = client.get("/scenarios/scen-api-2/runs/999")
    assert resp.status_code == 404
