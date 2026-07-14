"""PostgreSQL-backed :class:`ScenarioStore` (RIS-30).

Implements the exact interface :mod:`scenario_store` defines so the REST
routers and WebSocket handler are unchanged by the storage swap. Every method
opens a short-lived session — there is no engine-wide caching — so scenarios,
runs, and graph snapshots survive process restarts (`RW-FR-009`, `RW-FR-015`).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from riskweave.explain import EdgeEvidence
from riskweave.propagation import ENGINE_VERSION, GraphEdge, GraphNode, GraphSnapshot

from .db_models import ScenarioRun, StoredGraphSnapshot, StoredScenario
from .models import (
    RunResult,
    ScenarioCreateRequest,
    ScenarioRecord,
    ScenarioState,
    validate_transition,
)
from .scenario_store import NotFoundError, RunRecord, ScenarioStore, TransitionError


class PostgresScenarioStore(ScenarioStore):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Snapshot management
    # ------------------------------------------------------------------

    def register_snapshot(self, snapshot: GraphSnapshot) -> None:
        nodes_json = [asdict(n) for n in snapshot.nodes]
        edges_json = [asdict(e) for e in snapshot.edges]
        with self._session_factory() as session:
            stmt = pg_insert(StoredGraphSnapshot).values(
                snapshot_id=snapshot.snapshot_id,
                graph_version=snapshot.graph_version,
                nodes_json=nodes_json,
                edges_json=edges_json,
                provenance_json={},
                created_at=datetime.now(UTC),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["snapshot_id"],
                set_={
                    "graph_version": stmt.excluded.graph_version,
                    "nodes_json": stmt.excluded.nodes_json,
                    "edges_json": stmt.excluded.edges_json,
                },
            )
            session.execute(stmt)
            session.commit()

    def get_snapshot(self, snapshot_id: str) -> GraphSnapshot:
        with self._session_factory() as session:
            row = session.get(StoredGraphSnapshot, snapshot_id)
            if row is None:
                raise NotFoundError(snapshot_id)
            return _snapshot_from_row(row)

    def list_snapshots(self) -> tuple[GraphSnapshot, ...]:
        with self._session_factory() as session:
            rows = session.scalars(select(StoredGraphSnapshot)).all()
            return tuple(_snapshot_from_row(row) for row in rows)

    def register_provenance(
        self, snapshot_id: str, provenance_by_edge: dict[str, EdgeEvidence]
    ) -> None:
        provenance_json = {edge_id: asdict(ev) for edge_id, ev in provenance_by_edge.items()}
        with self._session_factory() as session:
            row = session.get(StoredGraphSnapshot, snapshot_id)
            if row is None:
                raise NotFoundError(snapshot_id)
            row.provenance_json = provenance_json
            session.commit()

    def get_provenance(self, snapshot_id: str) -> dict[str, EdgeEvidence]:
        with self._session_factory() as session:
            row = session.get(StoredGraphSnapshot, snapshot_id)
            if row is None:
                return {}
            return {
                edge_id: EdgeEvidence(**fields) for edge_id, fields in row.provenance_json.items()
            }

    # ------------------------------------------------------------------
    # Scenario lifecycle (RW-FR-009)
    # ------------------------------------------------------------------

    def create(self, req: ScenarioCreateRequest) -> ScenarioRecord:
        now = datetime.now(UTC)
        factors_json = [f.model_dump() for f in req.factors]
        with self._session_factory() as session:
            stmt = pg_insert(StoredScenario).values(
                scenario_id=req.scenario_id,
                snapshot_id=req.snapshot_id,
                graph_version=req.graph_version,
                engine_version=ENGINE_VERSION,
                seed=req.seed,
                state=ScenarioState.DRAFT.value,
                config_json=req.config,
                factors_json=factors_json,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["scenario_id"],
                set_={
                    "snapshot_id": stmt.excluded.snapshot_id,
                    "graph_version": stmt.excluded.graph_version,
                    "engine_version": stmt.excluded.engine_version,
                    "seed": stmt.excluded.seed,
                    "state": stmt.excluded.state,
                    "config_json": stmt.excluded.config_json,
                    "factors_json": stmt.excluded.factors_json,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            session.execute(stmt)
            session.commit()
            row = session.get(StoredScenario, req.scenario_id)
            return _record_from_row(row)

    def get(self, scenario_id: str) -> ScenarioRecord:
        with self._session_factory() as session:
            row = session.get(StoredScenario, scenario_id)
            if row is None:
                raise NotFoundError(scenario_id)
            return _record_from_row(row)

    def delete_scenario(self, scenario_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(StoredScenario, scenario_id)
            if row is not None:
                session.query(ScenarioRun).filter(ScenarioRun.scenario_id == scenario_id).delete()
                session.delete(row)
                session.commit()

    def transition(self, scenario_id: str, next_state: ScenarioState) -> ScenarioRecord:
        with self._session_factory() as session:
            row = session.get(StoredScenario, scenario_id)
            if row is None:
                raise NotFoundError(scenario_id)
            current = ScenarioState(row.state)
            try:
                validate_transition(current, next_state)
            except ValueError as exc:
                raise TransitionError(str(exc)) from exc
            row.state = next_state.value
            row.updated_at = datetime.now(UTC)
            session.commit()
            return _record_from_row(row)

    def get_config(self, scenario_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.get(StoredScenario, scenario_id)
            if row is None:
                raise NotFoundError(scenario_id)
            return {"factors": row.factors_json, "seed": row.seed}

    # ------------------------------------------------------------------
    # Run (propagate) — persisted audit records
    # ------------------------------------------------------------------

    def list_runs(self, scenario_id: str) -> tuple[RunRecord, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ScenarioRun)
                .where(ScenarioRun.scenario_id == scenario_id)
                .order_by(ScenarioRun.id.desc())
            ).all()
            return tuple(_run_record_from_row(row) for row in rows)

    def get_run(self, scenario_id: str, run_id: int) -> RunRecord:
        with self._session_factory() as session:
            row = session.get(ScenarioRun, run_id)
            if row is None or row.scenario_id != scenario_id:
                raise NotFoundError(run_id)
            return _run_record_from_row(row)

    def _record_run(self, scenario_id: str, run_result: RunResult, latency_ms: float) -> RunRecord:
        with self._session_factory() as session:
            row = ScenarioRun(
                scenario_id=scenario_id,
                snapshot_id=run_result.snapshot_id,
                graph_version=run_result.graph_version,
                engine_version=run_result.engine_version,
                seed=run_result.seed,
                severity=run_result.severity,
                latency_ms=latency_ms,
                result_json=run_result.model_dump(),
                created_at=datetime.now(UTC),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _run_record_from_row(row)


def _snapshot_from_row(row: StoredGraphSnapshot) -> GraphSnapshot:
    nodes = tuple(GraphNode(**fields) for fields in row.nodes_json)
    edges = tuple(GraphEdge(**fields) for fields in row.edges_json)
    return GraphSnapshot(
        snapshot_id=row.snapshot_id,
        graph_version=row.graph_version,
        nodes=nodes,
        edges=edges,
    )


def _record_from_row(row: StoredScenario) -> ScenarioRecord:
    return ScenarioRecord(
        scenario_id=row.scenario_id,
        snapshot_id=row.snapshot_id,
        graph_version=row.graph_version,
        engine_version=row.engine_version,
        seed=row.seed,
        config=row.config_json,
        state=ScenarioState(row.state),
    )


def _run_record_from_row(row: ScenarioRun) -> RunRecord:
    return RunRecord(
        run_id=row.id,
        scenario_id=row.scenario_id,
        snapshot_id=row.snapshot_id,
        graph_version=row.graph_version,
        engine_version=row.engine_version,
        seed=row.seed,
        severity=row.severity,
        latency_ms=row.latency_ms,
        result=RunResult(**row.result_json),
        created_at=row.created_at.isoformat(),
    )
