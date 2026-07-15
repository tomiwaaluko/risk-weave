"""Scenario lifecycle REST endpoints (RW-FR-009, RW-FR-015, RW-FR-020)."""

from __future__ import annotations

import contextlib
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from riskweave.explain import (
    Audience,
    ExplanationTransport,
    QaAnswer,
    QaToolTransport,
    RunToolContext,
    answer_question,
    build_node_context,
    build_registry,
    generate_node_explanation,
    payload_for_run,
)
from riskweave.scenario import ParsedScenario, ScenarioStatus, list_templates, parse_shock_text
from riskweave.scenario.presets import get_preset, list_presets
from riskweave.scenario.validation import validate_scenario as validate_structured_scenario
from riskweave_api.accounting.service import GeminiAccountingService
from riskweave_api.cache import get_cached, make_cache_key, set_cached
from riskweave_api.dependencies import (
    get_accounting,
    get_accounting_session_factory,
    get_explanation_transport,
    get_qa_transport,
    get_redis,
    get_shock_parser,
    get_store,
)
from riskweave_api.extraction.shock_parser import GeminiShockParser
from riskweave_api.models import (
    CitationOut,
    ExplanationOut,
    NodeImpactOut,
    QaAnswerOut,
    QaRequest,
    RunRequest,
    RunResult,
    RunSummaryOut,
    ScenarioCreateRequest,
    ScenarioRecord,
    ScenarioState,
    StructuredNumberOut,
    ToolCallAuditOut,
)
from riskweave_api.observability.metrics import (
    EXPLANATION_GENERATION,
    PROPAGATION_RECOMPUTE,
    SCENARIO_PARSE,
    latency_timer,
    record_latency,
)
from riskweave_api.scenario_store import NotFoundError, ScenarioStore, TransitionError
from riskweave_api.security import default_rate_limit, gemini_rate_limit, require_api_key

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


class FreeformParseResponse(BaseModel):
    """A freeform NL parse plus the provenance of how it was produced."""

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


@router.get(
    "/templates",
    response_model=tuple[ParsedScenario, ...],
    dependencies=[Depends(default_rate_limit)],
)
def scenario_templates() -> tuple[ParsedScenario, ...]:
    """Return editable, prevalidated CRE and oil demo templates (`RW-FR-002`)."""
    return list_templates()


@router.post("/parse", response_model=ParsedScenario, dependencies=[Depends(default_rate_limit)])
def parse_scenario(req: ParseScenarioRequest) -> ParsedScenario:
    """Parse shock text deterministically into a reviewable scenario (no Gemini call)."""
    return parse_shock_text(req.text)


@router.post(
    "/parse/live",
    response_model=FreeformParseResponse,
    dependencies=[Depends(require_api_key), Depends(gemini_rate_limit)],
)
def parse_scenario_live(
    req: ParseScenarioRequest,
    parser: GeminiShockParser = Depends(get_shock_parser),
) -> FreeformParseResponse:
    """Parse untrusted freeform NL shock text via live Gemini Pro (`RW-FR-001`).

    The user's text is treated as data, never instructions (`RW-SEC-003`);
    magnitudes are echoed verbatim (`RW-AI-010`). Unsupported or malformed input
    is returned as an INVALID scenario with explained issues (`RW-FR-007`) rather
    than forced to READY; only a transport/schema integrity failure falls back to
    the committed deterministic parse.
    """
    with latency_timer(SCENARIO_PARSE):
        result = parser.parse_freeform(req.text)
    return FreeformParseResponse(
        source=result.source,
        model_alias=result.model_alias,
        prompt_version=result.prompt_version,
        attempts=result.attempts,
        fallback_reason=result.fallback_reason,
        scenario=result.scenario,
    )


@router.get("/presets", response_model=list[PresetOut], dependencies=[Depends(default_rate_limit)])
def scenario_presets() -> list[PresetOut]:
    """List the clickable preset shock prompts (`RW-FR-002`, reduced RIS-18)."""
    return [
        PresetOut(preset_id=p.preset_id, label=p.label, prompt_text=p.prompt_text)
        for p in list_presets()
    ]


@router.post(
    "/presets/{preset_id}/parse",
    response_model=PresetParseResponse,
    dependencies=[Depends(require_api_key), Depends(gemini_rate_limit)],
)
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
    with latency_timer(SCENARIO_PARSE):
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


@router.post(
    "/review/validate",
    response_model=ParsedScenario,
    dependencies=[Depends(default_rate_limit)],
)
def validate_review_scenario(scenario: ParsedScenario) -> ParsedScenario:
    """Revalidate edited structured factors without re-invoking parsing (`RW-FR-005`)."""
    validation = validate_structured_scenario(scenario)
    return scenario.model_copy(update={"validation": validation, "status": validation.status})


@router.post("/review/run", dependencies=[Depends(default_rate_limit)])
def run_review_scenario(scenario: ParsedScenario) -> dict[str, str | bool]:
    """Gate reviewed scenario execution on deterministic validation (`RW-FR-004`)."""
    validation = validate_structured_scenario(scenario)
    accepted = scenario.status is ScenarioStatus.READY and validation.status is ScenarioStatus.READY
    return {"scenario_id": scenario.scenario_id, "accepted": accepted}


@router.post(
    "",
    response_model=ScenarioRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key), Depends(default_rate_limit)],
)
def create_scenario(
    req: ScenarioCreateRequest,
    store: ScenarioStore = Depends(get_store),
) -> ScenarioRecord:
    record = store.create(req)
    return record


@router.get(
    "/{scenario_id}", response_model=ScenarioRecord, dependencies=[Depends(default_rate_limit)]
)
def get_scenario(
    scenario_id: str,
    store: ScenarioStore = Depends(get_store),
) -> ScenarioRecord:
    try:
        return store.get(scenario_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="scenario not found") from exc


@router.post(
    "/{scenario_id}/validate",
    response_model=ScenarioRecord,
    dependencies=[Depends(require_api_key), Depends(default_rate_limit)],
)
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


@router.post(
    "/{scenario_id}/run",
    response_model=RunResult,
    dependencies=[Depends(require_api_key), Depends(default_rate_limit)],
)
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
        run_result, latency_ms = store.run_and_record(scenario_id, body.severity)
        store.transition(scenario_id, ScenarioState.COMPLETED)
    except (NotFoundError, TransitionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        with contextlib.suppress(Exception):
            store.transition(scenario_id, ScenarioState.FAILED)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    record_latency(PROPAGATION_RECOMPUTE, latency_ms)
    logger.info(
        "recompute p50 %.1f ms scenario=%s severity=%.2f", latency_ms, scenario_id, body.severity
    )

    if redis is not None:
        await set_cached(redis, cache_key, run_result)

    return run_result


@router.get(
    "/{scenario_id}/results",
    response_model=RunResult,
    dependencies=[Depends(default_rate_limit)],
)
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


@router.get(
    "/{scenario_id}/runs",
    response_model=list[RunSummaryOut],
    dependencies=[Depends(default_rate_limit)],
)
def list_scenario_runs(
    scenario_id: str,
    store: ScenarioStore = Depends(get_store),
) -> list[RunSummaryOut]:
    """List persisted runs for a scenario, newest first (`RW-FR-015`).

    A run re-fetched here after a process restart is byte-identical to what
    was returned at run time — the point of persisting it (RIS-30).
    """
    return [
        RunSummaryOut(
            run_id=r.run_id,
            scenario_id=r.scenario_id,
            snapshot_id=r.snapshot_id,
            graph_version=r.graph_version,
            engine_version=r.engine_version,
            seed=r.seed,
            severity=r.severity,
            latency_ms=r.latency_ms,
            created_at=r.created_at,
        )
        for r in store.list_runs(scenario_id)
    ]


@router.get(
    "/{scenario_id}/runs/{run_id}",
    response_model=RunResult,
    dependencies=[Depends(default_rate_limit)],
)
def get_scenario_run(
    scenario_id: str,
    run_id: int,
    store: ScenarioStore = Depends(get_store),
) -> RunResult:
    """Fetch one persisted run's exact stored result payload (`RW-FR-015`)."""
    try:
        return store.get_run(scenario_id, run_id).result
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@router.get(
    "/{scenario_id}/impacts",
    response_model=list[NodeImpactOut],
    dependencies=[Depends(default_rate_limit)],
)
async def ranked_impacts(
    scenario_id: str,
    severity: float = 1.0,
    store: ScenarioStore = Depends(get_store),
    redis=Depends(get_redis),
) -> list[NodeImpactOut]:
    result = await get_results(scenario_id, severity, store, redis)
    return [result.impacts[eid] for eid in result.ranked_entity_ids if eid in result.impacts]


@router.get(
    "/{scenario_id}/explanation/{node_id}",
    response_model=ExplanationOut,
    dependencies=[Depends(require_api_key), Depends(gemini_rate_limit)],
)
def explain_node(
    scenario_id: str,
    node_id: str,
    severity: float = 1.0,
    audience: Audience = Audience.ANALYST,
    store: ScenarioStore = Depends(get_store),
    transport: ExplanationTransport = Depends(get_explanation_transport),
    accounting: GeminiAccountingService = Depends(get_accounting),
    accounting_session_factory=Depends(get_accounting_session_factory),
) -> ExplanationOut:
    """Generate a guarded, evidence-bound explanation of one node's impact.

    Gemini writes the prose from the computation payload + pre-baked provenance;
    the deterministic numeric-containment guard (`RW-AI-011`) rejects any prose
    introducing an unbacked number, regenerating once before falling back to
    labeled verified figures. No number here ever originates from Gemini. The
    ``audience`` query parameter selects the analyst/student/retail voice variant
    (`RW-FR-022`); all three are held to the identical guard.
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
        with latency_timer(EXPLANATION_GENERATION):
            generated = generate_node_explanation(context, payload, transport, audience=audience)
    except Exception as exc:  # transport/network failure — surface, don't crash the demo
        logger.warning("explanation generation failed for %s/%s: %s", scenario_id, node_id, exc)
        raise HTTPException(status_code=502, detail="explanation provider unavailable") from exc

    # RIS-34 / RW-DATA-005: best-effort accounting, never allowed to break an
    # already-generated explanation response.
    accounting.record_best_effort(
        accounting_session_factory,
        purpose="explanation",
        model=generated.model,
        input_tokens=generated.input_token_count,
        output_tokens=generated.output_token_count,
    )

    return ExplanationOut(
        node_id=generated.node_id,
        node_name=context.node_name,
        audience=generated.audience.value,
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


@router.get(
    "/{scenario_id}/paths/{node_id}",
    response_model=list[dict],
    dependencies=[Depends(default_rate_limit)],
)
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


# ---------------------------------------------------------------------------
# Run-scoped Q&A (RW-FR-024, RW-AI-002, RW-SEC-002)
# ---------------------------------------------------------------------------


def _audience_from(value: str) -> Audience:
    try:
        return Audience(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"unknown audience {value!r}") from exc


def _qa_answer_to_out(answer: QaAnswer) -> QaAnswerOut:
    return QaAnswerOut(
        session_id=answer.session_id,
        question=answer.question,
        audience=answer.audience.value,
        answer=answer.answer,
        withheld=answer.withheld,
        reason=answer.reason,
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
            for c in answer.citations
        ],
        audit=[
            ToolCallAuditOut(
                tool_name=e.tool_name,
                args=e.args,
                result_hash=e.result_hash,
                status=e.status,
                timestamp=e.timestamp,
            )
            for e in answer.audit
        ],
        tool_call_count=answer.tool_call_count,
        answer_attempts=answer.answer_attempts,
        guard_violations=list(answer.guard_violations),
        model=answer.model,
    )


@router.post(
    "/{scenario_id}/qa",
    response_model=QaAnswerOut,
    dependencies=[Depends(require_api_key), Depends(gemini_rate_limit)],
)
def ask_run_scoped_question(
    scenario_id: str,
    req: QaRequest,
    store: ScenarioStore = Depends(get_store),
    transport: QaToolTransport = Depends(get_qa_transport),
    accounting: GeminiAccountingService = Depends(get_accounting),
    accounting_session_factory=Depends(get_accounting_session_factory),
) -> QaAnswerOut:
    """Answer a free-text question about a run via Gemini tool orchestration.

    Gemini may call only the closed §13.2 registry, bound to this run's approved
    state (`RW-AI-002`, `RW-SEC-002`); unknown tools and schema-invalid arguments
    are refused server-side. The answer is held to the same numeric-containment +
    citation guard as explanations (`RW-AI-011`); anything it cannot ground is
    explicitly withheld, never improvised. Every tool call — executed or refused —
    is captured in the returned per-session audit log (`RW-FR-024`).
    """
    audience = _audience_from(req.audience)
    try:
        record = store.get(scenario_id)
        result, _ = store.propagate_scenario(scenario_id, req.severity)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="scenario or snapshot not found") from exc

    snapshot = store.get_snapshot(record.snapshot_id)
    node_names = {n.node_id: n.name for n in snapshot.nodes}
    node_types = {n.node_id: n.node_type for n in snapshot.nodes}
    provenance = store.get_provenance(record.snapshot_id)

    context = RunToolContext(
        scenario_id=scenario_id,
        result=result,
        snapshot=snapshot,
        provenance_by_edge=provenance,
        node_names=node_names,
        node_types=node_types,
    )
    registry = build_registry(context)
    session_id = f"qa-{uuid.uuid4().hex[:12]}"

    try:
        answer = answer_question(
            req.question,
            registry,
            transport,
            session_id=session_id,
            base_payload=payload_for_run(result),
            audience=audience,
        )
    except Exception as exc:  # transport/network failure — surface, don't crash the demo
        logger.warning("Q&A failed for %s: %s", scenario_id, exc)
        raise HTTPException(status_code=502, detail="Q&A provider unavailable") from exc

    store.record_qa_session(answer)
    # RIS-34 / RW-DATA-005: best-effort accounting, never allowed to break an
    # already-answered question.
    accounting.record_best_effort(
        accounting_session_factory,
        purpose="qa",
        model=answer.model,
        input_tokens=answer.input_token_count,
        output_tokens=answer.output_token_count,
    )
    return _qa_answer_to_out(answer)


@router.get(
    "/{scenario_id}/qa/sessions/{session_id}",
    response_model=QaAnswerOut,
    dependencies=[Depends(default_rate_limit)],
)
def get_qa_session(
    scenario_id: str,
    session_id: str,
    store: ScenarioStore = Depends(get_store),
) -> QaAnswerOut:
    """Retrieve a recorded Q&A session, including its full tool-call audit log."""
    try:
        answer = store.get_qa_session(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="q&a session not found") from exc
    return _qa_answer_to_out(answer)
