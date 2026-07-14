"""RIS-30: scenarios/runs/snapshots survive a simulated backend restart.

Skipped without a live TEST_DATABASE_URL (same convention as
test_postgres_ingestion.py). A "restart" is simulated by throwing away the
PostgresScenarioStore instance (and its session factory) and building a brand
new one against the same database — nothing may be cached in the process.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from riskweave.propagation import GraphEdge, GraphNode, GraphSnapshot
from riskweave_api.ingestion.database import session_factory
from riskweave_api.models import ScenarioCreateRequest, ScenarioState, ShockFactorIn
from riskweave_api.postgres_scenario_store import PostgresScenarioStore

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for PostgreSQL persistence integration tests",
)


def _make_snapshot() -> GraphSnapshot:
    nodes = (
        GraphNode(node_id="bank-a", node_type="bank", name="Bank Alpha"),
        GraphNode(node_id="bank-b", node_type="bank", name="Bank Beta"),
    )
    edges = (
        GraphEdge(
            edge_id="e1",
            source_id="bank-a",
            target_id="bank-b",
            weight=0.5,
            method_id="DER-CREDIT",
            provenance_ref="prov:001",
        ),
    )
    return GraphSnapshot(snapshot_id="snap-restart", graph_version="v1", nodes=nodes, edges=edges)


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    sf = session_factory(TEST_DATABASE_URL)
    with sf() as session:
        session.execute(text("DELETE FROM scenario_runs"))
        session.execute(text("DELETE FROM stored_scenarios"))
        session.execute(text("DELETE FROM stored_graph_snapshots"))
        session.commit()


def test_scenario_and_run_survive_a_restart() -> None:
    before = PostgresScenarioStore(session_factory(TEST_DATABASE_URL))
    before.register_snapshot(_make_snapshot())
    before.create(
        ScenarioCreateRequest(
            scenario_id="scen-restart",
            snapshot_id="snap-restart",
            graph_version="v1",
            factors=[ShockFactorIn(factor_id="f1", node_id="bank-a", magnitude=1.0)],
            seed=7,
        )
    )
    before.transition("scen-restart", ScenarioState.VALIDATING)
    before.transition("scen-restart", ScenarioState.READY)
    run_result, _ = before.run_and_record("scen-restart", severity=1.0)

    # Simulate a process restart: a brand new store, new session factory, no
    # shared process state whatsoever.
    after = PostgresScenarioStore(session_factory(TEST_DATABASE_URL))

    record = after.get("scen-restart")
    assert record.state == ScenarioState.READY
    assert record.snapshot_id == "snap-restart"
    assert record.seed == 7

    snapshot = after.get_snapshot("snap-restart")
    assert {n.node_id for n in snapshot.nodes} == {"bank-a", "bank-b"}

    runs = after.list_runs("scen-restart")
    assert len(runs) == 1
    assert runs[0].result == run_result

    # Recomputing from the persisted snapshot + scenario is deterministic and
    # bit-identical, aside from the freshly-measured latency (`RW-NFR-002`).
    replayed_result, _ = after.run("scen-restart", severity=1.0)
    assert replayed_result.model_dump(exclude={"latency_ms"}) == run_result.model_dump(
        exclude={"latency_ms"}
    )
