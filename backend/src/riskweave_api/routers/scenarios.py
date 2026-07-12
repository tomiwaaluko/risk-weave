"""Scenario lifecycle REST endpoints (RW-FR-009, RW-FR-015, RW-FR-020)."""

from __future__ import annotations

import contextlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from riskweave.explain import (
    ExplanationTransport,
    build_node_context,
    generate_node_explanation,
)
from riskweave.scenario import ParsedScenario, ScenarioStatus, list_templates, parse_shock_text
from riskweave.scenario.validation import validate_scenario as validate_structured_scenario
from riskweave_api.cache import get_cached, make_cache_key, set_cached
from riskweave_api.dependencies import get_explanation_transport, get_redis, get_store
from riskweave_api.models import (
    CitationOut,
    ExplanationOut,
    NodeImpactOut,
    RunRequest,
    RunResult,
    ScenarioCreateRequest,
    ScenarioRecord,
    ScenarioState,
    StructuredNumberOut,
)
from riskweave_api.scenario_store import NotFoundError, ScenarioStore, TransitionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


class ParseScenarioRequest(BaseModel):
    text: str


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


@router.get("/{scenario_id}/explanation/{node_id}", response_model=ExplanationOut)
def explain_node(
    scenario_id: str,
    node_id: str,
    severity: float = 1.0,
    store: ScenarioStore = Depends(get_store),
    transport: ExplanationTransport = Depends(get_explanation_transport),
) -> ExplanationOut:
    """Generate a guarded, evidence-bound explanation of one node's impact.

    Gemini writes the prose from the computation payload + pre-baked provenance;
    the deterministic numeric-containment guard (`RW-AI-011`) rejects any prose
    introducing an unbacked number, regenerating once before falling back to
    labeled verified figures. No number here ever originates from Gemini.
    """
    try:
        record = store.get(scenario_id)
        result, _ = store.propagate_scenario(scenario_id, severity)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="scenario or snapshot not found") from exc

    if node_id not in result.impacts:
        raise HTTPException(
            status_code=404, detail="node not impacted at this severity or not found"
        )

    snapshot = store.get_snapshot(record.snapshot_id)
    node_names = {n.node_id: n.name for n in snapshot.nodes}
    node_types = {n.node_id: n.node_type for n in snapshot.nodes}
    provenance = store.get_provenance(record.snapshot_id)

    context, payload = build_node_context(
        result,
        node_id,
        node_name=node_names.get(node_id, node_id),
        node_type=node_types.get(node_id, "entity"),
        provenance_by_edge=provenance,
        node_names=node_names,
    )

    try:
        generated = generate_node_explanation(context, payload, transport)
    except Exception as exc:  # transport/network failure — surface, don't crash the demo
        logger.warning("explanation generation failed for %s/%s: %s", scenario_id, node_id, exc)
        raise HTTPException(status_code=502, detail="explanation provider unavailable") from exc

    return ExplanationOut(
        node_id=generated.node_id,
        node_name=context.node_name,
        prose=generated.prose,
        used_fallback=generated.used_fallback,
        attempts=generated.attempts,
        guard_violations=list(generated.guard_violations),
        model=generated.model,
        citations=[
            CitationOut(
                citation_id=c.citation_id,
                edge_id=c.edge_id,
                source_name=c.source_name,
                target_name=c.target_name,
                relationship_type=c.relationship_type,
                method_id=c.method_id,
                source_document_id=c.source_document_id,
                source_passage=c.source_passage,
                char_start=c.char_start,
                char_end=c.char_end,
                filing_date=c.filing_date,
                data_timestamp=c.data_timestamp,
                extraction_confidence=c.extraction_confidence,
            )
            for c in generated.citations
        ],
        structured_numbers=[
            StructuredNumberOut(label=s.label, value=s.value, citation_ids=list(s.citation_ids))
            for s in generated.structured_numbers
        ],
    )


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
