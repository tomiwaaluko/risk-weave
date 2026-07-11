"""Tests for RIS-14: scenario lifecycle, Redis caching, WebSocket slider, registry.

Covers: RW-FR-009 (lifecycle), RW-FR-015 (reproducibility bundle),
        RW-FR-020 (live recompute), RW-NFR-004 (Redis caching), §13.2 registry.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from riskweave.propagation import GraphEdge, GraphNode, GraphSnapshot
from riskweave_api.main import app
from riskweave_api.models import ScenarioState
from riskweave_api.scenario_store import ScenarioStore, TransitionError

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def _make_snapshot(snapshot_id: str = "snap-1", graph_version: str = "v1") -> GraphSnapshot:
    nodes = (
        GraphNode(node_id="bank-a", node_type="bank", name="Bank Alpha"),
        GraphNode(node_id="bank-b", node_type="bank", name="Bank Beta"),
        GraphNode(node_id="reit-c", node_type="reit", name="REIT Corp"),
    )
    edges = (
        GraphEdge(
            edge_id="e1",
            source_id="bank-a",
            target_id="bank-b",
            weight=0.6,
            method_id="DER-CREDIT",
            provenance_ref="prov:001",
        ),
        GraphEdge(
            edge_id="e2",
            source_id="bank-b",
            target_id="reit-c",
            weight=0.5,
            method_id="DER-CONCENTRATION",
            provenance_ref="prov:002",
        ),
    )
    return GraphSnapshot(
        snapshot_id=snapshot_id, graph_version=graph_version, nodes=nodes, edges=edges
    )


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    with TestClient(app, raise_server_exceptions=True) as c:
        # Inject snapshot and disable Redis (no live Redis in tests)
        snapshot = _make_snapshot()
        c.app.state.store.register_snapshot(snapshot)
        c.app.state.redis = None
        yield c


@pytest.fixture()
def scenario_id(client):
    return "scen-test-1"


@pytest.fixture()
def created_scenario(client, scenario_id):
    resp = client.post(
        "/scenarios",
        json={
            "scenario_id": scenario_id,
            "snapshot_id": "snap-1",
            "graph_version": "v1",
            "factors": [{"factor_id": "f1", "node_id": "bank-a", "magnitude": 0.8}],
            "seed": 42,
        },
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Scenario lifecycle (RW-FR-009)
# ---------------------------------------------------------------------------


def test_create_scenario_returns_draft_state(client, scenario_id):
    resp = client.post(
        "/scenarios",
        json={
            "scenario_id": scenario_id,
            "snapshot_id": "snap-1",
            "graph_version": "v1",
            "factors": [{"factor_id": "f1", "node_id": "bank-a", "magnitude": 1.0}],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["state"] == "DRAFT"


def test_get_scenario_returns_record(client, created_scenario, scenario_id):
    resp = client.get(f"/scenarios/{scenario_id}")
    assert resp.status_code == 200
    assert resp.json()["scenario_id"] == scenario_id


def test_get_nonexistent_scenario_returns_404(client):
    assert client.get("/scenarios/does-not-exist").status_code == 404


def test_validate_transitions_to_ready(client, created_scenario, scenario_id):
    resp = client.post(f"/scenarios/{scenario_id}/validate")
    assert resp.status_code == 200
    assert resp.json()["state"] == "READY"


def test_invalid_transition_rejected(client, scenario_id):
    # Still in DRAFT; jumping straight to RUNNING should fail
    client.post(
        "/scenarios",
        json={
            "scenario_id": scenario_id,
            "snapshot_id": "snap-1",
            "graph_version": "v1",
            "factors": [{"factor_id": "f1", "node_id": "bank-a", "magnitude": 1.0}],
        },
    )
    store: ScenarioStore = client.app.state.store
    with pytest.raises(TransitionError):
        store.transition(scenario_id, ScenarioState.RUNNING)


# ---------------------------------------------------------------------------
# Run and reproducibility (RW-FR-015)
# ---------------------------------------------------------------------------


def test_run_returns_result_with_latency(client, created_scenario, scenario_id):
    client.post(f"/scenarios/{scenario_id}/validate")
    resp = client.post(f"/scenarios/{scenario_id}/run", json={"severity": 1.0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenario_id"] == scenario_id
    assert "latency_ms" in data
    assert data["latency_ms"] >= 0


def test_run_without_ready_state_rejected(client, created_scenario, scenario_id):
    # DRAFT → run should be 409
    resp = client.post(f"/scenarios/{scenario_id}/run", json={"severity": 1.0})
    assert resp.status_code == 409


def test_identical_run_request_reproduces_identical_results(client, scenario_id):
    for i in range(2):
        client.post(
            "/scenarios",
            json={
                "scenario_id": f"{scenario_id}-r{i}",
                "snapshot_id": "snap-1",
                "graph_version": "v1",
                "factors": [{"factor_id": "f1", "node_id": "bank-a", "magnitude": 0.8}],
                "seed": 99,
            },
        )
        client.post(f"/scenarios/{scenario_id}-r{i}/validate")

    r1 = client.post(f"/scenarios/{scenario_id}-r0/run", json={"severity": 0.7}).json()
    r2 = client.post(f"/scenarios/{scenario_id}-r1/run", json={"severity": 0.7}).json()

    def _numeric_impacts(result: dict) -> dict:
        """Keep only deterministic numeric fields; drop scenario_id-derived path_keys."""
        return {
            node_id: {
                "raw_impact": ni["raw_impact"],
                "risk_score": ni["risk_score"],
                "hop_counts": sorted(c["hop_count"] for c in ni["contributions"]),
                "contributions": sorted(c["contribution"] for c in ni["contributions"]),
            }
            for node_id, ni in result["impacts"].items()
        }

    assert _numeric_impacts(r1) == _numeric_impacts(r2)
    assert r1["damping"] == r2["damping"]
    assert r1["floor"] == r2["floor"]
    assert r1["max_hops"] == r2["max_hops"]
    assert r1["engine_version"] == r2["engine_version"]


def test_result_carries_reproducibility_bundle(client, created_scenario, scenario_id):
    client.post(f"/scenarios/{scenario_id}/validate")
    data = client.post(f"/scenarios/{scenario_id}/run", json={"severity": 1.0}).json()
    bundle_fields = (
        "snapshot_id",
        "graph_version",
        "engine_version",
        "seed",
        "damping",
        "floor",
        "max_hops",
    )
    for field in bundle_fields:
        assert field in data, f"reproducibility bundle missing field: {field}"


# ---------------------------------------------------------------------------
# Redis cache (RW-NFR-004)
# ---------------------------------------------------------------------------


def test_cache_hit_returns_same_result(client, created_scenario, scenario_id, monkeypatch):
    """Repeated severity values should return identical data (from cache in prod)."""
    client.post(f"/scenarios/{scenario_id}/validate")
    client.post(f"/scenarios/{scenario_id}/run", json={"severity": 0.5})

    # Second call at same severity; without Redis the store reruns but result must be identical
    r1 = client.post(f"/scenarios/{scenario_id}/run", json={"severity": 0.5}).json()
    r2 = client.post(f"/scenarios/{scenario_id}/run", json={"severity": 0.5}).json()

    r1.pop("latency_ms", None)
    r2.pop("latency_ms", None)
    assert r1 == r2


# ---------------------------------------------------------------------------
# Ranked impacts and paths
# ---------------------------------------------------------------------------


def test_ranked_impacts_ordered_by_risk_score(client, created_scenario, scenario_id):
    client.post(f"/scenarios/{scenario_id}/validate")
    data = client.get(f"/scenarios/{scenario_id}/impacts?severity=1.0").json()
    scores = [item["risk_score"] for item in data]
    assert scores == sorted(scores, reverse=True)


def test_paths_for_entity_returns_contributions(client, created_scenario, scenario_id):
    client.post(f"/scenarios/{scenario_id}/validate")
    client.post(f"/scenarios/{scenario_id}/run", json={"severity": 1.0})
    # bank-b should be impacted by bank-a's shock
    resp = client.get(f"/scenarios/{scenario_id}/paths/bank-b?severity=1.0")
    assert resp.status_code == 200
    paths = resp.json()
    assert len(paths) > 0
    for path in paths:
        assert "provenance_refs" in path
        assert len(path["provenance_refs"]) > 0


def test_paths_for_nonexistent_node_returns_404(client, created_scenario, scenario_id):
    client.post(f"/scenarios/{scenario_id}/validate")
    resp = client.get(f"/scenarios/{scenario_id}/paths/unknown-node?severity=1.0")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# §13.2 Registry endpoints
# ---------------------------------------------------------------------------


def test_resolve_entity_finds_node_by_name(client, created_scenario):
    resp = client.post("/registry/resolve_entity", json={"query": "Bank Alpha"})
    assert resp.status_code == 200
    assert resp.json()["node_id"] == "bank-a"


def test_resolve_entity_returns_nulls_for_unknown(client):
    resp = client.post("/registry/resolve_entity", json={"query": "Nonexistent Corp"})
    assert resp.status_code == 200
    assert resp.json()["node_id"] is None


def test_get_company_exposures_returns_provenance_bearing_edges(client):
    resp = client.get("/registry/company_exposures/bank-a?snapshot_id=snap-1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["outgoing_edges"]) > 0
    for edge in data["outgoing_edges"]:
        assert "method_id" in edge
        assert "provenance_ref" in edge


def test_run_scenario_registry_returns_result(client, scenario_id):
    client.post(
        "/scenarios",
        json={
            "scenario_id": scenario_id,
            "snapshot_id": "snap-1",
            "graph_version": "v1",
            "factors": [{"factor_id": "f1", "node_id": "bank-a", "magnitude": 0.5}],
        },
    )
    resp = client.post(f"/registry/run_scenario/{scenario_id}", json={"severity": 1.0})
    assert resp.status_code == 200
    assert "result" in resp.json()


def test_propagation_paths_registry_returns_provenance(client, scenario_id):
    client.post(
        "/scenarios",
        json={
            "scenario_id": scenario_id,
            "snapshot_id": "snap-1",
            "graph_version": "v1",
            "factors": [{"factor_id": "f1", "node_id": "bank-a", "magnitude": 1.0}],
        },
    )
    resp = client.get(f"/registry/propagation_paths/{scenario_id}/bank-b")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert len(paths) > 0
    for path in paths:
        assert len(path["provenance_refs"]) > 0


def test_breach_distance_stub_returns_not_implemented(client):
    resp = client.get("/registry/breach_distance/scen-1/bank-a")
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_implemented"


def test_duration_transmission_stub_returns_not_implemented(client):
    resp = client.get("/registry/duration_transmission/scen-1/bank-a")
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_implemented"


# ---------------------------------------------------------------------------
# WebSocket slider (RW-FR-020, RW-NFR-002)
# ---------------------------------------------------------------------------


def test_slider_websocket_returns_updated_scores(client, scenario_id):
    client.post(
        "/scenarios",
        json={
            "scenario_id": scenario_id,
            "snapshot_id": "snap-1",
            "graph_version": "v1",
            "factors": [{"factor_id": "f1", "node_id": "bank-a", "magnitude": 1.0}],
        },
    )
    with client.websocket_connect(f"/scenarios/{scenario_id}/slider") as ws:
        ws.send_text(json.dumps({"severity": 0.5}))
        msg = json.loads(ws.receive_text())
        assert "severity" in msg
        assert msg["severity"] == 0.5
        assert "impacts" in msg
        assert "latency_ms" in msg


def test_slider_websocket_nonexistent_scenario_closes(client):
    with (
        client.websocket_connect("/scenarios/no-such-scen/slider") as ws,
        pytest.raises(Exception),  # noqa: B017
    ):
        ws.receive_text()


def test_slider_recompute_within_budget(client, scenario_id):
    """p95 proxy: all single recomputes on the tiny test graph must finish in time."""
    client.post(
        "/scenarios",
        json={
            "scenario_id": scenario_id,
            "snapshot_id": "snap-1",
            "graph_version": "v1",
            "factors": [{"factor_id": "f1", "node_id": "bank-a", "magnitude": 1.0}],
        },
    )
    with client.websocket_connect(f"/scenarios/{scenario_id}/slider") as ws:
        for sev in (0.1, 0.5, 1.0):
            ws.send_text(json.dumps({"severity": sev}))
            msg = json.loads(ws.receive_text())
            budget_ms = 500
            assert msg["latency_ms"] < budget_ms, (
                f"budget exceeded at severity={sev}: {msg['latency_ms']:.1f} ms"
            )
