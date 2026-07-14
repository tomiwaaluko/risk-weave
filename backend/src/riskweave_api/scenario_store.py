"""Scenario/run/graph-snapshot store interface + in-memory implementation.

:class:`ScenarioStore` is the interface the REST layer and WebSocket handler
depend on; :class:`PostgresScenarioStore` (in ``postgres_scenario_store.py``)
implements the same interface against PostgreSQL so persistence is a storage
swap, not a routing change. :class:`InMemoryScenarioStore` remains the
fixture/test/offline-demo backend (RIS-30).
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from riskweave.explain import EdgeEvidence
from riskweave.explain.qa import QaAnswer
from riskweave.propagation import (
    ENGINE_VERSION,
    GraphSnapshot,
    PropagationResult,
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


@dataclass(frozen=True)
class RunRecord:
    """One persisted propagation run — an audit artifact (`RW-FR-015`)."""

    run_id: int
    scenario_id: str
    snapshot_id: str
    graph_version: str
    engine_version: str
    seed: int
    severity: float
    latency_ms: float
    result: RunResult
    created_at: str


class ScenarioStore(ABC):
    """Storage interface shared by the in-memory and PostgreSQL backends."""

    # ------------------------------------------------------------------
    # Snapshot management
    # ------------------------------------------------------------------

    @abstractmethod
    def register_snapshot(self, snapshot: GraphSnapshot) -> None: ...

    @abstractmethod
    def get_snapshot(self, snapshot_id: str) -> GraphSnapshot: ...

    @abstractmethod
    def list_snapshots(self) -> tuple[GraphSnapshot, ...]: ...

    @abstractmethod
    def register_provenance(
        self, snapshot_id: str, provenance_by_edge: dict[str, EdgeEvidence]
    ) -> None: ...

    @abstractmethod
    def get_provenance(self, snapshot_id: str) -> dict[str, EdgeEvidence]: ...

    # ------------------------------------------------------------------
    # Scenario lifecycle (RW-FR-009)
    # ------------------------------------------------------------------

    @abstractmethod
    def create(self, req: ScenarioCreateRequest) -> ScenarioRecord: ...

    @abstractmethod
    def get(self, scenario_id: str) -> ScenarioRecord: ...

    @abstractmethod
    def delete_scenario(self, scenario_id: str) -> None:
        """Remove a scenario and its config, if present. Idempotent."""

    @abstractmethod
    def transition(self, scenario_id: str, next_state: ScenarioState) -> ScenarioRecord: ...

    @abstractmethod
    def get_config(self, scenario_id: str) -> dict[str, Any]: ...

    # ------------------------------------------------------------------
    # Run-scoped Q&A sessions (RW-FR-024)
    # ------------------------------------------------------------------

    @abstractmethod
    def record_qa_session(self, answer: QaAnswer) -> None:
        """Persist a completed Q&A session so its audit log is retrievable."""

    @abstractmethod
    def get_qa_session(self, session_id: str) -> QaAnswer:
        """Return a recorded Q&A session, or raise :class:`NotFoundError`."""

    # ------------------------------------------------------------------
    # Run (propagate)
    # ------------------------------------------------------------------
    #
    # ``run`` is the plain, unpersisted recompute used by read paths (results,
    # impacts, paths, the live slider WebSocket) — it must stay cheap, since the
    # slider budget is <=500 ms per tick (`RW-NFR-002`) and a naive write on
    # every uncached tick would blow that budget. ``run_and_record`` is the
    # explicit "submit a run" path (`POST /scenarios/{id}/run` and the registry
    # run tools) that persists an audit record so it can be re-fetched after a
    # restart (`RW-FR-015`).

    @abstractmethod
    def list_runs(self, scenario_id: str) -> tuple[RunRecord, ...]:
        """Persisted runs for a scenario, newest first."""

    @abstractmethod
    def get_run(self, scenario_id: str, run_id: int) -> RunRecord: ...

    def _record_run(self, scenario_id: str, run_result: RunResult, latency_ms: float) -> RunRecord:
        """Persist a run record. Overridden by backends that store runs."""
        raise NotImplementedError

    def run_and_record(self, scenario_id: str, severity: float) -> tuple[RunResult, float]:
        """Run propagation and persist the result as an audit record."""
        run_result, latency_ms = self.run(scenario_id, severity)
        self._record_run(scenario_id, run_result, latency_ms)
        return run_result, latency_ms

    def propagate_scenario(
        self, scenario_id: str, severity: float
    ) -> tuple[PropagationResult, float]:
        """Run propagation and return the raw engine (result, latency_ms).

        Kept separate from :meth:`run` so callers that need the full engine
        result (e.g. explanation generation, RIS-19) get the un-serialized
        contributions with edge objects, not just the API projection.
        """
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
        return prop_result, latency_ms

    def run(self, scenario_id: str, severity: float) -> tuple[RunResult, float]:
        """Run propagation and return (result, latency_ms). Not persisted — see above."""
        prop_result, latency_ms = self.propagate_scenario(scenario_id, severity)
        run_result = propagation_result_to_run_result(prop_result, severity, latency_ms)
        return run_result, latency_ms


class InMemoryScenarioStore(ScenarioStore):
    """Thread-safe in-memory scenario registry (fixture/test/offline-demo backend)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, ScenarioRecord] = {}
        self._snapshots: dict[str, GraphSnapshot] = {}
        self._configs: dict[str, dict[str, Any]] = {}
        # snapshot_id -> {edge_id -> EdgeEvidence}; the pre-baked provenance an
        # explanation cites (RIS-19). Registered alongside the snapshot.
        self._provenance: dict[str, dict[str, EdgeEvidence]] = {}
        self._runs: dict[str, list[RunRecord]] = {}
        self._next_run_id = 1
        # session_id -> QaAnswer; the per-session run-scoped Q&A record, kept so
        # its tool-call audit log is retrievable per session (RIS-19, RW-FR-024).
        self._qa_sessions: dict[str, QaAnswer] = {}

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

    def list_snapshots(self) -> tuple[GraphSnapshot, ...]:
        with self._lock:
            return tuple(self._snapshots.values())

    def register_provenance(
        self, snapshot_id: str, provenance_by_edge: dict[str, EdgeEvidence]
    ) -> None:
        """Attach the per-edge provenance an explanation may cite (RIS-19)."""
        with self._lock:
            self._provenance[snapshot_id] = dict(provenance_by_edge)

    def get_provenance(self, snapshot_id: str) -> dict[str, EdgeEvidence]:
        """Per-edge provenance for a snapshot; empty if none was registered."""
        with self._lock:
            return dict(self._provenance.get(snapshot_id, {}))

    # ------------------------------------------------------------------
    # Run-scoped Q&A sessions (RW-FR-024)
    # ------------------------------------------------------------------

    def record_qa_session(self, answer: QaAnswer) -> None:
        """Persist a completed Q&A session so its audit log is retrievable."""
        with self._lock:
            self._qa_sessions[answer.session_id] = answer

    def get_qa_session(self, session_id: str) -> QaAnswer:
        """Return a recorded Q&A session, or raise :class:`NotFoundError`."""
        with self._lock:
            if session_id not in self._qa_sessions:
                raise NotFoundError(session_id)
            return self._qa_sessions[session_id]

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

    def delete_scenario(self, scenario_id: str) -> None:
        with self._lock:
            self._records.pop(scenario_id, None)
            self._configs.pop(scenario_id, None)
            self._runs.pop(scenario_id, None)

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

    def list_runs(self, scenario_id: str) -> tuple[RunRecord, ...]:
        with self._lock:
            return tuple(reversed(self._runs.get(scenario_id, [])))

    def get_run(self, scenario_id: str, run_id: int) -> RunRecord:
        with self._lock:
            for record in self._runs.get(scenario_id, []):
                if record.run_id == run_id:
                    return record
        raise NotFoundError(run_id)

    def _record_run(self, scenario_id: str, run_result: RunResult, latency_ms: float) -> RunRecord:
        with self._lock:
            run_id = self._next_run_id
            self._next_run_id += 1
            record = RunRecord(
                run_id=run_id,
                scenario_id=scenario_id,
                snapshot_id=run_result.snapshot_id,
                graph_version=run_result.graph_version,
                engine_version=run_result.engine_version,
                seed=run_result.seed,
                severity=run_result.severity,
                latency_ms=latency_ms,
                result=run_result,
                created_at=datetime.now(UTC).isoformat(),
            )
            self._runs.setdefault(scenario_id, []).append(record)
            return record
