"""Scenario lifecycle REST endpoints (RW-FR-009, RW-FR-015, RW-FR-020)."""

from __future__ import annotations

import contextlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from riskweave.scenario import ParsedScenario, ScenarioStatus, list_templates, parse_shock_text
from riskweave.scenario.presets import get_preset, list_presets
from riskweave.scenario.validation import validate_scenario as validate_structured_scenario
from riskweave_api.cache import get_cached, make_cache_key, set_cached
from riskweave_api.dependencies import get_redis, get_shock_parser, get_store
from riskweave_api.extraction.shock_parser import GeminiShockParser
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


class ParseScenarioRequest(BaseModel):
    text: str


class PresetOut(BaseModel):
    """A clickable preset shock prompt (reduced RIS-18 demo path)."""

    preset_id: str
    label: str
    prompt_text: str


class PresetParseResponse(BaseModel):
    """A parsed preset plus the provenance of how it was produced."""

    preset_id: str
    source: str
    model_alias: str
    prompt_version: str
    attempts: int
    fallback_reason: str | None
    scenario: ParsedScenario


def _scenario_config_json(req: ScenarioCreateRequest) -> str:
    payload = {
        "scenario_id": req.scenario_id,
        "snapshot_id": req.snapshot_id,
        "graph_version": req.graph_version,
        "factors": [f.model_dump() for f in req.factors],
        "seed": req.seed,
    }
    return json.dumps(payload, sort_keys=True)


@router.get("/templates", response_model=tuple[ParsedScenario, ...])
def scenario_templates() -> tuple[ParsedScenario, ...]:
    """Return editable, prevalidated CRE and oil demo templates (`RW-FR-002`)."""
    return list_templates()


@router.post("/parse", response_model=ParsedScenario)
def parse_scenario(req: ParseScenarioRequest) -> ParsedScenario:
    """Parse untrusted natural-language shock text into a reviewable scenario."""
    return parse_shock_text(req.text)


@router.get("/presets", response_model=list[PresetOut])
def scenario_presets() -> list[PresetOut]:
    """List the clickable preset shock prompts (`RW-FR-002`, reduced RIS-18)."""
    return [
        PresetOut(preset_id=p.preset_id, label=p.label, prompt_text=p.prompt_text)
        for p in list_presets()
    ]


@router.post("/presets/{preset_id}/parse", response_model=PresetParseResponse)
def parse_preset_endpoint(
    preset_id: str,
    parser: GeminiShockParser = Depends(get_shock_parser),
) -> PresetParseResponse:
    """Parse a preset through a real Gemini structured call, with committed fallback.

    Gemini finds the factors already written in the trusted sentence and echoes
    magnitudes verbatim (`RW-AI-010`); a schema-invalid or non-verbatim response
    retries once then falls back to the committed pre-parse so the demo never
    white-screens.
    """
    try:
        preset = get_preset(preset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown preset") from exc
    result = parser.parse_preset(preset)
    return PresetParseResponse(
        preset_id=preset_id,
        source=result.source,
        model_alias=result.model_alias,
        prompt_version=result.prompt_version,
        attempts=result.attempts,
        fallback_reason=result.fallback_reason,
        scenario=result.scenario,
    )


@router.post("/review/validate", response_model=ParsedScenario)
def validate_review_scenario(scenario: ParsedScenario) -> ParsedScenario:
    """Revalidate edited structured factors without re-invoking parsing (`RW-FR-005`)."""
    validation = validate_structured_scenario(scenario)
    return scenario.model_copy(update={"validation": validation, "status": validation.status})


@router.post("/review/run")
def run_review_scenario(scenario: ParsedScenario) -> dict[str, str | bool]:
    """Gate reviewed scenario execution on deterministic validation (`RW-FR-004`)."""
    validation = validate_structured_scenario(scenario)
    accepted = scenario.status is ScenarioStatus.READY and validation.status is ScenarioStatus.READY
    return {"scenario_id": scenario.scenario_id, "accepted": accepted}


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
