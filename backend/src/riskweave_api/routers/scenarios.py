"""Scenario lifecycle REST endpoints (RW-FR-009, RW-FR-015, RW-FR-020)."""

from __future__ import annotations

import contextlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from riskweave_api.cache import get_cached, make_cache_key, set_cached
from riskweave_api.dependencies import get_redis, get_store
from riskweave_api.models import (
    NodeImpactOut,
    RunRequest,
    RunResult,
    ScenarioCreateRequest,
    ScenarioRecord,
    ScenarioState,
)
from riskweave_api.scenario_store import NotFoundError, ScenarioStore, TransitionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _scenario_config_json(req: ScenarioCreateRequest) -> str:
    payload = {
        "scenario_id": req.scenario_id,
        "snapshot_id": req.snapshot_id,
        "graph_version": req.graph_version,
        "factors": [f.model_dump() for f in req.factors],
        "seed": req.seed,
    }
    return json.dumps(payload, sort_keys=True)


@router.post("", response_model=ScenarioRecord, status_code=status.HTTP_201_CREATED)
def create_scenario(
    req: ScenarioCreateRequest,
    store: ScenarioStore = Depends(get_store),
) -> ScenarioRecord:
    record = store.create(req)
    return record


@router.get("/{scenario_id}", response_model=ScenarioRecord)
def get_scenario(
    scenario_id: str,
    store: ScenarioStore = Depends(get_store),
) -> ScenarioRecord:
    try:
        return store.get(scenario_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="scenario not found") from exc


@router.post("/{scenario_id}/validate", response_model=ScenarioRecord)
def validate_scenario(
    scenario_id: str,
    store: ScenarioStore = Depends(get_store),
) -> ScenarioRecord:
    try:
        record = store.transition(scenario_id, ScenarioState.VALIDATING)
        record = store.transition(scenario_id, ScenarioState.READY)
        return record
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="scenario not found") from exc
    except TransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{scenario_id}/run", response_model=RunResult)
async def run_scenario(
    scenario_id: str,
    body: RunRequest = RunRequest(),
    store: ScenarioStore = Depends(get_store),
    redis=Depends(get_redis),
) -> RunResult:
    try:
        record = store.get(scenario_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="scenario not found") from exc

    if record.state not in {ScenarioState.READY, ScenarioState.COMPLETED}:
        raise HTTPException(
            status_code=409,
            detail=f"scenario must be READY or COMPLETED to run; current state: {record.state}",
        )

    config = store.get_config(scenario_id)
    cache_key = make_cache_key(
        record.snapshot_id,
        record.graph_version,
        json.dumps(config, sort_keys=True),
        body.severity,
    )

    if redis is not None:
        cached = await get_cached(redis, cache_key)
        if cached is not None:
            logger.debug("cache hit for %s", cache_key)
            return cached

    try:
        store.transition(scenario_id, ScenarioState.QUEUED)
        store.transition(scenario_id, ScenarioState.RUNNING)
        run_result, latency_ms = store.run(scenario_id, body.severity)
        store.transition(scenario_id, ScenarioState.COMPLETED)
    except (NotFoundError, TransitionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        with contextlib.suppress(Exception):
            store.transition(scenario_id, ScenarioState.FAILED)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info(
        "recompute p50 %.1f ms scenario=%s severity=%.2f", latency_ms, scenario_id, body.severity
    )

    if redis is not None:
        await set_cached(redis, cache_key, run_result)

    return run_result


@router.get("/{scenario_id}/results", response_model=RunResult)
async def get_results(
    scenario_id: str,
    severity: float = 1.0,
    store: ScenarioStore = Depends(get_store),
    redis=Depends(get_redis),
) -> RunResult:
    try:
        record = store.get(scenario_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="scenario not found") from exc

    config = store.get_config(scenario_id)
    cache_key = make_cache_key(
        record.snapshot_id,
        record.graph_version,
        json.dumps(config, sort_keys=True),
        severity,
    )

    if redis is not None:
        cached = await get_cached(redis, cache_key)
        if cached is not None:
            return cached

    run_result, _ = store.run(scenario_id, severity)
    return run_result


@router.get("/{scenario_id}/impacts", response_model=list[NodeImpactOut])
async def ranked_impacts(
    scenario_id: str,
    severity: float = 1.0,
    store: ScenarioStore = Depends(get_store),
    redis=Depends(get_redis),
) -> list[NodeImpactOut]:
    result = await get_results(scenario_id, severity, store, redis)
    return [result.impacts[eid] for eid in result.ranked_entity_ids if eid in result.impacts]


@router.get("/{scenario_id}/paths/{node_id}", response_model=list[dict])
async def paths_for_entity(
    scenario_id: str,
    node_id: str,
    severity: float = 1.0,
    store: ScenarioStore = Depends(get_store),
    redis=Depends(get_redis),
) -> list[dict]:
    result = await get_results(scenario_id, severity, store, redis)
    impact = result.impacts.get(node_id)
    if impact is None:
        raise HTTPException(status_code=404, detail="node not impacted or not found")
    return [c.model_dump() for c in impact.contributions]
