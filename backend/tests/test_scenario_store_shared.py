"""Shared behavior contract tests for RIS-30: run against every ScenarioStore backend.

InMemoryScenarioStore always runs. PostgresScenarioStore only runs when
TEST_DATABASE_URL is set (same convention as test_postgres_ingestion.py), so
the unit test suite still passes without a live PostgreSQL instance.

Covers RW-FR-009 (lifecycle transition validation identical across backends)
and the RIS-30 acceptance criterion that a persisted run's stored bundle
(snapshot_id + engine_version + seed) reproduces the identical result.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from riskweave.propagation import (
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    Scenario,
    ShockFactor,
    propagate,
)
from riskweave_api.ingestion.database import session_factory
from riskweave_api.models import ScenarioCreateRequest, ScenarioState, ShockFactorIn
from riskweave_api.postgres_scenario_store import PostgresScenarioStore
from riskweave_api.scenario_store import InMemoryScenarioStore, NotFoundError, TransitionError

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _make_snapshot(snapshot_id: str = "snap-shared", graph_version: str = "v1") -> GraphSnapshot:
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


def _make_request(scenario_id: str, snapshot_id: str = "snap-shared") -> ScenarioCreateRequest:
    return ScenarioCreateRequest(
        scenario_id=scenario_id,
        snapshot_id=snapshot_id,
        graph_version="v1",
        factors=[ShockFactorIn(factor_id="f1", node_id="bank-a", magnitude=1.0)],
        seed=42,
    )


def _clean_postgres_tables() -> None:
    sf = session_factory(TEST_DATABASE_URL)
    with sf() as session:
        session.execute(text("DELETE FROM scenario_runs"))
        session.execute(text("DELETE FROM stored_scenarios"))
        session.execute(text("DELETE FROM stored_graph_snapshots"))
        session.commit()


def _store_params():
    params = [pytest.param("memory", id="memory")]
    params.append(
        pytest.param(
            "postgres",
            id="postgres",
            marks=pytest.mark.skipif(
                not TEST_DATABASE_URL,
                reason="TEST_DATABASE_URL is required for PostgresScenarioStore tests",
            ),
        )
    )
    return params


@pytest.fixture(params=_store_params())
def store(request):
    if request.param == "memory":
        return InMemoryScenarioStore()
    _clean_postgres_tables()
    return PostgresScenarioStore(session_factory(TEST_DATABASE_URL))


def test_snapshot_and_provenance_roundtrip(store) -> None:
    snapshot = _make_snapshot()
    store.register_snapshot(snapshot)
    fetched = store.get_snapshot(snapshot.snapshot_id)
    assert fetched.snapshot_id == snapshot.snapshot_id
    assert {n.node_id for n in fetched.nodes} == {n.node_id for n in snapshot.nodes}
    assert {e.edge_id for e in fetched.edges} == {e.edge_id for e in snapshot.edges}
    assert snapshot in store.list_snapshots() or fetched in store.list_snapshots()


def test_get_snapshot_raises_not_found_for_unknown_id(store) -> None:
    with pytest.raises(NotFoundError):
        store.get_snapshot("does-not-exist")


def test_create_then_get_roundtrips(store) -> None:
    store.register_snapshot(_make_snapshot())
    req = _make_request("scen-shared-1")
    created = store.create(req)
    assert created.state == ScenarioState.DRAFT
    fetched = store.get("scen-shared-1")
    assert fetched.scenario_id == "scen-shared-1"
    assert fetched.snapshot_id == "snap-shared"
    assert fetched.seed == 42


def test_get_raises_not_found_for_unknown_scenario(store) -> None:
    with pytest.raises(NotFoundError):
        store.get("no-such-scenario")


def test_transition_enforces_lifecycle_validation(store) -> None:
    store.register_snapshot(_make_snapshot())
    store.create(_make_request("scen-shared-2"))

    # DRAFT -> READY directly is invalid; must go through VALIDATING.
    with pytest.raises(TransitionError):
        store.transition("scen-shared-2", ScenarioState.READY)

    valid = store.transition("scen-shared-2", ScenarioState.VALIDATING)
    assert valid.state == ScenarioState.VALIDATING

    ready = store.transition("scen-shared-2", ScenarioState.READY)
    assert ready.state == ScenarioState.READY

    # READY is not terminal-adjacent to FAILED.
    with pytest.raises(TransitionError):
        store.transition("scen-shared-2", ScenarioState.FAILED)


def test_transition_unknown_scenario_raises_not_found(store) -> None:
    with pytest.raises(NotFoundError):
        store.transition("no-such-scenario", ScenarioState.READY)


def test_delete_scenario_is_idempotent(store) -> None:
    store.register_snapshot(_make_snapshot())
    store.create(_make_request("scen-shared-3"))
    store.delete_scenario("scen-shared-3")
    with pytest.raises(NotFoundError):
        store.get("scen-shared-3")
    # Deleting again (or deleting something that never existed) must not raise.
    store.delete_scenario("scen-shared-3")
    store.delete_scenario("never-existed")


def test_run_and_record_persists_reproducible_bundle(store) -> None:
    """Acceptance: a run record's stored snapshot_id/engine_version/seed
    reproduce an identical result when replayed independently (`RW-FR-015`).
    """
    snapshot = _make_snapshot()
    store.register_snapshot(snapshot)
    store.create(_make_request("scen-shared-4"))

    run_result, latency_ms = store.run_and_record("scen-shared-4", severity=0.75)

    runs = store.list_runs("scen-shared-4")
    assert len(runs) == 1
    record = runs[0]
    assert record.snapshot_id == run_result.snapshot_id
    assert record.engine_version == run_result.engine_version
    assert record.seed == run_result.seed
    assert record.result == run_result

    fetched = store.get_run("scen-shared-4", record.run_id)
    assert fetched.result == run_result

    # Reproduce independently from the stored bundle: same snapshot + config +
    # seed + severity must propagate to the exact same result.
    config = store.get_config("scen-shared-4")
    replay_snapshot = store.get_snapshot(record.snapshot_id)
    factors = tuple(
        ShockFactor(
            factor_id=f["factor_id"],
            node_id=f["node_id"],
            magnitude=f["magnitude"] * record.severity,
        )
        for f in config["factors"]
    )
    replay_scenario = Scenario(scenario_id="scen-shared-4", factors=factors, seed=config["seed"])
    replayed = propagate(replay_snapshot, replay_scenario)

    assert replayed.engine_version == record.engine_version
    for node_id, impact in replayed.impacts.items():
        assert impact.raw_impact == run_result.impacts[node_id].raw_impact
        assert impact.risk_score == run_result.impacts[node_id].risk_score


def test_run_does_not_persist_a_record(store) -> None:
    """The plain (unpersisted) recompute used by read paths and the slider
    WebSocket must not write an audit row on every call (`RW-NFR-002`).
    """
    store.register_snapshot(_make_snapshot())
    store.create(_make_request("scen-shared-5"))
    store.run("scen-shared-5", severity=1.0)
    assert store.list_runs("scen-shared-5") == ()
