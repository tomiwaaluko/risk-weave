from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from riskweave.propagation import Scenario, ShockFactor, propagate
from riskweave.scenario import ParsedScenario, ScenarioStatus, list_templates, parse_shock_text
from riskweave.scenario.validation import validate_scenario
from riskweave_api.dependencies import get_store
from riskweave_api.models import ScenarioRunRequest
from riskweave_api.result_conversion import propagation_result_to_payload
from riskweave_api.scenario_store import ScenarioStore

router = APIRouter(prefix="/scenarios", tags=["scenarios"])
StoreDependency = Annotated[ScenarioStore, Depends(get_store)]


@router.get("/templates", response_model=tuple[ParsedScenario, ...])
def scenario_templates() -> tuple[ParsedScenario, ...]:
    return list_templates()


@router.post("/parse", response_model=ParsedScenario)
def parse_scenario(payload: dict[str, str]) -> ParsedScenario:
    return parse_shock_text(payload.get("text", ""))


@router.post("/validate", response_model=ParsedScenario)
def validate_structured_scenario(scenario: ParsedScenario) -> ParsedScenario:
    validation = validate_scenario(scenario)
    return scenario.model_copy(update={"validation": validation, "status": validation.status})


@router.post("/review/run")
def run_review_scenario(scenario: ParsedScenario) -> dict[str, str | bool]:
    validation = validate_scenario(scenario)
    accepted = scenario.status is ScenarioStatus.READY and validation.status is ScenarioStatus.READY
    return {"scenario_id": scenario.scenario_id, "accepted": accepted}


@router.post("/{scenario_id}/run")
def run_scenario(
    scenario_id: str,
    request: ScenarioRunRequest,
    store: StoreDependency,
) -> dict:
    try:
        record = store.get(scenario_id)
        snapshot = store.get_snapshot(record.snapshot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown scenario {scenario_id!r}") from exc

    if record.state.value != "READY":
        raise HTTPException(status_code=409, detail="Scenario is not READY")

    scaled = Scenario(
        scenario_id=record.scenario.scenario_id,
        factors=tuple(
            ShockFactor(
                factor_id=factor.factor_id,
                node_id=factor.node_id,
                magnitude=factor.magnitude * request.severity,
            )
            for factor in record.scenario.factors
        ),
        seed=record.scenario.seed,
    )
    return propagation_result_to_payload(propagate(snapshot, scaled), request.severity)
