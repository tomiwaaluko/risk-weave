from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from riskweave.propagation import GraphSnapshot, Scenario, ShockFactor
from riskweave_api.models import ScenarioCreateRequest, ScenarioState


@dataclass(frozen=True)
class ScenarioRecord:
    scenario: Scenario
    snapshot_id: str
    graph_version: str
    state: ScenarioState


class ScenarioStore:
    """In-memory scenario lifecycle store until RIS-14 persistence lands."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._snapshots: dict[str, GraphSnapshot] = {}
        self._records: dict[str, ScenarioRecord] = {}
        self._configs: dict[str, ScenarioCreateRequest] = {}

    def register_snapshot(self, snapshot: GraphSnapshot) -> None:
        with self._lock:
            self._snapshots[snapshot.snapshot_id] = snapshot

    def create(self, request: ScenarioCreateRequest) -> ScenarioRecord:
        with self._lock:
            if request.snapshot_id not in self._snapshots:
                raise KeyError(f"unknown snapshot {request.snapshot_id!r}")
            scenario = Scenario(
                scenario_id=request.scenario_id,
                factors=tuple(
                    ShockFactor(
                        factor_id=factor.factor_id,
                        node_id=factor.node_id,
                        magnitude=factor.magnitude,
                    )
                    for factor in request.factors
                ),
                seed=request.seed,
            )
            record = ScenarioRecord(
                scenario=scenario,
                snapshot_id=request.snapshot_id,
                graph_version=request.graph_version,
                state=ScenarioState.DRAFT,
            )
            self._records[request.scenario_id] = record
            self._configs[request.scenario_id] = request
            return record

    def get(self, scenario_id: str) -> ScenarioRecord:
        with self._lock:
            return self._records[scenario_id]

    def get_snapshot(self, snapshot_id: str) -> GraphSnapshot:
        with self._lock:
            return self._snapshots[snapshot_id]

    def transition(self, scenario_id: str, state: ScenarioState) -> ScenarioRecord:
        with self._lock:
            record = self._records[scenario_id]
            next_record = ScenarioRecord(
                scenario=record.scenario,
                snapshot_id=record.snapshot_id,
                graph_version=record.graph_version,
                state=state,
            )
            self._records[scenario_id] = next_record
            return next_record
