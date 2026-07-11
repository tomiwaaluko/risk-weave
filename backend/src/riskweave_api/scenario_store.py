"""In-memory scenario and graph-snapshot store.

A real implementation persists to PostgreSQL; this module provides the same
interface so the REST layer and WebSocket handler are decoupled from storage.
The in-memory store is sufficient for demo and test use. Replace the store
fixture/dependency when the DB layer is wired.
"""

from __future__ import annotations

import threading
from typing import Any

from riskweave.propagation import (
    ENGINE_VERSION,
    GraphSnapshot,
    Scenario,
    ShockFactor,
    propagate,
)

from .models import (
    RunResult,
    ScenarioCreateRequest,
    ScenarioRecord,
    ScenarioState,
    validate_transition,
)
from .result_conversion import propagation_result_to_run_result


class NotFoundError(KeyError):
    pass


class TransitionError(ValueError):
    pass


class ScenarioStore:
    """Thread-safe in-memory scenario registry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, ScenarioRecord] = {}
        self._snapshots: dict[str, GraphSnapshot] = {}
        self._configs: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Snapshot management
    # ------------------------------------------------------------------

    def register_snapshot(self, snapshot: GraphSnapshot) -> None:
        with self._lock:
            self._snapshots[snapshot.snapshot_id] = snapshot

    def get_snapshot(self, snapshot_id: str) -> GraphSnapshot:
        with self._lock:
            if snapshot_id not in self._snapshots:
                raise NotFoundError(snapshot_id)
            return self._snapshots[snapshot_id]

    # ------------------------------------------------------------------
    # Scenario lifecycle (RW-FR-009)
    # ------------------------------------------------------------------

    def create(self, req: ScenarioCreateRequest) -> ScenarioRecord:
        record = ScenarioRecord(
            scenario_id=req.scenario_id,
            snapshot_id=req.snapshot_id,
            graph_version=req.graph_version,
            engine_version=ENGINE_VERSION,
            seed=req.seed,
            config=req.config,
            state=ScenarioState.DRAFT,
        )
        with self._lock:
            self._records[req.scenario_id] = record
            self._configs[req.scenario_id] = {
                "factors": [f.model_dump() for f in req.factors],
                "seed": req.seed,
            }
        return record

    def get(self, scenario_id: str) -> ScenarioRecord:
        with self._lock:
            if scenario_id not in self._records:
                raise NotFoundError(scenario_id)
            return self._records[scenario_id]

    def transition(self, scenario_id: str, next_state: ScenarioState) -> ScenarioRecord:
        with self._lock:
            if scenario_id not in self._records:
                raise NotFoundError(scenario_id)
            record = self._records[scenario_id]
            try:
                validate_transition(record.state, next_state)
            except ValueError as exc:
                raise TransitionError(str(exc)) from exc
            updated = record.model_copy(update={"state": next_state})
            self._records[scenario_id] = updated
            return updated

    def get_config(self, scenario_id: str) -> dict[str, Any]:
        with self._lock:
            if scenario_id not in self._configs:
                raise NotFoundError(scenario_id)
            return self._configs[scenario_id]

    # ------------------------------------------------------------------
    # Run (propagate)
    # ------------------------------------------------------------------

    def run(self, scenario_id: str, severity: float) -> tuple[RunResult, float]:
        """Run propagation and return (result, latency_ms)."""
        import time

        record = self.get(scenario_id)
        snapshot = self.get_snapshot(record.snapshot_id)
        config = self.get_config(scenario_id)

        factors = tuple(
            ShockFactor(
                factor_id=f["factor_id"],
                node_id=f["node_id"],
                magnitude=f["magnitude"] * severity,
            )
            for f in config["factors"]
        )
        scenario = Scenario(
            scenario_id=scenario_id,
            factors=factors,
            seed=config["seed"],
        )

        t0 = time.perf_counter()
        prop_result = propagate(snapshot, scenario)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        run_result = propagation_result_to_run_result(prop_result, severity, latency_ms)
        return run_result, latency_ms
